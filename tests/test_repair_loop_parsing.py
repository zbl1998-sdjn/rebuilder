import json

import pytest

from core.data_models import (
    BehaviorContract,
    Codebase,
    DiffReport,
    ProgramSpec,
    RepairStrategy,
    TestCase,
    TestResult,
)
from core.repair_loop import RepairLoop
from core.repair.clustering import FailureCluster, FailureKind
from llm_clients.base import LLMResponse
from tests.test_probe_engine import MockLLMClient


def test_parse_repair_strategy_normalizes_list_hints():
    raw = json.dumps(
        {
            "strategy_type": "fix_output_format",
            "description": "fix argparse aliases",
            "target_files": ["program.py"],
            "hints": ["Use -u", "Keep --unique"],
        }
    )

    strategy = RepairLoop(MockLLMClient())._parse_strategy(raw)

    assert strategy.hints == "Use -u\nKeep --unique"


def test_parse_repair_strategy_extracts_json_from_explanatory_text():
    raw = """Looking at the failure data, the shared issue is output formatting.

```json
{
  "strategy_type": "fix_output_format",
  "description": "match executable spelling in help output",
  "target_files": ["main.py"],
  "hints": "Use the observed command name exactly."
}
```
"""

    strategy = RepairLoop(MockLLMClient())._parse_strategy(raw)

    assert strategy.strategy_type == "fix_output_format"
    assert strategy.description == "match executable spelling in help output"
    assert strategy.target_files == ["main.py"]
    assert strategy.hints == "Use the observed command name exactly."


def test_parse_repair_strategy_normalizes_target_files():
    raw = json.dumps(
        {
            "strategy_type": "fix_algorithm",
            "description": "repair selected files",
            "target_files": ["z.py", "a.py", "a.py", "", 7, None],
            "hints": "dedupe target files",
        }
    )

    strategy = RepairLoop(MockLLMClient())._parse_strategy(raw)

    assert strategy.target_files == ["a.py", "z.py"]


def test_parse_repair_strategy_accepts_single_target_file_string():
    raw = json.dumps(
        {
            "strategy_type": "fix_algorithm",
            "description": "repair selected file",
            "target_files": "main.py",
            "hints": "single target",
        }
    )

    strategy = RepairLoop(MockLLMClient())._parse_strategy(raw)

    assert strategy.target_files == ["main.py"]


def test_parse_repair_strategy_normalizes_target_file_paths():
    raw = json.dumps(
        {
            "strategy_type": "fix_algorithm",
            "description": "repair nested file",
            "target_files": [
                "src\\main.py",
                "./src/main.py",
                "../escape.py",
                "C:\\absolute.py",
                "",
            ],
            "hints": "normalize paths",
        }
    )

    strategy = RepairLoop(MockLLMClient())._parse_strategy(raw)

    assert strategy.target_files == ["src/main.py"]


def test_parse_repair_strategy_normalizes_non_string_strategy_fields():
    raw = json.dumps(
        {
            "strategy_type": None,
            "description": ["repair", "formatting"],
            "target_files": ["main.py"],
            "hints": "normalize strings",
        }
    )

    strategy = RepairLoop(MockLLMClient())._parse_strategy(raw)

    assert strategy.strategy_type == "fix_algorithm"
    assert strategy.description == '["repair", "formatting"]'


class CaptureLLM(MockLLMClient):
    def __init__(self):
        super().__init__()
        self.messages = None

    async def chat(self, messages, temperature=None, max_tokens=None, **kwargs):
        self.messages = messages
        return LLMResponse(
            content=json.dumps(
                {
                    "strategy_type": "fix_output_format",
                    "description": "repair shared stdout formatting",
                    "target_files": ["main.py"],
                    "hints": "match the cluster",
                }
            )
        )


def diff(name: str) -> DiffReport:
    return DiffReport(
        test_case=TestCase(name=name, args=["--help"]),
        original_result=TestResult(stdout="expected", stderr="", exit_code=0),
        replacement_result=TestResult(stdout="actual", stderr="", exit_code=0),
        stdout_match=False,
        stderr_match=True,
        exit_code_match=True,
        file_outputs_match=True,
    )


def long_help_diff() -> DiffReport:
    expected = "Usage:\n" + ("x" * 900) + "\nfinal expected example\n"
    actual = "Usage:\n" + ("x" * 900) + "\nwrong example\n"
    return DiffReport(
        test_case=TestCase(name="help_long", args=["--help"]),
        original_result=TestResult(stdout="", stderr=expected, exit_code=0),
        replacement_result=TestResult(stdout=actual, stderr="", exit_code=0),
        stdout_match=False,
        stderr_match=False,
        exit_code_match=True,
        file_outputs_match=True,
    )


def file_input_diff(name: str) -> DiffReport:
    return DiffReport(
        test_case=TestCase(
            name=name,
            args=["add", "alpha"],
            input_files={"alpha/.keep": b""},
        ),
        original_result=TestResult(stdout="", stderr="", exit_code=0),
        replacement_result=TestResult(stdout="", stderr="bad", exit_code=0),
        stdout_match=True,
        stderr_match=False,
        exit_code_match=True,
        file_outputs_match=True,
    )


def binary_file_input_diff(name: str) -> DiffReport:
    return DiffReport(
        test_case=TestCase(
            name=name,
            args=["add", "alpha"],
            input_files={"alpha.bin": b"\x00\xff\x01"},
        ),
        original_result=TestResult(stdout="", stderr="", exit_code=0),
        replacement_result=TestResult(stdout="", stderr="bad", exit_code=0),
        stdout_match=True,
        stderr_match=False,
        exit_code_match=True,
        file_outputs_match=True,
    )


def contract_spec() -> ProgramSpec:
    return ProgramSpec(
        summary="cli tool",
        behavior_contracts=[
            BehaviorContract(
                test_name="help_long",
                args=["--help"],
                stdout="exact help\n",
            ),
            BehaviorContract(
                test_name="no_args",
                args=[],
                stderr="exact stderr\n",
                exit_code=2,
            ),
        ],
    )


@pytest.mark.asyncio
async def test_diagnose_cluster_summarizes_related_failures(tmp_path):
    llm = CaptureLLM()
    cluster = FailureCluster(kind=FailureKind.STDOUT, reports=[diff("help"), diff("version")])

    await RepairLoop(llm).diagnose_cluster(
        cluster,
        ProgramSpec(summary="cli tool"),
        Codebase(root_path=tmp_path, language="python", files={"main.py": "print('x')"}),
    )

    prompt = llm.messages[-1].content
    assert "failure_cluster" in prompt
    assert '"kind": "stdout"' in prompt
    assert '"count": 2' in prompt
    assert "help" in prompt
    assert "version" in prompt


@pytest.mark.asyncio
async def test_diagnose_cluster_sorts_existing_files_in_prompt(tmp_path):
    llm = CaptureLLM()
    cluster = FailureCluster(kind=FailureKind.STDOUT, reports=[diff("help")])

    await RepairLoop(llm).diagnose_cluster(
        cluster,
        ProgramSpec(summary="cli tool"),
        Codebase(root_path=tmp_path, language="python", files={"z.py": "", "a.py": ""}),
    )

    prompt = llm.messages[-1].content
    assert prompt.index('"a.py"') < prompt.index('"z.py"')


@pytest.mark.asyncio
async def test_diagnose_cluster_keeps_help_tail_and_channel_guidance(tmp_path):
    llm = CaptureLLM()
    cluster = FailureCluster(kind=FailureKind.MULTIPLE, reports=[long_help_diff()])

    await RepairLoop(llm).diagnose_cluster(
        cluster,
        ProgramSpec(summary="cli tool"),
        Codebase(root_path=tmp_path, language="python", files={"main.py": "print('x')"}),
    )

    system_prompt = llm.messages[0].content
    prompt = llm.messages[-1].content
    assert "Preserve exact output channels" in system_prompt
    assert "final expected example" in prompt
    assert '"original_stderr"' in prompt
    assert '"replacement_stdout"' in prompt


@pytest.mark.asyncio
async def test_diagnose_cluster_prompts_with_exact_behavior_contracts_once(tmp_path):
    llm = CaptureLLM()
    cluster = FailureCluster(kind=FailureKind.STDOUT, reports=[diff("query")])

    await RepairLoop(llm).diagnose_cluster(
        cluster,
        contract_spec(),
        Codebase(root_path=tmp_path, language="python", files={"main.py": "print('x')"}),
    )

    prompt = llm.messages[-1].content
    assert "Exact behavior contracts" in prompt
    assert "exact help\\n" in prompt
    assert "exact stderr\\n" in prompt
    assert prompt.count("exact help\\n") == 1


@pytest.mark.asyncio
async def test_diagnose_cluster_serializes_file_input_test_cases(tmp_path):
    llm = CaptureLLM()
    cluster = FailureCluster(kind=FailureKind.STDERR, reports=[file_input_diff("stateful_add")])

    strategy = await RepairLoop(llm).diagnose_cluster(
        cluster,
        ProgramSpec(summary="cli tool"),
        Codebase(root_path=tmp_path, language="python", files={"main.py": "print('x')"}),
    )

    prompt = llm.messages[-1].content
    assert strategy.strategy_type == "fix_output_format"
    assert "alpha/.keep" in prompt


@pytest.mark.asyncio
async def test_diagnose_cluster_serializes_binary_file_input_test_cases(tmp_path):
    llm = CaptureLLM()
    cluster = FailureCluster(kind=FailureKind.STDERR, reports=[binary_file_input_diff("binary_add")])

    strategy = await RepairLoop(llm).diagnose_cluster(
        cluster,
        ProgramSpec(summary="cli tool"),
        Codebase(root_path=tmp_path, language="python", files={"main.py": "print('x')"}),
    )

    prompt = llm.messages[-1].content
    assert strategy.strategy_type == "fix_output_format"
    assert "alpha.bin" in prompt
    assert '"__type__": "bytes"' in prompt


class ApplyCaptureLLM(MockLLMClient):
    def __init__(self):
        super().__init__()
        self.messages = None

    async def chat(self, messages, temperature=None, max_tokens=None, **kwargs):
        self.messages = messages
        return LLMResponse(
            content=(
                "--- FILE: main.py ---\n"
                "print('fixed')\n"
                "--- END FILE ---"
            )
        )


class ExtraFileRepairLLM(MockLLMClient):
    async def chat(self, messages, temperature=None, max_tokens=None, **kwargs):
        return LLMResponse(
            content=(
                "--- FILE: main.py ---\n"
                "print('fixed')\n"
                "--- END FILE ---\n"
                "--- FILE: extra.py ---\n"
                "print('extra')\n"
                "--- END FILE ---"
            )
        )


class NestedFileRepairLLM(MockLLMClient):
    async def chat(self, messages, temperature=None, max_tokens=None, **kwargs):
        return LLMResponse(
            content=(
                "--- FILE: src/main.py ---\n"
                "print('fixed')\n"
                "--- END FILE ---\n"
                "--- FILE: extra.py ---\n"
                "print('extra')\n"
                "--- END FILE ---"
            )
        )


class ExtraMetadataRepairLLM(MockLLMClient):
    async def chat(self, messages, temperature=None, max_tokens=None, **kwargs):
        return LLMResponse(
            content=(
                "--- FILE: main.py ---\n"
                "print('fixed')\n"
                "--- END FILE ---\n"
                "--- BUILD SCRIPT: run ---\n"
                "python alternate.py\n"
                "--- END BUILD ---"
            )
        )


@pytest.mark.asyncio
async def test_apply_repair_prompts_with_compact_behavior_contracts(tmp_path):
    llm = ApplyCaptureLLM()
    contracts = [
        BehaviorContract(test_name=f"case_{index}", args=[str(index)], stdout="x" * 200)
        for index in range(20)
    ]
    contracts.append(
        BehaviorContract(test_name="no_args", args=[], stderr="usage\n", exit_code=2)
    )

    await RepairLoop(llm).apply_repair(
        RepairStrategy(
            strategy_type="fix_algorithm",
            description="repair query behavior",
            target_files=["main.py"],
        ),
        Codebase(root_path=tmp_path, language="python", files={"main.py": "print('x')"}),
        ProgramSpec(summary="cli tool", behavior_contracts=contracts),
    )

    prompt = llm.messages[-1].content
    assert "Exact behavior contracts" in prompt
    assert "no_args" in prompt
    assert "case_19" not in prompt
    assert len(prompt) < 6000


@pytest.mark.asyncio
async def test_apply_repair_sorts_target_file_context_in_prompt(tmp_path):
    llm = ApplyCaptureLLM()

    await RepairLoop(llm).apply_repair(
        RepairStrategy(
            strategy_type="fix_algorithm",
            description="repair query behavior",
            target_files=["z.py", "a.py"],
        ),
        Codebase(
            root_path=tmp_path,
            language="python",
            files={"z.py": "print('z')\n", "a.py": "print('a')\n"},
        ),
        ProgramSpec(summary="cli tool"),
    )

    prompt = llm.messages[-1].content
    assert prompt.index('"a.py"') < prompt.index('"z.py"')


@pytest.mark.asyncio
async def test_apply_repair_ignores_non_target_files_when_targets_are_specified(tmp_path):
    codebase = Codebase(
        root_path=tmp_path,
        language="python",
        files={"main.py": "print('old')\n", "keep.py": "print('keep')\n"},
    )

    repaired = await RepairLoop(ExtraFileRepairLLM()).apply_repair(
        RepairStrategy(
            strategy_type="fix_algorithm",
            description="repair only main",
            target_files=["main.py"],
        ),
        codebase,
        ProgramSpec(summary="cli tool"),
    )

    assert repaired.files["main.py"] == "print('fixed')"
    assert repaired.files["keep.py"] == "print('keep')\n"
    assert "extra.py" not in repaired.files


@pytest.mark.asyncio
async def test_apply_repair_normalizes_direct_target_files(tmp_path):
    codebase = Codebase(
        root_path=tmp_path,
        language="python",
        files={"main.py": "print('old')\n", "keep.py": "print('keep')\n"},
    )

    repaired = await RepairLoop(ExtraFileRepairLLM()).apply_repair(
        RepairStrategy(
            strategy_type="fix_algorithm",
            description="repair only main",
            target_files=[" main.py "],
        ),
        codebase,
        ProgramSpec(summary="cli tool"),
    )

    assert repaired.files["main.py"] == "print('fixed')"
    assert repaired.files["keep.py"] == "print('keep')\n"
    assert "extra.py" not in repaired.files


@pytest.mark.asyncio
async def test_apply_repair_normalizes_direct_target_file_paths(tmp_path):
    codebase = Codebase(
        root_path=tmp_path,
        language="python",
        files={"src/main.py": "print('old')\n", "keep.py": "print('keep')\n"},
    )

    repaired = await RepairLoop(NestedFileRepairLLM()).apply_repair(
        RepairStrategy(
            strategy_type="fix_algorithm",
            description="repair nested main",
            target_files=["src\\main.py"],
        ),
        codebase,
        ProgramSpec(summary="cli tool"),
    )

    assert repaired.files["src/main.py"] == "print('fixed')"
    assert repaired.files["keep.py"] == "print('keep')\n"
    assert "extra.py" not in repaired.files


@pytest.mark.asyncio
async def test_apply_repair_preserves_build_metadata_when_targets_are_specified(tmp_path):
    codebase = Codebase(
        root_path=tmp_path,
        language="python",
        files={"main.py": "print('old')\n"},
        build_script="python main.py",
        executable_path=tmp_path / "main.py",
    )

    repaired = await RepairLoop(ExtraMetadataRepairLLM()).apply_repair(
        RepairStrategy(
            strategy_type="fix_algorithm",
            description="repair only main",
            target_files=["main.py"],
        ),
        codebase,
        ProgramSpec(summary="cli tool"),
    )

    assert repaired.files["main.py"] == "print('fixed')"
    assert repaired.build_script == "python main.py"
    assert repaired.executable_path == tmp_path / "main.py"
