from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HARNESS_PATH = ROOT / "output" / "file_bridge_manual" / "run_chmln_file_bridge.py"


def load_harness():
    spec = importlib.util.spec_from_file_location("run_chmln_file_bridge", HARNESS_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def extract_main_py(artifact: str) -> str:
    start = "--- FILE: main.py ---\n"
    end = "\n--- END FILE ---"
    assert artifact.startswith(start)
    assert artifact.endswith(end + "\n") or artifact.endswith(end)
    return artifact[len(start) : artifact.rfind(end)]


def run_generated(tmp_path: Path, args: list[str], stdin: str = "") -> subprocess.CompletedProcess[str]:
    harness = load_harness()
    main_py = tmp_path / "main.py"
    main_py.write_text(
        extract_main_py(harness.implementation_artifact("baseline_regex_patch1")),
        encoding="utf-8",
    )
    return subprocess.run(
        [sys.executable, str(main_py), *args],
        input=stdin,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        cwd=tmp_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def test_generated_artifact_normalizes_tarball_newlines() -> None:
    harness = load_harness()
    source = extract_main_py(harness.implementation_artifact("baseline_regex_patch1"))

    assert "\r" not in source


def test_unclosed_group_uses_rust_regex_diagnostic(tmp_path: Path) -> None:
    result = run_generated(tmp_path, ["(abc", "X"], "abc\n(abc\n")

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == (
        "error: invalid regex regex parse error:\n"
        "    (abc\n"
        "    ^\n"
        "error: unclosed group\n"
    )


def test_existing_lookaround_diagnostic_is_preserved(tmp_path: Path) -> None:
    result = run_generated(tmp_path, ["(?<!foo)bar", "X"], "bar\nfoobar\n")

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == (
        "error: invalid regex regex parse error:\n"
        "    (?<!foo)bar\n"
        "    ^^^^\n"
        "error: look-around, including look-ahead and look-behind, is not supported\n"
    )


def test_negative_max_replacements_still_matches_clap_unexpected_argument(tmp_path: Path) -> None:
    result = run_generated(tmp_path, ["--max-replacements", "-1", "a", "b"], "aaa\n")

    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr == (
        "error: unexpected argument '-1' found\n\n"
        "  tip: to pass '-1' as a value, use '-- -1'\n\n"
        "Usage: executable [OPTIONS] <FIND> <REPLACE_WITH> [FILES]...\n\n"
        "For more information, try '--help'.\n"
    )
