# ProgramBench Mini-Lab Runner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a batch runner that executes several prepared or catalog-selected ProgramBench cleanroom tasks and writes aggregate experiment reports.

**Architecture:** Keep batch orchestration separate from reconstruction. The runner prepares missing cleanroom workspaces only from `task_cleanroom` metadata, invokes the existing `main.py` pipeline per task, then reads each task's `result.json` to create JSON and Markdown summaries. It reports holdout only as aggregate fields already emitted by `TaskResult`.

**Tech Stack:** Python standard library, existing ProgramBench catalog/adapter/session modules, existing ReBuilder CLI, pytest.

**Anti-Overfit Rule:** The runner must never use `task` images, official eval JSON, hidden failures, or holdout detailed failures as repair input. It only invokes cleanroom reconstruction and summarizes resulting aggregate metrics.

---

### Task 1: Result Aggregation

**Files:**
- Create: `core/experiments/mini_lab.py`
- Test: `tests/test_mini_lab_runner.py`

- [ ] Read per-task `generated/<instance_id>/result.json`.
- [ ] Produce rows with task id, status, resolved rate, holdout rate, probe count, repair count, generated file count, and result path.
- [ ] Produce aggregate averages without exposing holdout failure details.
- [ ] Write `mini_lab_summary.json` and `mini_lab_summary.md`.

### Task 2: Cleanroom Command Builder

**Files:**
- Modify: `core/experiments/mini_lab.py`
- Test: `tests/test_mini_lab_runner.py`

- [ ] Build `python main.py --task <workspace> --config <config> --reference-docker-image <task_cleanroom>`.
- [ ] Reject any reference image not ending in `:task_cleanroom`.
- [ ] Support optional `--max-repairs`.

### Task 3: CLI Script

**Files:**
- Create: `scripts/run_programbench_mini_lab.py`
- Modify: `docs/programbench-cleanroom-runbook.md`
- Test: `pytest -q`

- [ ] Accept `--instances`, `--limit`, `--catalog`, `--runs`, `--config`, `--max-repairs`, `--prepare-missing`, and `--pull`.
- [ ] Prepare missing cleanroom sessions only when explicitly requested.
- [ ] Run each selected cleanroom task through the existing ReBuilder CLI.
- [ ] Write aggregate reports under `<runs>/mini_lab/`.
