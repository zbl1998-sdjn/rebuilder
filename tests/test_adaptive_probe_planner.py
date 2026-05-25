from pathlib import PurePosixPath

from core.probing.adaptive import AdaptiveProbePlanner


def _axis_descriptions(probes):
    return " ".join(probe.description for probe in probes)


def _assert_safe_relative_input_paths(probes):
    for probe in probes:
        for path in probe.input_files:
            posix_path = PurePosixPath(path)
            assert path == posix_path.as_posix()
            assert not posix_path.is_absolute()
            assert ".." not in posix_path.parts


def test_json_transform_profile_generates_domain_axes_and_key_inputs():
    probes = AdaptiveProbePlanner().plan({"primary_domain": "json_transform"})

    assert 9 <= len(probes) <= 12
    descriptions = _axis_descriptions(probes)
    assert "adaptive_axis:json_transform.nested_paths" in descriptions
    assert "adaptive_axis:json_transform.array_root" in descriptions
    assert "adaptive_axis:json_transform.json_stream_output" in descriptions
    assert "adaptive_axis:json_transform.stream_records" in descriptions
    assert "adaptive_axis:json_transform.ungron_sparse_array" in descriptions
    assert "adaptive_axis:json_transform.json_stream_ungron" in descriptions
    assert "adaptive_axis:json_transform.invalid_json" in descriptions
    assert any('"users"' in probe.stdin for probe in probes)
    assert any("json.likes[2]" in probe.stdin for probe in probes)
    assert any(probe.args == ["--json", "--ungron"] for probe in probes)
    assert any(probe.input_files.get("input.json") for probe in probes)
    _assert_safe_relative_input_paths(probes)


def test_html_selector_profile_generates_selector_mutation_and_error_probes():
    probes = AdaptiveProbePlanner().plan({"domains": ["html_selector"]})

    assert 16 <= len(probes) <= 19
    descriptions = _axis_descriptions(probes)
    assert "adaptive_axis:html_selector.basic_selector" in descriptions
    assert "adaptive_axis:html_selector.attribute_selector" in descriptions
    assert "adaptive_axis:html_selector.text_mode" in descriptions
    assert "adaptive_axis:html_selector.ignore_whitespace" in descriptions
    assert "adaptive_axis:html_selector.attribute_output" in descriptions
    assert "adaptive_axis:html_selector.detect_base_attribute" in descriptions
    assert "adaptive_axis:html_selector.base_option_attribute" in descriptions
    assert "adaptive_axis:html_selector.comma_selector" in descriptions
    assert "adaptive_axis:html_selector.remove_nodes" in descriptions
    assert "adaptive_axis:html_selector.input_output_file" in descriptions
    assert "adaptive_axis:html_selector.no_selector" in descriptions
    assert "adaptive_axis:html_selector.no_selector_fragment" in descriptions
    assert "adaptive_axis:html_selector.dash_selector" in descriptions
    assert "adaptive_axis:html_selector.output_dash_selector" in descriptions
    assert any("<main" in probe.stdin for probe in probes)
    assert any(probe.args == ["--filename", "input.html", "--output", "out.html", "a"] for probe in probes)
    _assert_safe_relative_input_paths(probes)


def test_syntax_highlighter_profile_generates_formatter_html_and_bound_probes():
    probes = AdaptiveProbePlanner().plan({"primary_domain": "syntax_highlighter"})

    assert 10 <= len(probes) <= 14
    descriptions = _axis_descriptions(probes)
    assert "adaptive_axis:syntax_highlighter.invalid_formatter" in descriptions
    assert "adaptive_axis:syntax_highlighter.lexer_stdin" in descriptions
    assert "adaptive_axis:syntax_highlighter.filename_stdin" in descriptions
    assert "adaptive_axis:syntax_highlighter.terminal16m_formatter" in descriptions
    assert "adaptive_axis:syntax_highlighter.tokens_formatter" in descriptions
    assert "adaptive_axis:syntax_highlighter.noop_formatter" in descriptions
    assert "adaptive_axis:syntax_highlighter.html_inline_file" in descriptions
    assert "adaptive_axis:syntax_highlighter.html_line_table" in descriptions
    assert "adaptive_axis:syntax_highlighter.style_css" in descriptions
    assert "adaptive_axis:syntax_highlighter.multi_file" in descriptions
    assert "adaptive_axis:syntax_highlighter.explicit_dash_stdin" in descriptions
    assert "adaptive_axis:syntax_highlighter.bounded_large_file" in descriptions
    assert any(probe.args == ["--formatter", "tokens", "--lexer", "python"] for probe in probes)
    assert any(probe.args[:3] == ["--html", "--html-only", "--html-lines"] for probe in probes)
    assert any(probe.input_files.get("large.py") for probe in probes)
    _assert_safe_relative_input_paths(probes)


def test_go_dependency_report_profile_generates_ndjson_and_flag_probes():
    probes = AdaptiveProbePlanner().plan({"primary_domain": "go_dependency_report"})

    assert 5 <= len(probes) <= 8
    descriptions = _axis_descriptions(probes)
    assert "adaptive_axis:go_dependency_report.help_flag" in descriptions
    assert "adaptive_axis:go_dependency_report.direct_update" in descriptions
    assert "adaptive_axis:go_dependency_report.indirect_dependency" in descriptions
    assert "adaptive_axis:go_dependency_report.invalid_json" in descriptions
    assert any('"Path":"github.com/acme/lib"' in probe.stdin for probe in probes)
    _assert_safe_relative_input_paths(probes)


def test_binary_hexdump_profile_generates_byte_layout_and_error_probes():
    probes = AdaptiveProbePlanner().plan({"primary_domain": "binary_hexdump"})

    assert 5 <= len(probes) <= 8
    descriptions = _axis_descriptions(probes)
    assert "adaptive_axis:binary_hexdump.empty_stdin" in descriptions
    assert "adaptive_axis:binary_hexdump.file_bytes" in descriptions
    assert "adaptive_axis:binary_hexdump.length_skip" in descriptions
    assert "adaptive_axis:binary_hexdump.invalid_color_scheme" in descriptions
    assert any(probe.input_files.get("sample.bin") for probe in probes)
    assert any(b"\xff" in probe.input_files.get("sample.bin", b"") for probe in probes)
    _assert_safe_relative_input_paths(probes)


def test_csv_table_profile_generates_smoke_contract_probes():
    probes = AdaptiveProbePlanner().plan({"primary_domain": "csv_table"})

    assert 10 <= len(probes) <= 13
    descriptions = _axis_descriptions(probes)
    assert "smoke_contract:csv_table.quoted_fields" in descriptions
    assert "smoke_contract:csv_table.explicit_stdin" in descriptions
    assert "smoke_contract:csv_table.file_input" in descriptions
    assert "smoke_contract:csv_table.delimiter_mode" in descriptions
    assert "smoke_contract:csv_table.headers_command" in descriptions
    assert "smoke_contract:csv_table.count_command" in descriptions
    assert "smoke_contract:csv_table.frequency_stable_order" in descriptions
    assert "smoke_contract:csv_table.index_file_output" in descriptions
    assert "smoke_contract:csv_table.join_cross_invalid_arity" in descriptions
    frequency_probe = next(
        probe for probe in probes if probe.name == "adaptive_csv_table_frequency_stable_order"
    )
    assert "exact observed tie order" in frequency_probe.description
    assert "do not assume first-seen or lexical ties" in frequency_probe.description
    assert any('"x,y"' in probe.stdin for probe in probes)
    assert any(probe.input_files.get("input.csv") for probe in probes)
    assert any(probe.input_files.get("data.csv") for probe in probes)
    _assert_safe_relative_input_paths(probes)


def test_excluded_domain_suppresses_only_that_adaptive_profile():
    probes = AdaptiveProbePlanner(excluded_domains=["csv_table"]).plan(
        {"primary_domain": "csv_table", "domains": ["csv_table", "json_transform"]}
    )

    descriptions = _axis_descriptions(probes)
    assert "smoke_contract:csv_table." not in descriptions
    assert "adaptive_axis:json_transform." in descriptions
    _assert_safe_relative_input_paths(probes)


def test_find_replace_profile_generates_regex_replacement_probes():
    probes = AdaptiveProbePlanner().plan({"primary_domain": "find_replace"})

    assert 12 <= len(probes) <= 15
    descriptions = _axis_descriptions(probes)
    assert "smoke_contract:find_replace.basic_regex_stdin" in descriptions
    assert "smoke_contract:find_replace.capture_groups" in descriptions
    assert "smoke_contract:find_replace.adjacent_indexed_captures" in descriptions
    assert "smoke_contract:find_replace.empty_captures" in descriptions
    assert "smoke_contract:find_replace.dollar_numeric_literal" in descriptions
    assert "smoke_contract:find_replace.dollar_prefix_literal" in descriptions
    assert "smoke_contract:find_replace.fixed_string" in descriptions
    assert "smoke_contract:find_replace.preview_file_input" in descriptions
    assert "smoke_contract:find_replace.invalid_dash_file" in descriptions
    assert "smoke_contract:find_replace.missing_file" in descriptions
    assert "smoke_contract:find_replace.invalid_regex" in descriptions
    assert "smoke_contract:find_replace.unsupported_lookaround" in descriptions
    assert any("$2:$1" in probe.args for probe in probes)
    assert any("cmd: $1, channel: $2, subcmd: $3" in probe.args for probe in probes)
    assert any("$$1" in probe.args for probe in probes)
    assert any("$$bar" in probe.args for probe in probes)
    assert any(probe.args[:1] == ["--preview"] for probe in probes)
    assert any(probe.args == ["hello", "world", "-"] for probe in probes)
    assert any(probe.args == ["foo", "bar", "missing.txt"] for probe in probes)
    assert any("foo(?=bar)" in probe.args for probe in probes)
    assert any(probe.input_files.get("input.txt") for probe in probes)
    _assert_safe_relative_input_paths(probes)


def test_archive_compression_profile_generates_binary_error_probes():
    probes = AdaptiveProbePlanner().plan({"primary_domain": "archive_compression"})

    assert 7 <= len(probes) <= 10
    descriptions = _axis_descriptions(probes)
    assert "smoke_contract:archive_compression.corrupt_archive" in descriptions
    assert "smoke_contract:archive_compression.empty_archive" in descriptions
    assert "smoke_contract:archive_compression.missing_file" in descriptions
    assert "smoke_contract:archive_compression.clap_required_flags" in descriptions
    assert "smoke_contract:archive_compression.clap_required_input_with_range" in descriptions
    assert "smoke_contract:archive_compression.password_dictionary" in descriptions
    assert "smoke_contract:archive_compression.charset_file" in descriptions
    assert any(probe.input_files.get("empty.zip", b"").startswith(b"PK") for probe in probes)
    assert any(probe.input_files.get("corrupt.zip") == b"not a zip archive\n" for probe in probes)
    assert any(probe.input_files.get("words.txt") for probe in probes)
    _assert_safe_relative_input_paths(probes)


def test_network_ping_profile_generates_loopback_error_and_parser_probes():
    probes = AdaptiveProbePlanner().plan({"primary_domain": "network_ping"})

    assert 6 <= len(probes) <= 10
    descriptions = _axis_descriptions(probes)
    assert "adaptive_axis:network_ping.loopback_ipv4" in descriptions
    assert "adaptive_axis:network_ping.loopback_ipv6" in descriptions
    assert "adaptive_axis:network_ping.special_address_error" in descriptions
    assert "adaptive_axis:network_ping.count_parse_error" in descriptions
    assert "adaptive_axis:network_ping.missing_host" in descriptions
    assert any(probe.args[:2] == ["-c", "1"] for probe in probes if probe.args)
    assert any("224.0.0.1" in probe.args for probe in probes)
    assert any("abc" in probe.args for probe in probes)
    _assert_safe_relative_input_paths(probes)


def test_terminal_ui_profile_generates_env_and_bounded_render_probes():
    probes = AdaptiveProbePlanner().plan({"primary_domain": "terminal_ui"})

    assert 5 <= len(probes) <= 8
    descriptions = _axis_descriptions(probes)
    assert "smoke_contract:terminal_ui.no_tty" in descriptions
    assert "smoke_contract:terminal_ui.term_unknown" in descriptions
    assert "smoke_contract:terminal_ui.color_disabled" in descriptions
    assert "smoke_contract:terminal_ui.dimensions" in descriptions
    assert "smoke_contract:terminal_ui.help_flag" in descriptions
    assert any(probe.env_vars.get("TERM") == "unknown" for probe in probes)
    assert any(probe.env_vars.get("COLUMNS") == "40" for probe in probes)
    _assert_safe_relative_input_paths(probes)


def test_filesystem_tool_profile_generates_path_and_error_probes():
    probes = AdaptiveProbePlanner().plan({"primary_domain": "filesystem_tool"})

    assert 6 <= len(probes) <= 9
    descriptions = _axis_descriptions(probes)
    assert "smoke_contract:filesystem_tool.file_input" in descriptions
    assert "smoke_contract:filesystem_tool.directory_input" in descriptions
    assert "smoke_contract:filesystem_tool.hidden_file" in descriptions
    assert "smoke_contract:filesystem_tool.missing_path" in descriptions
    assert "smoke_contract:filesystem_tool.recursive_flag" in descriptions
    assert any(probe.input_files.get("dir/a.txt") for probe in probes)
    assert any(probe.input_files.get("dir/.hidden") for probe in probes)
    assert any("missing.txt" in probe.args for probe in probes)
    _assert_safe_relative_input_paths(probes)


def test_terminal_animation_profile_generates_noninteractive_error_probes():
    probes = AdaptiveProbePlanner().plan({"primary_domain": "terminal_animation"})

    assert 6 <= len(probes) <= 9
    descriptions = _axis_descriptions(probes)
    assert "smoke_contract:terminal_animation.term_unknown" in descriptions
    assert "smoke_contract:terminal_animation.term_missing" in descriptions
    assert "smoke_contract:terminal_animation.help_flag" in descriptions
    assert "smoke_contract:terminal_animation.version_flag" in descriptions
    assert "smoke_contract:terminal_animation.invalid_flag" in descriptions
    assert any(probe.env_vars.get("TERM") == "unknown" for probe in probes)
    assert any(probe.args == ["--version"] for probe in probes)
    _assert_safe_relative_input_paths(probes)


def test_high_signal_domains_emit_named_smoke_contract_axes():
    domains = [
        "json_transform",
        "html_selector",
        "csv_table",
        "network_ping",
        "archive_compression",
        "binary_hexdump",
        "find_replace",
        "syntax_highlighter",
        "terminal_ui",
        "filesystem_tool",
        "terminal_animation",
    ]

    for domain in domains:
        probes = AdaptiveProbePlanner().plan({"primary_domain": domain})
        descriptions = _axis_descriptions(probes)

        assert f"smoke_contract:{domain}." in descriptions


def test_unknown_profile_does_not_generate_many_generic_probes():
    probes = AdaptiveProbePlanner().plan({"primary_domain": "custom_unknown_domain"})

    assert len(probes) <= 2
    _assert_safe_relative_input_paths(probes)


def test_public_api_keeps_supported_domains_and_optional_context_compatibility():
    assert "json_transform" in AdaptiveProbePlanner.SUPPORTED_DOMAINS

    profile = {"primary_domain": "json_transform"}
    baseline = AdaptiveProbePlanner().plan(profile)
    with_context = AdaptiveProbePlanner().plan(
        profile,
        documentation="ignored deterministic planner context",
        cli_surface={"flags": ["--json"]},
        corpus=["ignored corpus sample"],
    )

    assert [probe.name for probe in with_context] == [probe.name for probe in baseline]
    _assert_safe_relative_input_paths(with_context)
