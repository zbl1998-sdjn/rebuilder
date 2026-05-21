"""
Spec Synthesizer: Infer program specification from observed behavior corpus.
"""

from __future__ import annotations

import json
import re
from typing import Any, List

from core.data_models import BehaviorContract, BehaviorSample, ProgramSpec, Invariant, CLISurface, TaskProfile
from core.execution.env import safe_env_vars
from core.execution.files import UnsafeInputFilePathError, safe_input_file_relative_path
from core.llm_output import extract_json_object
from core.profiling import infer_task_profile
from llm_clients.base import BaseLLMClient, Message
from llm_clients.options import configured_max_tokens
from pydantic import ValidationError


class SpecSynthesizer:
    """Use LLM to synthesize a human-readable program specification from behavior samples."""
    
    DOCUMENTATION_PROMPT_MAX_CHARS = 3000
    OBSERVATION_PROMPT_MAX_CHARS = 4500
    FAILED_DRAFT_MAX_CHARS = 2000
    REPAIR_DRAFT_MAX_CHARS = 4000
    
    SYSTEM_PROMPT = """You are a senior software architect analyzing black-box behavior observations.
Your task is to synthesize a precise, implementable specification of the target program.

Output only a JSON object with these fields:
- "summary": One paragraph describing what the program does
- "input_formats": List of recognized input formats (e.g., ["plain_text", "json", "csv"])
- "output_formats": List of output formats
- "cli_surface": Object describing subcommands, flags, positional args
- "edge_cases": List of known edge cases and error conditions
- "stateful": Boolean indicating if the program maintains state across runs
- "invariants": List of objects with "description", "type" (deterministic/idempotent/monotonic/ordered), "confidence" (0-1)
- "complexity_hints": Object with estimated algorithmic complexity and task-domain notes when evident
- "raw_observations": Your detailed technical observations

Be precise and conservative. If you are uncertain about a behavior, note it as speculative."""
    
    def __init__(self, llm_client: BaseLLMClient):
        self.llm = llm_client
    
    async def synthesize(
        self,
        corpus: List[BehaviorSample],
        documentation: str,
        cli_surface: CLISurface,
    ) -> ProgramSpec:
        """Synthesize specification from behavior corpus."""
        
        # Build rich observation text
        observation_text = self._format_corpus(
            corpus,
            max_chars=self.OBSERVATION_PROMPT_MAX_CHARS,
        )
        documentation_text = self._format_documentation(
            documentation,
            max_chars=self.DOCUMENTATION_PROMPT_MAX_CHARS,
        )
        
        messages = [
            self.llm.system_prompt(self.SYSTEM_PROMPT),
            self.llm.user_prompt(
                f"Original documentation:\n{documentation_text}\n\n"
                f"Discovered CLI surface:\n{cli_surface.model_dump_json(indent=2)}\n\n"
                f"Behavior observations ({len(corpus)} samples):\n{observation_text}\n\n"
                f"Synthesize a complete implementable specification as JSON."
            ),
        ]
        
        resp = await self.llm.chat(
            messages,
            temperature=0.2,
            max_tokens=configured_max_tokens(self.llm, 8192),
        )
        spec = self._parse_spec(resp.content)
        failed_output = resp.content
        if self._is_parse_failure(spec):
            retry = await self.llm.chat(
                self._spec_repair_messages(resp.content),
                temperature=0.0,
                max_tokens=configured_max_tokens(self.llm, 4096),
            )
            repaired = self._parse_spec(retry.content)
            if not self._is_parse_failure(repaired):
                spec = repaired
            else:
                failed_output = retry.content
        if self._is_parse_failure(spec):
            spec = self._fallback_spec(
                corpus=corpus,
                documentation=documentation,
                cli_surface=cli_surface,
                failed_output=failed_output,
            )
        self._attach_task_profile(spec, documentation, cli_surface, corpus)
        spec.behavior_contracts = self._contracts_from_corpus(corpus)
        return spec

    def _attach_task_profile(
        self,
        spec: ProgramSpec,
        documentation: str,
        cli_surface: CLISurface,
        corpus: List[BehaviorSample],
    ) -> None:
        profile = infer_task_profile(
            documentation=documentation,
            cli_surface=cli_surface,
            corpus=corpus,
        )
        hints = dict(spec.complexity_hints or {})
        existing = hints.get("task_profile")
        if isinstance(existing, dict):
            profile = {**profile, **existing}
        hints["task_profile"] = profile
        spec.complexity_hints = hints
        try:
            spec.task_profile = TaskProfile.model_validate(profile)
        except ValidationError:
            spec.task_profile = None
    
    def _format_corpus(
        self,
        corpus: List[BehaviorSample],
        max_chars: int | None = None,
    ) -> str:
        """Format behavior samples into a readable text for the LLM."""
        chunks = [
            self._format_sample_for_prompt(i, sample, compact=False)
            for i, sample in enumerate(corpus)
        ]
        formatted = "\n".join(chunks)
        if max_chars is None or len(formatted) <= max_chars:
            return formatted
        return self._format_corpus_with_budget(corpus, max_chars)

    def _format_corpus_with_budget(
        self,
        corpus: List[BehaviorSample],
        max_chars: int,
    ) -> str:
        if max_chars <= 0:
            return f"... {len(corpus)} samples omitted due to prompt budget."

        prioritized = sorted(
            enumerate(corpus),
            key=lambda item: (-self._sample_prompt_priority(item[1], item[0]), item[0]),
        )
        footer = f"\n\n... {len(corpus)} samples omitted due to prompt budget."
        body_budget = max(max_chars - len(footer), 0)
        selected: list[tuple[int, str]] = []
        used = 0
        for i, sample in prioritized:
            chunk = self._format_sample_for_prompt(i, sample, compact=True)
            separator_len = 2 if selected else 0
            remaining = body_budget - used - separator_len
            if remaining <= 0:
                continue
            if len(chunk) > remaining:
                if remaining < 240:
                    continue
                chunk = self._truncate_text(chunk, remaining)
            selected.append((i, chunk))
            used += separator_len + len(chunk)

        if not selected:
            return self._truncate_text(footer.strip(), max_chars)

        selected.sort(key=lambda item: item[0])
        omitted = max(len(corpus) - len(selected), 0)
        body = "\n\n".join(chunk for _i, chunk in selected)
        if omitted:
            footer = f"\n\n... {omitted} samples omitted due to prompt budget."
            if len(body) + len(footer) > max_chars:
                body = self._truncate_text(body, max_chars - len(footer))
            return f"{body}{footer}"
        return self._truncate_text(body, max_chars)

    def _format_sample_for_prompt(
        self,
        i: int,
        sample: BehaviorSample,
        *,
        compact: bool,
    ) -> str:
        if compact:
            return self._format_sample_for_prompt_compact(i, sample)

        tc = sample.test_case
        res = sample.observed_result
        input_files, unsafe_input_names = self._safe_input_file_partition(tc.input_files)
        args = self._redact_unsafe_input_file_args(tc.args, unsafe_input_names)
        env_vars = safe_env_vars(tc.env_vars)
        stdout_limit = 8000 if self._is_shell_init_sample(sample) else 500
        stderr_limit = 2000 if self._is_shell_init_sample(sample) else 300
        return (
            f"=== Sample {i}: {tc.name} [{', '.join(sample.tags)}] ===\n"
            f"Input: args={args}, stdin={repr(tc.stdin[:200])}\n"
            f"Files in: {list(input_files.keys())}\n"
            f"Input file previews: {self._file_previews(input_files)}\n"
            f"Env: {env_vars}\n"
            f"Output: exit_code={res.exit_code}, stdout={repr(res.stdout[:stdout_limit])}, "
            f"stderr={repr(res.stderr[:stderr_limit])}\n"
            f"Files out: {list(res.output_files.keys())}\n"
            f"File previews: {self._file_previews(res.output_files)}\n"
        )

    def _format_sample_for_prompt_compact(self, i: int, sample: BehaviorSample) -> str:
        tc = sample.test_case
        res = sample.observed_result
        input_files, unsafe_input_names = self._safe_input_file_partition(tc.input_files)
        args = self._redact_unsafe_input_file_args(tc.args, unsafe_input_names)
        env_vars = safe_env_vars(tc.env_vars)
        stdout_limit = 1400 if self._is_shell_init_sample(sample) else 450
        stderr_limit = 700 if self._is_shell_init_sample(sample) else 260
        return (
            f"=== Sample {i}: {tc.name} [{', '.join(sample.tags)}] ===\n"
            f"Input: args={args}, stdin={repr(self._truncate_text(tc.stdin, 120))}\n"
            f"Files in: {list(input_files.keys())}\n"
            f"Input file previews: {self._file_previews(input_files, limit=260)}\n"
            f"Env: {env_vars}\n"
            f"Output: exit_code={res.exit_code}, "
            f"stdout={repr(self._truncate_text(res.stdout, stdout_limit))}, "
            f"stderr={repr(self._truncate_text(res.stderr, stderr_limit))}\n"
            f"Files out: {list(res.output_files.keys())}\n"
            f"File previews: {self._file_previews(res.output_files, limit=260)}\n"
        )

    def _sample_prompt_priority(self, sample: BehaviorSample, index: int) -> int:
        tags = set(sample.tags)
        name = sample.test_case.name.lower()
        args = [str(arg).lower() for arg in sample.test_case.args]
        result = sample.observed_result
        priority = max(12 - index, 0)
        if self._is_shell_init_sample(sample):
            priority += 120
        if "cli_discovery" in tags or "--help" in args or "help" in name:
            priority += 110
        if (
            "file_io" in tags
            or "side_effect" in tags
            or sample.test_case.input_files
            or result.output_files
        ):
            priority += 100
        if (
            "error_mode" in tags
            or "invalid" in name
            or result.exit_code != 0
            or result.timeout_triggered
        ):
            priority += 90
        if "stateful" in tags:
            priority += 70
        if any(tag.startswith("smoke_contract:") for tag in tags):
            priority += 60
        if any(tag.startswith("adaptive_axis:") for tag in tags):
            priority += 50
        if sample.test_case.stdin:
            priority += 20
        return priority

    def _truncate_text(self, text: str, limit: int) -> str:
        if limit <= 0:
            return ""
        if len(text) <= limit:
            return text
        marker = "\n...[truncated]"
        if limit <= len(marker):
            return text[:limit]
        return f"{text[: limit - len(marker)]}{marker}"

    def _truncate_middle(
        self,
        text: str,
        limit: int,
        marker: str = "\n...[truncated due to prompt budget]...\n",
    ) -> str:
        if limit <= 0:
            return ""
        if len(text) <= limit:
            return text
        if limit <= len(marker):
            return text[:limit]
        remaining = limit - len(marker)
        head_len = max(remaining * 2 // 3, 0)
        tail_len = remaining - head_len
        return f"{text[:head_len]}{marker}{text[-tail_len:] if tail_len else ''}"

    def _format_documentation(
        self,
        documentation: str,
        max_chars: int | None = None,
    ) -> str:
        text = documentation.strip()
        if max_chars is None:
            return text
        return self._truncate_middle(
            text,
            max_chars,
            marker="\n...[documentation truncated due to prompt budget]...\n",
        )

    def _contracts_from_corpus(
        self,
        corpus: List[BehaviorSample],
        limit: int = 24,
    ) -> list[BehaviorContract]:
        contracts: list[BehaviorContract] = []
        for sample in self._select_contract_samples(corpus, limit):
            tc = sample.test_case
            res = sample.observed_result
            input_files, unsafe_input_names = self._safe_input_file_partition(tc.input_files)
            stdout_limit = 8000 if self._is_shell_init_sample(sample) else 2000
            stderr_limit = 8000 if self._is_shell_init_sample(sample) else 2000
            contracts.append(
                BehaviorContract(
                    test_name=tc.name,
                    args=self._redact_unsafe_input_file_args(tc.args, unsafe_input_names),
                    stdin=tc.stdin[:1000],
                    input_files=input_files,
                    input_file_previews=self._file_previews(input_files),
                    env_vars=safe_env_vars(tc.env_vars),
                    stdout=res.stdout[:stdout_limit],
                    stderr=res.stderr[:stderr_limit],
                    exit_code=res.exit_code,
                    output_files=sorted(res.output_files),
                    output_file_previews=self._file_previews(res.output_files),
                    tags=sample.tags,
                )
            )
        return contracts

    def _select_contract_samples(
        self,
        corpus: list[BehaviorSample],
        limit: int,
    ) -> list[BehaviorSample]:
        if limit <= 0:
            return []
        if len(corpus) <= limit:
            return list(corpus)

        selected = list(corpus[:limit])
        selected_ids = {id(sample) for sample in selected}
        sparse_dimensions = (
            self._sample_has_input_files,
            self._sample_has_output_files,
            self._sample_has_env_vars,
            self._sample_has_stdin,
            self._sample_has_nonzero_exit,
        )
        additions: list[BehaviorSample] = []
        for predicate in sparse_dimensions:
            if any(predicate(sample) for sample in selected):
                continue
            candidate = next(
                (
                    sample
                    for sample in corpus[limit:]
                    if id(sample) not in selected_ids
                    and id(sample) not in {id(addition) for addition in additions}
                    and predicate(sample)
                ),
                None,
            )
            if candidate is not None:
                additions.append(candidate)

        if not additions:
            return selected

        while len(selected) + len(additions) > limit and selected:
            remove_index = min(
                range(len(selected)),
                key=lambda index: (
                    self._sample_sparse_dimension_count(selected[index]),
                    -index,
                ),
            )
            del selected[remove_index]
        return selected + additions

    def _is_shell_init_sample(self, sample: BehaviorSample) -> bool:
        tc = sample.test_case
        return (
            "shell_init" in sample.tags
            or tc.name.startswith("shell_init_")
            or tc.args[:1] == ["init"]
        )

    def _sample_sparse_dimension_count(self, sample: BehaviorSample) -> int:
        return sum(
            (
                self._sample_has_input_files(sample),
                self._sample_has_output_files(sample),
                self._sample_has_env_vars(sample),
                self._sample_has_stdin(sample),
                self._sample_has_nonzero_exit(sample),
            )
        )

    def _sample_has_input_files(self, sample: BehaviorSample) -> bool:
        safe, _unsafe = self._safe_input_file_partition(sample.test_case.input_files)
        return bool(safe)

    def _sample_has_output_files(self, sample: BehaviorSample) -> bool:
        return bool(sample.observed_result.output_files)

    def _sample_has_env_vars(self, sample: BehaviorSample) -> bool:
        return bool(safe_env_vars(sample.test_case.env_vars))

    def _sample_has_stdin(self, sample: BehaviorSample) -> bool:
        return bool(sample.test_case.stdin)

    def _sample_has_nonzero_exit(self, sample: BehaviorSample) -> bool:
        return sample.observed_result.exit_code != 0


    def _safe_input_files(self, input_files: dict[str, bytes]) -> dict[str, bytes]:
        safe, _unsafe = self._safe_input_file_partition(input_files)
        return safe

    def _safe_input_file_partition(
        self,
        input_files: dict[str, bytes],
    ) -> tuple[dict[str, bytes], set[str]]:
        safe: dict[str, bytes] = {}
        unsafe: set[str] = set()
        for name, content in sorted(input_files.items()):
            try:
                normalized = safe_input_file_relative_path(name).as_posix()
            except UnsafeInputFilePathError:
                unsafe.add(name)
                continue
            safe[normalized] = content if isinstance(content, bytes) else str(content).encode("utf-8")
        return safe, unsafe

    def _redact_unsafe_input_file_args(
        self,
        args: list[str],
        unsafe_input_names: set[str],
    ) -> list[str]:
        return [
            "<unsafe_input_file>"
            if arg in unsafe_input_names or self._is_unsafe_file_like_arg(arg)
            else arg
            for arg in args
        ]

    def _is_unsafe_file_like_arg(self, arg: str) -> bool:
        if not isinstance(arg, str) or arg.startswith("-") or "://" in arg:
            return False
        if not self._is_probable_file_arg(arg):
            return False
        try:
            safe_input_file_relative_path(arg)
        except UnsafeInputFilePathError:
            return True
        return False

    def _is_probable_file_arg(self, arg: str) -> bool:
        file_suffixes = {
            ".csv",
            ".gz",
            ".htm",
            ".html",
            ".json",
            ".jsonl",
            ".md",
            ".mkd",
            ".tar",
            ".tgz",
            ".txt",
            ".xml",
            ".xz",
            ".zip",
        }
        normalized = arg.replace("\\", "/").lower()
        return "/" in normalized or any(normalized.endswith(suffix) for suffix in file_suffixes)

    def _file_previews(
        self,
        output_files: dict[str, bytes],
        limit: int = 2000,
    ) -> dict[str, str]:
        previews: dict[str, str] = {}
        for name, content in sorted(output_files.items()):
            if isinstance(content, bytes):
                text = content.decode("utf-8", errors="replace")
            else:
                text = str(content)
            if len(text) > limit:
                text = f"{text[:limit]}\n...[truncated]"
            previews[name] = text
        return previews
    
    def _parse_spec(self, text: str) -> ProgramSpec:
        """Parse LLM JSON output into ProgramSpec."""
        text = text.strip()
        if text.startswith("```"):
            text = re.sub(r"```(?:json)?\s*", "", text).replace("```", "")
        
        try:
            data = extract_json_object(text)
            cli_surface = self._normalize_cli_surface(data.get("cli_surface", {}))
            invariants = self._normalize_invariants(data.get("invariants", []))
            raw_observations = data.get("raw_observations", "")
            if not isinstance(raw_observations, str):
                raw_observations = json.dumps(raw_observations, ensure_ascii=False)
            return ProgramSpec(
                summary=data.get("summary", ""),
                input_formats=self._normalize_string_list(data.get("input_formats", [])),
                output_formats=self._normalize_string_list(data.get("output_formats", [])),
                cli_surface=CLISurface(**cli_surface),
                edge_cases=self._normalize_string_list(data.get("edge_cases", [])),
                stateful=data.get("stateful", False),
                invariants=[Invariant(**inv) for inv in invariants],
                complexity_hints=data.get("complexity_hints", {}),
                raw_observations=raw_observations,
            )
        except (json.JSONDecodeError, TypeError, ValidationError, ValueError):
            # Fallback: return a minimal spec with raw text
            return ProgramSpec(
                summary="Failed to parse structured spec. Raw LLM output preserved.",
                raw_observations=text,
            )

    def _is_parse_failure(self, spec: ProgramSpec) -> bool:
        return spec.summary == "Failed to parse structured spec. Raw LLM output preserved."

    def _spec_repair_messages(self, invalid_output: str) -> list[Message]:
        return [
            self.llm.system_prompt(
                self.SYSTEM_PROMPT
                + "\nReturn a strictly valid JSON object. Do not include markdown fences or prose."
            ),
            self.llm.user_prompt(
                "The previous attempt was not valid JSON for the required schema. "
                "Reformat the draft below into a valid JSON object that preserves its meaning as conservatively as possible.\n\n"
                f"{self._truncate_middle(invalid_output.strip(), self.REPAIR_DRAFT_MAX_CHARS)}"
            ),
        ]

    def _fallback_spec(
        self,
        corpus: List[BehaviorSample],
        documentation: str,
        cli_surface: CLISurface,
        failed_output: str,
    ) -> ProgramSpec:
        return ProgramSpec(
            summary=self._fallback_summary(documentation, corpus),
            cli_surface=cli_surface.model_copy(deep=True),
            edge_cases=self._fallback_edge_cases(corpus),
            stateful=any("stateful" in sample.tags for sample in corpus),
            raw_observations=(
                "Structured spec parsing failed; falling back to deterministic synthesis.\n\n"
                "Documentation:\n"
                f"{self._format_documentation(documentation, max_chars=self.DOCUMENTATION_PROMPT_MAX_CHARS)}\n\n"
                "Observed behavior:\n"
                f"{self._format_corpus(corpus, max_chars=self.OBSERVATION_PROMPT_MAX_CHARS)}\n\n"
                "Unparsed model draft:\n"
                f"{self._truncate_text(failed_output.strip(), self.FAILED_DRAFT_MAX_CHARS)}"
            ).strip(),
        )

    def _fallback_summary(
        self,
        documentation: str,
        corpus: List[BehaviorSample],
    ) -> str:
        lines = [line.strip() for line in documentation.splitlines() if line.strip()]
        if lines:
            return lines[0][:240]
        if corpus:
            sample = corpus[0]
            if sample.test_case.description:
                return sample.test_case.description[:240]
        return "Fallback specification derived from cleanroom observations."

    def _fallback_edge_cases(self, corpus: List[BehaviorSample]) -> list[str]:
        edge_cases: list[str] = []
        seen: set[str] = set()
        for sample in corpus:
            result = sample.observed_result
            if result.exit_code == 0 and not result.timeout_triggered:
                continue
            description = sample.test_case.description or sample.test_case.name
            detail = (
                f"{description}: exit={result.exit_code}"
                + (" timeout" if result.timeout_triggered else "")
            )
            if detail not in seen:
                seen.add(detail)
                edge_cases.append(detail)
        return edge_cases

    def _normalize_cli_surface(self, cli_surface: dict) -> dict:
        """Normalize common LLM JSON variants into CLISurface shape."""
        normalized = dict(cli_surface or {})

        subcommand_sections: list[dict[str, Any]] = []
        subcommands = normalized.get("subcommands", [])
        if isinstance(subcommands, dict):
            normalized["subcommands"] = list(subcommands.keys())
            subcommand_sections = [
                item for item in subcommands.values() if isinstance(item, dict)
            ]
        elif isinstance(subcommands, list):
            names: list[str] = []
            for item in subcommands:
                if isinstance(item, str):
                    names.append(item)
                elif isinstance(item, dict) and item.get("name"):
                    names.append(str(item["name"]))
                    subcommand_sections.append(item)
            normalized["subcommands"] = names
        else:
            normalized["subcommands"] = []

        flag_inputs: list[Any] = []
        flag_inputs.extend(normalized.get("global_flags", []) or [])
        flag_inputs.extend(normalized.get("flags", []) or [])
        for section in subcommand_sections:
            flag_inputs.extend(section.get("flags", []) or [])

        flags: list[dict[str, Any]] = []
        seen_flags: set[str] = set()
        for item in flag_inputs:
            flag = self._normalize_flag(item)
            if flag and flag["name"] not in seen_flags:
                seen_flags.add(flag["name"])
                flags.append(flag)
        normalized["flags"] = flags

        positional_args: list[dict[str, Any]] = []
        positional_inputs = list(normalized.get("positional_args", []) or [])
        for section in subcommand_sections:
            positional_inputs.extend(section.get("positional_args", []) or [])
        for index, item in enumerate(positional_inputs):
            arg = self._normalize_positional_arg(item, index)
            if arg:
                positional_args.append(arg)
        normalized["positional_args"] = positional_args

        parsed_codes: set[int] = set(self._parse_exit_codes(normalized.get("exit_codes", [])))
        for section in subcommand_sections:
            parsed_codes.update(self._parse_exit_codes(section.get("exit_codes", [])))
        normalized["exit_codes"] = sorted(parsed_codes)

        return normalized

    def _normalize_flag(self, item: Any) -> dict | None:
        if not isinstance(item, dict):
            return None
        raw_name = item.get("long") or item.get("name")
        if not raw_name:
            return None
        name = str(raw_name)
        if not name.startswith("-"):
            name = f"--{name}"
        flag = {
            "name": name,
            "short_form": item.get("short_form") or item.get("short"),
            "type_hint": item.get("type_hint") or item.get("type") or "bool",
            "required": bool(item.get("required", False)),
            "default_value": item.get("default_value"),
            "description": item.get("description", ""),
        }
        if flag["default_value"] is not None and not isinstance(flag["default_value"], str):
            flag["default_value"] = str(flag["default_value"])
        return flag

    def _normalize_positional_arg(self, item: Any, index: int) -> dict | None:
        if not isinstance(item, dict):
            return None
        if not item.get("name"):
            return None
        return {
            "name": str(item["name"]),
            "position": int(item.get("position", index)),
            "type_hint": item.get("type_hint") or item.get("type") or "string",
            "required": bool(item.get("required", True)),
            "variadic": bool(item.get("variadic", False)),
        }

    def _parse_exit_codes(self, exit_codes: Any) -> list[int]:
        parsed_codes = []
        if isinstance(exit_codes, dict):
            raw_values: list[Any] = list(exit_codes.keys())
        elif isinstance(exit_codes, list):
            raw_values = [
                item.get("code") if isinstance(item, dict) else item
                for item in exit_codes
            ]
        else:
            raw_values = []
        for value in raw_values:
            try:
                parsed_codes.append(int(value))
            except (TypeError, ValueError):
                continue
        return parsed_codes

    def _normalize_string_list(self, values: list) -> list[str]:
        normalized = []
        for item in values or []:
            if isinstance(item, str):
                normalized.append(item)
            else:
                normalized.append(json.dumps(item, ensure_ascii=False))
        return normalized

    def _normalize_invariants(self, invariants: list) -> list:
        normalized = []
        for item in invariants or []:
            invariant = dict(item)
            if "invariant_type" not in invariant and "type" in invariant:
                invariant["invariant_type"] = invariant.pop("type")
            normalized.append(invariant)
        return normalized
