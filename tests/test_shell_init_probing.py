import pytest

from core.data_models import TestResult
from core.probe_engine import ProbeEngine
from core.probing.shell_init import ShellInitProbePlanner
from tests.test_probe_engine import MockLLMClient


DOCS = """
Setup:
eval "$(zoxide init bash)"
eval "$(zoxide init zsh)"
zoxide init fish | source
zoxide init powershell | Out-String
"""


def test_shell_init_probe_planner_extracts_documented_shells():
    probes = ShellInitProbePlanner().plan(DOCS)

    assert [probe.name for probe in probes] == [
        "shell_init_bash",
        "shell_init_zsh",
        "shell_init_fish",
        "shell_init_powershell",
    ]
    assert [probe.args for probe in probes] == [
        ["init", "bash"],
        ["init", "zsh"],
        ["init", "fish"],
        ["init", "powershell"],
    ]


class ShellInitBackend:
    def __init__(self):
        self.calls = []

    async def run(self, executable, test_case):
        self.calls.append(test_case)
        if test_case.args[:1] == ["init"]:
            shell = test_case.args[1]
            return TestResult(stdout=f"{shell}:" + ("x" * 5000), exit_code=0)
        return TestResult(stdout="ok", exit_code=0)


@pytest.mark.asyncio
async def test_probe_engine_records_shell_init_full_output_samples(tmp_path):
    backend = ShellInitBackend()
    engine = ProbeEngine(
        executable="reference",
        documentation=DOCS,
        llm_client=MockLLMClient(),
        max_iterations=0,
        executor_backend=backend,
    )

    await engine._probe_shell_init_outputs()

    shell_samples = [
        sample for sample in engine.corpus if "shell_init" in sample.tags
    ]
    assert len(shell_samples) == 4
    assert shell_samples[0].observed_result.stdout.startswith("bash:")
    assert len(shell_samples[0].observed_result.stdout) > 5000
    assert all("full_output" in sample.tags for sample in shell_samples)
