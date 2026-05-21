from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HARNESS_PATH = ROOT / "output" / "file_bridge_manual" / "run_xsv_file_bridge.py"


def load_harness():
    spec = importlib.util.spec_from_file_location("run_xsv_file_bridge", HARNESS_PATH)
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
    main_py.write_text(
        extract_main_py(harness.implementation_artifact("restore_patch4")),
        encoding="utf-8",
    )
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


def test_frequency_ties_preserve_first_seen_after_count(tmp_path: Path) -> None:
    (tmp_path / "data.csv").write_text(
        "color,size\nred,S\nblue,M\nred,L\nred,S\nblue,S\n",
        encoding="utf-8",
    )

    result = run_generated(tmp_path, ["frequency", "data.csv"])

    assert result.returncode == 0
    assert result.stderr == ""
    assert result.stdout == (
        "field,value,count\n"
        "color,red,3\n"
        "color,blue,2\n"
        "size,S,3\n"
        "size,M,1\n"
        "size,L,1\n"
    )


def test_frequency_limit_zero_disables_limit_and_preserves_first_seen_ties(tmp_path: Path) -> None:
    (tmp_path / "data.csv").write_text(
        "name,age\nalice,30\nbob,25\ncarol,30\n",
        encoding="utf-8",
    )

    result = run_generated(tmp_path, ["frequency", "--limit", "0", "data.csv"])

    assert result.returncode == 0
    assert result.stderr == ""
    assert result.stdout == (
        "field,value,count\n"
        "name,alice,1\n"
        "name,bob,1\n"
        "name,carol,1\n"
        "age,30,2\n"
        "age,25,1\n"
    )


def test_index_without_input_uses_reference_usage_diagnostic(tmp_path: Path) -> None:
    result = run_generated(tmp_path, ["index"])

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == (
        "Invalid arguments.\n\n"
        "Usage:\n"
        "    xsv index [options] <input>\n"
        "    xsv index --help\n"
    )


def test_partition_without_required_args_uses_reference_usage(tmp_path: Path) -> None:
    result = run_generated(tmp_path, ["partition"])

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == (
        "Invalid arguments.\n\n"
        "Usage:\n"
        "    xsv partition [options] <column> <outdir> [<input>]\n"
        "    xsv partition --help\n"
    )


def test_sample_without_required_args_uses_reference_usage(tmp_path: Path) -> None:
    result = run_generated(tmp_path, ["sample"])

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == (
        "Invalid arguments.\n\n"
        "Usage:\n"
        "    xsv sample [options] <sample-size> [<input>]\n"
        "    xsv sample --help\n"
    )


def test_join_help_restores_full_observed_text(tmp_path: Path) -> None:
    harness = load_harness()
    expected = harness._load_observed_subcommand_help_texts()["join"]

    result = run_generated(tmp_path, ["join", "--help"])

    assert result.returncode == 0
    assert result.stderr == ""
    assert result.stdout == expected


def test_stats_everything_uses_streaming_float_sum_format(tmp_path: Path) -> None:
    (tmp_path / "data.csv").write_text(
        "id,value\n"
        "1,10.5\n"
        "2,20.3\n"
        "3,15.7\n"
        "4,8.2\n"
        "5,30.1\n",
        encoding="utf-8",
    )

    result = run_generated(tmp_path, ["stats", "--everything", "data.csv"])

    assert result.returncode == 0
    assert result.stderr == ""
    assert result.stdout == (
        "field,type,sum,min,max,min_length,max_length,mean,stddev,median,mode,cardinality\n"
        "id,Integer,15,1,5,1,1,3,1.4142135623730951,3,N/A,5\n"
        "value,Float,84.80000000000001,8.2,30.1,3,4,16.96,"
        "7.795793737651094,15.7,N/A,5\n"
    )


def test_stats_without_everything_uses_reference_welford_float_output(tmp_path: Path) -> None:
    (tmp_path / "data.csv").write_text(
        "name,score\n"
        "Alice,95.5\n"
        "Bob,87.3\n"
        "Charlie,92.1\n"
        "Diana,88.7\n"
        "Eve,91.2",
        encoding="utf-8",
    )

    result = run_generated(tmp_path, ["stats", "data.csv"])

    assert result.returncode == 0
    assert result.stderr == ""
    assert result.stdout == (
        "field,type,sum,min,max,min_length,max_length,mean,stddev\n"
        "name,Unicode,,Alice,Eve,3,7,,\n"
        "score,Float,454.79999999999995,87.3,95.5,4,4,"
        "90.96000000000001,2.8450659043333277\n"
    )
