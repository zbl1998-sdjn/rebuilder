"""Prepare a ProgramBench cleanroom workspace for ReBuilder.

This script uses only the official `task_cleanroom` image. It does not pull or
copy evaluation images, hidden tests, or test blobs.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.programbench.adapter import DockerCleanroomExporter, ProgramBenchTaskAdapter
from core.programbench.catalog import load_sample_catalog, select_sample


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare a ProgramBench cleanroom workspace")
    parser.add_argument("instance_id", help="ProgramBench instance id, e.g. owner__repo.abcdef0")
    parser.add_argument(
        "--catalog",
        default="examples/programbench_samples/samples.json",
        help="Path to ProgramBench sample metadata JSON",
    )
    parser.add_argument("--runs", default="runs", help="Root directory for run sessions")
    parser.add_argument(
        "--pull",
        action="store_true",
        help="Pull the task_cleanroom image if it is not available locally",
    )
    parser.add_argument(
        "--image-workspace",
        default="/workspace",
        help="Workspace path inside the task_cleanroom image",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    sample = select_sample(load_sample_catalog(args.catalog), args.instance_id)
    exporter = DockerCleanroomExporter(image_workspace_path=args.image_workspace)
    prepared = ProgramBenchTaskAdapter(exporter=exporter).prepare(
        sample=sample,
        run_root=Path(args.runs),
        pull=args.pull,
    )
    print(f"Prepared {prepared.sample.instance_id}")
    print(f"Session: {prepared.session.root_path}")
    print(f"Workspace: {prepared.workspace.root_path}")
    print(f"Executable: {prepared.workspace.executable_path}")


if __name__ == "__main__":
    main()
