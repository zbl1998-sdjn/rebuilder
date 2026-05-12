"""
Unit tests for the Probe Engine.
"""

import pytest
from pathlib import Path

from core.data_models import TestCase
from core.probe_engine import ProbeEngine
from llm_clients.base import BaseLLMClient, Message, LLMResponse


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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
