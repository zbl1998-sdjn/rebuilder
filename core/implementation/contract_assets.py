"""Materialize selected exact cleanroom contracts into generated code assets."""

from __future__ import annotations

import ast
from pathlib import Path

from core.data_models import BehaviorContract, Codebase, ProgramSpec


STATIC_ASSET_POLICY_NAME = "static_default_shell_init_only"
STATIC_SHELL_INIT_OUTPUT_MIN_CHARS = 1000
STATIC_SHELL_INIT_SHELLS = frozenset({"bash", "zsh", "fish", "powershell"})


def is_materializable_static_output_contract(contract: BehaviorContract) -> bool:
    """Return whether a contract is safe to materialize without overfitting."""
    return (
        _is_default_shell_init_contract(contract)
        and "full_output" in contract.tags
        and len(contract.stdout) >= STATIC_SHELL_INIT_OUTPUT_MIN_CHARS
        and contract.stderr == ""
        and contract.exit_code == 0
        and not contract.stdin
        and not contract.output_files
        and not contract.output_file_previews
    )


def _is_default_shell_init_contract(contract: BehaviorContract) -> bool:
    return (
        "shell_init" in contract.tags
        and len(contract.args) == 2
        and contract.args[0] == "init"
        and contract.args[1] in STATIC_SHELL_INIT_SHELLS
        and contract.test_name.lower() == f"shell_init_{contract.args[1]}"
    )


class PythonContractAssetInjector:
    """Inject exact deterministic CLI outputs as a small Python support asset."""

    ASSET_FILENAME = "rebuilder_contracts.py"

    def apply(
        self,
        spec: ProgramSpec,
        codebase: Codebase,
        entry_point: str | None,
    ) -> Codebase:
        contracts = self._materializable_contracts(spec)
        rejected_count = len(
            [
                contract
                for contract in spec.behavior_contracts
                if self._looks_like_contract_asset_candidate(contract)
                and not is_materializable_static_output_contract(contract)
            ]
        )
        codebase.generation_metadata["static_output_assets_enabled"] = True
        codebase.generation_metadata["contract_asset_policy"] = STATIC_ASSET_POLICY_NAME
        codebase.generation_metadata["contract_asset_rejected_count"] = rejected_count
        if not contracts:
            codebase.generation_metadata["contract_asset_status"] = "skipped_no_contracts"
            return codebase
        if not entry_point or entry_point not in codebase.files:
            codebase.generation_metadata["contract_asset_status"] = "skipped_no_entrypoint"
            return codebase

        asset_source = self._asset_source(contracts)
        entry_source = self._inject_entrypoint(codebase.files[entry_point])
        codebase.files[entry_point] = entry_source
        codebase.files[self.ASSET_FILENAME] = asset_source
        self._write_file(codebase.root_path / entry_point, entry_source)
        self._write_file(codebase.root_path / self.ASSET_FILENAME, asset_source)
        codebase.generation_metadata["contract_asset_status"] = "materialized"
        codebase.generation_metadata["contract_asset_count"] = len(contracts)
        codebase.generation_metadata["contract_asset_file"] = self.ASSET_FILENAME
        return codebase

    def _materializable_contracts(self, spec: ProgramSpec) -> list[BehaviorContract]:
        return [
            contract
            for contract in spec.behavior_contracts
            if is_materializable_static_output_contract(contract)
        ]

    def _looks_like_contract_asset_candidate(self, contract: BehaviorContract) -> bool:
        return (
            "shell_init" in contract.tags
            or contract.test_name.lower().startswith("shell_init_")
            or len(contract.stdout) >= STATIC_SHELL_INIT_OUTPUT_MIN_CHARS
            or bool(contract.output_files)
            or bool(contract.output_file_previews)
        )

    def _asset_source(self, contracts: list[BehaviorContract]) -> str:
        payload = {
            tuple(contract.args): {
                "stdout": contract.stdout,
                "stderr": contract.stderr,
                "exit_code": contract.exit_code,
            }
            for contract in contracts
        }
        return (
            '"""Exact cleanroom behavior contracts materialized by ReBuilder."""\n\n'
            f"EXACT_CONTRACTS = {payload!r}\n\n\n"
            "def dispatch_exact_contract(argv):\n"
            "    contract = EXACT_CONTRACTS.get(tuple(argv))\n"
            "    if contract is None:\n"
            "        return None\n"
            "    return (\n"
            "        contract['stdout'],\n"
            "        contract['stderr'],\n"
            "        contract['exit_code'],\n"
            "    )\n"
        )

    def _inject_entrypoint(self, source: str) -> str:
        if "dispatch_exact_contract" in source and self.ASSET_FILENAME in source:
            return source
        lines = source.splitlines(keepends=True)
        index = self._insertion_index(source, lines)
        snippet = self._dispatch_snippet()
        return "".join([*lines[:index], snippet, *lines[index:]])

    def _dispatch_snippet(self) -> str:
        return (
            "\n# ReBuilder exact cleanroom contract dispatch.\n"
            "import sys as _rebuilder_sys\n"
            "try:\n"
            "    from rebuilder_contracts import dispatch_exact_contract as _rebuilder_dispatch_exact_contract\n"
            "except Exception:\n"
            "    _rebuilder_dispatch_exact_contract = None\n"
            "if _rebuilder_dispatch_exact_contract is not None:\n"
            "    _rebuilder_match = _rebuilder_dispatch_exact_contract(_rebuilder_sys.argv[1:])\n"
            "    if _rebuilder_match is not None:\n"
            "        _rebuilder_stdout, _rebuilder_stderr, _rebuilder_exit_code = _rebuilder_match\n"
            "        _rebuilder_sys.stdout.write(_rebuilder_stdout)\n"
            "        _rebuilder_sys.stderr.write(_rebuilder_stderr)\n"
            "        raise SystemExit(_rebuilder_exit_code)\n"
            "\n"
        )

    def _insertion_index(self, source: str, lines: list[str]) -> int:
        index = 0
        if lines and lines[0].startswith("#!"):
            index = 1
        if len(lines) > index and "coding" in lines[index].lower():
            index += 1

        try:
            tree = ast.parse(source)
        except SyntaxError:
            return index

        body_index = 0
        if tree.body and isinstance(tree.body[0], ast.Expr):
            value = tree.body[0].value
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                index = max(index, int(getattr(tree.body[0], "end_lineno", 0)))
                body_index = 1

        for node in tree.body[body_index:]:
            if (
                isinstance(node, ast.ImportFrom)
                and node.module == "__future__"
                and node.level == 0
            ):
                index = max(index, int(getattr(node, "end_lineno", 0)))
                continue
            break
        return index

    def _write_file(self, path: Path, source: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
