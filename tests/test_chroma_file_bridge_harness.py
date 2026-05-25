from __future__ import annotations

import contextlib
import io
import importlib.util
import json
import re
import sys
import types
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HARNESS_PATH = ROOT / "output" / "file_bridge_manual" / "run_chroma_file_bridge.py"


def load_harness():
    spec = importlib.util.spec_from_file_location("run_chroma_file_bridge", HARNESS_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_candidate(source: str):
    module = types.ModuleType("chroma_candidate")
    exec(compile(source, "<chroma_candidate>", "exec"), module.__dict__)
    return module


@contextlib.contextmanager
def redirected_stdin(stream: io.StringIO):
    original = sys.stdin
    sys.stdin = stream
    try:
        yield
    finally:
        sys.stdin = original


def test_restore_patch2_generalization_probe_adds_chroma_specific_axes() -> None:
    harness = load_harness()

    probes = harness.probe_response("restore_patch2_generalization_probe")
    probe_names = {probe["name"] for probe in probes}

    assert "trace_python_stdin" in probe_names
    assert "unbuffered_terminal8_stdin" in probe_names
    assert "formatter_tokens_stdin" in probe_names
    assert "html_lines_table_linkable_file" in probe_names
    assert "style_as_missing_file" in probe_names
    assert "lexer_filename_stdin" in probe_names
    assert "multi_file_python_formatter" in probe_names


def test_chroma_task_profile_uses_syntax_highlighter_domain() -> None:
    harness = load_harness()

    hints = harness.SPEC_RESPONSE["complexity_hints"]

    assert hints["primary_domain"] == "syntax_highlighter"
    assert hints["domains"] == ["syntax_highlighter"]


def test_restore_patch2_generalization_probe_reuses_restore_patch2_source() -> None:
    harness = load_harness()

    source = harness.patched_source("restore_patch2_generalization_probe")

    assert "def validate_files(opts):" in source
    assert "expected string value but got" in source


def test_restore_patch3_generalization_probe_repairs_html_line_table_style_file(tmp_path: Path) -> None:
    harness = load_harness()
    module = load_candidate(harness.patched_source("restore_patch3_generalization_probe"))
    source_path = tmp_path / "src.py"
    source_path.write_bytes(b"def add(a, b):\n    return a + b\n")
    stdout = io.StringIO()
    stderr = io.StringIO()

    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        exit_code = module.main(
            [
                "--html",
                "--html-only",
                "--html-lines",
                "--html-lines-table",
                "--html-linkable-lines",
                "--html-highlight",
                "2",
                "--style",
                "github",
                str(source_path),
            ]
        )

    expected = (
        '<div class="chroma">\n'
        '<table class="lntable"><tr><td class="lntd">\n'
        '<pre class="chroma"><span class="lnt" id="L1"><a class="lnlinks" href="#L1">1</a>\n'
        '</span><span class="hl"><span class="lnt" id="L2"><a class="lnlinks" href="#L2">2</a>\n'
        '</span></span></pre></td>\n'
        '<td class="lntd">\n'
        '<pre class="chroma"><code><span class="line"><span class="cl"><span class="k">def</span> '
        '<span class="nf">add</span><span class="p">(</span><span class="n">a</span><span class="p">,</span> '
        '<span class="n">b</span><span class="p">):</span>\n'
        '</span></span><span class="line hl"><span class="cl">    <span class="k">return</span> '
        '<span class="n">a</span> <span class="o">+</span> <span class="n">b</span>\n'
        "</span></span></code></pre></td></tr></table>\n"
        "</div>\n"
    )

    assert exit_code == 0
    assert "open github" not in stderr.getvalue()
    assert stdout.getvalue() == expected


def test_restore_patch3_generalization_probe_repairs_html_lines_without_table(tmp_path: Path) -> None:
    harness = load_harness()
    module = load_candidate(harness.patched_source("restore_patch3_generalization_probe"))
    source_path = tmp_path / "src.py"
    source_path.write_bytes(b"def add(a, b):\n    return a + b\n")
    stdout = io.StringIO()
    stderr = io.StringIO()

    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        exit_code = module.main(
            [
                "--html",
                "--html-only",
                "--html-lines",
                "--html-linkable-lines",
                "--html-highlight",
                "2",
                "--style",
                "github",
                str(source_path),
            ]
        )

    expected = (
        '<pre class="chroma"><code><span class="line"><span class="ln" id="L1">'
        '<a class="lnlinks" href="#L1">1</a></span><span class="cl"><span class="k">def</span> '
        '<span class="nf">add</span><span class="p">(</span><span class="n">a</span><span class="p">,</span> '
        '<span class="n">b</span><span class="p">):</span>\n'
        '</span></span><span class="line hl"><span class="ln" id="L2"><a class="lnlinks" href="#L2">2</a>'
        '</span><span class="cl">    <span class="k">return</span> <span class="n">a</span> '
        '<span class="o">+</span> <span class="n">b</span>\n'
        "</span></span></code></pre>"
    )

    assert exit_code == 0
    assert stderr.getvalue() == ""
    assert stdout.getvalue() == expected


def test_restore_patch3_generalization_probe_repairs_monokai_css_prefix_probe() -> None:
    harness = load_harness()
    module = load_candidate(harness.patched_source("restore_patch3_generalization_probe"))
    stdout = io.StringIO()
    stderr = io.StringIO()

    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        exit_code = module.main(["--html-styles", "--html-prefix", "x-", "--style", "monokai"])

    css = stdout.getvalue()
    assert exit_code == 0
    assert stderr.getvalue() == ""
    assert "/* NameBuiltin */ .chroma .nb" not in css
    assert "/* NameConstant */ .chroma .no { color: #66d9ef }" in css
    assert "/* LiteralStringEscape */ .chroma .se { color: #ae81ff }" in css
    assert "/* CommentSingle */ .chroma .c1 { color: #75715e }" in css
    assert "/* GenericStrong */ .chroma .gs { font-weight: bold }" in css
    assert "-webkit-user-select: none; user-select: none;" in css


def test_restore_patch3_generalization_probe_repairs_github_style_css() -> None:
    harness = load_harness()
    module = load_candidate(harness.patched_source("restore_patch3_generalization_probe"))
    stdout = io.StringIO()
    stderr = io.StringIO()

    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        exit_code = module.main(["--html-styles", "--style", "github"])

    css = stdout.getvalue()
    assert exit_code == 0
    assert stderr.getvalue() == ""
    assert css.startswith("/* Background */ .bg { background-color: #f7f7f7; }\n")
    assert "/* KeywordConstant */ .chroma .kc { color: #cf222e }" in css
    assert "/* NameFunction */ .chroma .nf { color: #6639ba }" in css
    assert "/* TextWhitespace */ .chroma .w { color: #ffffff }\n" in css


def test_restore_patch3_generalization_probe_handles_style_css_edges() -> None:
    harness = load_harness()
    module = load_candidate(harness.patched_source("restore_patch3_generalization_probe"))
    stdout = io.StringIO()
    stderr = io.StringIO()

    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        exit_code = module.main(["--html-all-styles", "--style", "github"])

    assert exit_code == 0
    assert stdout.getvalue() == ""
    assert stderr.getvalue() == ""

    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        exit_code = module.main(["--html-styles", "--style", "swapoff"])

    assert exit_code == 1
    assert stdout.getvalue() == ""
    assert "open swapoff" in stderr.getvalue()


def test_restore_patch3_generalization_probe_repairs_plain_html_python(tmp_path: Path) -> None:
    harness = load_harness()
    module = load_candidate(harness.patched_source("restore_patch3_generalization_probe"))
    source_path = tmp_path / "src.py"
    source_path.write_bytes(b"def add(a, b):\n    return a + b\n")
    stdout = io.StringIO()
    stderr = io.StringIO()

    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        exit_code = module.main(["--html", "--html-only", "--style", "github", str(source_path)])

    assert exit_code == 0
    assert stderr.getvalue() == ""
    assert stdout.getvalue().startswith('<pre class="chroma"><code><span class="line"><span class="cl">')
    assert '<span class="nf">add</span>' in stdout.getvalue()
    assert stdout.getvalue().endswith("</code></pre>")


def test_restore_patch3_generalization_probe_repairs_prevent_surrounding_pre(tmp_path: Path) -> None:
    harness = load_harness()
    module = load_candidate(harness.patched_source("restore_patch3_generalization_probe"))
    source_path = tmp_path / "src.py"
    source_path.write_bytes(b"def add(a, b):\n    return a + b\n")
    stdout = io.StringIO()
    stderr = io.StringIO()

    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        exit_code = module.main(
            ["--html", "--html-only", "--html-prevent-surrounding-pre", "--style", "github", str(source_path)]
        )

    assert exit_code == 0
    assert stderr.getvalue() == ""
    assert "<pre" not in stdout.getvalue()
    assert stdout.getvalue().startswith('<span class="k">def</span> ')
    assert stdout.getvalue().endswith('<span class="n">b</span>\n')


def test_restore_patch3_generalization_probe_rejects_invalid_html_lines_style(tmp_path: Path) -> None:
    harness = load_harness()
    module = load_candidate(harness.patched_source("restore_patch3_generalization_probe"))
    source_path = tmp_path / "src.py"
    source_path.write_bytes(b"def add(a, b):\n")
    stdout = io.StringIO()
    stderr = io.StringIO()

    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        exit_code = module.main(
            [
                "--html",
                "--html-only",
                "--html-lines",
                "--html-lines-style",
                "color:red",
                "--style",
                "github",
                str(source_path),
            ]
        )

    assert exit_code == 1
    assert stdout.getvalue() == ""
    assert 'unknown style element "color:red"' in stderr.getvalue()


def test_restore_patch3_generalization_probe_preserves_missing_style_file_error() -> None:
    harness = load_harness()
    module = load_candidate(harness.patched_source("restore_patch3_generalization_probe"))
    stdout = io.StringIO()
    stderr = io.StringIO()

    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        exit_code = module.main(["--html-styles", "--style", "missing-style.xml"])

    assert exit_code == 1
    assert stdout.getvalue() == ""
    assert "open missing-style.xml" in stderr.getvalue()


def test_restore_patch3_generalization_probe_formats_terminal_stdin() -> None:
    harness = load_harness()
    module = load_candidate(harness.patched_source("restore_patch3_generalization_probe"))
    source = "def greet(name):\n    return name\n"
    stdout = io.StringIO()
    stderr = io.StringIO()

    with (
        contextlib.redirect_stdout(stdout),
        contextlib.redirect_stderr(stderr),
        redirected_stdin(io.StringIO(source)),
    ):
        exit_code = module.main(["--lexer", "python", "--style", "monokai"])

    stripped = re.sub(r"\x1b\[[0-9;]*m", "", stdout.getvalue())
    assert exit_code == 0
    assert stderr.getvalue() == ""
    assert "\x1b[" in stdout.getvalue()
    assert stripped == source


def test_restore_patch3_generalization_probe_json_preserves_source() -> None:
    harness = load_harness()
    module = load_candidate(harness.patched_source("restore_patch3_generalization_probe"))
    source = "def greet(name):\n    print(f'Hello, {name}')\n"
    stdout = io.StringIO()
    stderr = io.StringIO()

    with (
        contextlib.redirect_stdout(stdout),
        contextlib.redirect_stderr(stderr),
        redirected_stdin(io.StringIO(source)),
    ):
        exit_code = module.main(["--lexer", "python", "--style", "monokai", "--json"])

    tokens = json.loads(stdout.getvalue())
    assert exit_code == 0
    assert stderr.getvalue() == ""
    assert {"type": "Keyword", "value": "def"} in tokens
    assert "".join(token["value"] for token in tokens) == source


def test_restore_patch3_generalization_probe_supports_noop_and_tokens(tmp_path: Path) -> None:
    harness = load_harness()
    module = load_candidate(harness.patched_source("restore_patch3_generalization_probe"))
    source_path = tmp_path / "src.py"
    source_path.write_text('print("hello")\n', encoding="utf-8")
    stdout = io.StringIO()
    stderr = io.StringIO()

    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        exit_code = module.main(["--formatter", "noop", "--style", "monokai", str(source_path)])

    assert exit_code == 0
    assert stderr.getvalue() == ""
    assert stdout.getvalue() == 'print("hello")\n'

    stdout = io.StringIO()
    stderr = io.StringIO()
    with (
        contextlib.redirect_stdout(stdout),
        contextlib.redirect_stderr(stderr),
        redirected_stdin(io.StringIO('print("hello")')),
    ):
        exit_code = module.main(["--lexer", "python", "--style", "monokai", "--formatter", "tokens"])

    assert exit_code == 0
    assert stderr.getvalue() == ""
    assert stdout.getvalue() == (
        '&Token{NameBuiltin, "print"}\n'
        '&Token{Punctuation, "("}\n'
        '&Token{LiteralStringDouble, "\\"hello\\""}\n'
        '&Token{Punctuation, ")"}\n'
    )


def test_restore_patch3_generalization_probe_svg_uses_style_colors() -> None:
    harness = load_harness()
    module = load_candidate(harness.patched_source("restore_patch3_generalization_probe"))
    source = 'def hello():\n    return "world"\n'
    stdout = io.StringIO()
    stderr = io.StringIO()

    with (
        contextlib.redirect_stdout(stdout),
        contextlib.redirect_stderr(stderr),
        redirected_stdin(io.StringIO(source)),
    ):
        exit_code = module.main(["--lexer", "python", "--style", "monokai", "--svg"])

    root = ET.fromstring(stdout.getvalue())
    fills = {
        element.attrib["fill"]
        for element in root.iter()
        if element.tag.endswith("tspan") and "fill" in element.attrib
    }
    assert exit_code == 0
    assert stderr.getvalue() == ""
    assert root.tag.endswith("svg")
    assert fills == {"#66d9ef", "#e6db74", "#a6e22e"}


def test_restore_patch3_generalization_probe_fail_check_xml_and_profile(tmp_path: Path) -> None:
    harness = load_harness()
    module = load_candidate(harness.patched_source("restore_patch3_generalization_probe"))
    stdout = io.StringIO()
    stderr = io.StringIO()

    with (
        contextlib.redirect_stdout(stdout),
        contextlib.redirect_stderr(stderr),
        redirected_stdin(io.StringIO("plain text")),
    ):
        exit_code = module.main(["--fail", "--style", "monokai"])

    assert exit_code == 1
    assert stdout.getvalue() == ""
    assert stderr.getvalue() == ""

    valid_path = tmp_path / "valid.go"
    valid_path.write_text("package main\n", encoding="utf-8")
    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        exit_code = module.main(["--check", "--style", "solarized-dark", str(valid_path)])

    assert exit_code == 0
    assert stdout.getvalue() == ""
    assert stderr.getvalue() == ""

    xml_dir = tmp_path / "lexers"
    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        exit_code = module.main(["--xml", str(xml_dir)])

    assert exit_code == 0
    assert len(list(xml_dir.glob("*.xml"))) >= 100
    assert (xml_dir / "python.xml").read_text(encoding="utf-8").startswith("<lexer>\n")

    profile_path = tmp_path / "cpu.prof"
    stdout = io.StringIO()
    stderr = io.StringIO()
    with (
        contextlib.redirect_stdout(stdout),
        contextlib.redirect_stderr(stderr),
        redirected_stdin(io.StringIO("def foo():\n    pass\n")),
    ):
        exit_code = module.main(["--profile", str(profile_path), "--lexer", "python", "--style", "monokai"])

    assert exit_code == 0
    assert profile_path.read_bytes()


def test_config_is_file_bridge_only() -> None:
    harness = load_harness()
    config_path = ROOT / "output" / "file_bridge_manual" / "_test_chroma_config.yaml"
    request_dir = ROOT / "output" / "file_bridge_manual" / "_test_chroma_requests"
    try:
        harness.write_config(config_path, request_dir, "codex-file-bridge-chroma-test")
        config_text = config_path.read_text(encoding="utf-8")
    finally:
        config_path.unlink(missing_ok=True)

    assert 'provider: "file_bridge"' in config_text
    assert "local_openai:" not in config_text
    assert "kimi:" not in config_text
    assert "glm:" not in config_text


def test_official_eval_mode_keeps_file_bridge_harness_active() -> None:
    harness = load_harness()

    command = harness.build_closed_loop_command(
        "restore_patch3_generalization_probe",
        config_path=ROOT / "example.yaml",
        model="codex-file-bridge-chroma-test",
        run_name="file_bridge_no_external_chroma_test",
        pull=True,
        run_official_eval=True,
        official_eval_timeout_seconds=3600.0,
    )

    assert "--skip-official-eval" not in command
    assert "--official-eval-timeout-seconds" in command
    assert "3600" in command
    assert "--ack-local-llm-docker" in command


def test_official_eval_mode_forwards_resource_limits_and_force() -> None:
    harness = load_harness()

    command = harness.build_closed_loop_command(
        "restore_patch3_generalization_probe",
        config_path=ROOT / "example.yaml",
        model="codex-file-bridge-chroma-test",
        run_name="file_bridge_no_external_chroma_test",
        run_official_eval=True,
        official_eval_timeout_seconds=7200.0,
        docker_command_timeout_seconds=300.0,
        workers=1,
        branch_workers=1,
        docker_cpus=2,
        branch_retries=0,
        force=True,
    )

    assert command[command.index("--official-eval-timeout-seconds") + 1] == "7200"
    assert command[command.index("--docker-command-timeout-seconds") + 1] == "300"
    assert command[command.index("--workers") + 1] == "1"
    assert command[command.index("--branch-workers") + 1] == "1"
    assert command[command.index("--docker-cpus") + 1] == "2"
    assert command[command.index("--branch-retries") + 1] == "0"
    assert "--force" in command


def test_default_mode_stops_before_official_eval() -> None:
    harness = load_harness()

    command = harness.build_closed_loop_command(
        "restore_patch3_generalization_probe",
        config_path=ROOT / "example.yaml",
        model="codex-file-bridge-chroma-test",
        run_name="file_bridge_no_external_chroma_test",
    )

    assert "--skip-official-eval" in command
