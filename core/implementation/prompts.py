"""System prompt constants and prompt-builder helpers for the ImplementerAgent."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from core.data_models import ArchitectureBlueprint, Codebase, ProgramSpec
from core.codebase.integrity import CodebaseIntegrityIssue
from core.implementation.contract_assets import is_materializable_static_output_contract
from core.implementation.entrypoint import expected_entry_point
from core.prompting.behavior_contracts import (
    behavior_contract_prompt,
    implementation_behavior_contract_prompt,
    spec_prompt_json,
    task_profile_prompt,
)

if TYPE_CHECKING:
    from llm_clients.base import BaseLLMClient, Message

IMPLEMENTER_SYSTEM_PROMPT = """You are an expert software engineer implementing a cleanroom replacement.
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

RETRY_SYSTEM_PROMPT = (
    "Your previous implementation response was not a runnable complete codebase. "
    "Return only one JSON object with this exact shape: "
    '{"files":[{"path":"main.py","content":"..."}],"build_script":""}. '
    "Include every local module imported by the entry point, or make the entry "
    "point self-contained. Keep the implementation compact enough to fit in one "
    "response; prefer a concise single-file implementation when possible. "
    "Do not include prose or markdown fences."
)

_GUARD_DISABLED_TMPL = (
    "\n\nStatic output asset mode is disabled. You must implement those init <shell> "
    "argv forms directly in source, but keep the implementation compact and syntax-safe. "
    "Avoid giant escaped one-line literals and avoid deeply nested quote/backslash "
    "sequences in shell templates. Prefer small helper functions and triple-quoted "
    "templates with minimal escaping so generated Python parses cleanly: {argv_forms}."
)

_GUARD_ENABLED_TMPL = (
    "\n\nStatic output asset mode is enabled. Do not implement shell init script templates, "
    "completion scripts, or large bash/zsh/fish/powershell bodies in generated source. "
    "generated asset injection will handle those exact argv forms after code generation: "
    "{argv_forms}. Keep the entrypoint compact and implement only normal CLI parsing, "
    "stateful database logic, errors, and non-static behavior."
)


def static_asset_generation_guard(spec: ProgramSpec, enabled: bool) -> str:
    """Return an addendum string controlling static-asset generation in the prompt."""
    contracts = [
        c for c in spec.behavior_contracts if is_materializable_static_output_contract(c)
    ]
    if not contracts:
        return ""
    argv_forms = json.dumps([c.args for c in contracts], ensure_ascii=False)
    tmpl = _GUARD_ENABLED_TMPL if enabled else _GUARD_DISABLED_TMPL
    return tmpl.format(argv_forms=argv_forms)


def contract_prompt(spec: ProgramSpec, enabled: bool) -> str:
    """Return the behavior-contract prompt section."""
    profile = task_profile_prompt(spec)
    if enabled:
        return profile + implementation_behavior_contract_prompt(spec)
    return profile + behavior_contract_prompt(spec)


def build_entrypoint_messages(
    llm: "BaseLLMClient",
    spec: ProgramSpec,
    blueprint: ArchitectureBlueprint,
    enabled: bool,
) -> "list[Message]":
    return [
        llm.system_prompt(ENTRYPOINT_SYSTEM_PROMPT + static_asset_generation_guard(spec, enabled)),
        llm.user_prompt(
            f"Specification:\n{spec_prompt_json(spec)}\n\n"
            f"{contract_prompt(spec, enabled)}"
            f"Architecture Blueprint:\n{blueprint.model_dump_json(indent=2)}\n\n"
            f"Generate only {expected_entry_point(blueprint)}."
        ),
    ]


def build_support_messages(
    llm: "BaseLLMClient",
    spec: ProgramSpec,
    blueprint: ArchitectureBlueprint,
    entry_codebase: Codebase,
    enabled: bool,
) -> "list[Message]":
    return [
        llm.system_prompt(SUPPORT_SYSTEM_PROMPT + static_asset_generation_guard(spec, enabled)),
        llm.user_prompt(
            f"Specification:\n{spec_prompt_json(spec)}\n\n"
            f"{contract_prompt(spec, enabled)}"
            f"Architecture Blueprint:\n{blueprint.model_dump_json(indent=2)}\n\n"
            "Existing entrypoint files:\n"
            f"{json.dumps(entry_codebase.files, indent=2)}\n\n"
            "Generate supporting Python files or safe replacements now."
        ),
    ]


def build_retry_messages(
    llm: "BaseLLMClient",
    spec: ProgramSpec,
    blueprint: ArchitectureBlueprint,
    initial_output: str,
    integrity_issues: list[CodebaseIntegrityIssue],
    enabled: bool,
) -> "list[Message]":
    issue_summary = [
        {"kind": i.kind, "path": i.path, "module": i.module, "message": i.message}
        for i in integrity_issues
    ]
    return [
        llm.system_prompt(RETRY_SYSTEM_PROMPT + static_asset_generation_guard(spec, enabled)),
        llm.user_prompt(
            f"Specification:\n{spec_prompt_json(spec)}\n\n"
            f"{contract_prompt(spec, enabled)}"
            f"Architecture Blueprint:\n{blueprint.model_dump_json(indent=2)}\n\n"
            f"Integrity issues:\n{json.dumps(issue_summary, indent=2)}\n\n"
            f"Previous output preview:\n{_retry_output_preview(initial_output, integrity_issues)}\n\n"
            "Generate the complete source files now."
        ),
    ]


def _retry_output_preview(
    initial_output: str,
    integrity_issues: list[CodebaseIntegrityIssue],
) -> str:
    if not _has_likely_truncated_output_issue(integrity_issues):
        return initial_output[:1000]
    if len(initial_output) <= 2000:
        return initial_output
    return (
        initial_output[:900]
        + "\n...[middle omitted from previous output preview]...\n"
        + initial_output[-900:]
    )


def _has_likely_truncated_output_issue(
    integrity_issues: list[CodebaseIntegrityIssue],
) -> bool:
    return any("likely truncated generated output" in issue.message for issue in integrity_issues)
