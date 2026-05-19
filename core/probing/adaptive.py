"""Domain-aware deterministic probe planning from inferred task profiles."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import PurePosixPath
from typing import Any

from core.data_models import TestCase


class AdaptiveProbePlanner:
    """Plan cleanroom probes for high-signal task-profile domains.

    The planner intentionally does not call ProbeEngine or inspect repository
    identity. It only uses domain labels inferred from docs, CLI help, and
    corpus metadata, then emits deterministic edge cases for that domain.
    """

    SUPPORTED_DOMAINS = {
        "archive_compression",
        "binary_hexdump",
        "csv_table",
        "find_replace",
        "filesystem_tool",
        "html_selector",
        "go_dependency_report",
        "json_transform",
        "network_ping",
        "terminal_animation",
        "terminal_ui",
    }

    def plan(
        self,
        profile: dict,
        documentation: str = "",
        cli_surface: Any = None,
        corpus: Any = None,
    ) -> list[TestCase]:
        del documentation, cli_surface, corpus

        probes: list[TestCase] = []
        for domain in self._domains(profile):
            if domain == "binary_hexdump":
                probes.extend(self._binary_hexdump_probes())
            elif domain == "csv_table":
                probes.extend(self._csv_table_probes())
            elif domain == "find_replace":
                probes.extend(self._find_replace_probes())
            elif domain == "filesystem_tool":
                probes.extend(self._filesystem_tool_probes())
            elif domain == "json_transform":
                probes.extend(self._json_transform_probes())
            elif domain == "html_selector":
                probes.extend(self._html_selector_probes())
            elif domain == "archive_compression":
                probes.extend(self._archive_compression_probes())
            elif domain == "go_dependency_report":
                probes.extend(self._go_dependency_report_probes())
            elif domain == "network_ping":
                probes.extend(self._network_ping_probes())
            elif domain == "terminal_animation":
                probes.extend(self._terminal_animation_probes())
            elif domain == "terminal_ui":
                probes.extend(self._terminal_ui_probes())
        return probes

    def _domains(self, profile: dict) -> list[str]:
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
            if normalized in self.SUPPORTED_DOMAINS and normalized not in seen:
                unique.append(normalized)
                seen.add(normalized)
        return unique

    def _json_transform_probes(self) -> list[TestCase]:
        return [
            TestCase(
                name="adaptive_json_transform_nested_paths",
                stdin='{"users":[{"name":"Ada","active":true},{"name":"Lin","score":1.5e10}],"meta":{"count":2}}\n',
                description=self._axis(
                    "json_transform",
                    "nested_paths",
                    "nested objects, arrays, bools, and scientific notation",
                ),
            ),
            TestCase(
                name="adaptive_json_transform_array_root",
                stdin='[{"id":1},null,false,"text"]\n',
                description=self._axis(
                    "json_transform",
                    "array_root",
                    "top-level array and scalar children",
                ),
            ),
            TestCase(
                name="adaptive_json_transform_input_file",
                args=["input.json"],
                input_files=self._safe_input_files(
                    {"input.json": b'{"alpha":{"beta":[0,1]},"empty":{}}\n'}
                ),
                description=self._axis(
                    "json_transform",
                    "file_input",
                    "positional JSON file input",
                ),
            ),
            TestCase(
                name="adaptive_json_transform_no_sort",
                args=["--no-sort"],
                stdin='{"z":0,"a":1,"m":{"b":2,"a":3}}\n',
                description=self._axis(
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
                description=self._axis(
                    "json_transform",
                    "values_mode",
                    "assignment RHS value rendering",
                ),
            ),
            TestCase(
                name="adaptive_json_transform_json_stream_output",
                args=["--json"],
                stdin='{"User-Agent":"curl/7.43.0","nested":{"x":1},"items":["a"]}\n',
                description=self._axis(
                    "json_transform",
                    "json_stream_output",
                    "path/value JSON stream output mode",
                ),
            ),
            TestCase(
                name="adaptive_json_transform_stream_records",
                args=["--stream"],
                stdin='{"a":1}\n{"b":[true,null]}\n',
                description=self._axis(
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
                description=self._axis(
                    "json_transform",
                    "ungron_sparse_array",
                    "assignment-to-JSON sparse array null padding",
                ),
            ),
            TestCase(
                name="adaptive_json_transform_json_stream_ungron",
                args=["--json", "--ungron"],
                stdin='[["likes"],[]]\n[["likes",0],"code"]\n[["likes",2],"meat"]\n',
                description=self._axis(
                    "json_transform",
                    "json_stream_ungron",
                    "JSON stream path/value records back to JSON",
                ),
            ),
            TestCase(
                name="adaptive_json_transform_invalid_json",
                stdin='{"broken": [1, 2,}\n',
                description=self._axis(
                    "json_transform",
                    "invalid_json",
                    "parser error wording and exit behavior",
                ),
            ),
        ]

    def _html_selector_probes(self) -> list[TestCase]:
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
                description=self._axis(
                    "html_selector",
                    "basic_selector",
                    "element selector output",
                ),
            ),
            TestCase(
                name="adaptive_html_selector_attribute_selector",
                args=["a[href]"],
                stdin=html,
                description=self._axis(
                    "html_selector",
                    "attribute_selector",
                    "attribute predicate selection",
                ),
            ),
            TestCase(
                name="adaptive_html_selector_descendant_selector",
                args=["main span"],
                stdin=html,
                description=self._axis(
                    "html_selector",
                    "descendant_selector",
                    "nested text and newline placement",
                ),
            ),
            TestCase(
                name="adaptive_html_selector_text_mode",
                args=["--text", "main"],
                stdin=html,
                description=self._axis(
                    "html_selector",
                    "text_mode",
                    "text-only extraction from selected nodes",
                ),
            ),
            TestCase(
                name="adaptive_html_selector_ignore_whitespace",
                args=["--text", "--ignore-whitespace", "main"],
                stdin=html,
                description=self._axis(
                    "html_selector",
                    "ignore_whitespace",
                    "text mode whitespace-only node filtering",
                ),
            ),
            TestCase(
                name="adaptive_html_selector_attribute_output",
                args=["--attribute", "href", "a"],
                stdin=html,
                description=self._axis(
                    "html_selector",
                    "attribute_output",
                    "attribute value extraction for matched elements",
                ),
            ),
            TestCase(
                name="adaptive_html_selector_detect_base_attribute",
                args=["--detect-base", "--attribute", "href", "a"],
                stdin=html,
                description=self._axis(
                    "html_selector",
                    "detect_base_attribute",
                    "relative link resolution from base tag",
                ),
            ),
            TestCase(
                name="adaptive_html_selector_base_option_attribute",
                args=["--base", "https://fallback.example/root/", "--attribute", "href", "a"],
                stdin=html,
                description=self._axis(
                    "html_selector",
                    "base_option_attribute",
                    "relative link resolution from explicit base option",
                ),
            ),
            TestCase(
                name="adaptive_html_selector_comma_selector",
                args=["#app, a.external"],
                stdin=html,
                description=self._axis(
                    "html_selector",
                    "comma_selector",
                    "comma-separated selector union in document order",
                ),
            ),
            TestCase(
                name="adaptive_html_selector_remove_nodes",
                args=["--remove-nodes", "script", "main"],
                stdin=html,
                description=self._axis(
                    "html_selector",
                    "remove_nodes",
                    "mutation before selection",
                ),
            ),
            TestCase(
                name="adaptive_html_selector_pretty",
                args=["-p", "main"],
                stdin=html,
                description=self._axis(
                    "html_selector",
                    "pretty",
                    "pretty-print formatting mode",
                ),
            ),
            TestCase(
                name="adaptive_html_selector_input_output_file",
                args=["--filename", "input.html", "--output", "out.html", "a"],
                input_files=self._safe_input_files({"input.html": html.encode("utf-8")}),
                description=self._axis(
                    "html_selector",
                    "input_output_file",
                    "named input file and output file behavior",
                ),
            ),
            TestCase(
                name="adaptive_html_selector_no_selector",
                stdin=html,
                description=self._axis(
                    "html_selector",
                    "no_selector",
                    "missing selector error behavior",
                ),
            ),
            TestCase(
                name="adaptive_html_selector_no_selector_fragment",
                stdin='<a href="/x">link</a><p>Hello</p>\n',
                description=self._axis(
                    "html_selector",
                    "no_selector_fragment",
                    "default html selector wraps body fragments",
                ),
            ),
            TestCase(
                name="adaptive_html_selector_dash_selector",
                args=["-"],
                stdin=html,
                description=self._axis(
                    "html_selector",
                    "dash_selector",
                    "dash as selector argument rather than stdin marker",
                ),
            ),
            TestCase(
                name="adaptive_html_selector_output_dash_selector",
                args=["--output", "out.html", "-"],
                stdin=html,
                description=self._axis(
                    "html_selector",
                    "output_dash_selector",
                    "output-file side effects when dash selector panics",
                ),
            ),
            TestCase(
                name="adaptive_html_selector_malformed_html",
                args=["p"],
                stdin="<html><body><p>unterminated<div data-x='1'>tail\n",
                description=self._axis(
                    "html_selector",
                    "malformed_html",
                    "recovery around malformed markup",
                ),
            ),
        ]

    def _go_dependency_report_probes(self) -> list[TestCase]:
        return [
            TestCase(
                name="adaptive_go_dependency_report_help_flag",
                args=["-help"],
                description=self._axis(
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
                description=self._axis(
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
                description=self._axis(
                    "go_dependency_report",
                    "indirect_dependency",
                    "indirect marker rendering",
                ),
            ),
            TestCase(
                name="adaptive_go_dependency_report_no_update",
                stdin='{"Path":"github.com/acme/current","Version":"v2.0.0","Indirect":false}\n',
                description=self._axis(
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
                description=self._axis(
                    "go_dependency_report",
                    "multiple_records",
                    "newline-delimited JSON table layout",
                ),
            ),
            TestCase(
                name="adaptive_go_dependency_report_invalid_json",
                stdin='{"Path":"github.com/acme/broken","Version":\n',
                description=self._axis(
                    "go_dependency_report",
                    "invalid_json",
                    "unexpected EOF handling",
                ),
            ),
        ]

    def _csv_table_probes(self) -> list[TestCase]:
        csv_text = 'name,note\nAda,"x,y"\nLin,"line one\nline two"\n'
        tsv_text = "name\tscore\nAda\t10\nLin\t9\n"
        small_csv = "name,color,size\nAda,red,S\nLin,blue,M\nGrace,red,S\nKen,red,L\nMia,blue,S\n"
        return [
            TestCase(
                name="adaptive_csv_table_quoted_fields",
                stdin=csv_text,
                description=self._axis(
                    "csv_table",
                    "quoted_fields",
                    "quoted delimiters and embedded newlines",
                ),
            ),
            TestCase(
                name="adaptive_csv_table_explicit_stdin",
                args=["-"],
                stdin=csv_text,
                description=self._axis(
                    "csv_table",
                    "explicit_stdin",
                    "explicit '-' stdin marker",
                ),
            ),
            TestCase(
                name="adaptive_csv_table_file_input",
                args=["input.csv"],
                input_files=self._safe_input_files({"input.csv": csv_text.encode("utf-8")}),
                description=self._axis(
                    "csv_table",
                    "file_input",
                    "positional CSV file input",
                ),
            ),
            TestCase(
                name="adaptive_csv_table_delimiter_mode",
                args=["--delimiter", "\t"],
                stdin=tsv_text,
                description=self._axis(
                    "csv_table",
                    "delimiter_mode",
                    "non-comma delimiter mode",
                ),
            ),
            TestCase(
                name="adaptive_csv_table_select_header",
                args=["select", "name"],
                stdin=csv_text,
                description=self._axis(
                    "csv_table",
                    "select_header",
                    "subcommand column selection by header",
                ),
            ),
            TestCase(
                name="adaptive_csv_table_sample_rows",
                args=["sample", "2"],
                stdin="name,score\nAda,10\nLin,9\nGrace,8\n",
                description=self._axis(
                    "csv_table",
                    "sample_rows",
                    "sample subcommand row retention",
                ),
            ),
            TestCase(
                name="adaptive_csv_table_headers_command",
                args=["headers"],
                stdin=small_csv,
                description=self._axis(
                    "csv_table",
                    "headers_command",
                    "headers subcommand numbering and order",
                ),
            ),
            TestCase(
                name="adaptive_csv_table_count_command",
                args=["count"],
                stdin=small_csv,
                description=self._axis(
                    "csv_table",
                    "count_command",
                    "row count excluding the header",
                ),
            ),
            TestCase(
                name="adaptive_csv_table_frequency_stable_order",
                args=["frequency"],
                stdin=small_csv,
                description=self._axis(
                    "csv_table",
                    "frequency_stable_order",
                    "frequency output count ordering and tie stability",
                ),
            ),
            TestCase(
                name="adaptive_csv_table_index_file_output",
                args=["index", "data.csv"],
                input_files=self._safe_input_files({"data.csv": small_csv.encode("utf-8")}),
                description=self._axis(
                    "csv_table",
                    "index_file_output",
                    "index subcommand output-file side effect",
                ),
            ),
            TestCase(
                name="adaptive_csv_table_join_cross_invalid_arity",
                args=["join", "--cross", "left.csv", "right.csv"],
                input_files=self._safe_input_files(
                    {
                        "left.csv": b"id,val\n1,a\n2,b\n",
                        "right.csv": b"id,name\n1,x\n2,y\n",
                    }
                ),
                description=self._axis(
                    "csv_table",
                    "join_cross_invalid_arity",
                    "join --cross still enforces documented positional arity",
                ),
            ),
        ]

    def _binary_hexdump_probes(self) -> list[TestCase]:
        binary_fixture = bytes([0, 1, 2, 9, 10, 13, 31, 32, 65, 66, 67, 126, 127, 128, 255])
        return [
            TestCase(
                name="adaptive_binary_hexdump_empty_stdin",
                stdin="",
                description=self._axis(
                    "binary_hexdump",
                    "empty_stdin",
                    "no-file no-content rendering",
                ),
            ),
            TestCase(
                name="adaptive_binary_hexdump_file_bytes",
                args=["sample.bin"],
                input_files=self._safe_input_files({"sample.bin": binary_fixture}),
                description=self._axis(
                    "binary_hexdump",
                    "file_bytes",
                    "raw byte rendering and character table",
                ),
            ),
            TestCase(
                name="adaptive_binary_hexdump_length_skip",
                args=["--length", "8", "--skip", "4", "sample.bin"],
                input_files=self._safe_input_files({"sample.bin": binary_fixture}),
                description=self._axis(
                    "binary_hexdump",
                    "length_skip",
                    "byte offset after skip before length",
                ),
            ),
            TestCase(
                name="adaptive_binary_hexdump_block_panels",
                args=["--block-size", "8", "--panels", "2", "sample.bin"],
                input_files=self._safe_input_files({"sample.bin": binary_fixture}),
                description=self._axis(
                    "binary_hexdump",
                    "block_panels",
                    "row grouping and panel spacing",
                ),
            ),
            TestCase(
                name="adaptive_binary_hexdump_no_characters",
                args=["--no-characters", "--border", "none", "sample.bin"],
                input_files=self._safe_input_files({"sample.bin": binary_fixture}),
                description=self._axis(
                    "binary_hexdump",
                    "no_characters",
                    "border and character-column suppression",
                ),
            ),
            TestCase(
                name="adaptive_binary_hexdump_invalid_color_scheme",
                args=["--color-scheme", "classic", "sample.bin"],
                input_files=self._safe_input_files({"sample.bin": binary_fixture}),
                description=self._axis(
                    "binary_hexdump",
                    "invalid_color_scheme",
                    "clap enum diagnostic",
                ),
            ),
        ]

    def _archive_compression_probes(self) -> list[TestCase]:
        empty_zip = b"PK\x05\x06" + (b"\x00" * 18)
        return [
            TestCase(
                name="adaptive_archive_compression_clap_required_flags",
                args=["--charset", "ab"],
                description=self._axis(
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
                description=self._axis(
                    "archive_compression",
                    "clap_required_input_with_range",
                    "missing input file while other password flags are present",
                ),
            ),
            TestCase(
                name="adaptive_archive_compression_corrupt_archive",
                args=["--inputFile", "corrupt.zip"],
                input_files=self._safe_input_files({"corrupt.zip": b"not a zip archive\n"}),
                description=self._axis(
                    "archive_compression",
                    "corrupt_archive",
                    "corrupt archive diagnostics",
                ),
            ),
            TestCase(
                name="adaptive_archive_compression_empty_archive",
                args=["--inputFile", "empty.zip"],
                input_files=self._safe_input_files({"empty.zip": empty_zip}),
                description=self._axis(
                    "archive_compression",
                    "empty_archive",
                    "empty archive member handling",
                ),
            ),
            TestCase(
                name="adaptive_archive_compression_missing_file",
                args=["--inputFile", "missing.zip"],
                description=self._axis(
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
                input_files=self._safe_input_files({"empty.zip": empty_zip}),
                description=self._axis(
                    "archive_compression",
                    "password_charset",
                    "bounded charset/password search options",
                ),
            ),
            TestCase(
                name="adaptive_archive_compression_password_dictionary",
                args=["--inputFile", "empty.zip", "--passwordDictionary", "words.txt"],
                input_files=self._safe_input_files(
                    {
                        "empty.zip": empty_zip,
                        "words.txt": b"secret\npassword\n",
                    }
                ),
                description=self._axis(
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
                input_files=self._safe_input_files(
                    {
                        "empty.zip": empty_zip,
                        "charset.txt": b"ab\n",
                    }
                ),
                description=self._axis(
                    "archive_compression",
                    "charset_file",
                    "charset loaded from file with password bounds",
                ),
            ),
        ]

    def _find_replace_probes(self) -> list[TestCase]:
        return [
            TestCase(
                name="adaptive_find_replace_basic_regex_stdin",
                args=["a+", "X"],
                stdin="aa baaa\n",
                description=self._axis(
                    "find_replace",
                    "basic_regex_stdin",
                    "regex replacement over stdin",
                ),
            ),
            TestCase(
                name="adaptive_find_replace_capture_groups",
                args=[r"(\w+)-(\d+)", "$2:$1"],
                stdin="item-42 other-7\n",
                description=self._axis(
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
                description=self._axis(
                    "find_replace",
                    "adjacent_indexed_captures",
                    "numbered captures embedded in replacement text",
                ),
            ),
            TestCase(
                name="adaptive_find_replace_empty_captures",
                args=[r"(a*)(b*)", "[$1][$2]"],
                stdin="ab\n",
                description=self._axis(
                    "find_replace",
                    "empty_captures",
                    "empty capture and zero-length match behavior",
                ),
            ),
            TestCase(
                name="adaptive_find_replace_dollar_escape",
                args=["a", "$$"],
                stdin="a a\n",
                description=self._axis(
                    "find_replace",
                    "dollar_escape",
                    "literal dollar replacement escaping",
                ),
            ),
            TestCase(
                name="adaptive_find_replace_dollar_numeric_literal",
                args=["a", "$$1"],
                stdin="a\n",
                description=self._axis(
                    "find_replace",
                    "dollar_numeric_literal",
                    "literal dollar followed by numeric text",
                ),
            ),
            TestCase(
                name="adaptive_find_replace_dollar_prefix_literal",
                args=["foo", "$$bar"],
                stdin="foo\n",
                description=self._axis(
                    "find_replace",
                    "dollar_prefix_literal",
                    "literal dollar followed by replacement text",
                ),
            ),
            TestCase(
                name="adaptive_find_replace_fixed_string",
                args=["-F", "a.b", "X"],
                stdin="a.b axb\n",
                description=self._axis(
                    "find_replace",
                    "fixed_string",
                    "literal search mode without regex expansion",
                ),
            ),
            TestCase(
                name="adaptive_find_replace_file_input",
                args=["cat", "dog", "input.txt"],
                input_files=self._safe_input_files({"input.txt": b"cat\nwildcat\n"}),
                description=self._axis(
                    "find_replace",
                    "file_input",
                    "positional file transformation side effects",
                ),
            ),
            TestCase(
                name="adaptive_find_replace_preview_file_input",
                args=["--preview", "cat", "dog", "input.txt"],
                input_files=self._safe_input_files({"input.txt": b"cat\nwildcat\n"}),
                description=self._axis(
                    "find_replace",
                    "preview_file_input",
                    "preview mode emits observed output without rewriting files",
                ),
            ),
            TestCase(
                name="adaptive_find_replace_invalid_dash_file",
                args=["hello", "world", "-"],
                stdin="hello there",
                description=self._axis(
                    "find_replace",
                    "invalid_dash_file",
                    "dash passed as an explicit file operand",
                ),
            ),
            TestCase(
                name="adaptive_find_replace_missing_file",
                args=["foo", "bar", "missing.txt"],
                description=self._axis(
                    "find_replace",
                    "missing_file",
                    "missing file operand diagnostic",
                ),
            ),
            TestCase(
                name="adaptive_find_replace_invalid_regex",
                args=["[", "x"],
                stdin="abc\n",
                description=self._axis(
                    "find_replace",
                    "invalid_regex",
                    "regex parser diagnostic and exit behavior",
                ),
            ),
            TestCase(
                name="adaptive_find_replace_unsupported_lookaround",
                args=["foo(?=bar)", "XXX"],
                stdin="foobar\n",
                description=self._axis(
                    "find_replace",
                    "unsupported_lookaround",
                    "Rust regex-style unsupported look-around diagnostic",
                ),
            ),
        ]

    def _filesystem_tool_probes(self) -> list[TestCase]:
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
                input_files=self._safe_input_files(tree),
                description=self._axis(
                    "filesystem_tool",
                    "file_input",
                    "single file path behavior",
                ),
            ),
            TestCase(
                name="adaptive_filesystem_tool_directory_input",
                args=["dir"],
                input_files=self._safe_input_files(tree),
                description=self._axis(
                    "filesystem_tool",
                    "directory_input",
                    "directory traversal and ordering",
                ),
            ),
            TestCase(
                name="adaptive_filesystem_tool_hidden_file",
                args=["dir/.hidden"],
                input_files=self._safe_input_files(tree),
                description=self._axis(
                    "filesystem_tool",
                    "hidden_file",
                    "hidden file path handling",
                ),
            ),
            TestCase(
                name="adaptive_filesystem_tool_missing_path",
                args=["missing.txt"],
                description=self._axis(
                    "filesystem_tool",
                    "missing_path",
                    "missing path diagnostic",
                ),
            ),
            TestCase(
                name="adaptive_filesystem_tool_recursive_flag",
                args=["--recursive", "dir"],
                input_files=self._safe_input_files(tree),
                description=self._axis(
                    "filesystem_tool",
                    "recursive_flag",
                    "recursive directory flag behavior",
                ),
            ),
            TestCase(
                name="adaptive_filesystem_tool_multiple_paths",
                args=["dir/a.txt", "dir/nested/b.txt"],
                input_files=self._safe_input_files(tree),
                description=self._axis(
                    "filesystem_tool",
                    "multiple_paths",
                    "multiple positional paths",
                ),
            ),
            TestCase(
                name="adaptive_filesystem_tool_stdin_marker",
                args=["-"],
                stdin="stdin payload\n",
                description=self._axis(
                    "filesystem_tool",
                    "stdin_marker",
                    "dash stdin marker versus path handling",
                ),
            ),
        ]

    def _terminal_animation_probes(self) -> list[TestCase]:
        return [
            TestCase(
                name="adaptive_terminal_animation_term_unknown",
                env_vars={"TERM": "unknown"},
                description=self._axis(
                    "terminal_animation",
                    "term_unknown",
                    "unknown terminal capability error",
                ),
            ),
            TestCase(
                name="adaptive_terminal_animation_term_missing",
                env_vars={"TERM": ""},
                description=self._axis(
                    "terminal_animation",
                    "term_missing",
                    "missing TERM environment branch",
                ),
            ),
            TestCase(
                name="adaptive_terminal_animation_help_flag",
                args=["-h"],
                description=self._axis(
                    "terminal_animation",
                    "help_flag",
                    "short help output without animation",
                ),
            ),
            TestCase(
                name="adaptive_terminal_animation_version_flag",
                args=["--version"],
                description=self._axis(
                    "terminal_animation",
                    "version_flag",
                    "long version flag behavior",
                ),
            ),
            TestCase(
                name="adaptive_terminal_animation_short_version_flag",
                args=["-V"],
                description=self._axis(
                    "terminal_animation",
                    "version_flag",
                    "short version flag behavior",
                ),
            ),
            TestCase(
                name="adaptive_terminal_animation_invalid_flag",
                args=["--definitely-invalid"],
                description=self._axis(
                    "terminal_animation",
                    "invalid_flag",
                    "invalid flag diagnostic without help fallthrough",
                ),
            ),
            TestCase(
                name="adaptive_terminal_animation_small_screen_error",
                env_vars={"TERM": "unknown", "COLUMNS": "40", "LINES": "12"},
                description=self._axis(
                    "terminal_animation",
                    "small_screen_error",
                    "terminal-size env handling on noninteractive error path",
                ),
            ),
        ]

    def _terminal_ui_probes(self) -> list[TestCase]:
        return [
            TestCase(
                name="adaptive_terminal_ui_no_tty",
                description=self._axis(
                    "terminal_ui",
                    "no_tty",
                    "noninteractive terminal output branch",
                ),
            ),
            TestCase(
                name="adaptive_terminal_ui_term_unknown",
                env_vars={"TERM": "unknown"},
                description=self._axis(
                    "terminal_ui",
                    "term_unknown",
                    "unknown terminal environment behavior",
                ),
            ),
            TestCase(
                name="adaptive_terminal_ui_color_disabled",
                env_vars={"NO_COLOR": "1", "TERM": "xterm"},
                description=self._axis(
                    "terminal_ui",
                    "color_disabled",
                    "color suppression environment branch",
                ),
            ),
            TestCase(
                name="adaptive_terminal_ui_dimensions",
                env_vars={"TERM": "xterm", "COLUMNS": "40", "LINES": "12"},
                description=self._axis(
                    "terminal_ui",
                    "dimensions",
                    "small terminal dimensions",
                ),
            ),
            TestCase(
                name="adaptive_terminal_ui_help_flag",
                args=["--help"],
                description=self._axis(
                    "terminal_ui",
                    "help_flag",
                    "help output without terminal rendering",
                ),
            ),
            TestCase(
                name="adaptive_terminal_ui_invalid_flag",
                args=["--definitely-invalid"],
                description=self._axis(
                    "terminal_ui",
                    "invalid_flag",
                    "unknown option diagnostic",
                ),
            ),
        ]

    def _network_ping_probes(self) -> list[TestCase]:
        return [
            TestCase(
                name="adaptive_network_ping_loopback_ipv4",
                args=["-c", "1", "127.0.0.1"],
                description=self._axis(
                    "network_ping",
                    "loopback_ipv4",
                    "bounded successful local transcript",
                ),
            ),
            TestCase(
                name="adaptive_network_ping_loopback_ipv6",
                args=["-c", "1", "::1"],
                description=self._axis(
                    "network_ping",
                    "loopback_ipv6",
                    "bounded successful local transcript",
                ),
            ),
            TestCase(
                name="adaptive_network_ping_localhost_name",
                args=["-c", "1", "localhost"],
                description=self._axis(
                    "network_ping",
                    "localhost_name",
                    "resolver and transcript formatting",
                ),
            ),
            TestCase(
                name="adaptive_network_ping_special_address_error",
                args=["-c", "1", "224.0.0.1"],
                description=self._axis(
                    "network_ping",
                    "special_address_error",
                    "multicast network-error branch",
                ),
            ),
            TestCase(
                name="adaptive_network_ping_broadcast_error",
                args=["-c", "1", "255.255.255.255"],
                description=self._axis(
                    "network_ping",
                    "special_address_error",
                    "broadcast network-error branch",
                ),
            ),
            TestCase(
                name="adaptive_network_ping_link_local_error",
                args=["-c", "1", "169.254.1.1"],
                description=self._axis(
                    "network_ping",
                    "special_address_error",
                    "link-local network-error branch",
                ),
            ),
            TestCase(
                name="adaptive_network_ping_count_parse_error",
                args=["-c", "abc", "localhost"],
                description=self._axis(
                    "network_ping",
                    "count_parse_error",
                    "flag alias and parse diagnostics",
                ),
            ),
            TestCase(
                name="adaptive_network_ping_missing_host",
                args=["-c", "1"],
                description=self._axis(
                    "network_ping",
                    "missing_host",
                    "required host diagnostics",
                ),
            ),
            TestCase(
                name="adaptive_network_ping_multiple_hosts",
                args=["-c", "1", "127.0.0.1", "127.0.0.2"],
                description=self._axis(
                    "network_ping",
                    "multiple_hosts",
                    "extra positional host diagnostics",
                ),
            ),
        ]

    def _axis(self, domain: str, axis: str, detail: str) -> str:
        return f"smoke_contract:{domain}.{axis} adaptive_axis:{domain}.{axis} {detail}"

    def _safe_input_files(self, files: dict[str, bytes]) -> dict[str, bytes]:
        for path in files:
            posix_path = PurePosixPath(path)
            if path != posix_path.as_posix() or posix_path.is_absolute() or ".." in posix_path.parts:
                raise ValueError(f"unsafe adaptive probe input path: {path}")
        return files
