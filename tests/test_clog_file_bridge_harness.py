from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HARNESS_PATH = ROOT / "output" / "file_bridge_manual" / "run_clog_file_bridge.py"


def load_harness():
    spec = importlib.util.spec_from_file_location("run_clog_file_bridge", HARNESS_PATH)
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


def test_empty_git_outfile_fallback_matches_reference_blank_padding(tmp_path: Path) -> None:
    harness = load_harness()
    main_py = tmp_path / "main.py"
    main_py.write_text(
        extract_main_py(harness.implementation_artifact("from_latest_patch6")),
        encoding="utf-8",
    )
    (tmp_path / ".clog.toml").write_text("[clog]\n", encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(main_py),
            "--from",
            "HEAD~2",
            "--to",
            "HEAD",
            "--outfile",
            "changelog.md",
        ],
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        cwd=tmp_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert result.returncode == 0
    assert result.stdout.startswith("changelog written. (took ")
    assert result.stderr == ""
    content = (tmp_path / "changelog.md").read_text(encoding="utf-8")
    assert content.startswith('<a name=""></a>\n##   (')
    assert content.endswith(")\n\n\n\n\n")
