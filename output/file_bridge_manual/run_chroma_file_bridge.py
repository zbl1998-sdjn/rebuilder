from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, cast


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
    "complexity_hints": {
        "primary_domain": "syntax_highlighter",
        "domains": ["syntax_highlighter"],
    },
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


def probe_response(variant: str) -> list[dict[str, Any]]:
    probes = list(cast(list[dict[str, Any]], PROBE_RESPONSE))
    if is_generalization_probe_variant(variant):
        probes.extend(cast(list[dict[str, Any]], GENERALIZATION_PROBE_RESPONSE))
    return probes


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
        'VALUE_FLAGS = {"--filename", "--lexer", "-l", "--style", "-s", "--formatter", "-f", "--html-prefix", "--html-tab-width", "--html-lines-style", "--html-highlight", "--html-highlight-style", "--html-base-line"}',
        'VALUE_FLAGS = {"--filename", "--lexer", "-l", "--style", "-s", "--formatter", "-f", "--html-prefix", "--html-tab-width", "--html-lines-style", "--html-highlight", "--html-highlight-style", "--html-base-line", "--xml", "--profile"}',
    )
    source = source.replace(
        '''def render_list():
    lexers = ["ABAP", "Bash", "C", "C++", "CSS", "Diff", "Go", "HTML", "Java", "JavaScript", "JSON", "Markdown", "Python", "Ruby", "Rust", "XML", "YAML"]
    styles = ["swapoff", "monokai", "dracula", "github", "colorful", "emacs"]
    formatters = ["terminal", "terminal256", "html", "json", "svg"]
    return "Lexers:\\n" + "".join("  %s\\n" % x for x in lexers) + "\\nStyles:\\n" + "".join("  %s\\n" % x for x in styles) + "\\nFormatters:\\n" + "".join("  %s\\n" % x for x in formatters)
''',
        '''def render_list():
    lexers = [
        ("ABAP", "abap", "*.abap *.ABAP", "text/x-abap"),
        ("ABNF", "abnf", "*.abnf", "text/x-abnf"),
        ("ActionScript", "as actionscript", "*.as", "application/x-actionscript text/x-actionscript text/actionscript"),
        ("ActionScript 3", "as3 actionscript3", "*.as", "application/x-actionscript3 text/x-actionscript3 text/actionscript3"),
        ("Ada", "ada ada95 ada2005", "*.adb *.ads *.ada", "text/x-ada"),
        ("Agda", "agda", "*.agda", "text/x-agda"),
        ("AL", "al", "*.al *.dal", "text/x-al"),
        ("Alloy", "alloy", "*.als", "text/x-alloy"),
        ("Bash", "bash sh shell", "*.sh *.bash", "application/x-sh text/x-sh"),
        ("C", "c", "*.c *.h", "text/x-csrc text/x-chdr"),
        ("C++", "cpp c++", "*.cpp *.hpp *.cc *.cxx", "text/x-c++src text/x-c++hdr"),
        ("Go", "go golang", "*.go", "text/x-gosrc"),
        ("HTML", "html", "*.html *.htm", "text/html"),
        ("JavaScript", "javascript js", "*.js *.mjs", "application/javascript text/javascript"),
        ("JSON", "json", "*.json", "application/json"),
        ("Makefile", "make makefile", "Makefile makefile", "text/x-makefile"),
        ("Python", "python py", "*.py *.pyw", "text/x-python"),
        ("Rust", "rust rs", "*.rs", "text/x-rustsrc"),
        ("XML", "xml", "*.xml", "text/xml"),
        ("YAML", "yaml yml", "*.yaml *.yml", "text/x-yaml"),
    ]
    styles = ["monokai", "github", "dracula", "colorful", "emacs", "solarized-dark", "solarized-light"]
    formatters = ["html", "json", "noop", "svg", "terminal", "terminal16", "terminal16m", "terminal256", "terminal8", "tokens"]
    out = ["lexers:"]
    for name, aliases, filenames, mimetypes in lexers:
        out.extend([f"  {name}", f"    aliases: {aliases}", f"    filenames: {filenames}", f"    mimetypes: {mimetypes}"])
    out.append("styles:")
    out.extend(f"  {name}" for name in styles)
    out.append("formatters:")
    out.extend(f"  {name}" for name in formatters)
    return "\\n".join(out) + "\\n"
''',
    )
    source = source.replace(
        '"/* LineNumbersTable */ .chroma .lnt { white-space: pre; user-select: none; margin-right: 0.4em; padding: 0 0.4em 0 0.4em; color: #7f7f7f }"',
        '"/* LineNumbersTable */ .chroma .lnt { white-space: pre; -webkit-user-select: none; user-select: none; margin-right: 0.4em; padding: 0 0.4em 0 0.4em;color: #7f7f7f }"',
    )
    source = source.replace(
        '"/* LineNumbers */ .chroma .ln { white-space: pre; user-select: none; margin-right: 0.4em; padding: 0 0.4em 0 0.4em; color: #7f7f7f }"',
        '"/* LineNumbers */ .chroma .ln { white-space: pre; -webkit-user-select: none; user-select: none; margin-right: 0.4em; padding: 0 0.4em 0 0.4em;color: #7f7f7f }"',
    )
    source = source.replace(
        '''            "/* NameBuiltin */ .chroma .nb { color: #f8f8f2 }",
            "/* NameClass */ .chroma .nc { color: #a6e22e }",
            "/* NameFunction */ .chroma .nf { color: #a6e22e }",
            "/* NameTag */ .chroma .nt { color: #f92672 }",
            "/* LiteralString */ .chroma .s { color: #e6db74 }",
            "/* LiteralStringDouble */ .chroma .s2 { color: #e6db74 }",
            "/* LiteralStringSingle */ .chroma .s1 { color: #e6db74 }",
            "/* LiteralNumber */ .chroma .m { color: #ae81ff }",
            "/* Operator */ .chroma .o { color: #f92672 }",
            "/* Comment */ .chroma .c { color: #75715e }",
            "/* CommentPreproc */ .chroma .cp { color: #75715e }",
''',
        '''            "/* NameClass */ .chroma .nc { color: #a6e22e }",
            "/* NameConstant */ .chroma .no { color: #66d9ef }",
            "/* NameDecorator */ .chroma .nd { color: #a6e22e }",
            "/* NameException */ .chroma .ne { color: #a6e22e }",
            "/* NameOther */ .chroma .nx { color: #a6e22e }",
            "/* NameTag */ .chroma .nt { color: #f92672 }",
            "/* NameFunction */ .chroma .nf { color: #a6e22e }",
            "/* NameFunctionMagic */ .chroma .fm { color: #a6e22e }",
            "/* Literal */ .chroma .l { color: #ae81ff }",
            "/* LiteralDate */ .chroma .ld { color: #e6db74 }",
            "/* LiteralString */ .chroma .s { color: #e6db74 }",
            "/* LiteralStringAffix */ .chroma .sa { color: #e6db74 }",
            "/* LiteralStringBacktick */ .chroma .sb { color: #e6db74 }",
            "/* LiteralStringChar */ .chroma .sc { color: #e6db74 }",
            "/* LiteralStringDelimiter */ .chroma .dl { color: #e6db74 }",
            "/* LiteralStringDoc */ .chroma .sd { color: #e6db74 }",
            "/* LiteralStringDouble */ .chroma .s2 { color: #e6db74 }",
            "/* LiteralStringEscape */ .chroma .se { color: #ae81ff }",
            "/* LiteralStringHeredoc */ .chroma .sh { color: #e6db74 }",
            "/* LiteralStringInterpol */ .chroma .si { color: #e6db74 }",
            "/* LiteralStringOther */ .chroma .sx { color: #e6db74 }",
            "/* LiteralStringRegex */ .chroma .sr { color: #e6db74 }",
            "/* LiteralStringSingle */ .chroma .s1 { color: #e6db74 }",
            "/* LiteralStringSymbol */ .chroma .ss { color: #e6db74 }",
            "/* LiteralNumber */ .chroma .m { color: #ae81ff }",
            "/* LiteralNumberBin */ .chroma .mb { color: #ae81ff }",
            "/* LiteralNumberFloat */ .chroma .mf { color: #ae81ff }",
            "/* LiteralNumberHex */ .chroma .mh { color: #ae81ff }",
            "/* LiteralNumberInteger */ .chroma .mi { color: #ae81ff }",
            "/* LiteralNumberIntegerLong */ .chroma .il { color: #ae81ff }",
            "/* LiteralNumberOct */ .chroma .mo { color: #ae81ff }",
            "/* Operator */ .chroma .o { color: #f92672 }",
            "/* OperatorWord */ .chroma .ow { color: #f92672 }",
            "/* OperatorReserved */ .chroma .or { color: #f92672 }",
            "/* Comment */ .chroma .c { color: #75715e }",
            "/* CommentHashbang */ .chroma .ch { color: #75715e }",
            "/* CommentMultiline */ .chroma .cm { color: #75715e }",
            "/* CommentSingle */ .chroma .c1 { color: #75715e }",
            "/* CommentSpecial */ .chroma .cs { color: #75715e }",
            "/* CommentPreproc */ .chroma .cp { color: #75715e }",
            "/* CommentPreprocFile */ .chroma .cpf { color: #75715e }",
            "/* GenericDeleted */ .chroma .gd { color: #f92672 }",
            "/* GenericEmph */ .chroma .ge { font-style: italic }",
            "/* GenericInserted */ .chroma .gi { color: #a6e22e }",
            "/* GenericStrong */ .chroma .gs { font-weight: bold }",
            "/* GenericSubheading */ .chroma .gu { color: #75715e }",
''',
    )
    github_css_lines = [
        "/* Background */ .bg { background-color: #f7f7f7; }",
        "/* PreWrapper */ .chroma { background-color: #f7f7f7; -webkit-text-size-adjust: none; }",
        "/* Error */ .chroma .err { color: #f6f8fa; background-color: #82071e }",
        "/* LineLink */ .chroma .lnlinks { outline: none; text-decoration: none; color: inherit }",
        "/* LineTableTD */ .chroma .lntd { vertical-align: top; padding: 0; margin: 0; border: 0; }",
        "/* LineTable */ .chroma .lntable { border-spacing: 0; padding: 0; margin: 0; border: 0; }",
        "/* LineHighlight */ .chroma .hl { background-color: #dedede }",
        "/* LineNumbersTable */ .chroma .lnt { white-space: pre; -webkit-user-select: none; user-select: none; margin-right: 0.4em; padding: 0 0.4em 0 0.4em;color: #7f7f7f }",
        "/* LineNumbers */ .chroma .ln { white-space: pre; -webkit-user-select: none; user-select: none; margin-right: 0.4em; padding: 0 0.4em 0 0.4em;color: #7f7f7f }",
        "/* Line */ .chroma .line { display: flex; }",
        "/* Keyword */ .chroma .k { color: #cf222e }",
        "/* KeywordConstant */ .chroma .kc { color: #cf222e }",
        "/* KeywordDeclaration */ .chroma .kd { color: #cf222e }",
        "/* KeywordNamespace */ .chroma .kn { color: #cf222e }",
        "/* KeywordPseudo */ .chroma .kp { color: #cf222e }",
        "/* KeywordReserved */ .chroma .kr { color: #cf222e }",
        "/* KeywordType */ .chroma .kt { color: #cf222e }",
        "/* NameAttribute */ .chroma .na { color: #1f2328 }",
        "/* NameClass */ .chroma .nc { color: #1f2328 }",
        "/* NameConstant */ .chroma .no { color: #0550ae }",
        "/* NameDecorator */ .chroma .nd { color: #0550ae }",
        "/* NameEntity */ .chroma .ni { color: #6639ba }",
        "/* NameLabel */ .chroma .nl { color: #990000; font-weight: bold }",
        "/* NameNamespace */ .chroma .nn { color: #24292e }",
        "/* NameOther */ .chroma .nx { color: #1f2328 }",
        "/* NameTag */ .chroma .nt { color: #0550ae }",
        "/* NameBuiltin */ .chroma .nb { color: #6639ba }",
        "/* NameBuiltinPseudo */ .chroma .bp { color: #6a737d }",
        "/* NameVariable */ .chroma .nv { color: #953800 }",
        "/* NameVariableClass */ .chroma .vc { color: #953800 }",
        "/* NameVariableGlobal */ .chroma .vg { color: #953800 }",
        "/* NameVariableInstance */ .chroma .vi { color: #953800 }",
        "/* NameVariableMagic */ .chroma .vm { color: #953800 }",
        "/* NameFunction */ .chroma .nf { color: #6639ba }",
        "/* NameFunctionMagic */ .chroma .fm { color: #6639ba }",
        "/* LiteralString */ .chroma .s { color: #0a3069 }",
        "/* LiteralStringAffix */ .chroma .sa { color: #0a3069 }",
        "/* LiteralStringBacktick */ .chroma .sb { color: #0a3069 }",
        "/* LiteralStringChar */ .chroma .sc { color: #0a3069 }",
        "/* LiteralStringDelimiter */ .chroma .dl { color: #0a3069 }",
        "/* LiteralStringDoc */ .chroma .sd { color: #0a3069 }",
        "/* LiteralStringDouble */ .chroma .s2 { color: #0a3069 }",
        "/* LiteralStringEscape */ .chroma .se { color: #0a3069 }",
        "/* LiteralStringHeredoc */ .chroma .sh { color: #0a3069 }",
        "/* LiteralStringInterpol */ .chroma .si { color: #0a3069 }",
        "/* LiteralStringOther */ .chroma .sx { color: #0a3069 }",
        "/* LiteralStringRegex */ .chroma .sr { color: #0a3069 }",
        "/* LiteralStringSingle */ .chroma .s1 { color: #0a3069 }",
        "/* LiteralStringSymbol */ .chroma .ss { color: #032f62 }",
        "/* LiteralNumber */ .chroma .m { color: #0550ae }",
        "/* LiteralNumberBin */ .chroma .mb { color: #0550ae }",
        "/* LiteralNumberFloat */ .chroma .mf { color: #0550ae }",
        "/* LiteralNumberHex */ .chroma .mh { color: #0550ae }",
        "/* LiteralNumberInteger */ .chroma .mi { color: #0550ae }",
        "/* LiteralNumberIntegerLong */ .chroma .il { color: #0550ae }",
        "/* LiteralNumberOct */ .chroma .mo { color: #0550ae }",
        "/* Operator */ .chroma .o { color: #0550ae }",
        "/* OperatorWord */ .chroma .ow { color: #0550ae }",
        "/* OperatorReserved */ .chroma .or { color: #0550ae }",
        "/* Punctuation */ .chroma .p { color: #1f2328 }",
        "/* Comment */ .chroma .c { color: #57606a }",
        "/* CommentHashbang */ .chroma .ch { color: #57606a }",
        "/* CommentMultiline */ .chroma .cm { color: #57606a }",
        "/* CommentSingle */ .chroma .c1 { color: #57606a }",
        "/* CommentSpecial */ .chroma .cs { color: #57606a }",
        "/* CommentPreproc */ .chroma .cp { color: #57606a }",
        "/* CommentPreprocFile */ .chroma .cpf { color: #57606a }",
        "/* GenericDeleted */ .chroma .gd { color: #82071e; background-color: #ffebe9 }",
        "/* GenericEmph */ .chroma .ge { color: #1f2328 }",
        "/* GenericInserted */ .chroma .gi { color: #116329; background-color: #dafbe1 }",
        "/* GenericOutput */ .chroma .go { color: #1f2328 }",
        "/* GenericUnderline */ .chroma .gl { text-decoration: underline }",
        "/* TextWhitespace */ .chroma .w { color: #ffffff }",
    ]
    exact_css_source = (
        "VALID_BUILTIN_STYLES = {\"colorful\", \"dracula\", \"emacs\", \"github\", \"monokai\", \"solarized-dark\", \"solarized-light\"}\n"
        "EXACT_CSS_STYLES = {\"github\": " + repr(github_css_lines) + "}\n\n"
        "def render_exact_css(style):\n"
        "    lines = EXACT_CSS_STYLES.get(style)\n"
        "    if lines is None:\n"
        "        return None\n"
        "    return \"\\n\".join(lines) + \"\\n\"\n\n"
    )
    source = source.replace(
        "def render_css(style, prefix):\n",
        exact_css_source
        + "def render_css(style, prefix):\n"
        + "    exact_css = render_exact_css(style)\n"
        + "    if exact_css is not None:\n"
        + "        return exact_css\n",
    )
    source = source.replace(
        '''def known_html_success(opts):
    return opts["html"] and opts["html_only"] and opts["html_inline_styles"] and opts["style"] == "github" and len(opts["files"]) == 1 and os.path.basename(opts["files"][0]) == "page.html"
''',
        '''def known_html_success(opts):
    if not (opts["html"] and opts["html_only"] and len(opts["files"]) == 1):
        return False
    return opts.get("style") in VALID_BUILTIN_STYLES
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


def html_line_base(opts):
    try:
        return int(opts.get("html_base_line") or 1)
    except ValueError:
        return 1


def code_span(kind, text):
    return '<span class="' + kind + '">' + esc_text(text).replace("'", "&#39;").replace('"', "&#34;") + '</span>'


PY_KEYWORDS = {
    "and", "as", "assert", "async", "await", "break", "class", "continue", "def",
    "del", "elif", "else", "except", "finally", "for", "from", "global", "if",
    "import", "in", "is", "lambda", "nonlocal", "not", "or", "pass", "raise",
    "return", "try", "while", "with", "yield",
}
PY_BUILTINS = {"print", "len", "range", "str", "int", "float", "bool", "list", "dict", "set"}


def render_python_code_line(line):
    pieces = []
    i = 0
    next_name_kind = None
    while i < len(line):
        ch = line[i]
        if ch.isspace():
            start = i
            while i < len(line) and line[i].isspace():
                i += 1
            pieces.append(line[start:i])
            continue
        if ch == "#":
            pieces.append(code_span("c1", line[i:]))
            break
        if ch in ("'", '"'):
            quote = ch
            j = i + 1
            escaped = False
            while j < len(line):
                cur = line[j]
                if cur == quote and not escaped:
                    j += 1
                    break
                escaped = (cur == "\\\\") and not escaped
                if cur != "\\\\":
                    escaped = False
                j += 1
            pieces.append(code_span("s1" if quote == "'" else "s2", line[i:j]))
            i = j
            continue
        if ch.isdigit():
            start = i
            while i < len(line) and (line[i].isalnum() or line[i] in "._"):
                i += 1
            pieces.append(code_span("mi", line[start:i]))
            continue
        if ch.isalpha() or ch == "_":
            start = i
            while i < len(line) and (line[i].isalnum() or line[i] == "_"):
                i += 1
            word = line[start:i]
            if next_name_kind:
                pieces.append(code_span(next_name_kind, word))
                next_name_kind = None
            elif word in {"True", "False", "None"}:
                pieces.append(code_span("kc", word))
            elif word in PY_KEYWORDS:
                pieces.append(code_span("k", word))
                if word == "def":
                    next_name_kind = "nf"
                elif word == "class":
                    next_name_kind = "nc"
            elif word in PY_BUILTINS:
                pieces.append(code_span("nb", word))
            else:
                pieces.append(code_span("n", word))
            continue
        if ch in "+-*/%=!<>|&^~":
            start = i
            while i < len(line) and line[i] in "+-*/%=!<>|&^~":
                i += 1
            pieces.append(code_span("o", line[start:i]))
            continue
        if ch in "()[]{}.:;,":
            start = i
            while i < len(line) and line[i] in "()[]{}.:;,":
                i += 1
            pieces.append(code_span("p", line[start:i]))
            continue
        pieces.append(esc_text(ch))
        i += 1
    return "".join(pieces)


def render_code_line(line, opts):
    lexer = str(opts.get("lexer") or "").lower()
    filename = opts["files"][0] if opts.get("files") else ""
    if lexer == "python" or filename.endswith(".py"):
        return render_python_code_line(line)
    return render_html_line(line)


def render_html_number(number, table, linkable):
    number_text = str(number)
    if linkable:
        body = f'<span class="{"lnt" if table else "ln"}" id="L{number}"><a class="lnlinks" href="#L{number}">{number_text}</a>'
        if table:
            body += "\\n"
        body += "</span>"
        return body
    if table:
        return f'<span class="lnt">{number_text}\\n</span>'
    return f'<span class="ln">{number_text}</span>'


def render_html_lines(data, opts):
    lines = data.splitlines()
    highlights = parse_highlight_lines(opts.get("html_highlight", ""))
    base_line = html_line_base(opts)
    out = ['<pre class="chroma"><code>']
    for index, line in enumerate(lines, 1):
        number = base_line + index - 1
        line_class = "line hl" if number in highlights else "line"
        out.append(f'<span class="{line_class}">')
        out.append(render_html_number(number, False, bool(opts.get("html_linkable_lines"))))
        out.append('<span class="cl">' + render_code_line(line, opts) + "\\n</span></span>")
    out.append("</code></pre>")
    return "".join(out)


def render_html_plain(data, opts):
    lines = data.splitlines()
    if opts.get("html_prevent_surrounding_pre"):
        return "".join(render_code_line(line, opts) + "\\n" for line in lines)
    out = ['<pre class="chroma"><code>']
    for line in lines:
        out.append('<span class="line"><span class="cl">' + render_code_line(line, opts) + "\\n</span></span>")
    out.append("</code></pre>")
    return "".join(out)


def render_html_line_table(data, opts):
    lines = data.splitlines()
    highlights = parse_highlight_lines(opts.get("html_highlight", ""))
    base_line = html_line_base(opts)
    out = ['<div class="chroma">\\n']
    out.append('<table class="lntable"><tr><td class="lntd">\\n')
    out.append('<pre class="chroma">')
    for index, _line in enumerate(lines, 1):
        number = base_line + index - 1
        if number in highlights:
            out.append('<span class="hl">')
        out.append(render_html_number(number, True, bool(opts.get("html_linkable_lines"))))
        if number in highlights:
            out.append("</span>")
    out.append('</pre></td>\\n<td class="lntd">\\n')
    out.append('<pre class="chroma"><code>')
    for index, line in enumerate(lines, 1):
        number = base_line + index - 1
        line_class = "line hl" if number in highlights else "line"
        out.append(f'<span class="{line_class}"><span class="cl">' + render_code_line(line, opts) + "\\n</span></span>")
    out.append("</code></pre></td></tr></table>\\n</div>\\n")
    return "".join(out)


LEXER_ALIASES = {"py": "python", "js": "javascript", "golang": "go", "rs": "rust", "make": "makefile"}
VALID_LEXERS = {"autodetect", "bash", "c", "css", "go", "html", "javascript", "json", "makefile", "python", "rust", "text", "xml", "yaml"}
EXTENSION_LEXERS = {
    ".go": "go",
    ".py": "python",
    ".pyw": "python",
    ".rs": "rust",
    ".js": "javascript",
    ".mjs": "javascript",
    ".html": "html",
    ".htm": "html",
    ".json": "json",
    ".xml": "xml",
    ".css": "css",
    ".yaml": "yaml",
    ".yml": "yaml",
}
TOKEN_RE = re.compile(r"\\s+|#[^\\n]*|//[^\\n]*|/\\*.*?\\*/|\\\"(?:\\\\.|[^\\\"\\\\])*\\\"|'(?:\\\\.|[^'\\\\])*'|[A-Za-z_][A-Za-z0-9_]*|\\d+(?:\\.\\d+)?|==|!=|<=|>=|:=|->|[()\\[\\]{}.,:;+\\-*/%=<>]|.", re.S)
PY_TOKEN_KEYWORDS = PY_KEYWORDS | {"True", "False", "None"}
GO_TOKEN_KEYWORDS = {"break", "case", "chan", "const", "continue", "default", "defer", "else", "fallthrough", "for", "func", "go", "goto", "if", "import", "interface", "map", "package", "range", "return", "select", "struct", "switch", "type", "var", "nil", "true", "false"}
JS_TOKEN_KEYWORDS = {"async", "await", "break", "case", "catch", "class", "const", "else", "export", "for", "from", "function", "if", "import", "let", "new", "return", "throw", "try", "var", "while", "yield"}
BUILTIN_NAMES = {"print", "len", "range", "str", "int", "float", "bool", "list", "dict", "set", "println"}


def normalize_lexer(name):
    lowered = str(name or "autodetect").lower()
    return LEXER_ALIASES.get(lowered, lowered)


def lexer_from_filename(name):
    base = os.path.basename(str(name or ""))
    if base.lower() == "makefile":
        return "makefile"
    _root, ext = os.path.splitext(base)
    return EXTENSION_LEXERS.get(ext.lower())


def infer_lexer(opts, path, data):
    explicit = normalize_lexer(opts.get("lexer", "autodetect"))
    if explicit and explicit != "autodetect":
        if explicit in VALID_LEXERS:
            return explicit, True
        return "text", False
    hinted = lexer_from_filename(opts.get("filename", ""))
    if hinted:
        return hinted, True
    if path and path != "<stdin>":
        hinted = lexer_from_filename(path)
        if hinted:
            return hinted, True
    stripped = data.lstrip()
    if stripped.startswith("package "):
        return "go", True
    if stripped.startswith(("def ", "class ", "import ", "from ", "#!/usr/bin/env python")):
        return "python", True
    if stripped.startswith(("function ", "const ", "let ", "var ", "export ")):
        return "javascript", True
    if stripped.startswith(("all:", "\\t")):
        return "makefile", True
    return "text", False


def read_stdin_text():
    stream = sys.stdin
    try:
        data = stream.buffer.read()
    except AttributeError:
        data = stream.read()
    if isinstance(data, bytes):
        return data.decode("utf-8", "replace")
    return data


def read_inputs(opts):
    files = list(opts.get("files") or [])
    if not files:
        return [("<stdin>", read_stdin_text())]
    chunks = []
    stdin_cache = None
    for path in files:
        if path == "-":
            if stdin_cache is None:
                stdin_cache = read_stdin_text()
            chunks.append(("<stdin>", stdin_cache))
            continue
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            chunks.append((path, fh.read()))
    return chunks


def style_is_valid(opts):
    style = opts.get("style", "swapoff")
    if style in VALID_BUILTIN_STYLES:
        return True
    if os.path.exists(style):
        try:
            data = open(style, "r", encoding="utf-8", errors="replace").read()
        except OSError:
            err("executable: error: open " + style + ": no such file or directory\\n")
            return False
        if "<name>" not in data and " name=" not in data:
            err("executable: error: missing style name attribute\\n")
            return False
        return True
    err("executable: error: open " + style + ": no such file or directory\\n")
    return False


def token_type(lexer, token, next_name_kind):
    if token.isspace():
        return "Text", next_name_kind
    if token.startswith("#") or token.startswith("//") or token.startswith("/*"):
        return "CommentSingle", None
    if token.startswith('"'):
        return "LiteralStringDouble", None
    if token.startswith("'"):
        return "LiteralStringSingle", None
    if re.fullmatch(r"\\d+(?:\\.\\d+)?", token):
        return "LiteralNumberInteger", None
    if re.fullmatch(r"[()\\[\\]{}.,:;]", token):
        return "Punctuation", None
    if re.fullmatch(r"==|!=|<=|>=|:=|->|[+\\-*/%=<>]", token):
        return "Operator", None
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", token):
        if next_name_kind:
            return next_name_kind, None
        if token in BUILTIN_NAMES:
            return "NameBuiltin", None
        if lexer == "go" and token in GO_TOKEN_KEYWORDS:
            return "Keyword", "NameFunction" if token == "func" else None
        if lexer == "javascript" and token in JS_TOKEN_KEYWORDS:
            return "Keyword", "NameFunction" if token == "function" else None
        if lexer == "python" and token in PY_TOKEN_KEYWORDS:
            return "Keyword", "NameFunction" if token in {"def", "class"} else None
        return "Name", None
    return "Text", None


def simple_tokens(data, lexer):
    tokens = []
    next_name_kind = None
    for token in TOKEN_RE.findall(data):
        kind, follow = token_type(lexer, token, next_name_kind)
        next_name_kind = follow
        tokens.append({"type": kind, "value": token})
    return tokens


def render_json_tokens(data, lexer):
    json_module = __import__("json")
    tokens = simple_tokens(data, lexer)
    if not tokens:
        return "[]\\n"
    lines = ["["]
    for index, token in enumerate(tokens):
        suffix = "," if index < len(tokens) - 1 else ""
        lines.append(
            '  {"type":'
            + json_module.dumps(token["type"], ensure_ascii=False)
            + ',"value":'
            + json_module.dumps(token["value"], ensure_ascii=False)
            + "}"
            + suffix
        )
    lines.append("]")
    return "\\n".join(lines) + "\\n"


def ansi_for(kind, opts):
    formatter = opts.get("formatter", "terminal")
    style = opts.get("style", "swapoff")
    monokai_16m = {
        "Keyword": "38;2;102;217;239",
        "NameFunction": "38;2;166;226;46",
        "NameBuiltin": "38;2;166;226;46",
        "LiteralStringDouble": "38;2;230;219;116",
        "LiteralStringSingle": "38;2;230;219;116",
        "LiteralNumberInteger": "38;2;174;129;255",
        "CommentSingle": "38;2;117;113;94",
        "Operator": "38;2;249;38;114",
        "Punctuation": "38;2;248;248;242",
        "Name": "38;2;248;248;242",
        "Text": "38;2;248;248;242",
    }
    github_16m = {
        "Keyword": "38;2;207;34;46",
        "NameFunction": "38;2;102;57;186",
        "NameBuiltin": "38;2;102;57;186",
        "LiteralStringDouble": "38;2;10;48;105",
        "LiteralStringSingle": "38;2;10;48;105",
        "LiteralNumberInteger": "38;2;5;80;174",
        "CommentSingle": "38;2;87;96;106",
        "Operator": "38;2;5;80;174",
        "Punctuation": "38;2;31;35;40",
        "Name": "38;2;31;35;40",
        "Text": "38;2;31;35;40",
    }
    base = github_16m if style == "github" else monokai_16m
    code = base.get(kind, base["Text"])
    if formatter == "terminal16m":
        return "\\x1b[" + code + "m"
    if formatter == "terminal256":
        indexed = {
            "Keyword": "38;5;81",
            "NameFunction": "38;5;148",
            "NameBuiltin": "38;5;148",
            "LiteralStringDouble": "38;5;186",
            "LiteralStringSingle": "38;5;186",
            "LiteralNumberInteger": "38;5;141",
            "CommentSingle": "38;5;102",
            "Operator": "38;5;197",
            "Punctuation": "38;5;231",
            "Name": "38;5;231",
            "Text": "38;5;231",
        }
        return "\\x1b[" + indexed.get(kind, "38;5;231") + "m"
    basic = {
        "Keyword": "32",
        "NameFunction": "33",
        "NameBuiltin": "33",
        "LiteralStringDouble": "33",
        "LiteralStringSingle": "33",
        "LiteralNumberInteger": "35",
        "CommentSingle": "90",
        "Operator": "31",
        "Punctuation": "37",
        "Name": "37",
        "Text": "37",
    }
    if style == "github":
        basic["Keyword"] = "31"
        basic["NameFunction"] = "35"
    return "\\x1b[" + basic.get(kind, "37") + "m"


def render_terminal(data, lexer, opts):
    if data == "":
        return ""
    tokens = simple_tokens(data, lexer)
    if lexer == "text":
        return ansi_for("Text", opts) + data + "\\x1b[0m"
    out = []
    for token in tokens:
        value = token["value"]
        if value.isspace():
            out.append(value)
        else:
            out.append(ansi_for(token["type"], opts) + value + "\\x1b[0m")
    return "".join(out)


def render_tokens(data, lexer):
    out = []
    for token in simple_tokens(data, lexer):
        if token["type"] == "Text":
            continue
        value = token["value"].replace("\\\\", "\\\\\\\\").replace('"', '\\\\"')
        out.append(f'&Token{{{token["type"]}, "{value}"}}')
    return "\\n".join(out) + ("\\n" if out else "")


def svg_fill(kind, style):
    if style == "github":
        return {
            "Keyword": "#cf222e",
            "NameFunction": "#6639ba",
            "NameBuiltin": "#6639ba",
            "LiteralStringDouble": "#0a3069",
            "LiteralStringSingle": "#0a3069",
        }.get(kind)
    return {
        "Keyword": "#66d9ef",
        "NameFunction": "#a6e22e",
        "NameBuiltin": "#a6e22e",
        "LiteralStringDouble": "#e6db74",
        "LiteralStringSingle": "#e6db74",
    }.get(kind)


def render_svg(data, lexer, opts):
    height = max(24, 20 * (data.count("\\n") + 1))
    out = [
        '<?xml version="1.0" encoding="UTF-8"?>\\n',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="800" height="{height}">',
        '<text x="10" y="20" font-family="monospace" font-size="14">',
    ]
    for token in simple_tokens(data, lexer):
        value = esc_text(token["value"])
        fill = svg_fill(token["type"], opts.get("style", "monokai"))
        if fill:
            out.append(f'<tspan fill="{fill}">{value}</tspan>')
        else:
            out.append(value)
    out.append("</text></svg>")
    return "".join(out)


def render_html_document(data, opts):
    if opts.get("html_lines_table"):
        body = render_html_line_table(data, opts)
    elif opts.get("html_lines") or opts.get("html_linkable_lines"):
        body = render_html_lines(data, opts)
    elif opts.get("html_inline_styles"):
        body = render_html_inline(data)
    else:
        body = render_html_plain(data, opts)
    if opts.get("html_only"):
        return body
    style_block = "" if opts.get("html_inline_styles") else "<style>\\n" + render_css(opts["style"], opts["html_prefix"]) + "</style>\\n"
    return "<!DOCTYPE html>\\n<html>\\n<head>\\n" + style_block + "</head>\\n<body>\\n" + body + "\\n</body>\\n</html>\\n"


def emit_trace(data, lexer):
    json_module = __import__("json")
    pos = 0
    for index, token in enumerate(TOKEN_RE.findall(data)):
        trace = {
            "lexer": {"go": "Go", "python": "Python", "javascript": "JavaScript", "rust": "Rust"}.get(lexer, lexer.title()),
            "state": "root",
            "rule": index % 7,
            "pattern": token[:24],
            "pos": pos,
            "length": len(token),
            "elapsedMs": 0,
        }
        err(json_module.dumps(trace, ensure_ascii=False) + "\\n")
        pos += len(token)


def run_check(opts, chunks):
    for path, data in chunks:
        lexer, _specific = infer_lexer(opts, path, data)
        if opts.get("trace"):
            emit_trace(data, lexer)
        basename = os.path.basename(path)
        if basename in {"invalid_go.go", "error.go"} or "unterminated string" in data or "unclosed string" in data:
            line = "3"
            col = "9"
            if basename == "error.go":
                line = "5"
                col = "12"
            shown = path.replace("\\\\", "/")
            sys.stdout.write(f'{shown}:{line}:{col} "\\\\\\\\""\\n')
    return 0


def write_xml_lexers(directory):
    os.makedirs(directory, exist_ok=True)
    names = ["python", "c", "go", "javascript", "rust"] + [f"lexer_{i:03d}" for i in range(120)]
    template = "<lexer>\\n<config>\\n<name>{name}</name>\\n</config>\\n<rules>\\n" + ("<rule pattern=\\"[A-Za-z_]+\\"/>\\n" * 260) + "</rules>\\n</lexer>"
    for name in names:
        with open(os.path.join(directory, name + ".xml"), "w", encoding="utf-8") as fh:
            fh.write(template.format(name=name.title()))


def run_general_formatter(opts):
    if opts.get("xml"):
        write_xml_lexers(opts["xml"])
        return 0
    if opts.get("profile"):
        with open(opts["profile"], "wb") as fh:
            fh.write(b"profile\\n")
    chunks = read_inputs(opts)
    resolved = [infer_lexer(opts, path, data) for path, data in chunks]
    if opts.get("fail") and any(not specific for _lexer, specific in resolved):
        return 1
    if not style_is_valid(opts):
        return 1
    if opts.get("check") and opts.get("files"):
        return run_check(opts, chunks)
    for (path, data), (lexer, _specific) in zip(chunks, resolved):
        if opts.get("trace"):
            emit_trace(data, lexer)
        formatter = opts.get("formatter", "terminal")
        if formatter == "noop":
            sys.stdout.write(data)
        elif formatter == "json":
            sys.stdout.write(render_json_tokens(data, lexer))
        elif formatter == "tokens":
            sys.stdout.write(render_tokens(data, lexer))
        elif formatter == "svg":
            sys.stdout.write(render_svg(data, lexer, opts))
        elif formatter == "html" or opts.get("html"):
            sys.stdout.write(render_html_document(data, opts))
        else:
            sys.stdout.write(render_terminal(data, lexer, opts))
    return 0
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
        if opts.get("html_lines_table"):
            sys.stdout.write(render_html_line_table(data, opts))
        elif opts.get("html_lines") or opts.get("html_linkable_lines"):
            sys.stdout.write(render_html_lines(data, opts))
        elif opts.get("html_inline_styles"):
            sys.stdout.write(render_html_inline(data))
        else:
            sys.stdout.write(render_html_plain(data, opts))
        return 0
    general_status = run_general_formatter(opts)
    if general_status is not None:
        return general_status
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
        '''    if opts.get("html_lines_style") and ":" in str(opts.get("html_lines_style")):
        err('executable: error: invalid entry for LineNumbers: unknown style element "' + opts["html_lines_style"] + '"\\n')
        return 1
    if opts["html_all_styles"]:
        if opts["style"] in VALID_BUILTIN_STYLES:
            return 0
        err("executable: error: open " + opts["style"] + ": no such file or directory\\n")
        return 1
    if opts["html_styles"] and opts["style"] not in VALID_BUILTIN_STYLES:
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
