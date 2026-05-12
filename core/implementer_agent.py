"""
Implementer Agent: Generate actual source code based on architecture blueprint and spec.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from pathlib import PurePosixPath
from typing import Dict

from core.codebase.integrity import CodebaseIntegrityChecker, CodebaseIntegrityIssue
from core.data_models import ProgramSpec, ArchitectureBlueprint, Codebase
from core.implementation.contract_assets import (
    PythonContractAssetInjector,
    STATIC_ASSET_POLICY_NAME,
    is_materializable_static_output_contract,
)
from core.prompting.behavior_contracts import (
    behavior_contract_prompt,
    implementation_behavior_contract_prompt,
    spec_prompt_json,
)
from core.llm_output import extract_json_value
from llm_clients.base import BaseLLMClient, Message
from llm_clients.options import configured_max_tokens


class ImplementerAgent:
    """Generate complete source code for each module in the architecture."""
    
    SYSTEM_PROMPT = """You are an expert software engineer implementing a cleanroom replacement.
You will be given an architecture blueprint and a detailed specification.
Your task is to write COMPLETE, production-ready source code for each module.

Rules:
1. Write complete implementations, not stubs or TODOs.
2. Match the observed behavior EXACTLY, including error handling and edge cases.
3. Include appropriate comments explaining complex logic.
4. Handle all CLI arguments as described in the spec.
5. Use standard libraries where possible; minimize external dependencies.
6. If the original appears to use a specific algorithm (e.g., specific sort), implement it correctly.
7. Preserve stdout vs stderr exactly. Do not use default argparse help/version/error output when observed behavior uses
   custom formatting, custom option ordering, or prints help/usage to stderr.

Output only source artifacts, with no prose. Preferred output format:
For each file, output:
--- FILE: path/to/file.ext ---
<content>
--- END FILE ---

Also include a build script section:
--- BUILD SCRIPT: filename ---
<content>
--- END BUILD ---

If you cannot use that delimiter format, output a JSON object:
{"files": [{"path": "main.py", "content": "..."}], "build_script": ""}"""

    ENTRYPOINT_SYSTEM_PROMPT = """Generate only the Python CLI entrypoint for a cleanroom replacement.
The output must include exactly the entrypoint file requested by the architecture.
It must be runnable immediately, include a main() function and __main__ guard, parse CLI args,
and cover the observed help/version/no-args/error surface as best as possible.
Use only Python standard library imports. Do not import local generated modules in this stage.
Preserve stdout vs stderr exactly. Prefer hand-written help/version/usage text over argparse defaults when exact
behavior contracts show custom formatting or stderr output.

Return only source artifacts or a JSON file manifest. Do not include prose."""

    SUPPORT_SYSTEM_PROMPT = """Generate supporting Python files for an existing runnable CLI entrypoint.
Return only optional support modules or safe entrypoint improvements. If no support files are needed,
return {"files": []}. Keep files compact and include every local module that is imported.
Do not include prose."""
    
    def __init__(
        self,
        llm_client: BaseLLMClient,
        enable_static_output_assets: bool = True,
    ):
        self.llm = llm_client
        self.enable_static_output_assets = enable_static_output_assets
    
    async def implement(
        self,
        spec: ProgramSpec,
        blueprint: ArchitectureBlueprint,
        output_dir: Path,
    ) -> Codebase:
        """Generate the complete codebase."""
        if self._should_use_python_staging(blueprint):
            return await self._implement_python_staged(spec, blueprint, output_dir)
        
        return await self._implement_single_pass(spec, blueprint, output_dir)

    def _should_use_python_staging(self, blueprint: ArchitectureBlueprint) -> bool:
        return blueprint.language.lower() == "python" and bool(blueprint.modules)

    async def _implement_single_pass(
        self,
        spec: ProgramSpec,
        blueprint: ArchitectureBlueprint,
        output_dir: Path,
    ) -> Codebase:
        # For now, generate all modules in one LLM call
        # For very large projects, this should be parallelized per module
        messages = [
            self.llm.system_prompt(self.SYSTEM_PROMPT + self._static_asset_generation_guard(spec)),
            self.llm.user_prompt(
                f"Specification:\n{spec_prompt_json(spec)}\n\n"
                f"{self._contract_prompt(spec)}"
                f"Architecture Blueprint:\n{blueprint.model_dump_json(indent=2)}\n\n"
                f"Generate all source files and the build script. "
                f"Use language: {blueprint.language}."
            ),
        ]
        
        resp = await self.llm.chat(
            messages,
            temperature=0.2,
            max_tokens=configured_max_tokens(self.llm, 8192),
        )
        codebase = self._parse_codebase(resp.content, blueprint, output_dir)
        integrity_issues = CodebaseIntegrityChecker().find_issues(
            codebase,
            entry_point=self._expected_entry_point(blueprint),
        )
        if not codebase.files or integrity_issues:
            retry_reason = "unparseable_initial_output" if not codebase.files else "integrity_issues"
            retry = await self._retry_implementation(
                spec=spec,
                blueprint=blueprint,
                initial_output=resp.content,
                integrity_issues=integrity_issues,
            )
            self._clear_output_sources(output_dir)
            codebase = self._parse_codebase(retry.content, blueprint, output_dir)
            codebase.generation_metadata = {
                **codebase.generation_metadata,
                "implementation_retry": retry_reason,
                "initial_output_chars": len(resp.content),
            }
        else:
            codebase.generation_metadata["integrity_issues"] = []
        return self._apply_contract_assets(spec, blueprint, codebase)

    async def _implement_python_staged(
        self,
        spec: ProgramSpec,
        blueprint: ArchitectureBlueprint,
        output_dir: Path,
    ) -> Codebase:
        entry_resp = await self.llm.chat(
            self._entrypoint_messages(spec, blueprint),
            temperature=0.2,
            max_tokens=configured_max_tokens(self.llm, 8192),
        )
        entry_codebase = self._parse_codebase(entry_resp.content, blueprint, output_dir)
        entry_issues = CodebaseIntegrityChecker().find_issues(
            entry_codebase,
            entry_point=self._expected_entry_point(blueprint),
        )
        if not entry_codebase.files or entry_issues:
            retry = await self._retry_implementation(
                spec=spec,
                blueprint=blueprint,
                initial_output=entry_resp.content,
                integrity_issues=entry_issues,
            )
            self._clear_output_sources(output_dir)
            entry_codebase = self._parse_codebase(retry.content, blueprint, output_dir)
            entry_codebase.generation_metadata = {
                **entry_codebase.generation_metadata,
                "implementation_strategy": "python_staged",
                "entrypoint_stage_retry": True,
                "initial_output_chars": len(entry_resp.content),
            }
            entry_issues = CodebaseIntegrityChecker().find_issues(
                entry_codebase,
                entry_point=self._expected_entry_point(blueprint),
            )
            if entry_issues:
                fallback = await self._implement_single_pass(spec, blueprint, output_dir)
                fallback.generation_metadata = {
                    **fallback.generation_metadata,
                    "implementation_strategy": "python_staged_fallback_single_pass",
                    "entrypoint_stage_retry_failed_issues": [
                        issue.message for issue in entry_issues
                    ],
                }
                return fallback

        entry_codebase.generation_metadata = {
            **entry_codebase.generation_metadata,
            "implementation_strategy": "python_staged",
            "entrypoint_stage_files": sorted(entry_codebase.files),
        }
        if not entry_codebase.files:
            entry_codebase.generation_metadata["module_stage_status"] = "skipped_no_entrypoint"
            return entry_codebase

        module_resp = await self.llm.chat(
            self._support_messages(spec, blueprint, entry_codebase),
            temperature=0.2,
            max_tokens=configured_max_tokens(self.llm, 8192),
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            module_codebase = self._parse_codebase(
                module_resp.content,
                blueprint,
                Path(tmpdir),
            )

        if not module_codebase.files:
            self._write_unparseable_output(output_dir, module_resp.content)
            entry_codebase.generation_metadata["module_stage_status"] = "rejected_no_files"
            return self._apply_contract_assets(spec, blueprint, entry_codebase)

        merged_files = dict(entry_codebase.files)
        merged_files.update(module_codebase.files)
        merged = Codebase(
            root_path=output_dir,
            language=blueprint.language,
            files=merged_files,
            build_script=module_codebase.build_script or entry_codebase.build_script,
            generation_metadata={
                **entry_codebase.generation_metadata,
                "module_stage_files": sorted(module_codebase.files),
                "module_stage_status": "accepted",
            },
        )
        merged.executable_path = self._determine_executable(
            output_dir,
            blueprint,
            merged.build_script,
        )
        module_issues = CodebaseIntegrityChecker().find_issues(
            merged,
            entry_point=self._expected_entry_point(blueprint),
        )
        if module_issues:
            entry_codebase.generation_metadata["module_stage_status"] = "rejected_integrity"
            entry_codebase.generation_metadata["module_stage_issues"] = [
                issue.message for issue in module_issues
            ]
            self._clear_output_sources(output_dir)
            self._write_files(output_dir, entry_codebase.files)
            return self._apply_contract_assets(spec, blueprint, entry_codebase)

        self._clear_output_sources(output_dir)
        self._write_files(output_dir, merged.files)
        merged.executable_path = self._determine_executable(
            output_dir,
            blueprint,
            merged.build_script,
        )
        return self._apply_contract_assets(spec, blueprint, merged)

    def _apply_contract_assets(
        self,
        spec: ProgramSpec,
        blueprint: ArchitectureBlueprint,
        codebase: Codebase,
    ) -> Codebase:
        if blueprint.language.lower() != "python":
            return codebase
        if not self.enable_static_output_assets:
            codebase.generation_metadata.update(
                {
                    "static_output_assets_enabled": False,
                    "contract_asset_policy": STATIC_ASSET_POLICY_NAME,
                    "contract_asset_status": "disabled",
                    "contract_asset_count": 0,
                }
            )
            return codebase
        return PythonContractAssetInjector().apply(
            spec=spec,
            codebase=codebase,
            entry_point=self._expected_entry_point(blueprint),
        )

    def _contract_prompt(self, spec: ProgramSpec) -> str:
        if self.enable_static_output_assets:
            return implementation_behavior_contract_prompt(spec)
        return behavior_contract_prompt(spec)

    def _static_asset_generation_guard(self, spec: ProgramSpec) -> str:
        contracts = [
            contract
            for contract in spec.behavior_contracts
            if is_materializable_static_output_contract(contract)
        ]
        if not contracts:
            return ""
        argv_forms = [contract.args for contract in contracts]
        if not self.enable_static_output_assets:
            return (
                "\n\nStatic output asset mode is disabled. You must implement those init <shell> "
                "argv forms directly in source, but keep the implementation compact and syntax-safe. "
                "Avoid giant escaped one-line literals and avoid deeply nested quote/backslash "
                "sequences in shell templates. Prefer small helper functions and triple-quoted "
                "templates with minimal escaping so generated Python parses cleanly: "
                f"{json.dumps(argv_forms, ensure_ascii=False)}."
            )
        return (
            "\n\nStatic output asset mode is enabled. Do not implement shell init script templates, "
            "completion scripts, or large bash/zsh/fish/powershell bodies in generated source. "
            "generated asset injection will handle those exact argv forms after code generation: "
            f"{json.dumps(argv_forms, ensure_ascii=False)}. "
            "Keep the entrypoint compact and implement only normal CLI parsing, stateful database "
            "logic, errors, and non-static behavior."
        )

    def _entrypoint_messages(
        self,
        spec: ProgramSpec,
        blueprint: ArchitectureBlueprint,
    ) -> list[Message]:
        return [
            self.llm.system_prompt(
                self.ENTRYPOINT_SYSTEM_PROMPT
                + self._static_asset_generation_guard(spec)
            ),
            self.llm.user_prompt(
                f"Specification:\n{spec_prompt_json(spec)}\n\n"
                f"{self._contract_prompt(spec)}"
                f"Architecture Blueprint:\n{blueprint.model_dump_json(indent=2)}\n\n"
                f"Generate only {self._expected_entry_point(blueprint)}."
            ),
        ]

    def _support_messages(
        self,
        spec: ProgramSpec,
        blueprint: ArchitectureBlueprint,
        entry_codebase: Codebase,
    ) -> list[Message]:
        return [
            self.llm.system_prompt(
                self.SUPPORT_SYSTEM_PROMPT
                + self._static_asset_generation_guard(spec)
            ),
            self.llm.user_prompt(
                f"Specification:\n{spec_prompt_json(spec)}\n\n"
                f"{self._contract_prompt(spec)}"
                f"Architecture Blueprint:\n{blueprint.model_dump_json(indent=2)}\n\n"
                "Existing entrypoint files:\n"
                f"{json.dumps(entry_codebase.files, indent=2)}\n\n"
                "Generate supporting Python files or safe replacements now."
            ),
        ]

    def _expected_entry_point(self, blueprint: ArchitectureBlueprint) -> str | None:
        if blueprint.language.lower() != "python":
            return blueprint.entry_point
        return self._python_entry_path(blueprint)

    async def _retry_implementation(
        self,
        spec: ProgramSpec,
        blueprint: ArchitectureBlueprint,
        initial_output: str,
        integrity_issues: list[CodebaseIntegrityIssue],
    ):
        issue_summary = [
            {
                "kind": issue.kind,
                "path": issue.path,
                "module": issue.module,
                "message": issue.message,
            }
            for issue in integrity_issues
        ]
        messages = [
            self.llm.system_prompt(
                "Your previous implementation response was not a runnable complete codebase. "
                "Return only one JSON object with this exact shape: "
                '{"files":[{"path":"main.py","content":"..."}],"build_script":""}. '
                "Include every local module imported by the entry point, or make the entry "
                "point self-contained. Keep the implementation compact enough to fit in one "
                "response; prefer a concise single-file implementation when possible. "
                "Do not include prose or markdown fences."
                + self._static_asset_generation_guard(spec)
            ),
            self.llm.user_prompt(
                f"Specification:\n{spec_prompt_json(spec)}\n\n"
                f"{self._contract_prompt(spec)}"
                f"Architecture Blueprint:\n{blueprint.model_dump_json(indent=2)}\n\n"
                f"Integrity issues:\n{json.dumps(issue_summary, indent=2)}\n\n"
                f"Unparseable previous output preview:\n{initial_output[:1000]}\n\n"
                "Generate the complete source files now."
            ),
        ]
        return await self.llm.chat(
            messages,
            temperature=0.0,
            max_tokens=configured_max_tokens(self.llm, 8192),
        )

    def _clear_output_sources(self, output_dir: Path) -> None:
        output_dir.mkdir(parents=True, exist_ok=True)
        for child in output_dir.iterdir():
            if child.name == ".rebuilder":
                continue
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
    
    def _parse_codebase(
        self,
        text: str,
        blueprint: ArchitectureBlueprint,
        output_dir: Path,
    ) -> Codebase:
        """Parse file-delimited output into Codebase object."""
        import re
        
        files: Dict[str, str] = {}
        build_script: str | None = None
        
        files.update(self._parse_json_manifest(text))

        # Parse source files
        file_pattern = r"---\s*FILE:\s*(.+?)\s*---\s*\r?\n(.*?)\r?\n---\s*END FILE\s*---"
        for match in re.finditer(file_pattern, text, re.DOTALL | re.IGNORECASE):
            filepath = self._normalize_output_path(match.group(1))
            if filepath:
                content = match.group(2).strip("\r\n")
                files[filepath] = content
        
        # Parse build script
        build_pattern = r"---\s*BUILD SCRIPT:\s*(.+?)\s*---\n(.*?)\n---\s*END BUILD\s*---"
        build_match = re.search(build_pattern, text, re.DOTALL | re.IGNORECASE)
        if build_match:
            build_script = build_match.group(2).strip("\r\n")
        
        # If parsing failed, try to extract code blocks
        if not files:
            for i, (info, content) in enumerate(self._parse_code_blocks(text)):
                filepath = self._code_block_path(info, i, blueprint)
                if filepath:
                    files[filepath] = content.strip("\r\n")

        files = {
            filepath: self._normalize_file_content(content)
            for filepath, content in files.items()
        }
        
        output_dir.mkdir(parents=True, exist_ok=True)
        generation_metadata = {
            "parse_status": "ok" if files else "no_files",
            "raw_output_chars": len(text),
        }
        if not files:
            self._write_unparseable_output(output_dir, text)

        # Write files to disk
        for filepath, content in files.items():
            fpath = output_dir / filepath
            fpath.parent.mkdir(parents=True, exist_ok=True)
            fpath.write_text(content, encoding="utf-8")
        
        # Determine executable path based on language/build system
        executable_path = self._determine_executable(output_dir, blueprint, build_script)
        
        return Codebase(
            root_path=output_dir,
            language=blueprint.language,
            files=files,
            build_script=build_script,
            executable_path=executable_path,
            generation_metadata=generation_metadata,
        )

    def _parse_json_manifest(self, text: str) -> Dict[str, str]:
        """Parse a JSON file manifest if the model emitted one."""
        try:
            data = extract_json_value(text)
        except json.JSONDecodeError:
            data = None

        if isinstance(data, list):
            parsed = self._parse_file_items(data)
            if parsed:
                return parsed
        elif isinstance(data, dict):
            parsed = self._parse_json_manifest_dict(data)
            if parsed:
                return parsed

        return self._parse_jsonish_manifest(text)

    def _parse_json_manifest_dict(self, data: dict) -> Dict[str, str]:
        raw_files = data.get("files", {})
        parsed: Dict[str, str] = {}
        if isinstance(raw_files, dict):
            items = raw_files.items()
            for path, content in items:
                filepath = self._normalize_output_path(str(path))
                if filepath and isinstance(content, str):
                    parsed[filepath] = content
            return parsed

        if isinstance(raw_files, list):
            parsed.update(self._parse_file_items(raw_files))
        return parsed

    def _parse_jsonish_manifest(self, text: str) -> Dict[str, str]:
        """Recover a single file from a JSON-like manifest with unescaped code quotes."""
        import re

        path_match = re.search(r'"path"\s*:\s*"(?P<path>[^"]+)"', text)
        content_match = re.search(r'"content"\s*:\s*"', text)
        if not path_match or not content_match:
            return {}

        filepath = self._normalize_output_path(path_match.group("path"))
        if not filepath:
            return {}

        content_start = content_match.end()
        tail = text[content_start:]
        end_matches = list(
            re.finditer(r'"\s*}\s*]\s*,\s*"build_script"', tail, re.DOTALL)
        )
        if not end_matches:
            truncated = self._parse_truncated_jsonish_manifest(filepath, tail)
            if truncated:
                return truncated
            return {}

        encoded = tail[: end_matches[-1].start()]
        return {filepath: self._decode_jsonish_content(encoded)}

    def _parse_truncated_jsonish_manifest(
        self,
        filepath: str,
        tail: str,
    ) -> Dict[str, str]:
        """Recover content when the JSON manifest is truncated before build_script."""
        import re

        candidate = tail
        fence_index = candidate.find("\n```")
        if fence_index >= 0:
            candidate = candidate[:fence_index]
        # Some providers append partial object trailers; drop them when present.
        candidate = re.sub(r'"\s*}\s*]\s*}\s*$', "", candidate, flags=re.DOTALL)
        decoded = self._decode_jsonish_content(candidate).strip("\r\n")
        if not self._looks_like_source_code(decoded):
            return {}
        return {filepath: decoded}

    def _looks_like_source_code(self, text: str) -> bool:
        lowered = text.lower()
        markers = (
            "def ",
            "class ",
            "import ",
            "from ",
            "fn ",
            "function ",
            "#include",
            "package ",
            "public ",
            "int main(",
            "if __name__ ==",
        )
        return any(marker in lowered for marker in markers)

    def _decode_jsonish_content(self, encoded: str) -> str:
        return (
            encoded.replace("\\r\\n", "\n")
            .replace("\\n", "\n")
            .replace("\\t", "\t")
            .replace('\\"', '"')
            .replace("\\\\", "\\")
        )

    def _parse_file_items(self, raw_files: list) -> Dict[str, str]:
        parsed: Dict[str, str] = {}
        for item in raw_files:
            if not isinstance(item, dict):
                continue
            raw_path = (
                item.get("path")
                or item.get("file")
                or item.get("filename")
                or item.get("name")
            )
            content = (
                item.get("content")
                or item.get("source")
                or item.get("code")
                or item.get("text")
            )
            if raw_path and isinstance(content, str):
                filepath = self._normalize_output_path(str(raw_path))
                if filepath:
                    parsed[filepath] = content
        return parsed

    def _write_unparseable_output(self, output_dir: Path, text: str) -> None:
        diagnostic_dir = output_dir / ".rebuilder"
        diagnostic_dir.mkdir(parents=True, exist_ok=True)
        (diagnostic_dir / "implementation_raw.txt").write_text(text, encoding="utf-8")

    def _normalize_file_content(self, content: str) -> str:
        import re

        stripped = content.strip("\r\n")
        match = re.match(r"^```[^\n`]*\r?\n(?P<body>.*?)\r?\n```$", stripped, re.DOTALL)
        if match:
            return match.group("body").strip("\r\n")
        if stripped.startswith("```"):
            lines = stripped.splitlines()
            return "\n".join(lines[1:]).strip("\r\n")
        return content

    def _write_files(self, output_dir: Path, files: Dict[str, str]) -> None:
        output_dir.mkdir(parents=True, exist_ok=True)
        for filepath, content in files.items():
            target = output_dir / filepath
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")

    def _parse_code_blocks(self, text: str) -> list[tuple[str, str]]:
        import re

        return [
            (match.group("info").strip(), match.group("content"))
            for match in re.finditer(
                r"```(?P<info>[^\n`]*)\r?\n(?P<content>.*?)```",
                text,
                re.DOTALL,
            )
        ]

    def _code_block_path(
        self,
        info: str,
        index: int,
        blueprint: ArchitectureBlueprint,
    ) -> str | None:
        explicit = self._path_from_code_block_info(info)
        if explicit:
            return explicit

        language = (info.split() or [""])[0].lower()
        if blueprint.language.lower() == "python" and index == 0:
            return self._python_entry_path(blueprint)
        extension = {
            "python": "py",
            "py": "py",
            "bash": "sh",
            "sh": "sh",
            "shell": "sh",
            "javascript": "js",
            "js": "js",
            "typescript": "ts",
            "ts": "ts",
        }.get(language, "txt")
        return f"module_{index}.{extension}"

    def _path_from_code_block_info(self, info: str) -> str | None:
        for token in info.replace(",", " ").split():
            if "=" in token:
                key, value = token.split("=", 1)
                if key.lower() in {"file", "filename", "path"}:
                    normalized = self._normalize_output_path(value.strip("'\""))
                    if normalized:
                        return normalized
            elif "." in token and "/" not in token[:1]:
                normalized = self._normalize_output_path(token.strip("'\""))
                if normalized:
                    return normalized
        return None

    def _python_entry_path(self, blueprint: ArchitectureBlueprint) -> str:
        entry = blueprint.entry_point or "main.py"
        if (
            "." in entry
            and "/" not in entry
            and "\\" not in entry
            and not entry.endswith(".py")
        ):
            entry = entry.replace(".", "/")
        if not entry.endswith(".py"):
            entry += ".py"
        return self._normalize_output_path(entry) or "main.py"

    def _normalize_output_path(self, raw_path: str) -> str | None:
        normalized = raw_path.strip().strip("`").replace("\\", "/")
        if not normalized:
            return None
        pure = PurePosixPath(normalized)
        if pure.is_absolute() or any(part in {"..", ""} for part in pure.parts):
            return None
        if pure.parts and ":" in pure.parts[0]:
            return None
        return pure.as_posix()
    
    def _determine_executable(
        self,
        output_dir: Path,
        blueprint: ArchitectureBlueprint,
        build_script: str | None,
    ) -> Path | None:
        """Try to determine the path to the built executable."""
        # If Python, the entry point file itself is "executable"
        if blueprint.language.lower() == "python":
            entry = self._python_entry_path(blueprint)
            candidate = output_dir / entry
            if candidate.exists():
                return candidate
        return None
