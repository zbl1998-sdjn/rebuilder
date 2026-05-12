import pytest

from core.data_models import BehaviorSample, TestCase, TestResult
from core.differential_tester import DifferentialTester


class OriginalBackend:
    async def run(self, executable, test_case):
        return TestResult(stdout="same", exit_code=0)


class ReplacementBackend:
    async def run(self, executable, test_case):
        return TestResult(stdout="same", exit_code=0)


@pytest.mark.asyncio
async def test_differential_tester_supports_mixed_execution_backends():
    tester = DifferentialTester(
        original="docker-reference",
        replacement="local-replacement",
        original_backend=OriginalBackend(),
        replacement_backend=ReplacementBackend(),
    )

    report = await tester.compare(TestCase(name="case"))

    assert report.is_equivalent


class StatefulReplayBackend:
    def __init__(self):
        self.workdirs = []

    async def run(self, executable, test_case):
        return TestResult(stdout="stateless", exit_code=0)

    async def run_in_workdir(self, executable, test_case, workdir):
        self.workdirs.append(workdir)
        marker = workdir / "state.txt"
        if test_case.args == ["add", "alpha"]:
            marker.write_text("alpha", encoding="utf-8")
            return TestResult(exit_code=0)
        if test_case.args == ["query", "alpha"]:
            value = marker.read_text(encoding="utf-8") if marker.exists() else "missing"
            return TestResult(stdout=value + "\n", exit_code=0 if value != "missing" else 1)
        return TestResult(exit_code=0)


@pytest.mark.asyncio
async def test_differential_tester_replays_stateful_samples_in_shared_workdirs():
    original_backend = StatefulReplayBackend()
    replacement_backend = StatefulReplayBackend()
    samples = [
        BehaviorSample(
            test_case=TestCase(name="add", args=["add", "alpha"]),
            observed_result=TestResult(exit_code=0),
            tags=["stateful", "stateful_plan:demo", "stateful_step:0"],
        ),
        BehaviorSample(
            test_case=TestCase(name="query", args=["query", "alpha"]),
            observed_result=TestResult(stdout="alpha\n", exit_code=0),
            tags=["stateful", "stateful_plan:demo", "stateful_step:1"],
        ),
    ]

    reports = await DifferentialTester(
        original="orig",
        replacement="repl",
        original_backend=original_backend,
        replacement_backend=replacement_backend,
    ).run_full_suite(samples)

    assert [report.is_equivalent for report in reports] == [True, True]
    assert len(set(original_backend.workdirs)) == 1
    assert len(set(replacement_backend.workdirs)) == 1


def test_differential_tester_parses_embedded_test_case_json():
    tester = DifferentialTester(original="orig", replacement="repl")

    raw = """Adversarial ideas:

```json
[{"name":"probe","args":["--help"],"stdin":"","input_files":{},"description":"help"}]
```
"""

    cases = tester._parse_test_cases(raw)

    assert len(cases) == 1
    assert cases[0].name == "probe"
    assert cases[0].args == ["--help"]


class RaisingLLM:
    def system_prompt(self, content):
        return content

    def user_prompt(self, content):
        return content

    async def chat(self, *args, **kwargs):
        raise RuntimeError("transient llm failure")


@pytest.mark.asyncio
async def test_differential_tester_skips_adversarial_generation_on_llm_failure(caplog):
    sample = BehaviorSample(
        test_case=TestCase(name="case"),
        observed_result=TestResult(stdout="same", exit_code=0),
    )
    tester = DifferentialTester(
        original="orig",
        replacement="repl",
        llm_client=RaisingLLM(),
        original_backend=OriginalBackend(),
        replacement_backend=ReplacementBackend(),
    )

    reports = await tester.run_full_suite([sample])

    assert len(reports) == 1
    assert reports[0].is_equivalent
    assert "Skipping adversarial test generation after LLM failure" in caplog.text
