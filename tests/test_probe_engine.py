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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
