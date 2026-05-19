"""Prune historical ReBuilder run artifacts while protecting baseline-referenced runs.

Defaults to dry-run: pass --apply to actually delete. For each task_id discovered
under --runs, the newest N result.json directories are kept; older ones become
deletion candidates. Any directory referenced by a recorded baseline (typically
its submission.path) and all of its ancestors are protected.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@dataclass(frozen=True)
class RunEntry:
    task_id: str
    result_path: Path
    run_dir: Path
    mtime: float
    size_bytes: int


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", default="runs", help="Root directory containing run artifacts")
    parser.add_argument(
        "--baselines",
        default="baselines/programbench",
        help="Directory of recorded *.baseline.json files to protect",
    )
    parser.add_argument(
        "--keep",
        type=int,
        default=3,
        help="Number of newest result.json directories to keep per task_id (default 3)",
    )
    parser.add_argument(
        "--task",
        action="append",
        default=None,
        help="Limit pruning to specific task_id(s); pass multiple times to combine",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually delete. Without this flag the script only reports candidates.",
    )
    return parser.parse_args(argv)


def discover_protected_paths(baselines_root: Path) -> set[Path]:
    """Read baseline JSONs and return the set of referenced filesystem paths.

    The returned set holds only the leaf paths a baseline points at (e.g. a
    submission tarball). Use :func:`is_run_protected` to decide whether a
    specific run directory should be preserved.
    """
    protected: set[Path] = set()
    if not baselines_root.exists():
        return protected
    for baseline_path in baselines_root.rglob("*.baseline.json"):
        try:
            data = json.loads(baseline_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        for ref in _baseline_referenced_paths(data):
            resolved = (
                (ROOT / ref).resolve(strict=False)
                if not Path(ref).is_absolute()
                else Path(ref).resolve(strict=False)
            )
            protected.add(resolved)
    return protected


def is_run_protected(run_dir: Path, protected: set[Path]) -> bool:
    """Return True when any baseline-referenced path lives at or under ``run_dir``."""
    resolved = run_dir.resolve(strict=False)
    for ref in protected:
        if ref == resolved:
            return True
        if resolved in ref.parents:
            return True
    return False


def _baseline_referenced_paths(baseline: dict) -> list[str]:
    refs: list[str] = []
    submission = baseline.get("submission") or {}
    submission_path = submission.get("path")
    if isinstance(submission_path, str) and submission_path:
        refs.append(submission_path)
    for key in ("local_result_path", "local", "official_eval_path"):
        value = baseline.get(key)
        if isinstance(value, str) and value:
            refs.append(value)
        elif isinstance(value, dict):
            for nested_key in ("result_path", "path"):
                nested = value.get(nested_key)
                if isinstance(nested, str) and nested:
                    refs.append(nested)
    return refs


def discover_runs(runs_root: Path) -> list[RunEntry]:
    entries: list[RunEntry] = []
    if not runs_root.exists():
        return entries
    runs_root_resolved = runs_root.resolve(strict=False)
    for result_path in runs_root.rglob("result.json"):
        try:
            data = json.loads(result_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        task_id = data.get("task_id")
        if not isinstance(task_id, str) or not task_id:
            task_id = result_path.parent.name
        run_dir = _widen_run_dir(result_path.parent, task_id, runs_root_resolved)
        try:
            mtime = result_path.stat().st_mtime
        except OSError:
            continue
        entries.append(
            RunEntry(
                task_id=task_id,
                result_path=result_path,
                run_dir=run_dir,
                mtime=mtime,
                size_bytes=_directory_size(run_dir),
            )
        )
    return entries


def _widen_run_dir(start: Path, task_id: str, runs_root: Path) -> Path:
    """Expand ``start`` to the outermost ancestor under ``runs_root`` whose name == task_id.

    Many run layouts repeat the task id at multiple depths
    (e.g. ``runs/<batch>/<task_id>/generated/<task_id>/<task_id>``). Deleting the
    outermost task-id-named subdirectory captures evidence/logs/generated for that
    task within that batch without touching other tasks in the same batch.
    """
    start_resolved = start.resolve(strict=False)
    outermost = start_resolved
    for candidate in start_resolved.parents:
        if candidate == runs_root:
            break
        if candidate.name == task_id:
            outermost = candidate
    if outermost.name != task_id:
        return start_resolved
    return outermost


def _directory_size(path: Path) -> int:
    total = 0
    for child in path.rglob("*"):
        if child.is_file():
            try:
                total += child.stat().st_size
            except OSError:
                continue
    return total


def select_deletion_candidates(
    entries: list[RunEntry],
    *,
    keep: int,
    protected: set[Path],
    task_filter: set[str] | None,
) -> list[RunEntry]:
    grouped: dict[str, list[RunEntry]] = {}
    for entry in entries:
        if task_filter and entry.task_id not in task_filter:
            continue
        grouped.setdefault(entry.task_id, []).append(entry)

    candidates: list[RunEntry] = []
    for task_id, group in grouped.items():
        group.sort(key=lambda item: item.mtime, reverse=True)
        for entry in group[keep:]:
            if is_run_protected(entry.run_dir, protected):
                continue
            candidates.append(entry)
    return candidates


def format_size(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    runs_root = Path(args.runs)
    baselines_root = Path(args.baselines)
    task_filter = set(args.task) if args.task else None

    protected = discover_protected_paths(baselines_root)
    entries = discover_runs(runs_root)
    candidates = select_deletion_candidates(
        entries,
        keep=args.keep,
        protected=protected,
        task_filter=task_filter,
    )

    if not candidates:
        print("No deletion candidates after applying keep + baseline protection.")
        return 0

    total_size = sum(c.size_bytes for c in candidates)
    label = "WOULD DELETE" if not args.apply else "DELETING"
    print(f"{label} {len(candidates)} run directories ({format_size(total_size)}):")
    for entry in sorted(candidates, key=lambda c: (c.task_id, c.mtime)):
        print(
            f"  [{entry.task_id}] {entry.run_dir}  "
            f"({format_size(entry.size_bytes)}, mtime={int(entry.mtime)})"
        )

    if args.apply:
        for entry in candidates:
            try:
                shutil.rmtree(entry.run_dir)
            except OSError as exc:
                print(f"  ! failed to remove {entry.run_dir}: {exc}", file=sys.stderr)
        print(f"Freed approximately {format_size(total_size)}.")
    else:
        print("\nDry run only. Re-run with --apply to delete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
