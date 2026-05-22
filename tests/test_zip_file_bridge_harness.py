from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HARNESS_PATH = ROOT / "output" / "file_bridge_manual" / "run_zip_file_bridge.py"


def load_harness():
    spec = importlib.util.spec_from_file_location("run_zip_file_bridge", HARNESS_PATH)
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


def run_generated(tmp_path: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    harness = load_harness()
    main_py = tmp_path / "main.py"
    main_py.write_text(extract_main_py(harness.implementation_artifact()), encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(main_py), *args],
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        cwd=tmp_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def test_charset_option_is_validated_before_zip_archive_parsing(tmp_path: Path) -> None:
    (tmp_path / "empty.zip").write_bytes(b"")

    result = run_generated(
        tmp_path,
        [
            "--inputFile",
            "empty.zip",
            "--charset",
            "ab",
            "--minPasswordLen",
            "1",
            "--maxPasswordLen",
            "2",
        ],
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == 'CLI argument error - "Unknown charset option \'a\'"\n'


def test_missing_charset_value_uses_clap_placeholder_diagnostic(tmp_path: Path) -> None:
    result = run_generated(tmp_path, ["--charset"])

    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr == (
        "error: a value is required for '--charset <charset>' but none was supplied\n"
        "\n"
        "For more information, try '--help'.\n"
    )


def test_invalid_file_number_is_validated_before_missing_required_input(tmp_path: Path) -> None:
    result = run_generated(tmp_path, ["--fileNumber", "input.json"])

    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr == (
        "error: invalid value 'input.json' for '--fileNumber <fileNumber>': "
        "invalid digit found in string\n"
        "\n"
        "For more information, try '--help'.\n"
    )


def test_generated_config_uses_file_bridge_only(tmp_path: Path) -> None:
    harness = load_harness()
    config_path = tmp_path / "config.yaml"
    request_dir = tmp_path / "requests"

    harness.write_config(config_path, request_dir, "codex-file-bridge-zip-usage_patch3")

    config_text = config_path.read_text(encoding="utf-8")
    assert 'provider: "file_bridge"' in config_text
    assert "codex-file-bridge-zip-usage_patch3" in config_text
    assert "kimi" not in config_text.lower()
    assert "glm" not in config_text.lower()
    assert "openai" not in config_text.lower()


def test_zip_file_bridge_probe_plan_stays_archive_domain_only(
    monkeypatch,
    tmp_path: Path,
) -> None:
    harness = load_harness()
    historical_main = tmp_path / "main.py"
    historical_main.write_text("print('historical')\n", encoding="utf-8")
    captured: dict[str, object] = {}

    class FakePopen:
        returncode = 0

        def __init__(self, command: list[str], *, cwd: Path) -> None:
            captured["command"] = command
            captured["cwd"] = cwd

        def poll(self) -> int:
            return 0

    monkeypatch.setattr(harness, "ROOT", tmp_path)
    monkeypatch.setattr(harness, "HISTORICAL_MAIN", historical_main)
    monkeypatch.setattr(harness.subprocess, "Popen", FakePopen)
    monkeypatch.setattr(harness.time, "sleep", lambda _seconds: None)

    assert harness.run_variant("usage_patch3") == 0

    command = captured["command"]
    assert isinstance(command, list)
    excluded_domains = [
        str(command[index + 1])
        for index, value in enumerate(command)
        if value == "--adaptive-probe-exclude-domain"
    ]
    assert "json_transform" in excluded_domains
    assert "archive_compression" not in excluded_domains


def test_zip_domain_filter_variant_uses_fresh_run_name(monkeypatch, tmp_path: Path) -> None:
    harness = load_harness()
    historical_main = tmp_path / "main.py"
    historical_main.write_text("print('historical')\n", encoding="utf-8")
    captured: dict[str, object] = {}

    class FakePopen:
        returncode = 0

        def __init__(self, command: list[str], *, cwd: Path) -> None:
            captured["command"] = command
            captured["cwd"] = cwd

        def poll(self) -> int:
            return 0

    monkeypatch.setattr(harness, "ROOT", tmp_path)
    monkeypatch.setattr(harness, "HISTORICAL_MAIN", historical_main)
    monkeypatch.setattr(harness.subprocess, "Popen", FakePopen)
    monkeypatch.setattr(harness.time, "sleep", lambda _seconds: None)

    assert harness.run_variant("usage_patch4_domain_filter") == 0

    command = captured["command"]
    assert isinstance(command, list)
    assert "runs/file_bridge_no_external_zip_20260523_usage_patch4_domain_filter" in command
    assert "file_bridge_no_external_zip_20260523_usage_patch4_domain_filter_eval" in command
    assert "codex-file-bridge-zip-usage_patch4_domain_filter" in command
