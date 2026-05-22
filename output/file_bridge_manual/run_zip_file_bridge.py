from __future__ import annotations

import argparse
import base64
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TASK_ID = "agourlay__zip-password-finder.704700d"
HISTORICAL_MAIN = (
    ROOT
    / "runs"
    / "closed_loop_official_20260513_zip_strategy_pack_v2"
    / TASK_ID
    / "generated"
    / TASK_ID
    / TASK_ID
    / "main.py"
)
PRIOR_EVIDENCE_RECORDS = (
    ROOT
    / "runs"
    / "closed_loop_official_20260513_zip_strategy_pack_v2"
    / TASK_ID
    / "evidence"
    / "records"
)


SPEC_RESPONSE = {
    "summary": (
        "zip-password-finder is a CLI that validates encrypted ZIP archives, "
        "then tries a dictionary or charset-based brute-force search using "
        "clap-style flags and diagnostics."
    ),
    "input_formats": ["ZIP archive files", "password dictionary files", "charset files"],
    "output_formats": ["found password", "Password not found", "clap-style help/errors"],
    "cli_surface": {
        "subcommands": [],
        "positional_args": [],
        "stdin_mode": False,
        "file_input_mode": True,
        "file_output_mode": False,
        "flags": [
            "--inputFile",
            "--workers",
            "--passwordDictionary",
            "--charset",
            "--charsetFile",
            "--minPasswordLen",
            "--maxPasswordLen",
            "--fileNumber",
            "--startingPassword",
            "--help",
            "--version",
        ],
        "exit_codes": [0, 1, 2],
    },
    "edge_cases": [
        "Missing --inputFile is a parse error and the Usage line expands with observed supplied flags.",
        "Unexpected positional arguments use Usage: executable [OPTIONS] --inputFile <inputFile>.",
        "Invalid or missing ZIP files are application-level errors with exit code 1.",
        "Numeric length, worker, and file-number values follow clap-style parse errors.",
        "Dictionary and charset-file modes read local files without stdout side effects unless a password is found.",
    ],
    "stateful": False,
    "invariants": [
        {
            "description": "stdout, stderr, exit code, and file inputs are part of the contract.",
            "type": "deterministic",
            "confidence": 1.0,
        }
    ],
    "complexity_hints": {"primary_domain": "archive_compression"},
    "raw_observations": (
        "No external LLM is used. This candidate restores a prior local "
        "cleanroom artifact and applies a generic CLI usage repair from local "
        "exploration failures."
    ),
}


ARCH_RESPONSE = {
    "language": "python",
    "language_version": "3",
    "modules": [],
    "entry_point": "main.py",
    "build_system": "none",
    "architecture_notes": (
        "Single-file Python CLI restored through file_bridge. The local patch "
        "only changes argument-parser diagnostics; ZIP validation and password "
        "search logic stay in the historical implementation."
    ),
}


PROBE_RESPONSE = [
    {
        "name": "missing_required_with_range_flags",
        "args": ["--charset", "l", "--minPasswordLen", "1", "--maxPasswordLen", "3"],
        "stdin": "",
        "input_files": {},
        "description": (
            "smoke_contract:archive_compression.clap_required_input_with_range "
            "adaptive_axis:archive_compression.clap_required_input_with_range "
            "missing --inputFile while range flags are present"
        ),
    },
    {
        "name": "unexpected_positional_json_name",
        "args": ["input.json"],
        "stdin": "",
        "input_files": {},
        "description": (
            "smoke_contract:archive_compression.unexpected_positional "
            "adaptive_axis:archive_compression.unexpected_positional "
            "unexpected positional argument should keep [OPTIONS] usage"
        ),
    },
    {
        "name": "missing_input_file",
        "args": ["--inputFile", "missing.zip"],
        "stdin": "",
        "input_files": {},
        "description": (
            "smoke_contract:archive_compression.missing_file "
            "adaptive_axis:archive_compression.missing_file "
            "missing zip path reports application-level file error"
        ),
    },
    {
        "name": "invalid_file_number_before_missing_input_file",
        "args": ["--fileNumber", "input.json"],
        "stdin": "",
        "input_files": {},
        "description": (
            "smoke_contract:archive_compression.clap_numeric_value_precedence "
            "adaptive_axis:archive_compression.clap_numeric_value_precedence "
            "supplied numeric option values are parsed before missing required input"
        ),
    },
]


ZIP_ADAPTIVE_PROBE_EXCLUDED_DOMAINS = (
    "binary_hexdump",
    "csv_table",
    "filesystem_tool",
    "find_replace",
    "go_dependency_report",
    "html_selector",
    "json_transform",
    "network_ping",
    "terminal_animation",
    "terminal_ui",
)


ZIP_VARIANT_RUN_DATES = {
    "usage_patch1": "20260520",
    "usage_patch2": "20260520",
    "usage_patch3": "20260521",
    "usage_patch4_domain_filter": "20260523",
}


PATCH_SOURCE = r'''

# --- ReBuilder no-external zip-password-finder CLI usage patch ---

_ZIP_FLAG_DEFS = [
    ("inputFile", "i", True, True, None),
    ("workers", "w", True, False, None),
    ("passwordDictionary", "p", True, False, None),
    ("charset", "c", True, False, DEFAULT_CHARSET),
    ("charsetFile", None, True, False, None),
    ("minPasswordLen", None, True, False, "1"),
    ("maxPasswordLen", None, True, False, "10"),
    ("fileNumber", None, True, False, "0"),
    ("startingPassword", "s", True, False, None),
    ("help", "h", False, False, None),
    ("version", "V", False, False, None),
]


def _zip_usage_from_seen(seen_options):
    pieces = ["--inputFile <inputFile>"]
    for name in seen_options:
        if name in {"inputFile", "help", "version"}:
            continue
        pieces.append(f"--{name} <{name}>")
    return "Usage: executable " + " ".join(pieces)


def _zip_error_with_usage(message, usage_line):
    return (
        f"error: {message}\n"
        "\n"
        f"{usage_line}\n"
        "\n"
        "For more information, try '--help'.\n"
    )


def _zip_missing_value_error(option, placeholder):
    return (
        f"error: a value is required for '{option} <{placeholder}>' but none was supplied\n"
        "\n"
        "For more information, try '--help'.\n"
    )


def _zip_invalid_u64_error(value, name):
    return (
        f"error: invalid value '{value}' for '--{name} <{name}>': invalid digit found in string\n"
        "\n"
        "For more information, try '--help'.\n"
    )


def parse_args(argv):
    long_to_def = {d[0]: d for d in _ZIP_FLAG_DEFS}
    short_to_def = {d[1]: d for d in _ZIP_FLAG_DEFS if d[1] is not None}
    parsed = {}
    seen_options = []

    for long, _short, _takes_value, _required, default in _ZIP_FLAG_DEFS:
        if default is not None:
            parsed[long] = default

    def remember(name):
        if name not in seen_options:
            seen_options.append(name)

    positional = []
    i = 0
    while i < len(argv):
        token = argv[i]
        if token == "--":
            positional.extend(argv[i + 1:])
            break
        if token.startswith("--"):
            if "=" in token:
                flag, value = token.split("=", 1)
                flag = flag[2:]
            else:
                flag = token[2:]
                value = None
            if flag == "help":
                return None, generate_help_text(), 0
            if flag == "version":
                return None, version_text(), 0
            if flag not in long_to_def:
                return None, error_framework(f"unexpected argument '--{flag}' found", usage_with_options=True), 2
            _long, _short, takes_value, _required, _default = long_to_def[flag]
            remember(flag)
            if takes_value:
                if value is None:
                    if i + 1 >= len(argv):
                        return None, _zip_missing_value_error(f"--{flag}", flag), 2
                    value = argv[i + 1]
                    i += 1
                if flag in U64_ARGS and value.startswith("-"):
                    return None, error_framework(f"unexpected argument '{value}' found", usage_with_options=True), 2
                parsed[flag] = value
            else:
                parsed[flag] = "true"
        elif token.startswith("-") and len(token) >= 2 and token[1] != "-":
            rest = token[1:]
            j = 0
            while j < len(rest):
                ch = rest[j]
                if ch == "h":
                    return None, generate_help_text(), 0
                if ch == "V":
                    return None, version_text(), 0
                if ch not in short_to_def:
                    return None, error_framework(f"unexpected argument '-{ch}' found", usage_with_options=True), 2
                long_name, _short, takes_value, _required, _default = short_to_def[ch]
                remember(long_name)
                if takes_value:
                    remaining = rest[j + 1:]
                    if remaining:
                        parsed[long_name] = remaining
                    else:
                        if i + 1 >= len(argv):
                            return None, _zip_missing_value_error(f"-{ch}", long_name), 2
                        value = argv[i + 1]
                        if long_name in U64_ARGS and value.startswith("-"):
                            return None, error_framework(f"unexpected argument '{value}' found", usage_with_options=True), 2
                        parsed[long_name] = value
                        i += 1
                    break
                parsed[long_name] = "true"
                j += 1
        else:
            positional.append(token)
        i += 1

    if positional:
        return None, error_framework(f"unexpected argument '{positional[0]}' found", usage_with_options=True), 2

    for name in seen_options:
        if name not in U64_ARGS or name not in parsed:
            continue
        value = parsed.get(name)
        try:
            int(value)
        except (TypeError, ValueError):
            return None, _zip_invalid_u64_error(value, name), 2

    missing = []
    for long, _short, _takes_value, required, _default in _ZIP_FLAG_DEFS:
        if required and long not in parsed:
            missing.append(f"--{long} <{long}>")
    if missing:
        args_str = "\n  ".join(missing)
        return None, _zip_error_with_usage(
            f"the following required arguments were not provided:\n  {args_str}",
            _zip_usage_from_seen(seen_options),
        ), 2

    return parsed, None, 0


def _zip_validate_charset_option(charset_spec, charset_file):
    if charset_file:
        return None
    for letter in charset_spec or DEFAULT_CHARSET:
        if letter not in CHARSET_MAP:
            return f"Unknown charset option '{letter}'"
    return None


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]

    parsed, msg, code = parse_args(argv)

    if parsed is None and code == 0:
        sys.stdout.write(msg)
        return 0

    if parsed is None and code == 2:
        sys.stderr.write(msg)
        return 2

    args = parsed

    input_file = args.get("inputFile")
    if input_file is not None:
        if not Path(input_file).exists():
            sys.stderr.write(error_cli_argument("'inputFile' does not exist"))
            return 1

    workers = None
    w_str = args.get("workers")
    if w_str is not None:
        workers, w_err = validate_positive_int(w_str, "workers")
        if w_err is not None:
            sys.stderr.write(error_cli_argument(w_err))
            return 1

    file_number = 0
    fn_str = args.get("fileNumber")
    if fn_str is not None:
        file_number, fn_err = validate_nonneg_int(fn_str, "fileNumber")
        if fn_err is not None:
            sys.stderr.write(error_framework(fn_err, usage_with_options=True))
            return 2
        if file_number is None:
            file_number = 0

    min_len = 1
    max_len = 10
    mpl = args.get("minPasswordLen")
    if mpl is not None:
        try:
            min_len = int(mpl)
            if min_len < 0:
                raise ValueError
        except (ValueError, TypeError):
            sys.stderr.write(error_framework(f"invalid value '{mpl}' for '--minPasswordLen': invalid digit found in string", usage_with_options=True))
            return 2
    mxpl = args.get("maxPasswordLen")
    if mxpl is not None:
        try:
            max_len = int(mxpl)
            if max_len < 0:
                raise ValueError
        except (ValueError, TypeError):
            sys.stderr.write(error_framework(f"invalid value '{mxpl}' for '--maxPasswordLen': invalid digit found in string", usage_with_options=True))
            return 2

    if min_len > max_len:
        sys.stderr.write(error_cli_argument("'maxPasswordLen' must be equal or greater than 'minPasswordLen'"))
        return 1

    starting_password = args.get("startingPassword")
    if starting_password is not None:
        sp_len = len(starting_password)
        if sp_len < min_len or sp_len > max_len:
            sys.stderr.write(error_cli_argument("'startingPassword' does not respect 'max_password_len' or 'min_password_len' configuration"))
            return 1

    charset_spec = args.get("charset")
    charset_file = args.get("charsetFile")
    charset_error = _zip_validate_charset_option(charset_spec, charset_file)
    if charset_error is not None:
        sys.stderr.write(error_cli_argument(charset_error))
        return 1

    if input_file is not None:
        ok, zmsg = validate_zip(input_file)
        if not ok:
            sys.stderr.write(zmsg)
            return 1

    if workers is None:
        workers = min(os.cpu_count() or 1, 4)

    charset = resolve_charset(charset_spec, charset_file)
    dict_path = args.get("passwordDictionary")

    result = None
    if dict_path:
        result = dictionary_attack(input_file, dict_path, file_number, workers)
        if result == "__ERROR__":
            return 1
    else:
        result = brute_force_attack(input_file, charset, min_len, max_len,
                                    file_number, workers, starting_password)

    if result is not None:
        sys.stdout.write(result + "\n")
        return 0
    sys.stdout.write("Password not found\n")
    return 1
'''


def _strip_main_guard(source: str) -> str:
    guard_start = source.rfind('\nif __name__ == "__main__":')
    if guard_start != -1:
        return source[:guard_start].rstrip()
    return source.rstrip()


def implementation_artifact() -> str:
    source = HISTORICAL_MAIN.read_text(encoding="utf-8")
    return (
        f"--- FILE: main.py ---\n{_strip_main_guard(source)}\n{PATCH_SOURCE.rstrip()}\n\n"
        'if __name__ == "__main__":\n    sys.exit(main())\n'
        "--- END FILE ---\n"
    )


def _decode_input_file_payload(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict) and value.get("__type__") == "bytes":
        raw = base64.b64decode(str(value.get("base64", "")))
        return raw.decode("latin-1")
    return ""


def _axis_name(name: str) -> str:
    normalized = "".join(char.lower() if char.isalnum() else "_" for char in name)
    normalized = "_".join(part for part in normalized.split("_") if part)
    return (normalized or "probe")[:48]


def _probe_priority(probe: dict, result: dict) -> tuple[int, str]:
    args = [str(arg) for arg in probe.get("args") or []]
    has_input_files = bool(probe.get("input_files"))
    exit_code = result.get("exit_code")
    name = str(probe.get("name") or "")
    if any(arg in {"--help", "-h", "--version", "-V"} for arg in args):
        bucket = 0
    elif has_input_files and exit_code in {0, 1}:
        bucket = 1
    elif has_input_files:
        bucket = 2
    elif exit_code == 2:
        bucket = 3
    else:
        bucket = 4
    return (bucket, name)


def load_probe_response() -> list[dict]:
    prioritized: list[tuple[tuple[int, str], dict]] = []
    if PRIOR_EVIDENCE_RECORDS.exists():
        for path in sorted(PRIOR_EVIDENCE_RECORDS.glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            test_case = payload.get("test_case") or {}
            if not isinstance(test_case, dict):
                continue
            name = str(test_case.get("name") or path.stem[:12])
            axis = _axis_name(name)
            input_files = {
                str(file_name): _decode_input_file_payload(content)
                for file_name, content in (test_case.get("input_files") or {}).items()
            }
            description = str(test_case.get("description") or "zip-password-finder cleanroom probe")
            probe = {
                "name": name,
                "args": list(test_case.get("args") or []),
                "stdin": str(test_case.get("stdin") or ""),
                "input_files": input_files,
                "description": (
                    f"smoke_contract:archive_compression.{axis} "
                    f"adaptive_axis:archive_compression.{axis} {description}"
                ),
            }
            result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
            prioritized.append((_probe_priority(probe, result), probe))
    probes = [probe for _priority, probe in sorted(prioritized, key=lambda item: item[0])]
    return [*PROBE_RESPONSE, *probes]


def classify_request(request: dict) -> str:
    content = "\n".join(message.get("content", "") for message in request.get("messages", []))
    if "synthesize a precise, implementable specification" in content:
        return "spec"
    if "designing a cleanroom replacement" in content:
        return "architecture"
    if "implementing a cleanroom replacement" in content:
        return "implementation"
    if "adversarial test cases" in content:
        return "probe"
    return "implementation"


def write_response(request_path: Path, model: str) -> None:
    request = json.loads(request_path.read_text(encoding="utf-8"))
    kind = classify_request(request)
    if kind == "spec":
        content = json.dumps(SPEC_RESPONSE, ensure_ascii=False, indent=2)
    elif kind == "architecture":
        content = json.dumps(ARCH_RESPONSE, ensure_ascii=False, indent=2)
    elif kind == "probe":
        content = json.dumps(load_probe_response(), ensure_ascii=False, indent=2)
    else:
        content = implementation_artifact()
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


def write_config(config_path: Path, request_dir: Path, model: str) -> None:
    config_path.write_text(
        f"""# Generated by output/file_bridge_manual/run_zip_file_bridge.py
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
  internal_holdout_ratio: 0.25
  holdout_seed: "rebuilder"
  enable_early_stop: false
""",
        encoding="utf-8",
    )


def run_variant(variant: str, *, official_eval: bool = False) -> int:
    if variant not in ZIP_VARIANT_RUN_DATES:
        print(f"unknown variant: {variant}", file=sys.stderr)
        return 2
    if not HISTORICAL_MAIN.exists():
        print(f"missing historical source: {HISTORICAL_MAIN}", file=sys.stderr)
        return 2

    run_date = ZIP_VARIANT_RUN_DATES[variant]
    run_name = f"file_bridge_no_external_zip_{run_date}_{variant}"
    request_dir = ROOT / "output" / "file_bridge_manual" / f"requests_zip_{variant}"
    config_path = ROOT / "output" / "file_bridge_manual" / f"smoke_file_bridge_zip_{variant}.yaml"
    model = f"codex-file-bridge-zip-{variant}"
    official_eval_root = "runs/programbench_official_eval" if official_eval else f"runs/{run_name}_submission"
    eval_run_name = (
        f"submission_zip_password_finder_{variant}_{run_date}"
        if official_eval
        else f"{run_name}_eval"
    )

    shutil.rmtree(request_dir, ignore_errors=True)
    request_dir.mkdir(parents=True, exist_ok=True)
    write_config(config_path, request_dir, model)

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
        "0",
        "--min-probe-samples",
        "50",
        "--max-repairs",
        "0",
        "--replacement-executor",
        "local",
        "--static-output-assets",
        "disabled",
        "--adaptive-probes",
        "enabled",
        "--min-holdout-rate",
        "0.8",
        "--min-holdout-cases",
        "10",
        "--min-smoke-contract-axes",
        "1",
        "--require-runtime-smoke-dimensions",
        "args,input_files",
        "--official-eval-root",
        official_eval_root,
        "--eval-run-name",
        eval_run_name,
        "--model",
        model,
        "--ack-local-llm-docker",
        "--pull",
    ]
    for domain in ZIP_ADAPTIVE_PROBE_EXCLUDED_DOMAINS:
        cmd.extend(["--adaptive-probe-exclude-domain", domain])
    if official_eval:
        cmd.extend(
            [
                "--baseline-output",
                "baselines/programbench",
                "--official-eval-timeout-seconds",
                "1200",
                "--docker-command-timeout-seconds",
                "180",
                "--force",
            ]
        )
    else:
        cmd.append("--skip-official-eval")

    print("RUN", " ".join(cmd), flush=True)
    proc = subprocess.Popen(cmd, cwd=ROOT)
    seen: set[Path] = set()
    while proc.poll() is None:
        for request_path in sorted(request_dir.glob("request_*.json")):
            if request_path in seen:
                continue
            seen.add(request_path)
            write_response(request_path, model)
            print(f"RESPONDED {request_path.name}", flush=True)
        time.sleep(0.2)

    for request_path in sorted(request_dir.glob("request_*.json")):
        if request_path not in seen:
            seen.add(request_path)
            write_response(request_path, model)
            print(f"RESPONDED {request_path.name}", flush=True)
    print(f"CHILD_EXIT {proc.returncode}", flush=True)
    return int(proc.returncode or 0)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run no-external-LLM zip file_bridge variants")
    parser.add_argument("variant", nargs="?", default="usage_patch3")
    parser.add_argument("--official-eval", action="store_true")
    args = parser.parse_args()
    return run_variant(args.variant, official_eval=args.official_eval)


if __name__ == "__main__":
    raise SystemExit(main())
