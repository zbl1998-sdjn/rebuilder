"""Domain-specific adaptive probe fixtures."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import PurePosixPath

from core.data_models import TestCase

SUPPORTED_DOMAINS = frozenset(
    {
        "archive_compression",
        "binary_hexdump",
        "csv_table",
        "find_replace",
        "filesystem_tool",
        "html_selector",
        "go_dependency_report",
        "json_transform",
        "network_ping",
        "syntax_highlighter",
        "terminal_animation",
        "terminal_ui",
    }
)


def normalize_profile_domains(
    profile: dict,
    *,
    supported_domains: Iterable[str],
    excluded_domains: Iterable[str],
) -> list[str]:
    supported = {
        domain.strip().lower()
        for domain in supported_domains
        if isinstance(domain, str) and domain.strip()
    }
    excluded = {
        domain.strip().lower()
        for domain in excluded_domains
        if isinstance(domain, str) and domain.strip()
    }
    ordered: list[str] = []
    primary = profile.get("primary_domain")
    if isinstance(primary, str):
        ordered.append(primary)

    domains = profile.get("domains")
    if isinstance(domains, str):
        ordered.append(domains)
    elif isinstance(domains, Iterable):
        ordered.extend(domain for domain in domains if isinstance(domain, str))

    strategy_pack = profile.get("strategy_pack")
    if isinstance(strategy_pack, dict) and isinstance(strategy_pack.get("domain"), str):
        ordered.append(strategy_pack["domain"])

    unique: list[str] = []
    seen: set[str] = set()
    for domain in ordered:
        normalized = domain.strip().lower()
        if normalized in supported and normalized not in excluded and normalized not in seen:
            unique.append(normalized)
            seen.add(normalized)
    return unique


def json_transform_probes() -> list[TestCase]:
    return [
        TestCase(
            name="adaptive_json_transform_nested_paths",
            stdin='{"users":[{"name":"Ada","active":true},{"name":"Lin","score":1.5e10}],"meta":{"count":2}}\n',
            description=axis(
                "json_transform",
                "nested_paths",
                "nested objects, arrays, bools, and scientific notation",
            ),
        ),
        TestCase(
            name="adaptive_json_transform_array_root",
            stdin='[{"id":1},null,false,"text"]\n',
            description=axis(
                "json_transform",
                "array_root",
                "top-level array and scalar children",
            ),
        ),
        TestCase(
            name="adaptive_json_transform_input_file",
            args=["input.json"],
            input_files=safe_input_files(
                {"input.json": b'{"alpha":{"beta":[0,1]},"empty":{}}\n'}
            ),
            description=axis(
                "json_transform",
                "file_input",
                "positional JSON file input",
            ),
        ),
        TestCase(
            name="adaptive_json_transform_no_sort",
            args=["--no-sort"],
            stdin='{"z":0,"a":1,"m":{"b":2,"a":3}}\n',
            description=axis(
                "json_transform",
                "no_sort",
                "insertion-order preservation mode",
            ),
        ),
        TestCase(
            name="adaptive_json_transform_values_mode",
            args=["--values"],
            stdin=(
                'json.name = "Ada";\n'
                "json.missing = null;\n"
                "json.enabled = false;\n"
            ),
            description=axis(
                "json_transform",
                "values_mode",
                "assignment RHS value rendering",
            ),
        ),
        TestCase(
            name="adaptive_json_transform_json_stream_output",
            args=["--json"],
            stdin='{"User-Agent":"curl/7.43.0","nested":{"x":1},"items":["a"]}\n',
            description=axis(
                "json_transform",
                "json_stream_output",
                "path/value JSON stream output mode",
            ),
        ),
        TestCase(
            name="adaptive_json_transform_stream_records",
            args=["--stream"],
            stdin='{"a":1}\n{"b":[true,null]}\n',
            description=axis(
                "json_transform",
                "stream_records",
                "newline-delimited JSON records as indexed array paths",
            ),
        ),
        TestCase(
            name="adaptive_json_transform_ungron_sparse_array",
            args=["--ungron"],
            stdin=(
                "json.likes = [];\n"
                'json.likes[0] = "code";\n'
                'json.likes[2] = "meat";\n'
            ),
            description=axis(
                "json_transform",
                "ungron_sparse_array",
                "assignment-to-JSON sparse array null padding",
            ),
        ),
        TestCase(
            name="adaptive_json_transform_json_stream_ungron",
            args=["--json", "--ungron"],
            stdin='[["likes"],[]]\n[["likes",0],"code"]\n[["likes",2],"meat"]\n',
            description=axis(
                "json_transform",
                "json_stream_ungron",
                "JSON stream path/value records back to JSON",
            ),
        ),
        TestCase(
            name="adaptive_json_transform_invalid_json",
            stdin='{"broken": [1, 2,}\n',
            description=axis(
                "json_transform",
                "invalid_json",
                "parser error wording and exit behavior",
            ),
        ),
    ]

def html_selector_probes() -> list[TestCase]:
    html = (
        '<!doctype html><html><head><title>T</title><base href="https://example.com/base/">'
        "<script>x()</script></head><body><main id=\"app\">"
        '<a href="/docs">Docs</a><a class="external" href="https://ext.example/x">Ext</a>'
        '<p class="lead">Hello <span>world</span></p><p class="blank"> \n </p>'
        "</main></body></html>\n"
    )
    return [
        TestCase(
            name="adaptive_html_selector_basic_selector",
            args=["main"],
            stdin=html,
            description=axis(
                "html_selector",
                "basic_selector",
                "element selector output",
            ),
        ),
        TestCase(
            name="adaptive_html_selector_attribute_selector",
            args=["a[href]"],
            stdin=html,
            description=axis(
                "html_selector",
                "attribute_selector",
                "attribute predicate selection",
            ),
        ),
        TestCase(
            name="adaptive_html_selector_descendant_selector",
            args=["main span"],
            stdin=html,
            description=axis(
                "html_selector",
                "descendant_selector",
                "nested text and newline placement",
            ),
        ),
        TestCase(
            name="adaptive_html_selector_text_mode",
            args=["--text", "main"],
            stdin=html,
            description=axis(
                "html_selector",
                "text_mode",
                "text-only extraction from selected nodes",
            ),
        ),
        TestCase(
            name="adaptive_html_selector_ignore_whitespace",
            args=["--text", "--ignore-whitespace", "main"],
            stdin=html,
            description=axis(
                "html_selector",
                "ignore_whitespace",
                "text mode whitespace-only node filtering",
            ),
        ),
        TestCase(
            name="adaptive_html_selector_attribute_output",
            args=["--attribute", "href", "a"],
            stdin=html,
            description=axis(
                "html_selector",
                "attribute_output",
                "attribute value extraction for matched elements",
            ),
        ),
        TestCase(
            name="adaptive_html_selector_detect_base_attribute",
            args=["--detect-base", "--attribute", "href", "a"],
            stdin=html,
            description=axis(
                "html_selector",
                "detect_base_attribute",
                "relative link resolution from base tag",
            ),
        ),
        TestCase(
            name="adaptive_html_selector_base_option_attribute",
            args=["--base", "https://fallback.example/root/", "--attribute", "href", "a"],
            stdin=html,
            description=axis(
                "html_selector",
                "base_option_attribute",
                "relative link resolution from explicit base option",
            ),
        ),
        TestCase(
            name="adaptive_html_selector_comma_selector",
            args=["#app, a.external"],
            stdin=html,
            description=axis(
                "html_selector",
                "comma_selector",
                "comma-separated selector union in document order",
            ),
        ),
        TestCase(
            name="adaptive_html_selector_remove_nodes",
            args=["--remove-nodes", "script", "main"],
            stdin=html,
            description=axis(
                "html_selector",
                "remove_nodes",
                "mutation before selection",
            ),
        ),
        TestCase(
            name="adaptive_html_selector_pretty",
            args=["-p", "main"],
            stdin=html,
            description=axis(
                "html_selector",
                "pretty",
                "pretty-print formatting mode",
            ),
        ),
        TestCase(
            name="adaptive_html_selector_input_output_file",
            args=["--filename", "input.html", "--output", "out.html", "a"],
            input_files=safe_input_files({"input.html": html.encode("utf-8")}),
            description=axis(
                "html_selector",
                "input_output_file",
                "named input file and output file behavior",
            ),
        ),
        TestCase(
            name="adaptive_html_selector_no_selector",
            stdin=html,
            description=axis(
                "html_selector",
                "no_selector",
                "missing selector error behavior",
            ),
        ),
        TestCase(
            name="adaptive_html_selector_no_selector_fragment",
            stdin='<a href="/x">link</a><p>Hello</p>\n',
            description=axis(
                "html_selector",
                "no_selector_fragment",
                "default html selector wraps body fragments",
            ),
        ),
        TestCase(
            name="adaptive_html_selector_dash_selector",
            args=["-"],
            stdin=html,
            description=axis(
                "html_selector",
                "dash_selector",
                "dash as selector argument rather than stdin marker",
            ),
        ),
        TestCase(
            name="adaptive_html_selector_output_dash_selector",
            args=["--output", "out.html", "-"],
            stdin=html,
            description=axis(
                "html_selector",
                "output_dash_selector",
                "output-file side effects when dash selector panics",
            ),
        ),
        TestCase(
            name="adaptive_html_selector_malformed_html",
            args=["p"],
            stdin="<html><body><p>unterminated<div data-x='1'>tail\n",
            description=axis(
                "html_selector",
                "malformed_html",
                "recovery around malformed markup",
            ),
        ),
    ]

def syntax_highlighter_probes() -> list[TestCase]:
    python_source = (
        "import sys\n\n"
        "def greet(name):\n"
        "    print(f'hello {name}')\n\n"
        "if __name__ == '__main__':\n"
        "    greet(sys.argv[1] if len(sys.argv) > 1 else 'world')\n"
    )
    javascript_source = (
        "const items = [1, 2, 3];\n"
        "console.log(items.map((value) => value * 2).join(','));\n"
    )
    html_source = (
        "<!doctype html>\n"
        "<html><body><script>const x = 1 < 2;</script><p>hello</p></body></html>\n"
    )
    bounded_source = "\n".join(
        f"def generated_{index}(): return {index}"
        for index in range(200)
    ) + "\n"
    return [
        TestCase(
            name="adaptive_syntax_highlighter_invalid_formatter",
            args=["--formatter", "not_a_formatter"],
            stdin=python_source,
            description=axis(
                "syntax_highlighter",
                "invalid_formatter",
                "formatter validation and diagnostic wording",
            ),
        ),
        TestCase(
            name="adaptive_syntax_highlighter_lexer_stdin",
            args=["--lexer", "python"],
            stdin=python_source,
            description=axis(
                "syntax_highlighter",
                "lexer_stdin",
                "explicit lexer over stdin source",
            ),
        ),
        TestCase(
            name="adaptive_syntax_highlighter_filename_stdin",
            args=["--filename", "demo.py"],
            stdin=python_source,
            description=axis(
                "syntax_highlighter",
                "filename_stdin",
                "filename-based lexer inference for stdin",
            ),
        ),
        TestCase(
            name="adaptive_syntax_highlighter_terminal16m_formatter",
            args=["--formatter", "terminal16m", "--lexer", "javascript"],
            stdin=javascript_source,
            description=axis(
                "syntax_highlighter",
                "terminal16m_formatter",
                "terminal truecolor formatter alias over stdin",
            ),
        ),
        TestCase(
            name="adaptive_syntax_highlighter_tokens_formatter",
            args=["--formatter", "tokens", "--lexer", "python"],
            stdin=python_source,
            description=axis(
                "syntax_highlighter",
                "tokens_formatter",
                "token-stream formatter output mode",
            ),
        ),
        TestCase(
            name="adaptive_syntax_highlighter_noop_formatter",
            args=["--formatter", "noop", "--lexer", "python"],
            stdin=python_source,
            description=axis(
                "syntax_highlighter",
                "noop_formatter",
                "formatter mode that preserves raw source",
            ),
        ),
        TestCase(
            name="adaptive_syntax_highlighter_html_inline_file",
            args=["--html", "--html-only", "--html-inline-styles", "snippet.html"],
            input_files=safe_input_files({"snippet.html": html_source.encode("utf-8")}),
            description=axis(
                "syntax_highlighter",
                "html_inline_file",
                "HTML formatter over file input with inline styles",
            ),
        ),
        TestCase(
            name="adaptive_syntax_highlighter_html_line_table",
            args=[
                "--html",
                "--html-only",
                "--html-lines",
                "--html-lines-table",
                "--html-linkable-lines",
                "--html-highlight",
                "2",
                "snippet.py",
            ],
            input_files=safe_input_files({"snippet.py": python_source.encode("utf-8")}),
            description=axis(
                "syntax_highlighter",
                "html_line_table",
                "line-number table, linkable ids, and highlighted line output",
            ),
        ),
        TestCase(
            name="adaptive_syntax_highlighter_style_css",
            args=["--html-styles", "--style", "github"],
            description=axis(
                "syntax_highlighter",
                "style_css",
                "style stylesheet output without source input",
            ),
        ),
        TestCase(
            name="adaptive_syntax_highlighter_multi_file",
            args=["--lexer", "python", "a.py", "b.py"],
            input_files=safe_input_files(
                {
                    "a.py": b"print('a')\n",
                    "b.py": b"print('b')\n",
                }
            ),
            description=axis(
                "syntax_highlighter",
                "multi_file",
                "multiple file operands with shared lexer selection",
            ),
        ),
        TestCase(
            name="adaptive_syntax_highlighter_explicit_dash_stdin",
            args=["--lexer", "python", "-"],
            stdin=python_source,
            description=axis(
                "syntax_highlighter",
                "explicit_dash_stdin",
                "dash operand as explicit stdin marker",
            ),
        ),
        TestCase(
            name="adaptive_syntax_highlighter_bounded_large_file",
            args=["--html", "--html-only", "--html-lines", "large.py"],
            input_files=safe_input_files({"large.py": bounded_source.encode("utf-8")}),
            description=axis(
                "syntax_highlighter",
                "bounded_large_file",
                "bounded large source file rendering without runaway output or timeout",
            ),
        ),
    ]

def go_dependency_report_probes() -> list[TestCase]:
    return [
        TestCase(
            name="adaptive_go_dependency_report_help_flag",
            args=["-help"],
            description=axis(
                "go_dependency_report",
                "help_flag",
                "Go flag package help behavior",
            ),
        ),
        TestCase(
            name="adaptive_go_dependency_report_direct_update",
            stdin=(
                '{"Path":"github.com/acme/lib","Version":"v1.2.3",'
                '"Update":{"Path":"github.com/acme/lib","Version":"v1.4.0"},"Indirect":false}\n'
            ),
            description=axis(
                "go_dependency_report",
                "direct_update",
                "direct module with available update",
            ),
        ),
        TestCase(
            name="adaptive_go_dependency_report_indirect_dependency",
            stdin=(
                '{"Path":"github.com/acme/indirect","Version":"v0.9.0",'
                '"Update":{"Path":"github.com/acme/indirect","Version":"v1.0.0"},"Indirect":true}\n'
            ),
            description=axis(
                "go_dependency_report",
                "indirect_dependency",
                "indirect marker rendering",
            ),
        ),
        TestCase(
            name="adaptive_go_dependency_report_no_update",
            stdin='{"Path":"github.com/acme/current","Version":"v2.0.0","Indirect":false}\n',
            description=axis(
                "go_dependency_report",
                "no_update",
                "current dependency filtering",
            ),
        ),
        TestCase(
            name="adaptive_go_dependency_report_multiple_records",
            stdin=(
                '{"Path":"github.com/acme/a","Version":"v1.0.0","Update":{"Path":"github.com/acme/a","Version":"v1.1.0"}}\n'
                '{"Path":"github.com/acme/b","Version":"v0.1.0","Update":{"Path":"github.com/acme/b","Version":"v0.2.0"},"Indirect":true}\n'
            ),
            description=axis(
                "go_dependency_report",
                "multiple_records",
                "newline-delimited JSON table layout",
            ),
        ),
        TestCase(
            name="adaptive_go_dependency_report_invalid_json",
            stdin='{"Path":"github.com/acme/broken","Version":\n',
            description=axis(
                "go_dependency_report",
                "invalid_json",
                "unexpected EOF handling",
            ),
        ),
    ]

def csv_table_probes() -> list[TestCase]:
    csv_text = 'name,note\nAda,"x,y"\nLin,"line one\nline two"\n'
    tsv_text = "name\tscore\nAda\t10\nLin\t9\n"
    small_csv = "name,color,size\nAda,red,S\nLin,blue,M\nGrace,red,S\nKen,red,L\nMia,blue,S\n"
    return [
        TestCase(
            name="adaptive_csv_table_quoted_fields",
            stdin=csv_text,
            description=axis(
                "csv_table",
                "quoted_fields",
                "quoted delimiters and embedded newlines",
            ),
        ),
        TestCase(
            name="adaptive_csv_table_explicit_stdin",
            args=["-"],
            stdin=csv_text,
            description=axis(
                "csv_table",
                "explicit_stdin",
                "explicit '-' stdin marker",
            ),
        ),
        TestCase(
            name="adaptive_csv_table_file_input",
            args=["input.csv"],
            input_files=safe_input_files({"input.csv": csv_text.encode("utf-8")}),
            description=axis(
                "csv_table",
                "file_input",
                "positional CSV file input",
            ),
        ),
        TestCase(
            name="adaptive_csv_table_delimiter_mode",
            args=["--delimiter", "\t"],
            stdin=tsv_text,
            description=axis(
                "csv_table",
                "delimiter_mode",
                "non-comma delimiter mode",
            ),
        ),
        TestCase(
            name="adaptive_csv_table_select_header",
            args=["select", "name"],
            stdin=csv_text,
            description=axis(
                "csv_table",
                "select_header",
                "subcommand column selection by header",
            ),
        ),
        TestCase(
            name="adaptive_csv_table_sample_rows",
            args=["sample", "2"],
            stdin="name,score\nAda,10\nLin,9\nGrace,8\n",
            description=axis(
                "csv_table",
                "sample_rows",
                "sample subcommand row retention",
            ),
        ),
        TestCase(
            name="adaptive_csv_table_headers_command",
            args=["headers"],
            stdin=small_csv,
            description=axis(
                "csv_table",
                "headers_command",
                "headers subcommand numbering and order",
            ),
        ),
        TestCase(
            name="adaptive_csv_table_count_command",
            args=["count"],
            stdin=small_csv,
            description=axis(
                "csv_table",
                "count_command",
                "row count excluding the header",
            ),
        ),
        TestCase(
            name="adaptive_csv_table_frequency_stable_order",
            args=["frequency"],
            stdin=small_csv,
            description=axis(
                "csv_table",
                "frequency_stable_order",
                "frequency output count ordering and exact observed tie order; "
                "do not assume first-seen or lexical ties",
            ),
        ),
        TestCase(
            name="adaptive_csv_table_index_file_output",
            args=["index", "data.csv"],
            input_files=safe_input_files({"data.csv": small_csv.encode("utf-8")}),
            description=axis(
                "csv_table",
                "index_file_output",
                "index subcommand output-file side effect",
            ),
        ),
        TestCase(
            name="adaptive_csv_table_join_cross_invalid_arity",
            args=["join", "--cross", "left.csv", "right.csv"],
            input_files=safe_input_files(
                {
                    "left.csv": b"id,val\n1,a\n2,b\n",
                    "right.csv": b"id,name\n1,x\n2,y\n",
                }
            ),
            description=axis(
                "csv_table",
                "join_cross_invalid_arity",
                "join --cross still enforces documented positional arity",
            ),
        ),
    ]

def binary_hexdump_probes() -> list[TestCase]:
    binary_fixture = bytes([0, 1, 2, 9, 10, 13, 31, 32, 65, 66, 67, 126, 127, 128, 255])
    return [
        TestCase(
            name="adaptive_binary_hexdump_empty_stdin",
            stdin="",
            description=axis(
                "binary_hexdump",
                "empty_stdin",
                "no-file no-content rendering",
            ),
        ),
        TestCase(
            name="adaptive_binary_hexdump_file_bytes",
            args=["sample.bin"],
            input_files=safe_input_files({"sample.bin": binary_fixture}),
            description=axis(
                "binary_hexdump",
                "file_bytes",
                "raw byte rendering and character table",
            ),
        ),
        TestCase(
            name="adaptive_binary_hexdump_length_skip",
            args=["--length", "8", "--skip", "4", "sample.bin"],
            input_files=safe_input_files({"sample.bin": binary_fixture}),
            description=axis(
                "binary_hexdump",
                "length_skip",
                "byte offset after skip before length",
            ),
        ),
        TestCase(
            name="adaptive_binary_hexdump_block_panels",
            args=["--block-size", "8", "--panels", "2", "sample.bin"],
            input_files=safe_input_files({"sample.bin": binary_fixture}),
            description=axis(
                "binary_hexdump",
                "block_panels",
                "row grouping and panel spacing",
            ),
        ),
        TestCase(
            name="adaptive_binary_hexdump_no_characters",
            args=["--no-characters", "--border", "none", "sample.bin"],
            input_files=safe_input_files({"sample.bin": binary_fixture}),
            description=axis(
                "binary_hexdump",
                "no_characters",
                "border and character-column suppression",
            ),
        ),
        TestCase(
            name="adaptive_binary_hexdump_invalid_color_scheme",
            args=["--color-scheme", "classic", "sample.bin"],
            input_files=safe_input_files({"sample.bin": binary_fixture}),
            description=axis(
                "binary_hexdump",
                "invalid_color_scheme",
                "clap enum diagnostic",
            ),
        ),
    ]

def archive_compression_probes() -> list[TestCase]:
    empty_zip = b"PK\x05\x06" + (b"\x00" * 18)
    return [
        TestCase(
            name="adaptive_archive_compression_clap_required_flags",
            args=["--charset", "ab"],
            description=axis(
                "archive_compression",
                "clap_required_flags",
                "missing required archive/password flags",
            ),
        ),
        TestCase(
            name="adaptive_archive_compression_clap_required_input_with_range",
            args=[
                "--charset",
                "l",
                "--minPasswordLen",
                "1",
                "--maxPasswordLen",
                "3",
            ],
            description=axis(
                "archive_compression",
                "clap_required_input_with_range",
                "missing input file while other password flags are present",
            ),
        ),
        TestCase(
            name="adaptive_archive_compression_corrupt_archive",
            args=["--inputFile", "corrupt.zip"],
            input_files=safe_input_files({"corrupt.zip": b"not a zip archive\n"}),
            description=axis(
                "archive_compression",
                "corrupt_archive",
                "corrupt archive diagnostics",
            ),
        ),
        TestCase(
            name="adaptive_archive_compression_empty_archive",
            args=["--inputFile", "empty.zip"],
            input_files=safe_input_files({"empty.zip": empty_zip}),
            description=axis(
                "archive_compression",
                "empty_archive",
                "empty archive member handling",
            ),
        ),
        TestCase(
            name="adaptive_archive_compression_missing_file",
            args=["--inputFile", "missing.zip"],
            description=axis(
                "archive_compression",
                "missing_file",
                "missing archive path diagnostics",
            ),
        ),
        TestCase(
            name="adaptive_archive_compression_password_charset",
            args=[
                "--inputFile",
                "empty.zip",
                "--charset",
                "ab",
                "--minPasswordLen",
                "1",
                "--maxPasswordLen",
                "2",
            ],
            input_files=safe_input_files({"empty.zip": empty_zip}),
            description=axis(
                "archive_compression",
                "password_charset",
                "bounded charset/password search options",
            ),
        ),
        TestCase(
            name="adaptive_archive_compression_password_dictionary",
            args=["--inputFile", "empty.zip", "--passwordDictionary", "words.txt"],
            input_files=safe_input_files(
                {
                    "empty.zip": empty_zip,
                    "words.txt": b"secret\npassword\n",
                }
            ),
            description=axis(
                "archive_compression",
                "password_dictionary",
                "dictionary-file password search branch",
            ),
        ),
        TestCase(
            name="adaptive_archive_compression_charset_file",
            args=[
                "--inputFile",
                "empty.zip",
                "--charsetFile",
                "charset.txt",
                "--minPasswordLen",
                "1",
                "--maxPasswordLen",
                "2",
            ],
            input_files=safe_input_files(
                {
                    "empty.zip": empty_zip,
                    "charset.txt": b"ab\n",
                }
            ),
            description=axis(
                "archive_compression",
                "charset_file",
                "charset loaded from file with password bounds",
            ),
        ),
    ]

def find_replace_probes() -> list[TestCase]:
    return [
        TestCase(
            name="adaptive_find_replace_basic_regex_stdin",
            args=["a+", "X"],
            stdin="aa baaa\n",
            description=axis(
                "find_replace",
                "basic_regex_stdin",
                "regex replacement over stdin",
            ),
        ),
        TestCase(
            name="adaptive_find_replace_capture_groups",
            args=[r"(\w+)-(\d+)", "$2:$1"],
            stdin="item-42 other-7\n",
            description=axis(
                "find_replace",
                "capture_groups",
                "dollar capture replacement expansion",
            ),
        ),
        TestCase(
            name="adaptive_find_replace_adjacent_indexed_captures",
            args=[
                r"(\w+)\s+\+(\w+)\s+(\w+)",
                "cmd: $1, channel: $2, subcmd: $3",
            ],
            stdin="cargo +nightly watch\n",
            description=axis(
                "find_replace",
                "adjacent_indexed_captures",
                "numbered captures embedded in replacement text",
            ),
        ),
        TestCase(
            name="adaptive_find_replace_empty_captures",
            args=[r"(a*)(b*)", "[$1][$2]"],
            stdin="ab\n",
            description=axis(
                "find_replace",
                "empty_captures",
                "empty capture and zero-length match behavior",
            ),
        ),
        TestCase(
            name="adaptive_find_replace_dollar_escape",
            args=["a", "$$"],
            stdin="a a\n",
            description=axis(
                "find_replace",
                "dollar_escape",
                "literal dollar replacement escaping",
            ),
        ),
        TestCase(
            name="adaptive_find_replace_dollar_numeric_literal",
            args=["a", "$$1"],
            stdin="a\n",
            description=axis(
                "find_replace",
                "dollar_numeric_literal",
                "literal dollar followed by numeric text",
            ),
        ),
        TestCase(
            name="adaptive_find_replace_dollar_prefix_literal",
            args=["foo", "$$bar"],
            stdin="foo\n",
            description=axis(
                "find_replace",
                "dollar_prefix_literal",
                "literal dollar followed by replacement text",
            ),
        ),
        TestCase(
            name="adaptive_find_replace_fixed_string",
            args=["-F", "a.b", "X"],
            stdin="a.b axb\n",
            description=axis(
                "find_replace",
                "fixed_string",
                "literal search mode without regex expansion",
            ),
        ),
        TestCase(
            name="adaptive_find_replace_file_input",
            args=["cat", "dog", "input.txt"],
            input_files=safe_input_files({"input.txt": b"cat\nwildcat\n"}),
            description=axis(
                "find_replace",
                "file_input",
                "positional file transformation side effects",
            ),
        ),
        TestCase(
            name="adaptive_find_replace_preview_file_input",
            args=["--preview", "cat", "dog", "input.txt"],
            input_files=safe_input_files({"input.txt": b"cat\nwildcat\n"}),
            description=axis(
                "find_replace",
                "preview_file_input",
                "preview mode emits observed output without rewriting files",
            ),
        ),
        TestCase(
            name="adaptive_find_replace_invalid_dash_file",
            args=["hello", "world", "-"],
            stdin="hello there",
            description=axis(
                "find_replace",
                "invalid_dash_file",
                "dash passed as an explicit file operand",
            ),
        ),
        TestCase(
            name="adaptive_find_replace_missing_file",
            args=["foo", "bar", "missing.txt"],
            description=axis(
                "find_replace",
                "missing_file",
                "missing file operand diagnostic",
            ),
        ),
        TestCase(
            name="adaptive_find_replace_invalid_regex",
            args=["[", "x"],
            stdin="abc\n",
            description=axis(
                "find_replace",
                "invalid_regex",
                "regex parser diagnostic and exit behavior",
            ),
        ),
        TestCase(
            name="adaptive_find_replace_unsupported_lookaround",
            args=["foo(?=bar)", "XXX"],
            stdin="foobar\n",
            description=axis(
                "find_replace",
                "unsupported_lookaround",
                "Rust regex-style unsupported look-around diagnostic",
            ),
        ),
    ]

def filesystem_tool_probes() -> list[TestCase]:
    tree = {
        "dir/a.txt": b"alpha\n",
        "dir/nested/b.txt": b"bravo\n",
        "dir/.hidden": b"secret\n",
        "empty/.keep": b"",
    }
    return [
        TestCase(
            name="adaptive_filesystem_tool_file_input",
            args=["dir/a.txt"],
            input_files=safe_input_files(tree),
            description=axis(
                "filesystem_tool",
                "file_input",
                "single file path behavior",
            ),
        ),
        TestCase(
            name="adaptive_filesystem_tool_directory_input",
            args=["dir"],
            input_files=safe_input_files(tree),
            description=axis(
                "filesystem_tool",
                "directory_input",
                "directory traversal and ordering",
            ),
        ),
        TestCase(
            name="adaptive_filesystem_tool_hidden_file",
            args=["dir/.hidden"],
            input_files=safe_input_files(tree),
            description=axis(
                "filesystem_tool",
                "hidden_file",
                "hidden file path handling",
            ),
        ),
        TestCase(
            name="adaptive_filesystem_tool_missing_path",
            args=["missing.txt"],
            description=axis(
                "filesystem_tool",
                "missing_path",
                "missing path diagnostic",
            ),
        ),
        TestCase(
            name="adaptive_filesystem_tool_recursive_flag",
            args=["--recursive", "dir"],
            input_files=safe_input_files(tree),
            description=axis(
                "filesystem_tool",
                "recursive_flag",
                "recursive directory flag behavior",
            ),
        ),
        TestCase(
            name="adaptive_filesystem_tool_multiple_paths",
            args=["dir/a.txt", "dir/nested/b.txt"],
            input_files=safe_input_files(tree),
            description=axis(
                "filesystem_tool",
                "multiple_paths",
                "multiple positional paths",
            ),
        ),
        TestCase(
            name="adaptive_filesystem_tool_stdin_marker",
            args=["-"],
            stdin="stdin payload\n",
            description=axis(
                "filesystem_tool",
                "stdin_marker",
                "dash stdin marker versus path handling",
            ),
        ),
    ]

def terminal_animation_probes() -> list[TestCase]:
    return [
        TestCase(
            name="adaptive_terminal_animation_term_unknown",
            env_vars={"TERM": "unknown"},
            description=axis(
                "terminal_animation",
                "term_unknown",
                "unknown terminal capability error",
            ),
        ),
        TestCase(
            name="adaptive_terminal_animation_term_missing",
            env_vars={"TERM": ""},
            description=axis(
                "terminal_animation",
                "term_missing",
                "missing TERM environment branch",
            ),
        ),
        TestCase(
            name="adaptive_terminal_animation_help_flag",
            args=["-h"],
            description=axis(
                "terminal_animation",
                "help_flag",
                "short help output without animation",
            ),
        ),
        TestCase(
            name="adaptive_terminal_animation_version_flag",
            args=["--version"],
            description=axis(
                "terminal_animation",
                "version_flag",
                "long version flag behavior",
            ),
        ),
        TestCase(
            name="adaptive_terminal_animation_short_version_flag",
            args=["-V"],
            description=axis(
                "terminal_animation",
                "version_flag",
                "short version flag behavior",
            ),
        ),
        TestCase(
            name="adaptive_terminal_animation_invalid_flag",
            args=["--definitely-invalid"],
            description=axis(
                "terminal_animation",
                "invalid_flag",
                "invalid flag diagnostic without help fallthrough",
            ),
        ),
        TestCase(
            name="adaptive_terminal_animation_small_screen_error",
            env_vars={"TERM": "unknown", "COLUMNS": "40", "LINES": "12"},
            description=axis(
                "terminal_animation",
                "small_screen_error",
                "terminal-size env handling on noninteractive error path",
            ),
        ),
    ]

def terminal_ui_probes() -> list[TestCase]:
    return [
        TestCase(
            name="adaptive_terminal_ui_no_tty",
            description=axis(
                "terminal_ui",
                "no_tty",
                "noninteractive terminal output branch",
            ),
        ),
        TestCase(
            name="adaptive_terminal_ui_term_unknown",
            env_vars={"TERM": "unknown"},
            description=axis(
                "terminal_ui",
                "term_unknown",
                "unknown terminal environment behavior",
            ),
        ),
        TestCase(
            name="adaptive_terminal_ui_color_disabled",
            env_vars={"NO_COLOR": "1", "TERM": "xterm"},
            description=axis(
                "terminal_ui",
                "color_disabled",
                "color suppression environment branch",
            ),
        ),
        TestCase(
            name="adaptive_terminal_ui_dimensions",
            env_vars={"TERM": "xterm", "COLUMNS": "40", "LINES": "12"},
            description=axis(
                "terminal_ui",
                "dimensions",
                "small terminal dimensions",
            ),
        ),
        TestCase(
            name="adaptive_terminal_ui_help_flag",
            args=["--help"],
            description=axis(
                "terminal_ui",
                "help_flag",
                "help output without terminal rendering",
            ),
        ),
        TestCase(
            name="adaptive_terminal_ui_invalid_flag",
            args=["--definitely-invalid"],
            description=axis(
                "terminal_ui",
                "invalid_flag",
                "unknown option diagnostic",
            ),
        ),
    ]

def network_ping_probes() -> list[TestCase]:
    return [
        TestCase(
            name="adaptive_network_ping_loopback_ipv4",
            args=["-c", "1", "127.0.0.1"],
            description=axis(
                "network_ping",
                "loopback_ipv4",
                "bounded successful local transcript",
            ),
        ),
        TestCase(
            name="adaptive_network_ping_loopback_ipv6",
            args=["-c", "1", "::1"],
            description=axis(
                "network_ping",
                "loopback_ipv6",
                "bounded successful local transcript",
            ),
        ),
        TestCase(
            name="adaptive_network_ping_localhost_name",
            args=["-c", "1", "localhost"],
            description=axis(
                "network_ping",
                "localhost_name",
                "resolver and transcript formatting",
            ),
        ),
        TestCase(
            name="adaptive_network_ping_special_address_error",
            args=["-c", "1", "224.0.0.1"],
            description=axis(
                "network_ping",
                "special_address_error",
                "multicast network-error branch",
            ),
        ),
        TestCase(
            name="adaptive_network_ping_broadcast_error",
            args=["-c", "1", "255.255.255.255"],
            description=axis(
                "network_ping",
                "special_address_error",
                "broadcast network-error branch",
            ),
        ),
        TestCase(
            name="adaptive_network_ping_link_local_error",
            args=["-c", "1", "169.254.1.1"],
            description=axis(
                "network_ping",
                "special_address_error",
                "link-local network-error branch",
            ),
        ),
        TestCase(
            name="adaptive_network_ping_count_parse_error",
            args=["-c", "abc", "localhost"],
            description=axis(
                "network_ping",
                "count_parse_error",
                "flag alias and parse diagnostics",
            ),
        ),
        TestCase(
            name="adaptive_network_ping_missing_host",
            args=["-c", "1"],
            description=axis(
                "network_ping",
                "missing_host",
                "required host diagnostics",
            ),
        ),
        TestCase(
            name="adaptive_network_ping_multiple_hosts",
            args=["-c", "1", "127.0.0.1", "127.0.0.2"],
            description=axis(
                "network_ping",
                "multiple_hosts",
                "extra positional host diagnostics",
            ),
        ),
    ]

def axis(domain: str, axis: str, detail: str) -> str:
    return f"smoke_contract:{domain}.{axis} adaptive_axis:{domain}.{axis} {detail}"

def safe_input_files(files: dict[str, bytes]) -> dict[str, bytes]:
    for path in files:
        posix_path = PurePosixPath(path)
        if path != posix_path.as_posix() or posix_path.is_absolute() or ".." in posix_path.parts:
            raise ValueError(f"unsafe adaptive probe input path: {path}")
    return files


DOMAIN_PROBE_BUILDERS: dict[str, Callable[[], list[TestCase]]] = {
    "archive_compression": archive_compression_probes,
    "binary_hexdump": binary_hexdump_probes,
    "csv_table": csv_table_probes,
    "find_replace": find_replace_probes,
    "filesystem_tool": filesystem_tool_probes,
    "go_dependency_report": go_dependency_report_probes,
    "html_selector": html_selector_probes,
    "json_transform": json_transform_probes,
    "network_ping": network_ping_probes,
    "syntax_highlighter": syntax_highlighter_probes,
    "terminal_animation": terminal_animation_probes,
    "terminal_ui": terminal_ui_probes,
}
