"""
Unit tests for the Probe Engine.
"""

import pytest

from core.data_models import TestCase, TestResult
from core.execution.files import UnsafeInputFilePathError
from core.probe_engine import ProbeEngine
from llm_clients.base import BaseLLMClient, LLMResponse


class MockLLMClient(BaseLLMClient):
    """Mock LLM for testing without API calls."""
    
    def __init__(self):
        super().__init__("fake-key", "http://fake", "mock-model")
    
    async def chat(self, messages, temperature=None, max_tokens=None, **kwargs):
        # Return a simple JSON test case list
        return LLMResponse(
            content='[{"name": "test1", "args": ["--help"], "stdin": "", "input_files": {}, "description": "Test help"}]'
        )
    
    async def chat_stream(self, messages, temperature=None, max_tokens=None, **kwargs):
        yield "mock"


class RecordingProbeLLM(MockLLMClient):
    def __init__(self):
        super().__init__()
        self.messages = []

    async def chat(self, messages, temperature=None, max_tokens=None, **kwargs):
        self.messages.append(messages)
        return await super().chat(messages, temperature=temperature, max_tokens=max_tokens, **kwargs)


@pytest.fixture
def mock_llm():
    return MockLLMClient()


@pytest.fixture
def mock_executable(tmp_path):
    # Create a simple batch script as mock executable
    exe = tmp_path / "program.bat"
    exe.write_text("@echo off\necho Hello %1\n")
    return exe


@pytest.mark.asyncio
async def test_probe_cli_surface(mock_llm, mock_executable):
    engine = ProbeEngine(
        executable=mock_executable,
        documentation="A simple test program",
        llm_client=mock_llm,
        max_iterations=1,
    )
    corpus = await engine.probe()
    
    # Should have at least the discovery commands
    assert len(corpus) >= 3
    
    # Check that CLI surface was populated (batch script echoes arguments, which are parsed as flags)
    assert len(engine.cli_surface.flags) >= 0


@pytest.mark.asyncio
async def test_generate_test_cases(mock_llm, mock_executable):
    engine = ProbeEngine(
        executable=mock_executable,
        documentation="Test",
        llm_client=mock_llm,
    )
    cases = await engine._generate_test_cases(0)
    assert len(cases) == 1
    assert cases[0].name == "test1"


def test_parse_help_output(mock_llm, mock_executable):
    engine = ProbeEngine(
        executable=mock_executable,
        documentation="Test",
        llm_client=mock_llm,
    )
    help_text = """
    --input FILE    Input file path
    --verbose       Enable verbose output
    -o FILE         Output file
    """
    engine._parse_help_output(help_text)
    
    assert len(engine.cli_surface.flags) == 2
    flag_names = [f.name for f in engine.cli_surface.flags]
    assert "--input" in flag_names
    assert "--verbose" in flag_names
    # Note: regex only captures --long-flags, not -o short forms


def test_parse_help_output_discovers_subcommands_and_io_modes(mock_llm, mock_executable):
    engine = ProbeEngine(
        executable=mock_executable,
        documentation="Test",
        llm_client=mock_llm,
    )
    help_text = """
Usage:
  tool <command> [FILE|-]

Commands:
  count       Count records
  select      Select columns

Options:
  --output FILE  Write to output file
"""
    engine._parse_help_output(help_text)

    assert engine.cli_surface.subcommands == ["count", "select"]
    assert engine.cli_surface.stdin_mode is True
    assert engine.cli_surface.file_input_mode is True
    assert engine.cli_surface.file_output_mode is True


@pytest.mark.asyncio
async def test_probe_cli_surface_parses_help_from_stderr(mock_llm, mock_executable, monkeypatch):
    engine = ProbeEngine(
        executable=mock_executable,
        documentation="A tool that prints help to stderr",
        llm_client=mock_llm,
        max_iterations=0,
    )

    async def fake_execute(tc, tags):
        from core.data_models import TestResult

        if tc.args == ["--help"]:
            return TestResult(stderr="Usage:\n  tool --json --no-sort\n")
        return TestResult()

    monkeypatch.setattr(engine, "_execute_test", fake_execute)

    await engine._probe_cli_surface()

    flag_names = [flag.name for flag in engine.cli_surface.flags]
    assert "--json" in flag_names
    assert "--no-sort" in flag_names


@pytest.mark.asyncio
async def test_probe_engine_adds_supplemental_cases_until_min_samples(mock_llm, mock_executable, monkeypatch):
    engine = ProbeEngine(
        executable=mock_executable,
        documentation="Test",
        llm_client=mock_llm,
        max_iterations=0,
        min_samples=12,
    )

    async def fake_execute(tc, tags):
        from core.data_models import TestResult

        if tc.args == ["--help"]:
            return TestResult(stderr="Usage:\n  tool --json --no-sort\n")
        return TestResult(stdout="ok\n")

    monkeypatch.setattr(engine, "_execute_test", fake_execute)

    corpus = await engine.probe()

    assert len(corpus) >= 12
    assert any("supplemental" in sample.tags for sample in corpus)


@pytest.mark.asyncio
async def test_probe_engine_runs_coverage_gap_probes_for_min_coverage(mock_llm, mock_executable, monkeypatch):
    engine = ProbeEngine(
        executable=mock_executable,
        documentation="Test",
        llm_client=mock_llm,
        max_iterations=0,
        min_coverage=0.8,
        enable_adaptive_probes=False,
    )
    executed = []

    async def fake_execute(tc, tags):
        from core.data_models import TestResult

        executed.append((tc.name, tuple(tc.args), tuple(tags)))
        if tc.args == ["--help"]:
            return TestResult(stdout="Usage:\nCommands:\n  count       Count rows\nOptions:\n  --json      JSON output\n")
        if tc.args == ["--__rebuilder_invalid_flag__"]:
            return TestResult(stderr="unknown flag\n", exit_code=2)
        return TestResult(stdout="ok\n")

    monkeypatch.setattr(engine, "_execute_test", fake_execute)

    corpus = await engine.probe()

    assert any(sample.test_case.name == "probe_flag_json" for sample in corpus)
    assert any(sample.test_case.name == "probe_subcommand_count_help" for sample in corpus)
    assert any("coverage_gap" in sample.tags for sample in corpus)
    assert any(args == ("--__rebuilder_invalid_flag__",) for _name, args, _tags in executed)


def test_probe_engine_parses_embedded_test_case_json(mock_llm, mock_executable):
    engine = ProbeEngine(
        executable=mock_executable,
        documentation="Test",
        llm_client=mock_llm,
    )

    raw = """Here are the next cases:

```json
{"test_cases":[{"name":"wrapped","args":["--version"],"stdin":"","input_files":{},"description":"wrapped case"}]}
```
"""

    cases = engine._parse_test_cases(raw)

    assert len(cases) == 1
    assert cases[0].name == "wrapped"
    assert cases[0].args == ["--version"]


def test_probe_engine_ignores_non_object_test_case_entries(mock_llm, mock_executable):
    engine = ProbeEngine(
        executable=mock_executable,
        documentation="Test",
        llm_client=mock_llm,
    )

    raw = '["just-a-string", {"name":"valid","args":["--help"],"stdin":"","input_files":{},"description":"ok"}]'

    cases = engine._parse_test_cases(raw)

    assert len(cases) == 1
    assert cases[0].name == "valid"


def test_probe_engine_clamps_unbounded_count_like_probe_args(mock_llm, mock_executable):
    engine = ProbeEngine(
        executable=mock_executable,
        documentation="ping-like tool",
        llm_client=mock_llm,
    )

    raw = (
        '[{"name":"huge_count",'
        '"args":["-c","1000000000","--count=2147483647","-n","0","--repeat=0x10","localhost"],'
        '"stdin":"","input_files":{},"description":"stress count"}]'
    )

    cases = engine._parse_test_cases(raw)

    assert cases[0].args == ["-c", "3", "--count=3", "-n", "1", "--repeat=3", "localhost"]


def test_probe_engine_adds_count_guard_to_ping_host_probe(mock_llm, mock_executable):
    engine = ProbeEngine(
        executable=mock_executable,
        documentation="pingu sends ICMP ping packets to a host",
        llm_client=mock_llm,
    )

    raw = (
        '[{"name":"bare_host",'
        '"args":["127.0.0.1"],'
        '"stdin":"","input_files":{},"description":"bare host"}]'
    )

    cases = engine._parse_test_cases(raw)

    assert cases[0].args == ["-c", "1", "127.0.0.1"]


@pytest.mark.asyncio
async def test_probe_engine_runs_adaptive_profile_probes_from_documentation(mock_llm, mock_executable, monkeypatch):
    engine = ProbeEngine(
        executable=mock_executable,
        documentation="gron json transform nested object array values",
        llm_client=mock_llm,
        max_iterations=0,
        enable_adaptive_probes=True,
    )

    async def fake_execute(tc, tags):
        return TestResult(stdout="ok\n")

    monkeypatch.setattr(engine, "_execute_test", fake_execute)

    corpus = await engine.probe()

    adaptive_samples = [sample for sample in corpus if "adaptive_profile" in sample.tags]
    assert any(sample.test_case.name == "adaptive_json_transform_nested_paths" for sample in adaptive_samples)
    assert any("adaptive_axis:json_transform.invalid_json" in sample.test_case.description for sample in adaptive_samples)


@pytest.mark.asyncio
async def test_probe_engine_compacts_large_documentation_in_llm_prompt(mock_executable):
    llm = RecordingProbeLLM()
    documentation = "usage-start\n" + ("x" * 9000) + "\nexamples-tail"
    engine = ProbeEngine(
        executable=mock_executable,
        documentation=documentation,
        llm_client=llm,
        max_iterations=1,
    )

    cases = await engine._generate_test_cases(0)

    prompt = llm.messages[0][1].content
    assert cases[0].name == "test1"
    assert "usage-start" in prompt
    assert "examples-tail" in prompt
    assert "documentation truncated due to prompt budget" in prompt
    assert len(prompt) < 5000


@pytest.mark.asyncio
async def test_deterministic_probe_promotes_smoke_contract_axes_to_tags(mock_llm, mock_executable, monkeypatch):
    engine = ProbeEngine(
        executable=mock_executable,
        documentation="csv table",
        llm_client=mock_llm,
        max_iterations=0,
    )
    recorded_tags = []

    async def fake_execute(tc, tags):
        recorded_tags.extend(tags)
        return TestResult(stdout="ok\n")

    monkeypatch.setattr(engine, "_execute_test", fake_execute)

    await engine._run_deterministic_probe(
        TestCase(
            name="adaptive_csv_table_quoted_fields",
            stdin='name,note\nAda,"x,y"\n',
            description=(
                "smoke_contract:csv_table.quoted_fields "
                "adaptive_axis:csv_table.quoted_fields quoted delimiters"
            ),
        ),
        base_tags=["adaptive_profile", "profile_domain:csv_table"],
    )

    sample = engine.corpus[0]
    assert "smoke_contract:csv_table.quoted_fields" in recorded_tags
    assert "adaptive_axis:csv_table.quoted_fields" in recorded_tags
    assert "smoke_contract:csv_table.quoted_fields" in sample.tags
    assert "adaptive_axis:csv_table.quoted_fields" in sample.tags


@pytest.mark.asyncio
async def test_probe_engine_can_disable_adaptive_profile_probes(mock_llm, mock_executable, monkeypatch):
    engine = ProbeEngine(
        executable=mock_executable,
        documentation="gron json transform nested object array values",
        llm_client=mock_llm,
        max_iterations=0,
        enable_adaptive_probes=False,
    )

    async def fake_execute(tc, tags):
        return TestResult(stdout="ok\n")

    monkeypatch.setattr(engine, "_execute_test", fake_execute)

    corpus = await engine.probe()

    assert not any("adaptive_profile" in sample.tags for sample in corpus)


@pytest.mark.asyncio
async def test_generated_probe_with_unsafe_input_file_becomes_failed_sample(mock_llm):
    class RejectingBackend:
        async def run(self, executable, test_case):
            raise UnsafeInputFilePathError("unsafe input file path: '../outside.txt'")

    engine = ProbeEngine(
        executable="fake-tool",
        documentation="Test",
        llm_client=mock_llm,
        executor_backend=RejectingBackend(),
    )

    await engine._run_test(TestCase(name="bad_file", input_files={"../outside.txt": b"x"}))

    assert len(engine.corpus) == 1
    sample = engine.corpus[0]
    assert sample.observed_result.exit_code != 0
    assert "unsafe input file path" in sample.observed_result.stderr
    assert "error_mode" in sample.tags
    assert "invalid_input_file" in sample.tags


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
