"""
Architect Agent: Design code architecture based on synthesized specification.
"""

from __future__ import annotations

import json
import re
from typing import List

from core.data_models import ProgramSpec, ArchitectureBlueprint, ModuleBlueprint, InterfaceSpec
from core.llm_output import extract_json_object
from core.prompting.behavior_contracts import behavior_contract_prompt, spec_prompt_json, task_profile_prompt
from llm_clients.base import BaseLLMClient
from llm_clients.options import configured_max_tokens
from pydantic import ValidationError


class ArchitectAgent:
    """Generate a high-level architecture blueprint for the replacement implementation."""
    
    SYSTEM_PROMPT = """You are a senior software architect designing a cleanroom replacement for a black-box program.
You must design an architecture that matches the observed behavior, not necessarily the original implementation.

Output only a JSON object:
- "language": Recommended implementation language
- "language_version": Version constraint if any
- "modules": List of module objects, each with:
  - "name": Module name
  - "responsibility": What this module does
  - "interfaces": List of interface objects with "name", "signature", "input_types", "output_type", "description"
  - "dependencies": List of other module names it depends on
- "entry_point": Main entry function/file
- "build_system": Recommended build system (cmake, makefile, cargo, poetry, npm, etc.)
- "architecture_notes": Key design decisions and rationale

Prefer modular design for complex programs. For simple CLI tools, a single module is acceptable.
Choose languages that are well-suited to the observed I/O behavior."""
    
    def __init__(
        self,
        llm_client: BaseLLMClient,
        complexity_threshold: int = 3,
        preferred_languages: List[str] | None = None,
        max_modules: int | None = None,
    ):
        self.llm = llm_client
        self.complexity_threshold = complexity_threshold
        self.preferred_languages = [
            self._normalize_language(language)
            for language in (preferred_languages or [])
            if language
        ]
        self.max_modules = max_modules
    
    async def design(self, spec: ProgramSpec) -> ArchitectureBlueprint:
        """Generate architecture blueprint from specification."""
        messages = [
            self.llm.system_prompt(self.SYSTEM_PROMPT),
            self.llm.user_prompt(
                f"Program specification:\n{spec_prompt_json(spec)}\n\n"
                f"{task_profile_prompt(spec, purpose='architecture')}"
                f"{behavior_contract_prompt(spec)}"
                f"{self._constraints_prompt()}"
                f"Design a clean, implementable architecture. Output as JSON."
            ),
        ]
        
        resp = await self.llm.chat(
            messages,
            temperature=0.3,
            max_tokens=configured_max_tokens(self.llm, 8192),
        )
        return self._parse_blueprint(resp.content)
    
    def _parse_blueprint(self, text: str) -> ArchitectureBlueprint:
        text = text.strip()
        if text.startswith("```"):
            text = re.sub(r"```(?:json)?\s*", "", text).replace("```", "")
        
        try:
            data = extract_json_object(text)
            modules = []
            for mod in data.get("modules", []):
                if not isinstance(mod, dict):
                    continue
                interfaces = [
                    InterfaceSpec(**iface)
                    for iface in mod.get("interfaces", [])
                    if isinstance(iface, dict)
                ]
                modules.append(ModuleBlueprint(
                    name=mod.get("name", "main"),
                    responsibility=mod.get("responsibility", ""),
                    interfaces=interfaces,
                    dependencies=mod.get("dependencies", []),
                ))
            
            raw_language = data.get("language", "python")
            language = self._normalize_language(str(raw_language))
            entry_point = self._normalize_entry_point(
                language,
                data.get("entry_point", self._default_entry_point(language)),
            )
            build_system = data.get("build_system", "auto")
            architecture_notes = data.get("architecture_notes", "")
            if self.preferred_languages and language not in self.preferred_languages:
                preferred = self.preferred_languages[0]
                architecture_notes = (
                    f"Unsupported language {raw_language!r} replaced with preferred "
                    f"language {preferred!r}. {architecture_notes}"
                ).strip()
                language = preferred
                entry_point = self._default_entry_point(language)
                build_system = self._default_build_system(language)

            if self.max_modules is not None:
                modules = modules[: self.max_modules]

            return ArchitectureBlueprint(
                language=language,
                language_version=data.get("language_version", ""),
                modules=modules,
                entry_point=entry_point,
                build_system=build_system,
                architecture_notes=architecture_notes,
            )
        except (json.JSONDecodeError, KeyError, TypeError, ValidationError, ValueError) as e:
            # Fallback to minimal Python architecture
            return ArchitectureBlueprint(
                language="python",
                modules=[ModuleBlueprint(
                    name="main",
                    responsibility="Single module implementation",
                    interfaces=[],
                    dependencies=[],
                )],
                entry_point="main.py",
                build_system="none",
                architecture_notes=f"Parse error: {e}. Falling back to monolithic Python.",
            )

    def _constraints_prompt(self) -> str:
        constraints = []
        if self.preferred_languages:
            constraints.append(
                "Allowed implementation languages, in preference order: "
                f"{', '.join(self.preferred_languages)}. "
                "Choose only from this list."
            )
        if self.max_modules is not None:
            constraints.append(f"Use at most {self.max_modules} modules.")
        if not constraints:
            return ""
        return "Architecture constraints:\n- " + "\n- ".join(constraints) + "\n\n"

    def _normalize_language(self, language: str) -> str:
        normalized = language.strip().lower().replace(" ", "")
        return {
            "py": "python",
            "python3": "python",
            "c++": "cpp",
            "cplusplus": "cpp",
            "rustlang": "rust",
        }.get(normalized, normalized)

    def _normalize_entry_point(self, language: str, entry_point: object) -> str:
        default = self._default_entry_point(language)
        if not isinstance(entry_point, str):
            return default
        value = entry_point.strip().replace("\\", "/")
        if not value:
            return default
        if language != "python":
            return value
        if ":" in value or value.startswith("/"):
            return default
        if "/" in value:
            parts = value.split("/")
            if (
                value.endswith(".py")
                and all(self._is_safe_python_entry_part(part) for part in parts)
            ):
                return value
            return default
        if value.endswith(".py") and self._is_safe_python_entry_part(value):
            return value
        if all(self._is_safe_python_entry_part(part) for part in value.split(".")):
            return value
        return default

    def _is_safe_python_entry_part(self, value: str) -> bool:
        return bool(value) and value not in {".", ".."} and all(
            char.isalnum() or char in {"_", "-", "."}
            for char in value
        )

    def _default_entry_point(self, language: str) -> str:
        return {
            "python": "main.py",
            "rust": "src/main.rs",
            "javascript": "index.js",
            "typescript": "src/index.ts",
            "c": "main.c",
            "cpp": "main.cpp",
        }.get(language, "main")

    def _default_build_system(self, language: str) -> str:
        return {
            "python": "none",
            "rust": "cargo",
            "javascript": "npm",
            "typescript": "npm",
            "c": "make",
            "cpp": "make",
        }.get(language, "auto")
