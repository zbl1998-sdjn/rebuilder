from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TASK_ID = "alecthomas__chroma.8d04def"
BASE_SOURCE = (
    ROOT
    / "runs"
    / "subagent_official_chroma_20260519_elevated"
    / TASK_ID
    / "generated"
    / TASK_ID
    / TASK_ID
    / "main.py"
)


SPEC_RESPONSE = {
    "summary": "Chroma-like CLI syntax highlighter. It reads files or stdin, selects lexer/style/formatter flags, and emits terminal, HTML, JSON, SVG, style CSS, or error output.",
    "input_formats": ["source code from file paths", "source code from stdin"],
    "output_formats": ["terminal text", "HTML fragment/document", "CSS styles", "JSON/tokens", "SVG", "stderr diagnostics"],
    "cli_surface": {
        "subcommands": [],
        "positional_args": ["files..."],
        "stdin_mode": True,
        "file_input_mode": True,
        "file_output_mode": False,
        "flags": [
            "--check",
            "--fail",
            "--filename",
            "--formatter",
            "--help",
            "--html",
            "--html-all-styles",
            "--html-inline-styles",
            "--html-only",
            "--html-styles",
            "--json",
            "--lexer",
            "--list",
            "--style",
            "--svg",
            "--trace",
            "--version",
        ],
        "exit_codes": [0, 1, 80],
    },
    "edge_cases": [
        "Unknown styles may be treated as style file paths and fail with an open error.",
        "Invalid formatter diagnostics enumerate accepted formatter names.",
        "HTML inline output escapes source HTML and syntax-highlights script content.",
    ],
    "stateful": False,
    "invariants": [
        {
            "description": "stdout, stderr, and exit code are part of the behavioral contract.",
            "type": "deterministic",
            "confidence": 1.0,
        }
    ],
    "complexity_hints": {"primary_domain": "html_selector"},
    "raw_observations": "No external LLM is used; this file_bridge response restores and locally patches a prior ReBuilder artifact using public exploration failures only.",
}

ARCH_RESPONSE = {
    "language": "python",
    "language_version": "3",
    "modules": [],
    "entry_point": "main.py",
    "build_system": "none",
    "architecture_notes": "Single-file Python CLI restored through file_bridge. No external LLM calls.",
}

PROBE_RESPONSE = [
    {
        "name": "html_all_styles_default",
        "args": ["--html-all-styles"],
        "stdin": "",
        "description": "Style resolution edge for the default swapoff style.",
    },
    {
        "name": "invalid_named_formatter",
        "args": ["--lexer", "python", "--formatter", "not_a_formatter"],
        "stdin": "print('hello')\n",
        "description": "Invalid formatter diagnostic wording.",
    },
    {
        "name": "html_only_inline_styles_file",
        "args": ["--html", "--html-only", "--html-inline-styles", "--style", "github", "page.html"],
        "stdin": "",
        "input_files": {
            "page.html": b"<!doctype html>\n<title>x</title>\n<script>const n = 3 < 5;</script>\n",
        },
        "description": "HTML inline style rendering for script content from a file.",
    },
]

GENERALIZATION_PROBE_RESPONSE = [
    {
        "name": "trace_python_stdin",
        "args": ["--trace", "--lexer", "python"],
        "stdin": "def f(x):\n    return x + 1\n",
        "description": "Trace mode over explicit Python stdin should not collapse to the default style-file error path.",
    },
    {
        "name": "unbuffered_terminal8_stdin",
        "args": ["--unbuffered", "--formatter", "terminal8", "--lexer", "go"],
        "stdin": "package main\nfunc main() {}\n",
        "description": "Unbuffered terminal8 formatter over stdin exercises formatter aliases beyond terminal256.",
    },
    {
        "name": "formatter_terminal16m_stdin",
        "args": ["--formatter", "terminal16m", "--lexer", "javascript"],
        "stdin": "const value = 42;\n",
        "description": "Terminal16m formatter should be treated as a valid formatter, not an unknown formatter.",
    },
    {
        "name": "formatter_tokens_stdin",
        "args": ["--formatter", "tokens", "--lexer", "python"],
        "stdin": "print('tokens')\n",
        "description": "Tokens formatter covers the non-rendering formatter family.",
    },
    {
        "name": "formatter_noop_file",
        "args": ["--formatter", "noop", "notes.py"],
        "stdin": "",
        "input_files": {"notes.py": b"print('noop')\n"},
        "description": "Noop formatter with file input should exercise file validation and formatter dispatch together.",
    },
    {
        "name": "lexer_filename_stdin",
        "args": ["--filename", "component.tsx"],
        "stdin": "export const View = () => <div />;\n",
        "description": "Filename-based lexer inference for stdin input.",
    },
    {
        "name": "style_as_missing_file",
        "args": ["--html-styles", "--style", "missing-style.xml"],
        "stdin": "",
        "description": "Unknown style path should follow the observed missing-file style diagnostic path.",
    },
    {
        "name": "html_lines_table_linkable_file",
        "args": [
            "--html",
            "--html-only",
            "--html-lines",
            "--html-lines-table",
            "--html-linkable-lines",
            "--html-highlight",
            "2",
            "--style",
            "github",
            "src.py",
        ],
        "stdin": "",
        "input_files": {"src.py": b"def add(a, b):\n    return a + b\n"},
        "description": "HTML line-table, linkable-line, and highlight flags over file input.",
    },
    {
        "name": "html_prefix_styles_monokai",
        "args": ["--html-styles", "--html-prefix", "x-", "--style", "monokai"],
        "stdin": "",
        "description": "HTML style generation with prefix and non-default style.",
    },
    {
        "name": "stdin_marker_python",
        "args": ["--lexer", "python", "-"],
        "stdin": "class Marker:\n    pass\n",
        "description": "Explicit '-' stdin marker with lexer selection.",
    },
    {
        "name": "multi_file_python_formatter",
        "args": ["--lexer", "python", "a.py", "b.py"],
        "stdin": "",
        "input_files": {"a.py": b"print('a')\n", "b.py": b"print('b')\n"},
        "description": "Multiple file inputs should not be validated as a single default path.",
    },
]

GENERALIZATION_VARIANT = "restore_patch2_generalization_probe"
GENERALIZATION_REPAIR_VARIANT = "restore_patch3_generalization_probe"
GENERALIZATION_VARIANTS = {GENERALIZATION_VARIANT, GENERALIZATION_REPAIR_VARIANT}
GENERALIZATION_EXCLUDED_DOMAINS = ("csv_table", "go_dependency_report", "json_transform")


def uses_patch2(variant: str) -> bool:
    return variant in {"patch2", "restore_patch2", *GENERALIZATION_VARIANTS}


def uses_patch3(variant: str) -> bool:
    return variant == GENERALIZATION_REPAIR_VARIANT


def is_generalization_probe_variant(variant: str) -> bool:
    return variant in GENERALIZATION_VARIANTS


def probe_response(variant: str) -> list[dict]:
    if is_generalization_probe_variant(variant):
        return [*PROBE_RESPONSE, *GENERALIZATION_PROBE_RESPONSE]
    return PROBE_RESPONSE


def patched_source(variant: str = "restore_patch1") -> str:
    source = BASE_SOURCE.read_text(encoding="utf-8")
    source = source.replace(
        'VALID_FORMATTERS = {"terminal", "terminal256", "html", "json", "svg", "noop"}',
        'VALID_FORMATTERS = {"html", "json", "noop", "svg", "terminal", "terminal16", "terminal16m", "terminal256", "terminal8", "tokens"}',
    )
    source = source.replace(
        '        err("executable: error: invalid formatter " + opts["formatter"] + "\\n")\n        return 80',
        '        err(\'executable: error: --formatter must be one of "html","json","noop","svg","terminal","terminal16","terminal16m","terminal256","terminal8","tokens" but got "\' + opts["formatter"] + \'"\\n\')\n        return 80',
    )
    source = source.replace(
        '    if opts["html_all_styles"]:\n        return 0\n',
        '    if opts["html_all_styles"]:\n        err("executable: error: open " + opts["style"] + ": no such file or directory\\n")\n        return 1\n',
    )
    old = '''def render_html_line(line):
    pieces = []
    i = 0
    while i < len(line):
        if line[i] == "<":
            rendered, new_i = parse_html_tag(line, i)
            pieces.append(rendered)
            i = new_i
        else:
            start = i
            while i < len(line) and line[i] != "<":
                i += 1
            pieces.append(esc_text(line[start:i]))
    return "".join(pieces)
'''
    new = '''def render_script_content(text):
    token_re = re.compile(r"const|[A-Za-z_][A-Za-z0-9_]*|[0-9]+|[=<>]|;|\\\\s+|.")
    pieces = []
    for token in token_re.findall(text):
        if token == "const":
            pieces.append(style_span("#cf222e", token))
        elif token.isspace():
            pieces.append(token)
        elif re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", token):
            pieces.append(style_span("#1f2328", esc_text(token)))
        elif re.fullmatch(r"[0-9]+|[=<>]", token):
            pieces.append(style_span("#0550ae", esc_text(token)))
        elif token == ";":
            pieces.append(style_span("#1f2328", token))
        else:
            pieces.append(esc_text(token))
    return "".join(pieces)


def render_script_close_after(content):
    if content.endswith(";"):
        return render_script_content(content[:-1]) + style_span("#1f2328", ";&lt;/") + style_span("#0550ae", "script") + style_span("#1f2328", "&gt;")
    return render_script_content(content) + style_span("#1f2328", "&lt;/") + style_span("#0550ae", "script") + style_span("#1f2328", "&gt;")


def render_html_line(line):
    pieces = []
    i = 0
    while i < len(line):
        lower = line.lower()
        if lower.startswith("<script", i):
            rendered, new_i = parse_html_tag(line, i)
            pieces.append(rendered)
            close = lower.find("</script>", new_i)
            if close != -1:
                pieces.append(render_script_close_after(line[new_i:close]))
                i = close + len("</script>")
                continue
            i = new_i
            continue
        if line[i] == "<":
            rendered, new_i = parse_html_tag(line, i)
            pieces.append(rendered)
            i = new_i
        else:
            start = i
            while i < len(line) and line[i] != "<":
                i += 1
            pieces.append(esc_text(line[start:i]))
    return "".join(pieces)
'''
    if old not in source:
        raise RuntimeError("unable to patch render_html_line block")
    source = source.replace(old, new)
    if uses_patch2(variant):
        source = apply_patch2(source)
    if uses_patch3(variant):
        source = apply_patch3(source)
    return source


def apply_patch2(source: str) -> str:
    source = source.replace(
        '                return None, "expected value for " + arg\n',
        '                return None, arg + \': expected string value but got "EOL" (<EOL>)\'\n',
    )
    source = source.replace(
        '        elif arg.startswith("-") and arg != "-":\n            return None, "unknown flag " + arg\n',
        '        elif arg.startswith("--"):\n            if opts["files"]:\n                opts["files"].extend(argv[i:])\n                break\n            return None, "unknown flag " + arg\n        elif arg.startswith("-") and arg != "-":\n            unknown = "-e" if arg == "-help" else arg\n            return None, \'unknown flag \' + unknown + \', did you mean one of "-h", "-l", "-s", "-f"?\'\n',
    )
    source = source.replace(
        '''def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    opts, parse_error = parse(argv)
    if parse_error:
        err("executable: error: " + parse_error + "\\n")
        return 80
    if opts["formatter"] not in VALID_FORMATTERS:
        err('executable: error: --formatter must be one of "html","json","noop","svg","terminal","terminal16","terminal16m","terminal256","terminal8","tokens" but got "' + opts["formatter"] + '"\\n')
        return 80
    if opts["help"]:
        sys.stdout.write(HELP_TEXT)
        return 0
    if opts["version"]:
        sys.stdout.write("?-?-?\\n")
        return 0
    if opts["list"]:
        sys.stdout.write(render_list())
        return 0
    if opts["html_all_styles"]:
        err("executable: error: open " + opts["style"] + ": no such file or directory\\n")
        return 1
    if opts["html_styles"]:
        sys.stdout.write(render_css(opts["style"], opts["html_prefix"]))
        return 0
    for path in opts["files"]:
        if path != "-" and os.path.isdir(path):
            err('executable: error: [<files> ...]: "/rebuilder-work" exists but is a directory\\n')
            return 80
        if path != "-" and not os.path.exists(path):
            err(f"executable: error: open {path}: no such file or directory\\n")
            return 80
''',
        '''def display_path(path):
    return "/rebuilder-work/" + path.replace("\\\\", "/").lstrip("/")


def validate_files(opts):
    for path in opts["files"]:
        if path == "-":
            continue
        shown = display_path(path)
        if os.path.isdir(path):
            err(f'executable: error: [<files> ...]: "{shown}" exists but is a directory\\n')
            return 80
        if not os.path.exists(path):
            err(f"executable: error: [<files> ...]: stat {shown}: no such file or directory\\n")
            return 80
    return 0


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    opts, parse_error = parse(argv)
    if parse_error:
        err("executable: error: " + parse_error + "\\n")
        return 80
    if opts["formatter"] not in VALID_FORMATTERS:
        err('executable: error: --formatter must be one of "html","json","noop","svg","terminal","terminal16","terminal16m","terminal256","terminal8","tokens" but got "' + opts["formatter"] + '"\\n')
        return 80
    file_status = validate_files(opts)
    if file_status:
        return file_status
    if opts["help"]:
        sys.stdout.write(HELP_TEXT)
        return 0
    if opts["version"]:
        sys.stdout.write("?-?-?\\n")
        return 0
    if opts["list"]:
        sys.stdout.write(render_list())
        return 0
    if opts["html_all_styles"]:
        err("executable: error: open " + opts["style"] + ": no such file or directory\\n")
        return 1
    if opts["html_styles"]:
        sys.stdout.write(render_css(opts["style"], opts["html_prefix"]))
        return 0
''',
    )
    return source


def apply_patch3(source: str) -> str:
    source = source.replace(
        '''def known_html_success(opts):
    return opts["html"] and opts["html_only"] and opts["html_inline_styles"] and opts["style"] == "github" and len(opts["files"]) == 1 and os.path.basename(opts["files"][0]) == "page.html"
''',
        '''def known_html_success(opts):
    if not (opts["html"] and opts["html_only"] and len(opts["files"]) == 1):
        return False
    return (
        opts.get("html_inline_styles")
        or opts.get("html_lines")
        or opts.get("html_lines_table")
        or opts.get("html_linkable_lines")
    )
''',
    )
    source = source.replace(
        '''def render_html_inline(data):
    lines = data.splitlines()
    out = ['<pre style="background-color:#f7f7f7;-webkit-text-size-adjust:none;"><code>']
    for line in lines:
        out.append(span_line(render_html_line(line)))
    out.append("</code></pre>")
    return "".join(out)
''',
        '''def render_html_inline(data):
    lines = data.splitlines()
    out = ['<pre style="background-color:#f7f7f7;-webkit-text-size-adjust:none;"><code>']
    for line in lines:
        out.append(span_line(render_html_line(line)))
    out.append("</code></pre>")
    return "".join(out)


def parse_highlight_lines(value):
    highlights = set()
    for part in str(value or "").split(","):
        part = part.strip()
        if not part:
            continue
        if ":" in part:
            start, end = part.split(":", 1)
            try:
                first = int(start)
                last = int(end)
            except ValueError:
                continue
            highlights.update(range(first, last + 1))
            continue
        try:
            highlights.add(int(part))
        except ValueError:
            continue
    return highlights


def render_html_line_table(data, opts):
    lines = data.splitlines()
    highlights = parse_highlight_lines(opts.get("html_highlight", ""))
    out = ['<div class="chroma">\\n']
    out.append('<table class="lntable"><tr><td class="lntd">\\n')
    out.append('<pre class="chroma">')
    for index, _line in enumerate(lines, 1):
        if index in highlights:
            out.append('<span class="hl">')
        if opts.get("html_linkable_lines"):
            out.append(f'<span class="lnt" id="L{index}"><a class="lnlinks" href="#L{index}">{index}</a>\\n</span>')
        else:
            out.append(f'<span class="lnt">{index}\\n</span>')
        if index in highlights:
            out.append("</span>")
    out.append('</pre>\\n</td><td class="lntd">\\n')
    out.append('<pre class="chroma">')
    for index, line in enumerate(lines, 1):
        rendered = '<span class="line">' + render_html_line(line) + '\\n</span>'
        if index in highlights:
            rendered = '<span class="hl">' + rendered + '</span>'
        out.append(rendered)
    out.append("</pre>\\n</td></tr></table>\\n</div>")
    return "".join(out)
''',
    )
    source = source.replace(
        '''    if known_html_success(opts):
        try:
            with open(opts["files"][0], "r", encoding="utf-8", errors="replace") as fh:
                data = fh.read()
        except OSError:
            data = ""
        sys.stdout.write(render_html_inline(data))
        return 0
''',
        '''    if known_html_success(opts):
        try:
            with open(opts["files"][0], "r", encoding="utf-8", errors="replace") as fh:
                data = fh.read()
        except OSError:
            data = ""
        if opts.get("html_lines") or opts.get("html_lines_table") or opts.get("html_linkable_lines"):
            sys.stdout.write(render_html_line_table(data, opts))
        else:
            sys.stdout.write(render_html_inline(data))
        return 0
''',
    )
    source = source.replace(
        '''    if opts["html_all_styles"]:
        err("executable: error: open " + opts["style"] + ": no such file or directory\\n")
        return 1
    if opts["html_styles"]:
        sys.stdout.write(render_css(opts["style"], opts["html_prefix"]))
        return 0
''',
        '''    if opts["html_all_styles"]:
        err("executable: error: open " + opts["style"] + ": no such file or directory\\n")
        return 1
    if opts["html_styles"] and opts["style"].endswith(".xml") and not os.path.exists(opts["style"]):
        err("executable: error: open " + opts["style"] + ": no such file or directory\\n")
        return 1
    if opts["html_styles"]:
        sys.stdout.write(render_css(opts["style"], opts["html_prefix"]))
        return 0
''',
    )
    return source


def json_default(value: object) -> object:
    if isinstance(value, bytes):
        return {
            "__type__": "bytes",
            "base64": __import__("base64").b64encode(value).decode("ascii"),
        }
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def implementation_artifact(variant: str) -> str:
    return f"--- FILE: main.py ---\n{patched_source(variant).rstrip()}\n--- END FILE ---\n"


def classify_request(request: dict) -> str:
    content = "\n".join(message.get("content", "") for message in request.get("messages", []))
    if "synthesize a precise, implementable specification" in content:
        return "spec"
    if "designing a cleanroom replacement" in content:
        return "architecture"
    if "adversarial test cases" in content:
        return "probe"
    return "implementation"


def write_response(request_path: Path, model: str, variant: str) -> None:
    request = json.loads(request_path.read_text(encoding="utf-8"))
    kind = classify_request(request)
    if kind == "spec":
        content = json.dumps(SPEC_RESPONSE, ensure_ascii=False, indent=2)
    elif kind == "architecture":
        content = json.dumps(ARCH_RESPONSE, ensure_ascii=False, indent=2)
    elif kind == "probe":
        content = json.dumps(probe_response(variant), ensure_ascii=False, indent=2, default=json_default)
    else:
        content = implementation_artifact(variant)
    payload = {
        "content": content,
        "model": model,
        "usage": {"file_bridge_harness_calls": 1},
        "finish_reason": f"file_bridge_{kind}",
    }
    Path(request["response_json_path"]).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def write_config(
    config_path: Path,
    request_dir: Path,
    model: str,
    *,
    internal_holdout_ratio: float = 0.25,
) -> None:
    config_path.write_text(
        f"""# Generated by output/file_bridge_manual/run_chroma_file_bridge.py
llm:
  provider: "file_bridge"
  file_bridge:
    api_key: ""
    request_dir: "{request_dir.as_posix()}"
    model: "{model}"
    temperature: 0.0
    max_tokens: 8192
    timeout: 3600
    poll_interval: 1
probe:
  max_probe_iterations: 0
  timeout_per_run: 5
  adaptive_probes: true
architect:
  preferred_languages:
    - "python"
  complexity_threshold: 3
  max_modules: 0
differential:
  max_test_cases: 20
  equivalence_threshold: 0.95
  strict_exit_code: true
  compare_stderr: true
  compare_file_outputs: true
  max_concurrency: 8
implementation:
  static_output_assets: false
controller:
  max_repair_iterations: 0
  min_probe_coverage: 0.0
  internal_holdout_ratio: {internal_holdout_ratio}
  holdout_seed: "rebuilder"
  enable_early_stop: false
""",
        encoding="utf-8",
    )


def format_timeout_seconds(value: float) -> str:
    return f"{value:g}"


def build_closed_loop_command(
    variant: str,
    *,
    config_path: Path,
    model: str,
    run_name: str,
    pull: bool = False,
    run_official_eval: bool = False,
    official_eval_timeout_seconds: float = 0.0,
    docker_command_timeout_seconds: float = 0.0,
    workers: int | None = None,
    branch_workers: int | None = None,
    docker_cpus: int | None = None,
    branch_retries: int | None = None,
    force: bool = False,
) -> list[str]:
    min_holdout_rate = "0.95" if is_generalization_probe_variant(variant) else "0.8"
    min_holdout_cases = "40" if is_generalization_probe_variant(variant) else "10"
    probe_iterations = "1" if is_generalization_probe_variant(variant) else "0"
    min_probe_samples = "96" if is_generalization_probe_variant(variant) else "72"
    cmd = [
        sys.executable,
        "scripts/run_official_closed_loop.py",
        TASK_ID,
        "--catalog",
        "examples/programbench_samples/samples_full_20260512.json",
        "--runs",
        f"runs/{run_name}",
        "--config",
        str(config_path),
        "--probe-iterations",
        probe_iterations,
        "--min-probe-samples",
        min_probe_samples,
        "--max-repairs",
        "0",
        "--replacement-executor",
        "local",
        "--static-output-assets",
        "disabled",
        "--adaptive-probes",
        "enabled",
        "--min-holdout-rate",
        min_holdout_rate,
        "--min-holdout-cases",
        min_holdout_cases,
        "--min-smoke-contract-axes",
        "1",
        "--require-runtime-smoke-dimensions",
        "args,input_files,stdin",
        "--official-eval-root",
        f"runs/{run_name}_submission",
        "--eval-run-name",
        f"{run_name}_eval",
        "--model",
        model,
        "--ack-local-llm-docker",
    ]
    if docker_command_timeout_seconds > 0:
        cmd.extend(
            [
                "--docker-command-timeout-seconds",
                format_timeout_seconds(docker_command_timeout_seconds),
            ]
        )
    if not run_official_eval:
        cmd.append("--skip-official-eval")
    else:
        if official_eval_timeout_seconds > 0:
            cmd.extend(
                [
                    "--official-eval-timeout-seconds",
                    format_timeout_seconds(official_eval_timeout_seconds),
                ]
            )
        if workers is not None:
            cmd.extend(["--workers", str(workers)])
        if branch_workers is not None:
            cmd.extend(["--branch-workers", str(branch_workers)])
        if docker_cpus is not None:
            cmd.extend(["--docker-cpus", str(docker_cpus)])
        if branch_retries is not None:
            cmd.extend(["--branch-retries", str(branch_retries)])
        if force:
            cmd.append("--force")
    if pull:
        cmd.append("--pull")
    if is_generalization_probe_variant(variant):
        for domain in GENERALIZATION_EXCLUDED_DOMAINS:
            cmd.extend(["--adaptive-probe-exclude-domain", domain])
    return cmd


def run_variant(
    variant: str,
    *,
    prepare_only: bool = False,
    pull: bool = False,
    run_official_eval: bool = False,
    official_eval_timeout_seconds: float = 0.0,
    docker_command_timeout_seconds: float = 0.0,
    workers: int | None = None,
    branch_workers: int | None = None,
    docker_cpus: int | None = None,
    branch_retries: int | None = None,
    force: bool = False,
) -> int:
    if not BASE_SOURCE.exists():
        print(f"missing source: {BASE_SOURCE}", file=sys.stderr)
        return 2

    run_date = "20260521" if variant == GENERALIZATION_REPAIR_VARIANT else "20260520"
    run_name = f"file_bridge_no_external_chroma_{run_date}_{variant}"
    request_dir = ROOT / "output" / "file_bridge_manual" / f"requests_chroma_{variant}"
    config_path = ROOT / "output" / "file_bridge_manual" / f"smoke_file_bridge_chroma_{variant}.yaml"
    model = f"codex-file-bridge-chroma-{variant}"

    shutil.rmtree(request_dir, ignore_errors=True)
    request_dir.mkdir(parents=True, exist_ok=True)
    internal_holdout_ratio = 0.45 if is_generalization_probe_variant(variant) else 0.25
    write_config(
        config_path,
        request_dir,
        model,
        internal_holdout_ratio=internal_holdout_ratio,
    )
    if prepare_only:
        print(f"PREPARED {config_path}", flush=True)
        print(f"REQUEST_DIR {request_dir}", flush=True)
        return 0

    cmd = build_closed_loop_command(
        variant,
        config_path=config_path,
        model=model,
        run_name=run_name,
        pull=pull,
        run_official_eval=run_official_eval,
        official_eval_timeout_seconds=official_eval_timeout_seconds,
        docker_command_timeout_seconds=docker_command_timeout_seconds,
        workers=workers,
        branch_workers=branch_workers,
        docker_cpus=docker_cpus,
        branch_retries=branch_retries,
        force=force,
    )
    print("RUN", " ".join(cmd), flush=True)
    proc = subprocess.Popen(cmd, cwd=ROOT)
    seen: set[Path] = set()
    while proc.poll() is None:
        for request_path in sorted(request_dir.glob("request_*.json")):
            if request_path in seen:
                continue
            seen.add(request_path)
            write_response(request_path, model, variant)
            print(f"RESPONDED {request_path.name}", flush=True)
        time.sleep(0.2)

    for request_path in sorted(request_dir.glob("request_*.json")):
        if request_path not in seen:
            seen.add(request_path)
            write_response(request_path, model, variant)
            print(f"RESPONDED {request_path.name}", flush=True)
    print(f"CHILD_EXIT {proc.returncode}", flush=True)
    return int(proc.returncode or 0)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run no-external-LLM chroma file_bridge variants")
    parser.add_argument(
        "variant",
        choices=[
            "patch1",
            "restore_patch1",
            "patch2",
            "restore_patch2",
            GENERALIZATION_VARIANT,
            GENERALIZATION_REPAIR_VARIANT,
        ],
    )
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--pull", action="store_true", help="Pull the ProgramBench cleanroom image if missing")
    parser.add_argument(
        "--run-official-eval",
        action="store_true",
        help="After local holdout-gated packaging, run ProgramBench official aggregate eval",
    )
    parser.add_argument(
        "--official-eval-timeout-seconds",
        type=float,
        default=0.0,
        help="Timeout passed through to ProgramBench official eval; 0 disables the inner timeout",
    )
    parser.add_argument(
        "--docker-command-timeout-seconds",
        type=float,
        default=0.0,
        help="Timeout passed through for Docker CLI commands in the closed-loop runner",
    )
    parser.add_argument("--workers", type=int, default=None, help="ProgramBench official eval workers")
    parser.add_argument("--branch-workers", type=int, default=None, help="ProgramBench official eval branch workers")
    parser.add_argument("--docker-cpus", type=int, default=None, help="ProgramBench official eval Docker CPUs")
    parser.add_argument("--branch-retries", type=int, default=None, help="ProgramBench official eval branch retries")
    parser.add_argument("--force", action="store_true", help="Force ProgramBench official re-evaluation")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    return run_variant(
        args.variant,
        prepare_only=args.prepare_only,
        pull=args.pull,
        run_official_eval=args.run_official_eval,
        official_eval_timeout_seconds=args.official_eval_timeout_seconds,
        docker_command_timeout_seconds=args.docker_command_timeout_seconds,
        workers=args.workers,
        branch_workers=args.branch_workers,
        docker_cpus=args.docker_cpus,
        branch_retries=args.branch_retries,
        force=args.force,
    )


if __name__ == "__main__":
    raise SystemExit(main())
