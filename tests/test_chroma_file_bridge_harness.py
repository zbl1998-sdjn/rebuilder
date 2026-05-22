from __future__ import annotations

import contextlib
import io
import importlib.util
import types
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HARNESS_PATH = ROOT / "output" / "file_bridge_manual" / "run_chroma_file_bridge.py"


def load_harness():
    spec = importlib.util.spec_from_file_location("run_chroma_file_bridge", HARNESS_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_candidate(source: str):
    module = types.ModuleType("chroma_candidate")
    exec(compile(source, "<chroma_candidate>", "exec"), module.__dict__)
    return module


def test_restore_patch2_generalization_probe_adds_chroma_specific_axes() -> None:
    harness = load_harness()

    probes = harness.probe_response("restore_patch2_generalization_probe")
    probe_names = {probe["name"] for probe in probes}

    assert "trace_python_stdin" in probe_names
    assert "unbuffered_terminal8_stdin" in probe_names
    assert "formatter_tokens_stdin" in probe_names
    assert "html_lines_table_linkable_file" in probe_names
    assert "style_as_missing_file" in probe_names
    assert "lexer_filename_stdin" in probe_names
    assert "multi_file_python_formatter" in probe_names


def test_restore_patch2_generalization_probe_reuses_restore_patch2_source() -> None:
    harness = load_harness()

    source = harness.patched_source("restore_patch2_generalization_probe")

    assert "def validate_files(opts):" in source
    assert "expected string value but got" in source


def test_restore_patch3_generalization_probe_repairs_html_line_table_style_file() -> None:
    harness = load_harness()
    module = load_candidate(harness.patched_source("restore_patch3_generalization_probe"))
    stdout = io.StringIO()
    stderr = io.StringIO()

    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        exit_code = module.main(
            [
                "--html",
                "--html-only",
                "--html-lines",
                "--html-lines-table",
                "--html-linkable-lines",
                "--html-highlight",
                "2",
                "--style",
                "github",
                "tests/test_chroma_file_bridge_harness.py",
            ]
        )

    assert exit_code == 0
    assert "open github" not in stderr.getvalue()
    assert '<table class="lntable">' in stdout.getvalue()
    assert 'id="L2"' in stdout.getvalue()


def test_restore_patch3_generalization_probe_preserves_missing_style_file_error() -> None:
    harness = load_harness()
    module = load_candidate(harness.patched_source("restore_patch3_generalization_probe"))
    stdout = io.StringIO()
    stderr = io.StringIO()

    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        exit_code = module.main(["--html-styles", "--style", "missing-style.xml"])

    assert exit_code == 1
    assert stdout.getvalue() == ""
    assert "open missing-style.xml" in stderr.getvalue()


def test_config_is_file_bridge_only() -> None:
    harness = load_harness()
    config_path = ROOT / "output" / "file_bridge_manual" / "_test_chroma_config.yaml"
    request_dir = ROOT / "output" / "file_bridge_manual" / "_test_chroma_requests"
    try:
        harness.write_config(config_path, request_dir, "codex-file-bridge-chroma-test")
        config_text = config_path.read_text(encoding="utf-8")
    finally:
        config_path.unlink(missing_ok=True)

    assert 'provider: "file_bridge"' in config_text
    assert "local_openai:" not in config_text
    assert "kimi:" not in config_text
    assert "glm:" not in config_text


def test_official_eval_mode_keeps_file_bridge_harness_active() -> None:
    harness = load_harness()

    command = harness.build_closed_loop_command(
        "restore_patch3_generalization_probe",
        config_path=ROOT / "example.yaml",
        model="codex-file-bridge-chroma-test",
        run_name="file_bridge_no_external_chroma_test",
        pull=True,
        run_official_eval=True,
        official_eval_timeout_seconds=3600.0,
    )

    assert "--skip-official-eval" not in command
    assert "--official-eval-timeout-seconds" in command
    assert "3600" in command
    assert "--ack-local-llm-docker" in command


def test_official_eval_mode_forwards_resource_limits_and_force() -> None:
    harness = load_harness()

    command = harness.build_closed_loop_command(
        "restore_patch3_generalization_probe",
        config_path=ROOT / "example.yaml",
        model="codex-file-bridge-chroma-test",
        run_name="file_bridge_no_external_chroma_test",
        run_official_eval=True,
        official_eval_timeout_seconds=7200.0,
        docker_command_timeout_seconds=300.0,
        workers=1,
        branch_workers=1,
        docker_cpus=2,
        branch_retries=0,
        force=True,
    )

    assert command[command.index("--official-eval-timeout-seconds") + 1] == "7200"
    assert command[command.index("--docker-command-timeout-seconds") + 1] == "300"
    assert command[command.index("--workers") + 1] == "1"
    assert command[command.index("--branch-workers") + 1] == "1"
    assert command[command.index("--docker-cpus") + 1] == "2"
    assert command[command.index("--branch-retries") + 1] == "0"
    assert "--force" in command


def test_default_mode_stops_before_official_eval() -> None:
    harness = load_harness()

    command = harness.build_closed_loop_command(
        "restore_patch3_generalization_probe",
        config_path=ROOT / "example.yaml",
        model="codex-file-bridge-chroma-test",
        run_name="file_bridge_no_external_chroma_test",
    )

    assert "--skip-official-eval" in command
