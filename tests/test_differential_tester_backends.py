import asyncio

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


class ExecutionErrorBackend:
    async def run(self, executable, test_case):
        return TestResult(stderr="[WinError 5] Access is denied.", exit_code=-1)


@pytest.mark.asyncio
async def test_infrastructure_execution_errors_are_not_behavioral_equivalence():
    tester = DifferentialTester(
        original="orig",
        replacement="repl",
        original_backend=ExecutionErrorBackend(),
        replacement_backend=ExecutionErrorBackend(),
    )

    report = await tester.compare(TestCase(name="permission_denied"))

    assert not report.is_equivalent


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


def test_differential_tester_parses_json_safe_bytes_input_files():
    tester = DifferentialTester(original="orig", replacement="repl")

    raw = """
[{
  "name": "binary_fixture",
  "args": ["sample.bin"],
  "input_files": {
    "sample.bin": {"__type__": "bytes", "base64": "AP8B"}
  }
}]
"""

    cases = tester._parse_test_cases(raw)

    assert len(cases) == 1
    assert cases[0].input_files == {"sample.bin": b"\x00\xff\x01"}


def test_differential_tester_filters_unmaterializable_directory_input_files():
    tester = DifferentialTester(original="orig", replacement="repl")

    raw = """
[{
  "name": "mixed_fixture",
  "input_files": {
    "CHANGELOG.previous.md": {"__type__": "directory"},
    "keep.txt": "alpha\\n"
  }
}]
"""

    cases = tester._parse_test_cases(raw)

    assert len(cases) == 1
    assert cases[0].input_files == {"keep.txt": b"alpha\n"}


def test_differential_tester_allows_tiny_go_log_timestamp_drift():
    tester = DifferentialTester(original="orig", replacement="repl")

    assert tester._streams_equivalent(
        "2026/05/19 20:52:12 invalid character '\\x00' looking for beginning of value\n",
        "2026/05/19 20:52:11 invalid character '\\x00' looking for beginning of value\n",
    )


def test_differential_tester_keeps_go_log_message_strict():
    tester = DifferentialTester(original="orig", replacement="repl")

    assert not tester._streams_equivalent(
        "2026/05/19 20:52:12 invalid character '\\x00' looking for beginning of value\n",
        "2026/05/19 20:52:11 invalid character 'x' looking for beginning of value\n",
    )


def test_differential_tester_allows_elapsed_status_drift():
    tester = DifferentialTester(original="orig", replacement="repl")

    assert tester._streams_equivalent(
        "<a name=\"1.0.0\"></a>\n## 1.0.0  (2026-05-19)\n\nchangelog written. (took 4 ms)\n",
        "<a name=\"1.0.0\"></a>\n## 1.0.0  (2026-05-19)\n\nchangelog written. (took 11 ms)\n",
    )


def test_differential_tester_keeps_elapsed_status_text_strict():
    tester = DifferentialTester(original="orig", replacement="repl")

    assert not tester._streams_equivalent(
        "changelog written. (took 4 ms)\n",
        "changelog saved. (took 4 ms)\n",
    )


def test_differential_tester_allows_text_file_line_ending_drift():
    tester = DifferentialTester(original="orig", replacement="repl")

    assert tester._files_equivalent(
        {"CHANGELOG.md": b"<a name=\"1.0.0\"></a>\n\n"},
        {"CHANGELOG.md": b"<a name=\"1.0.0\"></a>\r\n\r\n"},
    )


def test_differential_tester_keeps_binary_file_outputs_strict():
    tester = DifferentialTester(original="orig", replacement="repl")

    assert not tester._files_equivalent(
        {"out.bin": b"\xff\r\n"},
        {"out.bin": b"\xff\n"},
    )


class RaisingLLM:
    def system_prompt(self, content):
        return content

    def user_prompt(self, content):
        return content

    async def chat(self, *args, **kwargs):
        raise RuntimeError("transient llm failure")


class ConcurrencyProbeBackend:
    """Backend that records in-flight call counts and the order of test cases."""

    def __init__(self, label: str, delay: float = 0.05):
        self.label = label
        self.delay = delay
        self._inflight = 0
        self.peak_inflight = 0
        self.observed_order: list[str] = []
        self._lock = asyncio.Lock()

    async def run(self, executable, test_case):
        async with self._lock:
            self._inflight += 1
            self.peak_inflight = max(self.peak_inflight, self._inflight)
            self.observed_order.append(test_case.name)
        try:
            await asyncio.sleep(self.delay)
            return TestResult(stdout="same", exit_code=0)
        finally:
            async with self._lock:
                self._inflight -= 1


@pytest.mark.asyncio
async def test_run_full_suite_runs_regular_samples_concurrently():
    samples = [
        BehaviorSample(
            test_case=TestCase(name=f"case_{i}"),
            observed_result=TestResult(stdout="same", exit_code=0),
        )
        for i in range(8)
    ]
    original_backend = ConcurrencyProbeBackend("orig")
    replacement_backend = ConcurrencyProbeBackend("repl")

    tester = DifferentialTester(
        original="orig",
        replacement="repl",
        original_backend=original_backend,
        replacement_backend=replacement_backend,
        max_concurrency=4,
    )

    reports = await tester.run_full_suite(samples)

    assert [report.test_case.name for report in reports] == [s.test_case.name for s in samples]
    assert original_backend.peak_inflight > 1
    assert original_backend.peak_inflight <= 4
    assert replacement_backend.peak_inflight > 1


@pytest.mark.asyncio
async def test_run_full_suite_skips_unsafe_input_file_samples(caplog):
    samples = [
        BehaviorSample(
            test_case=TestCase(name="bad_file", input_files={"/tmp/htmlq.html": b"x"}),
            observed_result=TestResult(exit_code=2),
        ),
        BehaviorSample(
            test_case=TestCase(name="valid"),
            observed_result=TestResult(stdout="same", exit_code=0),
        ),
    ]
    original_backend = ConcurrencyProbeBackend("orig", delay=0)
    replacement_backend = ConcurrencyProbeBackend("repl", delay=0)

    reports = await DifferentialTester(
        original="orig",
        replacement="repl",
        original_backend=original_backend,
        replacement_backend=replacement_backend,
    ).run_full_suite(samples)

    assert [report.test_case.name for report in reports] == ["valid"]
    assert original_backend.observed_order == ["valid"]
    assert replacement_backend.observed_order == ["valid"]
    assert "unsafe input file path" in caplog.text


@pytest.mark.asyncio
async def test_run_full_suite_serialises_steps_within_stateful_plan():
    plan_samples = [
        BehaviorSample(
            test_case=TestCase(name=f"step_{i}"),
            observed_result=TestResult(exit_code=0),
            tags=["stateful_plan:demo", f"stateful_step:{i}"],
        )
        for i in range(3)
    ]
    original_backend = StatefulReplayBackend()
    replacement_backend = StatefulReplayBackend()

    reports = await DifferentialTester(
        original="orig",
        replacement="repl",
        original_backend=original_backend,
        replacement_backend=replacement_backend,
        max_concurrency=4,
    ).run_full_suite(plan_samples)

    assert [r.test_case.name for r in reports] == ["step_0", "step_1", "step_2"]
    assert len(set(original_backend.workdirs)) == 1
    assert len(set(replacement_backend.workdirs)) == 1


@pytest.mark.asyncio
async def test_run_full_suite_preserves_output_order_with_mixed_corpus():
    regular = [
        BehaviorSample(
            test_case=TestCase(name=f"reg_{i}"),
            observed_result=TestResult(exit_code=0),
        )
        for i in range(3)
    ]
    stateful = [
        BehaviorSample(
            test_case=TestCase(name=f"st_{i}"),
            observed_result=TestResult(exit_code=0),
            tags=["stateful_plan:p", f"stateful_step:{i}"],
        )
        for i in range(2)
    ]
    original_backend = StatefulReplayBackend()
    replacement_backend = StatefulReplayBackend()

    reports = await DifferentialTester(
        original="orig",
        replacement="repl",
        original_backend=original_backend,
        replacement_backend=replacement_backend,
        max_concurrency=4,
    ).run_full_suite(regular + stateful)

    assert [r.test_case.name for r in reports] == [
        "reg_0",
        "reg_1",
        "reg_2",
        "st_0",
        "st_1",
    ]


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
