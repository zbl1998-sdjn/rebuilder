import pytest

from core.data_models import (
    ArchitectureBlueprint,
    BehaviorSample,
    CLISurface,
    FlagSpec,
    ProgramSpec,
    TestCase,
    TestResult,
)
from core.implementer_agent import ImplementerAgent
from core.profiling import infer_task_profile
from core.spec_synthesizer import SpecSynthesizer
from core.prompting.behavior_contracts import task_profile_prompt
from llm_clients.base import BaseLLMClient, LLMResponse
from tests.test_probe_engine import MockLLMClient


def sample(name: str, args: list[str], stdout: str = "", stderr: str = "") -> BehaviorSample:
    return BehaviorSample(
        test_case=TestCase(name=name, args=args),
        observed_result=TestResult(stdout=stdout, stderr=stderr, exit_code=0),
        tags=["profile"],
    )


def test_profile_detects_network_ping_from_docs_help_and_output():
    profile = infer_task_profile(
        documentation="pingu is a ping tool using ICMP packets and host timeout options",
        cli_surface=CLISurface(
            flags=[FlagSpec(name="--count", description="number of packets")],
            positional_args=[],
        ),
        corpus=[sample("basic_ping", ["example.com"], stdout="64 bytes from host: ttl=64 time=1.2 ms")],
    )

    assert profile["primary_domain"] == "network_ping"
    assert "network_ping" in profile["domains"]
    assert any("privileged raw sockets" in hint for hint in profile["implementation_hints"])
    assert profile["strategy_pack"]["domain"] == "network_ping"
    assert any(
        "ping transcript" in step
        for step in profile["strategy_pack"]["implementation_playbook"]
    )
    assert any(
        "placeholder or debug output" in item
        for item in profile["strategy_pack"]["anti_patterns"]
    )


def test_profile_detects_common_data_tool_domains():
    cases = [
        ("xsv csv headers columns delimiter", "csv_table"),
        ("htmlq selects html nodes with CSS selector attributes", "html_selector"),
        ("gron transforms JSON objects and arrays into assignment paths", "json_transform"),
        ("go-mod-outdated reads go list -u -m -json modules and renders outdated dependency table", "go_dependency_report"),
    ]

    for docs, expected in cases:
        profile = infer_task_profile(documentation=docs)
        assert profile["primary_domain"] == expected


class ProfileLLM(BaseLLMClient):
    def __init__(self):
        super().__init__("fake-key", "http://fake", "mock-model")

    async def chat(self, messages, temperature=None, max_tokens=None, **kwargs):
        return LLMResponse(
            content='{"summary":"pingu clone","cli_surface":{},"raw_observations":"ping"}'
        )

    async def chat_stream(self, messages, temperature=None, max_tokens=None, **kwargs):
        yield "mock"


@pytest.mark.asyncio
async def test_synthesizer_attaches_task_profile_metadata():
    spec = await SpecSynthesizer(ProfileLLM()).synthesize(
        corpus=[sample("ping_host", ["localhost"], stdout="packets transmitted")],
        documentation="ping hosts with ICMP packets",
        cli_surface=CLISurface(),
    )

    assert spec.complexity_hints["task_profile"]["primary_domain"] == "network_ping"


def test_task_profile_prompt_exposes_domain_hints():
    spec = ProgramSpec(
        complexity_hints={
            "task_profile": infer_task_profile(documentation="csv table delimiter header")
        }
    )

    prompt = task_profile_prompt(spec)

    assert "Task strategy profile" in prompt
    assert "csv_table" in prompt
    assert "implementation_hints" in prompt
    assert "implementation_playbook" in prompt
    assert "csv.reader" in prompt


def test_csv_profile_exposes_xsv_subcommand_and_sample_guidance():
    spec = ProgramSpec(
        complexity_hints={
            "task_profile": infer_task_profile(
                documentation="xsv csv toolkit with sample command and many subcommand variants"
            )
        }
    )

    implementation_prompt = task_profile_prompt(spec)
    repair_prompt = task_profile_prompt(spec, purpose="repair")

    assert "xsv-like multi-command tools" in implementation_prompt
    assert "documented subcommand variant order" in implementation_prompt
    assert "reservoir sampling" in implementation_prompt
    assert "allowed-variants list" in repair_prompt
    assert "Python random defaults" in repair_prompt


def test_json_transform_profile_exposes_gron_mode_guidance():
    spec = ProgramSpec(
        complexity_hints={
            "task_profile": infer_task_profile(
                documentation="gron transforms JSON objects and arrays into assignment paths"
            )
        }
    )

    implementation_prompt = task_profile_prompt(spec)
    repair_prompt = task_profile_prompt(spec, purpose="repair")

    assert "gron-like tools" in implementation_prompt
    assert "--values modes" in implementation_prompt
    assert "invalid character 'x' looking for beginning of value" in implementation_prompt
    assert "--colorize" in implementation_prompt
    assert "--stream mode" in implementation_prompt
    assert "json = [];" in implementation_prompt
    assert "root initialization only" in implementation_prompt
    assert "never assign integer keys into dict roots" in implementation_prompt
    assert "infer the root container" in implementation_prompt
    assert "--no-sort" in implementation_prompt
    assert "invalid character 'o' in literal null" in implementation_prompt
    assert "1.5e10" in implementation_prompt
    assert "failed to form statements" in implementation_prompt
    assert "assignment RHS values" in repair_prompt
    assert "Python JSONDecodeError" in repair_prompt
    assert "falsey/None value" in repair_prompt
    assert "statement has no value" in repair_prompt
    assert "0m vs 0;22m" in repair_prompt
    assert "json = {};" in repair_prompt
    assert "child-assignment code" in repair_prompt
    assert "no root assignment error" in repair_prompt
    assert "original physical input line" in repair_prompt
    assert "no-sort insertion mode" in repair_prompt
    assert "scientific notation" in repair_prompt
    assert "json[0], json[1]" in repair_prompt
    assert "backslash-escaped single quotes" in repair_prompt


def test_html_selector_profile_exposes_mutation_and_panic_guidance():
    spec = ProgramSpec(
        complexity_hints={
            "task_profile": infer_task_profile(
                documentation="htmlq selects html nodes with CSS selector attributes and remove-nodes"
            )
        }
    )

    implementation_prompt = task_profile_prompt(spec)
    repair_prompt = task_profile_prompt(spec, purpose="repair")

    assert "--remove-nodes" in implementation_prompt
    assert "no-selector invocation" in implementation_prompt
    assert "--filename/--output" in implementation_prompt
    assert "-p/--pretty output" in implementation_prompt
    assert "exit 101" in implementation_prompt
    assert "single quotes around main" in implementation_prompt
    assert "malformed HTML" in repair_prompt
    assert "html/head/body wrappers" in repair_prompt
    assert "empty HTML skeleton" in repair_prompt
    assert "Rust panic text" in repair_prompt
    assert "unknown-flag" in repair_prompt
    assert "code, kind, and message fields" in repair_prompt
    assert "written file contents" in repair_prompt
    assert "newline placement around text nodes" in repair_prompt


def test_go_dependency_profile_exposes_go_flag_and_table_guidance():
    spec = ProgramSpec(
        complexity_hints={
            "task_profile": infer_task_profile(
                documentation=(
                    "go-mod-outdated reads newline-delimited go list -u -m -json module "
                    "records and prints outdated dependency tables"
                )
            )
        }
    )

    implementation_prompt = task_profile_prompt(spec)
    repair_prompt = task_profile_prompt(spec, purpose="repair")

    assert "go_dependency_report" in implementation_prompt
    assert "newline-delimited JSON" in implementation_prompt
    assert "-help prints usage to stderr with exit 0" in implementation_prompt
    assert "centered headers" in implementation_prompt
    assert "markdown style" in implementation_prompt
    assert "literal true" in implementation_prompt
    assert "Go flag package wording" in repair_prompt
    assert "Do not use argparse" in repair_prompt
    assert "odd/even padding" in repair_prompt
    assert "separator dash counts" in repair_prompt
    assert "unexpected EOF" in repair_prompt


def test_archive_profile_exposes_clap_usage_guidance():
    spec = ProgramSpec(
        complexity_hints={
            "task_profile": infer_task_profile(
                documentation="zip-password-finder opens encrypted zip archives with password charset flags"
            )
        }
    )

    implementation_prompt = task_profile_prompt(spec)
    repair_prompt = task_profile_prompt(spec, purpose="repair")

    assert "archive_compression" in implementation_prompt
    assert "Rust/clap-style archive CLIs" in implementation_prompt
    assert "every required flag in the Usage line" in implementation_prompt
    assert "complete clap-style Usage line" in repair_prompt
    assert "Do not use argparse" in repair_prompt


def test_repair_profile_prompt_exposes_repair_playbook():
    spec = ProgramSpec(
        complexity_hints={
            "task_profile": infer_task_profile(
                documentation="pingu sends ICMP ping packets and reports packet loss"
            )
        }
    )

    prompt = task_profile_prompt(spec, purpose="repair")

    assert "repair_hints" in prompt
    assert "repair_playbook" in prompt
    assert "Parsed: host=" in prompt
    assert "µs value rather than 0s" in prompt
    assert "multicast write errors" in prompt
    assert "implementation_playbook" not in prompt


def test_implementer_prompts_include_task_profile():
    spec = ProgramSpec(
        complexity_hints={
            "task_profile": infer_task_profile(documentation="html selector attribute text")
        }
    )

    messages = ImplementerAgent(MockLLMClient())._entrypoint_messages(
        spec,
        blueprint=ArchitectureBlueprint(
            language="python",
            entry_point="main.py",
        ),
    )

    prompt = messages[-1].content
    assert "Task strategy profile" in prompt
    assert "html_selector" in prompt
    assert "HTMLParser" in prompt
