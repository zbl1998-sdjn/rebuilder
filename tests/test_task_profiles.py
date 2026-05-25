import pytest

from core.data_models import (
    ArchitectureBlueprint,
    BehaviorSample,
    CLISurface,
    FlagSpec,
    ProgramSpec,
    TaskProfile,
    TestCase,
    TestResult,
)
from core.implementer_agent import ImplementerAgent
from core.profiling import infer_task_profile
from core.spec_synthesizer import SpecSynthesizer
from core.prompting.behavior_contracts import task_profile_prompt
from llm_clients.base import BaseLLMClient, LLMResponse
from tests.test_probe_engine import MockLLMClient


def test_profile_rules_load_all_yaml_files():
    from core.profiling.task_profile import _load_profile_rules

    _load_profile_rules.cache_clear()
    rules = _load_profile_rules()

    assert any(rule.domain == "terminal_animation" for rule in rules)
    assert all(rule.domain for rule in rules)


def test_profile_rules_define_generalization_playbook_for_every_domain():
    from core.profiling.task_profile import _load_profile_rules

    _load_profile_rules.cache_clear()
    rules = _load_profile_rules()

    assert rules
    assert all(rule.generalization_playbook for rule in rules)
    assert all(
        any("holdout" in step.lower() or "unseen" in step.lower() for step in rule.generalization_playbook)
        for rule in rules
    )


def test_profile_rules_define_validation_playbook_for_every_domain():
    from core.profiling.task_profile import _load_profile_rules

    _load_profile_rules.cache_clear()
    rules = _load_profile_rules()

    assert rules
    assert all(rule.validation_playbook for rule in rules)
    assert all(
        any(
            keyword in step.lower()
            for step in rule.validation_playbook
            for keyword in ("smoke", "holdout", "validate", "compare", "assert")
        )
        for rule in rules
    )


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
        "address-category state machine" in step
        for step in profile["strategy_pack"]["implementation_playbook"]
    )
    assert any(
        "Go/net-style resolver wording" in step
        for step in profile["strategy_pack"]["implementation_playbook"]
    )
    assert any(
        "dot-art prefix" in step
        for step in profile["strategy_pack"]["implementation_playbook"]
    )
    assert any(
        "-c, --count" in step
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
        ("hexyl is a command-line hex viewer for binary bytes with color-scheme panels", "binary_hexdump"),
        ("sd is an intuitive find & replace CLI with regex capture groups and fixed-strings mode", "find_replace"),
    ]

    for docs, expected in cases:
        profile = infer_task_profile(documentation=docs)
        assert profile["primary_domain"] == expected


def test_profile_detects_syntax_highlighter_from_chroma_docs():
    profile = infer_task_profile(
        documentation=(
            "Chroma is a syntax highlighter for source code. It selects lexers, "
            "formatter aliases like terminal16m and tokens, and can emit html-only "
            "line-numbered output with html-styles CSS."
        )
    )

    assert profile["primary_domain"] == "syntax_highlighter"
    assert "syntax_highlighter" in profile["domains"]
    assert profile["strategy_pack"]["domain"] == "syntax_highlighter"
    assert any("formatter aliases" in step for step in profile["strategy_pack"]["implementation_playbook"])
    assert any("moderately large files" in step for step in profile["strategy_pack"]["validation_playbook"])


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
    assert spec.task_profile is not None
    assert spec.task_profile.primary_domain == "network_ping"


def test_synthesizer_keeps_legacy_profile_when_typed_validation_fails():
    spec = ProgramSpec(
        complexity_hints={
            "task_profile": {
                "primary_domain": "legacy_domain",
                "strategy_pack": ["not", "a", "dict"],
            }
        }
    )

    SpecSynthesizer(ProfileLLM())._attach_task_profile(
        spec,
        documentation="ping hosts with ICMP packets",
        cli_surface=CLISurface(),
        corpus=[],
    )

    assert spec.task_profile is None
    assert spec.complexity_hints["task_profile"]["primary_domain"] == "legacy_domain"
    assert spec.complexity_hints["task_profile"]["strategy_pack"] == ["not", "a", "dict"]


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
    assert "validation_playbook" in prompt
    assert "generalization_playbook" in prompt
    assert "csv.reader" in prompt


def test_typed_task_profile_preserves_generalization_playbook():
    profile = TaskProfile.model_validate(
        infer_task_profile(documentation="htmlq CSS selector attribute text")
    )

    assert profile.strategy_pack.generalization_playbook
    assert any("unseen" in step.lower() or "holdout" in step.lower() for step in profile.strategy_pack.generalization_playbook)


def test_typed_task_profile_preserves_validation_playbook():
    profile = TaskProfile.model_validate(
        infer_task_profile(documentation="htmlq CSS selector attribute text")
    )

    assert profile.strategy_pack.validation_playbook
    assert any("smoke" in step.lower() or "validate" in step.lower() for step in profile.strategy_pack.validation_playbook)


def test_task_profile_prompt_prefers_typed_profile_over_legacy_profile():
    typed = TaskProfile.model_validate(
        infer_task_profile(documentation="html selector attribute text")
    )
    spec = ProgramSpec(
        task_profile=typed,
        complexity_hints={
            "task_profile": infer_task_profile(documentation="csv table delimiter header")
        },
    )

    prompt = task_profile_prompt(spec)

    assert "html_selector" in prompt
    assert "HTMLParser" in prompt
    assert "csv_table" not in prompt


def test_task_profile_prompt_falls_back_to_legacy_profile():
    spec = ProgramSpec(
        complexity_hints={
            "task_profile": infer_task_profile(documentation="csv table delimiter header")
        }
    )

    prompt = task_profile_prompt(spec)

    assert "csv_table" in prompt
    assert "csv.reader" in prompt


def test_task_profile_prompt_caps_large_profiles():
    profile = TaskProfile(
        primary_domain="csv_table",
        domains=[f"domain_{index}" for index in range(20)],
        input_format_hints=[
            f"input hint {index} " + ("x" * 300) for index in range(20)
        ],
        implementation_hints=[
            f"implementation hint {index} " + ("y" * 300) for index in range(20)
        ],
        strategy_pack={
            "domain": "csv_table",
            "implementation_playbook": [
                f"playbook item {index} " + ("z" * 300) for index in range(20)
            ],
            "anti_patterns": [
                f"anti pattern {index} " + ("q" * 300) for index in range(20)
            ],
        },
        evidence_keywords=[f"keyword_{index}" for index in range(20)],
    )

    prompt = task_profile_prompt(ProgramSpec(task_profile=profile))

    assert "implementation hint 0" in prompt
    assert "playbook item 0" in prompt
    assert "implementation hint 19" not in prompt
    assert "playbook item 19" not in prompt
    assert "__truncated__" in prompt
    assert len(prompt) < 5000


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
    assert "index file" in implementation_prompt
    assert "documented positional arity" in implementation_prompt
    assert "tie stability" in implementation_prompt
    assert "exact observed tie stability" in implementation_prompt
    assert "first-seen" in implementation_prompt
    assert "alphabetical" in implementation_prompt
    assert "reservoir sampling" in implementation_prompt
    assert "allowed-variants list" in repair_prompt
    assert "generated sidecar file names" in repair_prompt
    assert "usage arity" in repair_prompt
    assert "tie handling" in repair_prompt
    assert "global tie-order rule" in repair_prompt
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
    assert "--json mode" in implementation_prompt
    assert "[path_tokens, value]" in implementation_prompt
    assert "root initialization only" in implementation_prompt
    assert "never assign integer keys into dict roots" in implementation_prompt
    assert "padding missing array positions" in implementation_prompt
    assert "infer the root container" in implementation_prompt
    assert "--no-sort" in implementation_prompt
    assert "invalid character 'o' in literal null" in implementation_prompt
    assert "1.5e10" in implementation_prompt
    assert "failed to form statements" in implementation_prompt
    assert "assignment RHS values" in repair_prompt
    assert "Python JSONDecodeError" in repair_prompt
    assert "falsey/None value" in repair_prompt
    assert "statement has no value" in repair_prompt
    assert "--json --ungron failures" in repair_prompt
    assert "sparse-index rules" in repair_prompt
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
    assert "-t/--text" in implementation_prompt
    assert "-w/--ignore-whitespace" in implementation_prompt
    assert "-a/--attribute" in implementation_prompt
    assert "-B/--detect-base" in implementation_prompt
    assert "no-selector invocation" in implementation_prompt
    assert "--filename/--output" in implementation_prompt
    assert "-p/--pretty output" in implementation_prompt
    assert "exit 101" in implementation_prompt
    assert "single quotes around main" in implementation_prompt
    assert "fragment input with no selector" in implementation_prompt
    assert "malformed HTML" in repair_prompt
    assert "html/head/body wrappers" in repair_prompt
    assert "empty HTML skeleton" in repair_prompt
    assert "Rust panic text" in repair_prompt
    assert "unknown-flag" in repair_prompt
    assert "positional argument" in repair_prompt
    assert "selector parse panic" in repair_prompt
    assert "no-selector fragment failures" in repair_prompt
    assert "href/src base URL resolution" in repair_prompt
    assert "code, kind, and message fields" in repair_prompt
    assert "written file contents" in repair_prompt
    assert "newline placement around text nodes" in repair_prompt


def test_syntax_highlighter_profile_exposes_formatter_and_timeout_guidance():
    spec = ProgramSpec(
        complexity_hints={
            "task_profile": infer_task_profile(
                documentation=(
                    "Chroma syntax highlighter with lexer selection, formatter aliases, "
                    "terminal16m, tokens, html-only, html-lines, html-styles, and SVG output."
                )
            )
        }
    )

    implementation_prompt = task_profile_prompt(spec)
    repair_prompt = task_profile_prompt(spec, purpose="repair")

    assert "syntax_highlighter" in implementation_prompt
    assert "formatter aliases" in implementation_prompt
    assert "filename-based lexer inference" in implementation_prompt
    assert "html-only" in implementation_prompt
    assert "line tables" in implementation_prompt
    assert "Escape source HTML" in implementation_prompt
    assert "Bound rendering loops" in implementation_prompt
    assert "timeout or runaway output" in repair_prompt
    assert "style-file paths" in repair_prompt
    assert "invalid formatter" in repair_prompt


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
    assert "--passwordDictionary" in implementation_prompt
    assert "--minPasswordLen" in implementation_prompt
    assert "complete clap-style Usage line" in repair_prompt
    assert "provided flags" in repair_prompt
    assert "starting-password resume behavior" in repair_prompt
    assert "Do not use argparse" in repair_prompt


def test_find_replace_profile_exposes_replacement_guidance():
    spec = ProgramSpec(
        complexity_hints={
            "task_profile": infer_task_profile(
                documentation=(
                    "sd is an intuitive find & replace CLI. It supports regexp "
                    "capture groups, replacement strings, fixed-strings, and file inputs."
                )
            )
        }
    )

    implementation_prompt = task_profile_prompt(spec)
    repair_prompt = task_profile_prompt(spec, purpose="repair")

    assert "find_replace" in implementation_prompt
    assert "$1, $name, ${name}, and $$" in implementation_prompt
    assert "$$bar should become literal $bar" in implementation_prompt
    assert "$$1 is literal $1" in implementation_prompt
    assert "$1$2 joins the two captures" in implementation_prompt
    assert "preserve unknown names literally" in implementation_prompt
    assert "unsupported look-around" in implementation_prompt
    assert "fixed-string mode" in implementation_prompt
    assert "preview mode" in implementation_prompt
    assert "error: invalid path: <path>" in implementation_prompt
    assert "Rust/clap-style CLIs" in implementation_prompt
    assert "capture expansion" in repair_prompt
    assert "$$prefix text" in repair_prompt
    assert "numbered captures disappear" in repair_prompt
    assert "Python re semantics" in repair_prompt
    assert "file-input cases" in repair_prompt
    assert "preview cases" in repair_prompt
    assert "invalid-path wording" in repair_prompt
    assert "Do not use argparse" in repair_prompt


def test_find_replace_profile_ignores_incidental_benchmark_terms():
    profile = infer_task_profile(
        documentation=(
            "sd is an intuitive find & replace CLI with regex capture groups, "
            "fixed-strings, file inputs, cargo installation notes, and JSON benchmark examples."
        )
    )

    assert profile["primary_domain"] == "find_replace"
    assert profile["domains"] == ["find_replace"]
    assert profile["strategy_pack"]["domain"] == "find_replace"


def test_binary_hexdump_profile_exposes_hexyl_guidance():
    spec = ProgramSpec(
        complexity_hints={
            "task_profile": infer_task_profile(
                documentation=(
                    "hexyl is a command-line hex viewer for binary bytes with "
                    "block-size panels color-scheme border and character table options"
                )
            )
        }
    )

    implementation_prompt = task_profile_prompt(spec)
    repair_prompt = task_profile_prompt(spec, purpose="repair")

    assert "binary_hexdump" in implementation_prompt
    assert "Treat input as bytes" in implementation_prompt
    assert "empty stdin" in implementation_prompt
    assert "no-content table" in implementation_prompt
    assert "observed help text as an output contract" in implementation_prompt
    assert "long help" in implementation_prompt
    assert "--color-scheme <FORMAT>" in implementation_prompt
    assert "invalid --color-scheme" in implementation_prompt
    assert "byte rows" in repair_prompt
    assert "argparse usage" in repair_prompt
    assert "help_long" in repair_prompt
    assert "non-UTF-8 bytes" in repair_prompt


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
    assert "zero-transmitted statistics block" in prompt
    assert "do not truncate packet statistics after =>" in prompt
    assert "special address failures" in prompt
    assert "multicast, broadcast, and link-local" in prompt
    assert "Go/net-style resolver wording" in prompt
    assert "socket.gaierror" in prompt
    assert "dot-art prefix" in prompt
    assert "-c, --count" in prompt
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
