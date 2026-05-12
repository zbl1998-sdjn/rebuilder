import json

import pytest

from core.data_models import BehaviorSample, CLISurface, TestCase, TestResult
from core.spec_synthesizer import SpecSynthesizer
from llm_clients.base import BaseLLMClient, LLMResponse
from tests.test_probe_engine import MockLLMClient


def test_parse_spec_normalizes_common_llm_schema_variants():
    raw = json.dumps(
        {
            "summary": "tool",
            "cli_surface": {
                "flags": [
                    {"name": "--unique", "default_value": False},
                ],
                "positional_args": [
                    {"name": "input_file", "type_hint": "path"},
                ],
                "exit_codes": [
                    {"code": 0, "meaning": "Success"},
                    {"code": 2, "meaning": "Empty input"},
                ],
            },
            "invariants": [
                {"description": "deterministic", "type": "deterministic", "confidence": 0.9}
            ],
            "raw_observations": {"line_endings": "normalized"},
            "edge_cases": [{"condition": "empty stdin", "behavior": "exit 2"}],
        }
    )

    spec = SpecSynthesizer(MockLLMClient())._parse_spec(raw)

    assert spec.cli_surface.flags[0].default_value == "False"
    assert spec.cli_surface.positional_args[0].position == 0
    assert spec.cli_surface.exit_codes == [0, 2]
    assert spec.invariants[0].invariant_type == "deterministic"
    assert "line_endings" in spec.raw_observations
    assert "empty stdin" in spec.edge_cases[0]


def test_parse_spec_extracts_json_from_markdown_preamble():
    raw = """Here is the conservative specification:

```json
{
  "summary": "directory jumper",
  "input_formats": ["cli"],
  "output_formats": ["text"],
  "cli_surface": {
    "subcommands": ["query"],
    "exit_codes": {"0": "success", "1": "not found"}
  },
  "edge_cases": [],
  "stateful": true,
  "invariants": [],
  "complexity_hints": {},
  "raw_observations": "observed help and query behavior"
}
```
"""

    spec = SpecSynthesizer(MockLLMClient())._parse_spec(raw)

    assert spec.summary == "directory jumper"
    assert spec.cli_surface.subcommands == ["query"]
    assert spec.cli_surface.exit_codes == [0, 1]


def test_parse_spec_normalizes_nested_cli_surface_from_glm():
    raw = json.dumps(
        {
            "summary": "zoxide clone",
            "cli_surface": {
                "subcommands": {
                    "add": {
                        "flags": [
                            {
                                "name": "score",
                                "short": "-s",
                                "long": "--score",
                                "type": "number",
                            }
                        ],
                        "positional_args": [
                            {"name": "PATHS", "required": True, "variadic": True}
                        ],
                        "exit_codes": {"0": "Success", "2": "Usage error"},
                    },
                    "query": {
                        "flags": [
                            {
                                "name": "interactive",
                                "short": "-i",
                                "long": "--interactive",
                            }
                        ],
                        "exit_codes": {"1": "No match"},
                    },
                },
                "global_flags": [
                    {"name": "help", "short": "-h", "long": "--help"},
                ],
                "stdin_mode": False,
            },
            "invariants": [],
        }
    )

    spec = SpecSynthesizer(MockLLMClient())._parse_spec(raw)

    assert spec.summary == "zoxide clone"
    assert spec.cli_surface.subcommands == ["add", "query"]
    assert [flag.name for flag in spec.cli_surface.flags] == [
        "--help",
        "--score",
        "--interactive",
    ]
    assert spec.cli_surface.flags[1].short_form == "-s"
    assert spec.cli_surface.flags[1].type_hint == "number"
    assert spec.cli_surface.positional_args[0].name == "PATHS"
    assert spec.cli_surface.exit_codes == [0, 1, 2]


def test_synthesizer_preserves_shell_init_full_stdout_contract():
    stdout = "function __zoxide_z() {}\n" + ("x" * 5000) + "\n# tail-marker\n"
    corpus = [
        BehaviorSample(
            test_case=TestCase(name="shell_init_bash", args=["init", "bash"]),
            observed_result=TestResult(stdout=stdout, exit_code=0),
            tags=["shell_init", "full_output", "shell:bash"],
        )
    ]

    synthesizer = SpecSynthesizer(MockLLMClient())
    contracts = synthesizer._contracts_from_corpus(corpus)
    formatted = synthesizer._format_corpus(corpus)

    assert contracts[0].stdout == stdout
    assert "# tail-marker" in formatted


def test_synthesizer_adds_output_file_content_previews_to_contracts():
    corpus = [
        BehaviorSample(
            test_case=TestCase(
                name="file_io_input_output_flags",
                args=["--input", "input.txt", "--output", "out.txt"],
                input_files={"input.txt": b"alpha\n"},
            ),
            observed_result=TestResult(
                exit_code=0,
                output_files={"out.txt": b"result: alpha\n"},
            ),
            tags=["file_io", "side_effect"],
        )
    ]

    contracts = SpecSynthesizer(MockLLMClient())._contracts_from_corpus(corpus)

    assert contracts[0].output_files == ["out.txt"]
    assert contracts[0].output_file_previews == {"out.txt": "result: alpha\n"}


class SpecLLM(BaseLLMClient):
    def __init__(self):
        super().__init__("fake-key", "http://fake", "mock-model")

    async def chat(self, messages, temperature=None, max_tokens=None, **kwargs):
        return LLMResponse(
            content=json.dumps(
                {
                    "summary": "tool",
                    "cli_surface": {},
                    "raw_observations": "summary",
                }
            )
        )

    async def chat_stream(self, messages, temperature=None, max_tokens=None, **kwargs):
        yield "mock"


class RepairingSpecLLM(BaseLLMClient):
    def __init__(self):
        super().__init__("fake-key", "http://fake", "mock-model")
        self.calls = 0

    async def chat(self, messages, temperature=None, max_tokens=None, **kwargs):
        self.calls += 1
        if self.calls == 1:
            return LLMResponse(
                content='{"summary":"tool","cli_surface":{"flags":[{"name":"--help",}]},"raw_observations":"draft"}'
            )
        return LLMResponse(
            content=json.dumps(
                {
                    "summary": "tool",
                    "cli_surface": {"flags": [{"name": "--help"}]},
                    "raw_observations": "draft",
                }
            )
        )

    async def chat_stream(self, messages, temperature=None, max_tokens=None, **kwargs):
        yield "mock"


class AlwaysInvalidSpecLLM(BaseLLMClient):
    def __init__(self):
        super().__init__("fake-key", "http://fake", "mock-model")
        self.calls = 0

    async def chat(self, messages, temperature=None, max_tokens=None, **kwargs):
        self.calls += 1
        return LLMResponse(content='{"summary":"broken","cli_surface":{"flags":[{"name":"--help",}]}}')

    async def chat_stream(self, messages, temperature=None, max_tokens=None, **kwargs):
        yield "mock"


@pytest.mark.asyncio
async def test_synthesizer_preserves_exact_behavior_contracts_from_corpus():
    corpus = [
        BehaviorSample(
            test_case=TestCase(name="help_long", args=["--help"]),
            observed_result=TestResult(
                stdout="exact help\n",
                stderr="",
                exit_code=0,
            ),
            tags=["cli_discovery"],
        ),
        BehaviorSample(
            test_case=TestCase(name="no_args", args=[]),
            observed_result=TestResult(
                stdout="",
                stderr="exact error\n",
                exit_code=2,
            ),
            tags=["cli_discovery"],
        ),
    ]

    spec = await SpecSynthesizer(SpecLLM()).synthesize(
        corpus=corpus,
        documentation="docs",
        cli_surface=CLISurface(),
    )

    assert [contract.test_name for contract in spec.behavior_contracts] == [
        "help_long",
        "no_args",
    ]
    assert spec.behavior_contracts[0].args == ["--help"]
    assert spec.behavior_contracts[0].stdout == "exact help\n"
    assert spec.behavior_contracts[1].stderr == "exact error\n"
    assert spec.behavior_contracts[1].exit_code == 2


@pytest.mark.asyncio
async def test_synthesizer_retries_when_initial_spec_is_invalid_json():
    corpus = [
        BehaviorSample(
            test_case=TestCase(name="help_long", args=["--help"]),
            observed_result=TestResult(stdout="help\n", exit_code=0),
            tags=["cli_discovery"],
        )
    ]
    llm = RepairingSpecLLM()

    spec = await SpecSynthesizer(llm).synthesize(
        corpus=corpus,
        documentation="docs",
        cli_surface=CLISurface(),
    )

    assert llm.calls == 2
    assert spec.summary == "tool"
    assert spec.cli_surface.flags[0].name == "--help"


@pytest.mark.asyncio
async def test_synthesizer_falls_back_to_docs_and_cli_surface_when_repair_fails():
    corpus = [
        BehaviorSample(
            test_case=TestCase(name="no_args", description="Run without arguments"),
            observed_result=TestResult(stderr="usage\n", exit_code=2),
            tags=["cli_discovery", "error_mode"],
        )
    ]
    cli_surface = CLISurface(exit_codes=[0, 2])
    llm = AlwaysInvalidSpecLLM()

    spec = await SpecSynthesizer(llm).synthesize(
        corpus=corpus,
        documentation="Loop command runner\nUsage: tool [args]",
        cli_surface=cli_surface,
    )

    assert llm.calls == 2
    assert spec.summary == "Loop command runner"
    assert spec.cli_surface.exit_codes == [0, 2]
    assert spec.edge_cases == ["Run without arguments: exit=2"]
    assert "Structured spec parsing failed" in spec.raw_observations
