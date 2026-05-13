"""Infer domain-specific strategy hints from cleanroom evidence."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable

from core.data_models import BehaviorSample, CLISurface


@dataclass(frozen=True)
class ProfileRule:
    domain: str
    keywords: tuple[str, ...]
    formats: tuple[str, ...]
    implementation_hints: tuple[str, ...]
    repair_hints: tuple[str, ...]
    implementation_playbook: tuple[str, ...]
    repair_playbook: tuple[str, ...]
    anti_patterns: tuple[str, ...]


PROFILE_RULES: tuple[ProfileRule, ...] = (
    ProfileRule(
        domain="network_ping",
        keywords=(
            "ping",
            "icmp",
            "packet",
            "packets",
            "ttl",
            "latency",
            "rtt",
            "host",
            "hostname",
            "ipv4",
            "ipv6",
            "dns",
        ),
        formats=("plain_text",),
        implementation_hints=(
            "Treat network behavior as a CLI output contract first; do not depend on privileged raw sockets unless observed behavior requires it.",
            "Model host/count/timeout/interval parsing explicitly and preserve stderr, exit codes, and timeout wording for unreachable or invalid hosts.",
            "Keep any real network calls bounded by short timeouts and provide deterministic formatting around measured values.",
        ),
        repair_hints=(
            "If mismatches mention packet summaries, RTT/latency lines, DNS failures, or permission errors, repair formatting and exit-code semantics before adding network complexity.",
            "Check that count defaults, host position, and unreachable-host branches match observed contracts.",
        ),
        implementation_playbook=(
            "Build a manual CLI parser or tightly configured parser for help/version/count/privilege/host so option spelling and channels can match observations.",
            "Implement host normalization and address-family handling with socket.getaddrinfo where safe; special-case localhost, 127.0.0.1, and ::1 only when observed.",
            "Generate the observed ping transcript shape: header, per-packet sequence lines, blank lines, statistics separator, transmitted/received/loss summary, and RTT line when samples show it.",
            "For localhost/loopback pingu transcripts, keep the exact ASCII-art prefix, single blank-line placement, seq numbering from 0, '32bytes' spelling, ttl, and microsecond unit formatting.",
            "Use bounded subprocess/socket attempts only when required; otherwise synthesize deterministic measured fields from observed ranges and exact formatting contracts.",
            "Implement parse errors for count/host/unknown flags before network behavior, including duplicated original error text when contracts show it.",
        ),
        repair_playbook=(
            "If replacement prints parser/debug summaries such as 'Parsed: host=', replace them with observed ping transcript rendering.",
            "For stdout failures, diff header text, seq numbering, byte count, ttl/time unit spelling, statistics separator, packet-loss wording, and final newline.",
            "For pingu localhost stdout failures, compare whether there is exactly one newline after the header, whether time is a µs value rather than 0s, and whether the packet statistics line includes '=> 1 received (0% loss)'.",
            "For stderr failures, copy observed parse-error phrasing, flag aliases, quoting, and follow-up '[ ERROR ] parse error' lines before changing algorithmic behavior.",
            "For special-host failures, compare DNS lookup wording, multicast write errors, resolver addresses, and whether stdout still contains a zero-transmitted statistics block before stderr.",
            "For timeout failures, cap count-like loops and default host probes; never introduce an unbounded ping loop.",
        ),
        anti_patterns=(
            "Do not leave placeholder or debug output that only echoes parsed arguments.",
            "Do not rely on platform ping output directly unless wrapped with strict timeout and normalized to observed formatting.",
            "Do not use argparse default help/errors when observed output is Go-flags style or custom formatted.",
        ),
    ),
    ProfileRule(
        domain="csv_table",
        keywords=(
            "csv",
            "delimiter",
            "quote",
            "header",
            "column",
            "select",
            "sort",
            "table",
            "record",
            "tsv",
        ),
        formats=("csv", "tsv", "table"),
        implementation_hints=(
            "Use Python csv parsing instead of ad-hoc split logic so quoting, embedded delimiters, and newlines remain correct.",
            "Preserve header handling, column selection order, delimiter flags, and empty-field rendering exactly.",
        ),
        repair_hints=(
            "For table mismatches, inspect delimiter, quoting, header, row ordering, and trailing newline behavior first.",
            "Avoid normalizing whitespace unless observations prove the original does.",
        ),
        implementation_playbook=(
            "Centralize input acquisition from stdin, '-' and file arguments; keep text newline handling explicit.",
            "Use csv.reader/csv.writer with dialect parameters inferred from flags and contracts rather than splitting rows manually.",
            "Represent rows as lists plus optional header metadata so select/search/sort/count commands share parsing logic.",
            "For xsv-like multi-command tools, keep the documented subcommand variant order exact in invalid-command errors; do not alphabetize or reorder help variants.",
            "For sample-like commands, model whether observations require deterministic seeded sampling, reservoir sampling, or contract-specific replay; preserve headers and row order exactly.",
            "Preserve output delimiter, quoting mode, empty fields, record order, and final newline exactly as shown in contracts.",
        ),
        repair_playbook=(
            "When stdout differs, first compare delimiter, quoting, header inclusion, selected column order, and row sort stability.",
            "When file/STDIN cases differ, verify '-' handling and whether no-arg mode reads stdin or prints usage.",
            "For invalid subcommand failures, diff the complete allowed-variants list including order, quoting, commas, and line wrapping before changing parser logic.",
            "For sample failures, compare header retention, deterministic seed behavior, reservoir-vs-index sampling, selected row order, and whether stdin/file input changes randomness.",
            "When stderr differs, copy observed CSV parse diagnostics and missing-column wording before changing parser internals.",
        ),
        anti_patterns=(
            "Do not implement CSV by str.split(',') because quoted delimiters and embedded newlines will break.",
            "Do not strip or collapse whitespace in fields unless observed behavior proves it.",
            "Do not sort subcommands or enum variants unless the reference output sorts them.",
            "Do not use Python random defaults for sampling when observed outputs are deterministic.",
        ),
    ),
    ProfileRule(
        domain="json_transform",
        keywords=(
            "json",
            "jq",
            "gron",
            "object",
            "array",
            "key",
            "value",
            "pretty",
            "ungron",
        ),
        formats=("json",),
        implementation_hints=(
            "Use json.loads/json.dumps and preserve ordering, escaping, indentation, and newline behavior seen in contracts.",
            "Handle invalid JSON and empty input with observed stderr and exit-code semantics.",
        ),
        repair_hints=(
            "For JSON mismatches, check escaping, key ordering, list indexes, invalid-input diagnostics, and final newline behavior.",
        ),
        implementation_playbook=(
            "Read JSON from stdin or file according to observed argv forms and fail early on empty/invalid input with exact stderr and exit code.",
            "Preserve object insertion order from json.loads; only sort keys if flags or observations require sorting.",
            "For flattening tools, traverse dicts/lists recursively and implement path quoting, list indexes, booleans, null, and string escaping explicitly.",
            "For gron-like tools, keep transform modes distinct: normal JSON-to-assignments, assignment-to-JSON ungron, JSON-stream records, JSON-array records, and assignment-value extraction.",
            "For gron-like --values modes, print values from assignment input; do not flatten ordinary JSON input into scalar values unless observations prove that behavior.",
            "If gron-like --values sees raw JSON instead of assignment statements, match observed empty-output success or parse-error behavior; do not invent scalar output.",
            "For gron-like --stream mode, treat newline-delimited JSON objects as a single JSON array before flattening, so output starts with json = []; and indexes each record.",
            "For gron-like --ungron mode, treat root assignments such as json = {}; or json = []; as root initialization only; do not mutate an empty path after initializing root.",
            "For gron-like --ungron reconstruction, parse every assignment into path tokens first, skip empty-root paths after setting the root, grow arrays before assigning indexes, and never assign integer keys into dict roots.",
            "For gron-like --ungron input without an explicit json = ... root assignment, infer the root container from the first path token: json[0] requires a list root, while json.foo requires a dict root.",
            "For gron-like --no-sort, preserve input object insertion order all the way through traversal; do not sort or accidentally reorder via sets/intermediate dict rebuilds.",
            "When --json and --ungron conflict on gron-like tools, preserve the observed parse order and stderr prefix; some modes emit raw JSON parser errors without the normal 'failed to form statements:' wrapper.",
            "For gron-like --colorize, ANSI-wrap each path token/value category exactly as observed; dots/brackets often remain uncolored while each key segment is colored and reset separately.",
            "When mimicking Go JSON tools, translate Python JSONDecodeError into observed encoding/json wording such as \"invalid character 'x' looking for beginning of value\" instead of leaking Python exception text.",
            "For Go-style invalid literal diagnostics, preserve messages like \"invalid character 'o' in literal null (expecting 'u')\" rather than reducing every decode error to beginning-of-value wording.",
            "For gron-like numeric output, preserve the original JSON numeric lexeme when possible, including exponent notation such as 1.5e10 instead of normalizing to 15000000000.0.",
            "For pretty/compact transforms, set json.dumps indent/separators/ensure_ascii to match observed output contracts.",
        ),
        repair_playbook=(
            "For path-output mismatches, compare dot/bracket notation, quoted keys, list indexes, scalar rendering, and key order.",
            "For gron-like mode failures, isolate whether input is raw JSON, gron assignment lines, newline-delimited JSON stream, or JSON-array event output before changing traversal logic.",
            "For --values failures, verify the tool is extracting assignment RHS values rather than printing every scalar from raw JSON; if no assignment statements are parsed, preserve observed empty-output success versus error semantics.",
            "For --values null failures, print null as the literal line \"null\"; do not skip it as a falsey/None value.",
            "For --ungron failures, preserve line-specific diagnostics such as \"ungron failed for `<line>`: statement has no value\" instead of collapsing them to generic root-assignment errors.",
            "For --ungron root failures, special-case the empty json path so json = {}; initializes an object and json = []; initializes an array, then later json.foo/json[0] assignments mutate that same root without traceback.",
            "For --ungron container failures, ensure json = {}; followed by json.a = 1 mutates the root dict, json = []; followed by json[0] = ... mutates the root list, and empty-path root assignments are not passed to child-assignment code.",
            "For --ungron input that starts with json[0] without json = [];, infer a root list and grow it; do not reject it with a no root assignment error.",
            "For --ungron invalid composite RHS diagnostics, preserve the original physical input line in backticks, for example report `json.c = [` when the array literal begins on that line instead of normalizing it to a one-line [1, 2, 3].",
            "For --stream failures, verify newline-delimited input is wrapped as one array with json[0], json[1], ... paths rather than printing a separate json root per line.",
            "For --no-sort mismatches, check whether traversal preserved original key order from parsing; default sorted mode and no-sort insertion mode often differ.",
            "For numeric text mismatches, compare source lexemes for integers, negatives, floats, and scientific notation; JSON parsers often lose exponent spelling unless the generator preserves it separately.",
            "For invalid-character stderr failures, preserve escaped character spelling exactly, including backslash-escaped single quotes such as \"invalid character '\\''\".",
            "For color failures, compare raw ANSI reset variants (for example 0m vs 0;22m), per-segment key coloring, punctuation coloring, and value color by JSON type.",
            "For JSON text mismatches, compare indentation width, spaces after separators, escaped Unicode, slash escaping, and trailing newline.",
            "For stderr mismatches, preserve invalid JSON diagnostics, including Go-style invalid-character phrasing, and distinguish syntax errors from missing input.",
        ),
        anti_patterns=(
            "Do not regex-parse JSON.",
            "Do not sort keys or pretty-print unless observed behavior requires it.",
            "Do not expose Python JSONDecodeError text for Go/Rust-style tools when observed stderr has custom parser wording.",
            "Do not treat --values as a generic scalar-leaf dump for raw JSON in gron-like tools.",
        ),
    ),
    ProfileRule(
        domain="html_selector",
        keywords=(
            "html",
            "css selector",
            "selector",
            "tag",
            "attribute",
            "href",
            "text",
            "node",
            "element",
            "htmlq",
        ),
        formats=("html", "xml"),
        implementation_hints=(
            "Parse HTML leniently and preserve selector semantics, text-vs-HTML output modes, attribute extraction, and document order.",
            "Prefer small deterministic selector support over broad dependencies unless the project already allows them.",
        ),
        repair_hints=(
            "For HTML mismatches, check selector matching, text extraction whitespace, attribute mode, and whether output keeps original markup.",
        ),
        implementation_playbook=(
            "Use html.parser.HTMLParser to build a lightweight DOM that preserves tag names, attributes, text nodes, and original-ish inner/outer HTML when needed.",
            "Implement a small selector engine for tag, #id, .class, [attr], [attr=value], descendant selectors, and comma-separated selectors when observed.",
            "Keep output modes separate: outer HTML, inner text, attribute value, newline joining, and empty-match behavior.",
            "Apply mutation flags such as --remove-nodes before selecting output nodes, and return empty output when mutations remove all matching nodes.",
            "For htmlq-like no-selector invocation, preserve observed default output such as <html><head></head><body></body></html> rather than treating missing selector as an error.",
            "For htmlq-like --filename/--output, read from the named file and write selected output to the exact output path while keeping stdout empty when observed.",
            "For htmlq-like -p/--pretty output, preserve observed pretty-print layout: text nodes may stay on the opening-tag line while closing tags are indented onto their own line.",
            "For Rust-backed selector tools, preserve panic-style stderr and exit 101 for invalid selectors and file-open failures when observed.",
            "For htmlq-like invalid selectors, match the Rust panic text exactly, including single quotes around main, no extra blank line before the backtrace note, and selector text in parentheses.",
            "Preserve document order and whitespace normalization exactly as contracts show; do not pretty-print HTML.",
        ),
        repair_playbook=(
            "For selector failures, check class token matching, attribute equality, descendant combinators, comma selector union order, and case sensitivity.",
            "For text mismatches, compare entity unescaping, whitespace collapse, separators between nodes, and trailing newline behavior.",
            "For markup mismatches, check whether the original emits outer HTML, inner HTML, or raw source slices.",
            "For malformed HTML mismatches, keep lenient browser-like tree repair and still emit matched reconstructed outer HTML instead of crashing or returning empty output.",
            "For --remove-nodes failures, verify the removal selector mutates the DOM before the output selector and does not synthesize empty html/head/body wrappers after all selected content is removed.",
            "For no-argument htmlq failures, distinguish missing selector from empty-string selector: no args may output an empty HTML skeleton, while an explicit empty selector may panic.",
            "For invalid selector failures, copy observed Rust panic text including leading blank line, thread line with single-quoted 'main', source location, selector text, backtrace note, and exit code 101.",
            "For unknown-flag/flag-value selector failures, preserve whether leftover argv becomes an empty selector panic instead of silently accepting or printing default output.",
            "For --filename failures, preserve observed OS error structure including code, kind, and message fields rather than abbreviated Python exceptions.",
            "For --output failures, compare written file contents and stdout separately; many selector tools write the selection to the file and leave stdout empty.",
            "For pretty-print failures, compare newline placement around text nodes and closing tags; do not collapse <p>Text</p> or <span>Text</span> onto one line if observed output splits the closing tag.",
        ),
        anti_patterns=(
            "Do not parse HTML with one regex for nested or attributed elements.",
            "Do not reorder nodes or reserialize with pretty formatting unless observed behavior does.",
            "Do not auto-insert html/head/body wrappers when the observed output is empty or source-slice based.",
            "Do not silently accept malformed CSS selectors if the reference panics or exits nonzero.",
        ),
    ),
    ProfileRule(
        domain="archive_compression",
        keywords=(
            "zip",
            "tar",
            "gzip",
            "archive",
            "compress",
            "password",
            "encrypted",
            "crc",
        ),
        formats=("binary", "archive"),
        implementation_hints=(
            "Use standard archive libraries where possible and preserve binary-safe file handling.",
            "Treat passwords, missing files, and corrupt archives as explicit error branches with observed channels and exit codes.",
        ),
        repair_hints=(
            "For archive mismatches, check binary mode, password handling, member path normalization, and corrupt-file diagnostics.",
        ),
        implementation_playbook=(
            "Open archives in binary mode and map CLI flags to standard-library archive operations before custom parsing.",
            "Preserve member path normalization, directory entries, passwords, corrupt-file errors, and output ordering from contracts.",
            "For Rust/clap-style archive CLIs, implement required-argument validation manually so missing-argument stderr includes every required flag in the Usage line, not only the missing flag.",
            "Preserve clap-style phrasing for missing arguments, value placeholders, blank lines, and the final \"For more information, try '--help'.\" hint when observed.",
        ),
        repair_playbook=(
            "For archive failures, compare binary/text mode, path separators, member ordering, password branch, and corrupt-input diagnostics.",
            "For missing required-argument failures, diff the complete clap-style Usage line, required flag order, value placeholder casing, blank lines, and final help hint.",
            "If argparse-style usage appears in stderr for a Rust/clap-like tool, replace it with the observed clap wording rather than tweaking argparse configuration.",
        ),
        anti_patterns=(
            "Do not decode archive payloads as UTF-8 unless the observed behavior is text-only.",
            "Do not use argparse's default usage/error formatting when observed stderr is Rust/clap-style.",
        ),
    ),
    ProfileRule(
        domain="terminal_ui",
        keywords=(
            "terminal",
            "ansi",
            "escape",
            "color",
            "tui",
            "screen",
            "cursor",
            "matrix",
        ),
        formats=("ansi", "terminal"),
        implementation_hints=(
            "Keep terminal control output deterministic under test conditions and preserve ANSI sequences only when observed.",
            "Avoid interactive waits unless stdin/TTY behavior is explicitly covered.",
        ),
        repair_hints=(
            "For terminal mismatches, compare raw escape sequences, screen dimensions, color flags, and timeout behavior.",
        ),
        implementation_playbook=(
            "Separate frame generation from timing so tests can render deterministic terminal output without interactive sleeps.",
            "Gate ANSI/color/cursor sequences on observed flags and environment; preserve raw escape bytes when present.",
        ),
        repair_playbook=(
            "For terminal failures, diff raw escaped output, color enablement, dimensions, frame count, and final cursor reset.",
        ),
        anti_patterns=(
            "Do not start unbounded animations or wait for a TTY during automated probes.",
        ),
    ),
    ProfileRule(
        domain="go_dependency_report",
        keywords=(
            "go-mod-outdated",
            "go.mod",
            "go list",
            "module",
            "modules",
            "dependency",
            "dependencies",
            "outdated",
            "direct",
            "indirect",
            "update",
            "version",
            "versions",
            "valid timestamps",
            "markdown",
            "ndjson",
        ),
        formats=("json", "table", "markdown"),
        implementation_hints=(
            "Treat Go module reports as newline-delimited JSON records that render deterministic tables; preserve missing-field behavior and direct/indirect filtering.",
            "Model Go flag/help/log conventions explicitly instead of using argparse defaults.",
        ),
        repair_hints=(
            "For Go module report mismatches, check NDJSON parsing, missing version fields, table alignment, markdown mode, direct filtering, and Go-style stderr.",
            "For stderr mismatches, copy observed Go flag/log output including executable path, timestamps, tabs, and parser wording.",
        ),
        implementation_playbook=(
            "Read stdin as newline-delimited JSON objects; ignore blank lines only if observed, and handle malformed records with Go encoding/json-style diagnostics.",
            "Represent module rows with Path/Version/Update/Indirect/Replace/Time fields and explicit defaults for missing Version or Update fields.",
            "Render default output as a fixed-width ASCII table with centered headers, padded cells, exact border widths, and final newline; render markdown mode separately.",
            "For go-mod-outdated markdown style, keep the same fixed column widths as the default table; the separator row uses the full column widths rather than shrinking to header or cell text.",
            "Implement -direct by filtering indirect modules, -ci by changing exit code only when outdated rows are present, and -style exactly as observed.",
            "Implement Go flag semantics manually: -help prints usage to stderr with exit 0; unknown flags print 'flag provided but not defined' plus usage; usage starts with 'Usage of /workspace/executable:' and preserves the exact flag list/order.",
            "For Go log-style errors, match the observed timestamp/layout and JSON parser wording from contracts instead of using current local time or Python JSONDecodeError text.",
            "For Go encoding/json literal errors, preserve wording such as \"invalid character 'h' in literal true (expecting 'r')\" instead of replacing it with unexpected EOF or beginning-of-value text.",
        ),
        repair_playbook=(
            "For table stdout failures, diff header centering with odd/even padding, per-column width, border dashes, cell padding, empty Version/Update rendering, and markdown-vs-default style.",
            "For markdown table failures, compare separator dash counts against the default table column widths (for example module/version columns can be wider than their header text) rather than recomputing markdown-minimal widths.",
            "For NDJSON failures, verify one JSON object per line, missing field defaults, Update object handling, Indirect boolean filtering, and malformed-line continuation behavior.",
            "For -help or unknown flag failures, preserve Go flag package wording, stderr channel, exit code, tab indentation, and executable path exactly.",
            "For log stderr failures, copy observed date/time prefix and Go encoding/json wording; do not call time.now(), leak Python parser messages, or collapse literal-name diagnostics to unexpected EOF.",
        ),
        anti_patterns=(
            "Do not parse the whole stdin as one JSON array when observations show newline-delimited JSON records.",
            "Do not use argparse help/errors for Go flag-package CLIs.",
            "Do not left-align table headers if observed output centers them.",
        ),
    ),
    ProfileRule(
        domain="filesystem_tool",
        keywords=(
            "file",
            "directory",
            "path",
            "stat",
            "permission",
            "symlink",
            "mkdir",
            "rename",
        ),
        formats=("file", "path"),
        implementation_hints=(
            "Perform path and filesystem operations explicitly, including missing paths, directories vs files, and symlink behavior when observed.",
            "Keep writes idempotent where feasible and surface OS errors through observed stderr and exit-code semantics.",
        ),
        repair_hints=(
            "For filesystem mismatches, check path normalization, current working directory assumptions, file mode, and missing-path errors.",
        ),
        implementation_playbook=(
            "Resolve paths relative to the current working directory unless observations show config/cache directories or env overrides.",
            "Model file, directory, symlink, missing-path, permission, and overwrite branches explicitly.",
            "Keep output ordering deterministic and match observed path separator style.",
        ),
        repair_playbook=(
            "For filesystem failures, compare cwd, path normalization, hidden files, directory traversal order, symlink handling, and OS error wording.",
        ),
        anti_patterns=(
            "Do not silently ignore filesystem errors.",
            "Do not assume Windows path separators for generated Linux submissions.",
        ),
    ),
)

GENERIC_IMPLEMENTATION_HINTS = (
    "Implement only behavior supported by cleanroom evidence; mark uncertain semantics as conservative branches rather than guessing hidden behavior.",
    "Preserve exact stdout/stderr channels, exit codes, argument parsing, and trailing newline behavior from observed contracts.",
)

GENERIC_REPAIR_HINTS = (
    "Repair the smallest shared semantic mismatch indicated by the failure cluster before broad rewrites.",
    "Prefer exact observed behavior over inferred summaries whenever they disagree.",
)


def infer_task_profile(
    *,
    documentation: str = "",
    cli_surface: CLISurface | None = None,
    corpus: Iterable[BehaviorSample] | None = None,
) -> dict:
    """Return a JSON-safe domain profile for prompting and metadata."""
    evidence_text = _evidence_text(documentation, cli_surface, corpus)
    scores = {
        rule.domain: _score_rule(rule, evidence_text)
        for rule in PROFILE_RULES
    }
    domains = [
        domain
        for domain, score in sorted(scores.items(), key=lambda item: (-item[1], item[0]))
        if score > 0
    ]
    primary_domain = domains[0] if domains else "generic_cli"
    selected_rules = [
        rule
        for rule in PROFILE_RULES
        if rule.domain in set(domains[:3])
    ]
    implementation_hints = _dedupe(
        [
            hint
            for rule in selected_rules
            for hint in rule.implementation_hints
        ]
        or list(GENERIC_IMPLEMENTATION_HINTS)
    )
    repair_hints = _dedupe(
        [
            hint
            for rule in selected_rules
            for hint in rule.repair_hints
        ]
        or list(GENERIC_REPAIR_HINTS)
    )
    input_format_hints = _dedupe(
        [
            fmt
            for rule in selected_rules
            for fmt in rule.formats
        ]
    )
    strategy_pack = _strategy_pack(primary_domain, selected_rules)
    return {
        "primary_domain": primary_domain,
        "domains": domains or ["generic_cli"],
        "confidence": _confidence(scores.get(primary_domain, 0)),
        "input_format_hints": input_format_hints,
        "implementation_hints": implementation_hints[:6],
        "repair_hints": repair_hints[:6],
        "strategy_pack": strategy_pack,
        "evidence_keywords": _evidence_keywords(evidence_text, selected_rules),
    }


def _strategy_pack(primary_domain: str, rules: list[ProfileRule]) -> dict:
    if not rules:
        return {
            "domain": "generic_cli",
            "implementation_playbook": list(GENERIC_IMPLEMENTATION_HINTS),
            "repair_playbook": list(GENERIC_REPAIR_HINTS),
            "anti_patterns": [],
        }
    primary_rule = next((rule for rule in rules if rule.domain == primary_domain), rules[0])
    return {
        "domain": primary_rule.domain,
        "implementation_playbook": list(primary_rule.implementation_playbook),
        "repair_playbook": list(primary_rule.repair_playbook),
        "anti_patterns": list(primary_rule.anti_patterns),
    }


def _evidence_text(
    documentation: str,
    cli_surface: CLISurface | None,
    corpus: Iterable[BehaviorSample] | None,
) -> str:
    chunks: list[str] = [documentation]
    if cli_surface is not None:
        chunks.extend(cli_surface.subcommands)
        chunks.extend(flag.name for flag in cli_surface.flags)
        chunks.extend(flag.description for flag in cli_surface.flags)
        chunks.extend(arg.name for arg in cli_surface.positional_args)
    for sample in corpus or []:
        chunks.append(sample.test_case.name)
        chunks.append(sample.test_case.description)
        chunks.extend(sample.test_case.args)
        chunks.append(sample.test_case.stdin)
        chunks.extend(sample.tags)
        chunks.append(sample.observed_result.stdout[:1000])
        chunks.append(sample.observed_result.stderr[:500])
    return "\n".join(chunk for chunk in chunks if chunk).lower()


def _score_rule(rule: ProfileRule, text: str) -> int:
    score = 0
    for keyword in rule.keywords:
        if re.search(rf"(?<![a-z0-9]){re.escape(keyword)}(?![a-z0-9])", text):
            score += 2 if " " in keyword else 1
    for fmt in rule.formats:
        if fmt in text:
            score += 1
    return score


def _confidence(score: int) -> str:
    if score >= 4:
        return "high"
    if score >= 2:
        return "medium"
    if score == 1:
        return "low"
    return "fallback"


def _evidence_keywords(text: str, rules: list[ProfileRule]) -> list[str]:
    observed: list[str] = []
    for rule in rules:
        for keyword in rule.keywords:
            if keyword in text:
                observed.append(keyword)
    return _dedupe(observed)[:12]


def _dedupe(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result
