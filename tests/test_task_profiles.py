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
