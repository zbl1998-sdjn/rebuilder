import subprocess
import sys

import pytest

from core.data_models import (
    ArchitectureBlueprint,
    BehaviorContract,
    Codebase,
    ModuleBlueprint,
    ProgramSpec,
)
from core.implementation.contract_assets import (
    PythonContractAssetInjector,
    is_materializable_static_output_contract,
)
from core.implementer_agent import ImplementerAgent
from llm_clients.base import BaseLLMClient, LLMResponse


def test_python_contract_asset_injector_dispatches_shell_init_exact_output(tmp_path):
    stdout = "# shellcheck shell=bash\n" + ("x" * 2000) + "\n# tail\n"
    main_path = tmp_path / "main.py"
    main_path.write_text(
        "import sys\n\n"
        "def main():\n"
        "    print('stub')\n"
        "    return 0\n\n"
        "if __name__ == '__main__':\n"
        "    raise SystemExit(main())\n",
        encoding="utf-8",
    )
    codebase = Codebase(
        root_path=tmp_path,
        language="python",
        files={"main.py": main_path.read_text(encoding="utf-8")},
        executable_path=main_path,
    )
    spec = ProgramSpec(
        behavior_contracts=[
            BehaviorContract(
                test_name="shell_init_bash",
                args=["init", "bash"],
                stdout=stdout,
                exit_code=0,
                tags=["shell_init", "full_output"],
            ),
            BehaviorContract(test_name="query_empty", args=["query"], stdout=""),
        ]
    )

    updated = PythonContractAssetInjector().apply(
        spec=spec,
        codebase=codebase,
        entry_point="main.py",
    )

    assert "rebuilder_contracts.py" in updated.files
    assert "query_empty" not in updated.files["rebuilder_contracts.py"]
    completed = subprocess.run(
        [sys.executable, str(main_path), "init", "bash"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.stdout == stdout
    assert completed.stderr == ""
    assert completed.returncode == 0


def test_contract_asset_policy_only_allows_default_long_shell_init_outputs():
    allowed = BehaviorContract(
        test_name="shell_init_bash",
        args=["init", "bash"],
        stdout="# shellcheck shell=bash\n" + ("x" * 2000),
        exit_code=0,
        tags=["shell_init", "full_output"],
    )
    short_output = allowed.model_copy(update={"stdout": "short\n"})
    flag_variant = allowed.model_copy(
        update={
            "test_name": "shell_init_bash_cmd_variant",
            "args": ["init", "--cmd", "j", "bash"],
        }
    )
    stateful_query = BehaviorContract(
        test_name="query_alpha",
        args=["query", "alpha"],
        stdout="/tmp/alpha\n" + ("x" * 2000),
        tags=["stateful"],
    )

    assert is_materializable_static_output_contract(allowed)
    assert not is_materializable_static_output_contract(short_output)
    assert not is_materializable_static_output_contract(flag_variant)
    assert not is_materializable_static_output_contract(stateful_query)


def test_python_contract_asset_injector_excludes_policy_rejected_contracts(tmp_path):
    main_path = tmp_path / "main.py"
    main_path.write_text(
        "def main():\n"
        "    return 0\n\n"
        "if __name__ == '__main__':\n"
        "    raise SystemExit(main())\n",
        encoding="utf-8",
    )
    codebase = Codebase(
        root_path=tmp_path,
        language="python",
        files={"main.py": main_path.read_text(encoding="utf-8")},
        executable_path=main_path,
    )
    spec = ProgramSpec(
        behavior_contracts=[
            BehaviorContract(
                test_name="shell_init_bash",
                args=["init", "bash"],
                stdout="# shellcheck shell=bash\n" + ("x" * 2000),
                tags=["shell_init", "full_output"],
            ),
            BehaviorContract(
                test_name="shell_init_bash_cmd_variant",
                args=["init", "--cmd", "j", "bash"],
                stdout="# variant\n" + ("x" * 2000),
                tags=["shell_init", "full_output"],
            ),
            BehaviorContract(
                test_name="query_alpha",
                args=["query", "alpha"],
                stdout="/tmp/alpha\n" + ("x" * 2000),
                tags=["stateful"],
            ),
        ]
    )

    updated = PythonContractAssetInjector().apply(spec, codebase, "main.py")

    asset = updated.files["rebuilder_contracts.py"]
    assert "('init', 'bash')" in asset
    assert "--cmd" not in asset
    assert "query_alpha" not in asset
    assert updated.generation_metadata["contract_asset_policy"] == "static_default_shell_init_only"
    assert updated.generation_metadata["contract_asset_rejected_count"] == 2


class StubShellInitLLM(BaseLLMClient):
    def __init__(self):
        super().__init__("fake-key", "http://fake", "mock-model")
        self.calls = 0

    async def chat(self, messages, temperature=None, max_tokens=None, **kwargs):
        self.calls += 1
        if self.calls == 1:
            return LLMResponse(
                content=(
                    '{"files":[{"path":"main.py","content":'
                    '"def main():\\n    print(\\"stub\\")\\n    return 0\\n'
                    'if __name__ == \\"__main__\\":\\n    raise SystemExit(main())\\n"}]}'
                )
            )
        return LLMResponse(content='{"files":[]}')

    async def chat_stream(self, messages, temperature=None, max_tokens=None, **kwargs):
        yield "mock"


@pytest.mark.asyncio
async def test_implementer_materializes_shell_init_contract_assets(tmp_path):
    stdout = "# shellcheck shell=bash\n" + ("x" * 2000) + "\n"
    spec = ProgramSpec(
        summary="tool",
        behavior_contracts=[
            BehaviorContract(
                test_name="shell_init_bash",
                args=["init", "bash"],
                stdout=stdout,
                tags=["shell_init", "full_output"],
            )
        ],
    )
    blueprint = ArchitectureBlueprint(
        language="python",
        entry_point="main.py",
        modules=[ModuleBlueprint(name="cli", responsibility="entrypoint")],
    )

    codebase = await ImplementerAgent(StubShellInitLLM()).implement(
        spec,
        blueprint,
        tmp_path,
    )

    assert "rebuilder_contracts.py" in codebase.files
    assert codebase.generation_metadata["contract_asset_status"] == "materialized"


@pytest.mark.asyncio
async def test_implementer_can_disable_static_output_contract_assets(tmp_path):
    stdout = "# shellcheck shell=bash\n" + ("x" * 2000) + "\n"
    spec = ProgramSpec(
        summary="tool",
        behavior_contracts=[
            BehaviorContract(
                test_name="shell_init_bash",
                args=["init", "bash"],
                stdout=stdout,
                tags=["shell_init", "full_output"],
            )
        ],
    )
    blueprint = ArchitectureBlueprint(
        language="python",
        entry_point="main.py",
        modules=[ModuleBlueprint(name="cli", responsibility="entrypoint")],
    )

    codebase = await ImplementerAgent(
        StubShellInitLLM(),
        enable_static_output_assets=False,
    ).implement(
        spec,
        blueprint,
        tmp_path,
    )

    assert "rebuilder_contracts.py" not in codebase.files
    assert codebase.generation_metadata["static_output_assets_enabled"] is False
    assert codebase.generation_metadata["contract_asset_status"] == "disabled"
