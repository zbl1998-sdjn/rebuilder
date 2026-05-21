from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import unicodedata
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HARNESS_PATH = ROOT / "output" / "file_bridge_manual" / "run_go_mod_file_bridge.py"


def load_harness():
    spec = importlib.util.spec_from_file_location("run_go_mod_file_bridge", HARNESS_PATH)
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


def run_generated(tmp_path: Path, args: list[str], stdin: str) -> subprocess.CompletedProcess[str]:
    harness = load_harness()
    main_py = tmp_path / "main.py"
    main_py.write_text(extract_main_py(harness.implementation_artifact("table_patch5")), encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(main_py), *args],
        input=stdin,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def display_width(text: str) -> int:
    width = 0
    for char in text:
        if unicodedata.combining(char):
            continue
        if unicodedata.east_asian_width(char) in {"F", "W"}:
            width += 2
        else:
            width += 1
    return width


def test_table_patch5_supports_go_flag_terminator(tmp_path: Path) -> None:
    result = run_generated(
        tmp_path,
        ["--", "-style", "markdown"],
        '{"Path":"github.com/example/pkg","Version":"v1.0.0"}\n',
    )

    assert result.returncode == 0
    assert result.stderr == ""
    assert "github.com/example/pkg" in result.stdout
    assert result.stdout.startswith("+")


def test_table_patch5_uses_replacement_module_version(tmp_path: Path) -> None:
    result = run_generated(
        tmp_path,
        [],
        (
            '{"Path":"github.com/original/module","Version":"v1.0.0",'
            '"Replace":{"Path":"github.com/fork/module","Version":"v2.5.0",'
            '"Update":{"Version":"v2.6.0"}}}\n'
        ),
    )

    assert result.returncode == 0
    assert result.stderr == ""
    assert "github.com/original/module" in result.stdout
    assert "v2.5.0" in result.stdout
    assert "v2.6.0" in result.stdout


def test_table_patch5_reports_truncated_json_as_unexpected_eof(tmp_path: Path) -> None:
    result = run_generated(
        tmp_path,
        [],
        '{"Path":"github.com/example/pkg","Version":"v1.0.0"\n',
    )

    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr.endswith("unexpected EOF\n")


def test_table_patch5_uses_display_width_for_wide_module_names(tmp_path: Path) -> None:
    result = run_generated(
        tmp_path,
        [],
        '{"Path":"github.com/例子/模块","Version":"v1.0.0"}\n',
    )

    assert result.returncode == 0
    assert result.stderr == ""
    lines = [line for line in result.stdout.splitlines() if line]
    assert len(lines) >= 4
    expected = display_width(lines[0])
    assert all(display_width(line) == expected for line in lines)
