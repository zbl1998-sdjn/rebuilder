# ProgramBench Mini-Lab Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the first real experiment layer after smoke testing: deterministic internal holdout evaluation and failure-cluster reports while preserving ProgramBench cleanroom rules.

**Architecture:** Keep probing, reconstruction, and evaluation separated. `CorpusSplitter` decides what evidence can drive synthesis/repair versus what is held out for local validation. A focused report writer summarizes differential failures without feeding official hidden-test feedback into repair.

**Tech Stack:** Python, Pydantic models, existing `MetaController`, `DifferentialTester`, `CorpusSplitter`, and `FailureClusterer`.

**Anti-Overfit Rule:** Only exploration samples may drive specification, implementation, repair, and detailed failure reports. Internal holdout results are aggregate-only by default. Official hidden evaluation remains outside ReBuilder and must never feed repair or architecture tuning for the same run.

---

### Task 1: Wire Internal Holdout Into Controller

**Files:**
- Modify: `core/meta_controller.py`
- Modify: `main.py`
- Modify: `core/data_models.py`
- Test: `tests/test_meta_controller_config.py`
- Test: `tests/test_main_controller_config.py`

- [ ] Add `internal_holdout_ratio` and `holdout_seed` controller settings.
- [ ] Split probed corpus into exploration and holdout before spec synthesis.
- [ ] Use only exploration samples for spec synthesis and repair.
- [ ] Run final holdout differential evaluation after the repair loop when holdout samples exist.
- [ ] Store `holdout_resolved_rate`, `holdout_cases`, and `exploration_cases` on `TaskResult`.
- [ ] Do not expose detailed holdout failures in repair prompts or default failure reports.

### Task 2: Add Failure-Cluster Report Writer

**Files:**
- Create: `core/evaluation/failure_report.py`
- Modify: `core/evaluation/__init__.py`
- Modify: `core/meta_controller.py`
- Test: `tests/test_failure_report.py`

- [ ] Convert `DiffReport` lists into compact JSON and Markdown reports.
- [ ] Include cluster kind, count, representative test name, expected/actual exit code, and short stdout/stderr snippets.
- [ ] Write reports under the active session `reports/` directory when a `RunSession` exists.
- [ ] Keep the report as diagnostics only; do not feed it into repair unless it came from exploration data.
- [ ] Label reports as `exploration` so they cannot be confused with official or internal holdout test feedback.

### Task 3: Config And Documentation

**Files:**
- Modify: `config/settings.yaml`
- Modify: `config/smoke_glm.yaml`
- Modify: `docs/programbench-cleanroom-runbook.md`
- Test: `pytest -q`

- [ ] Add default holdout settings disabled for smoke and enabled in normal config.
- [ ] Document that internal holdout is local cleanroom evidence and official hidden eval remains outside repair.
- [ ] Run focused tests, then full `pytest -q`.
