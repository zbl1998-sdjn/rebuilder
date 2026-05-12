# ProgramBench Cleanroom Skeleton Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a compact, extensible skeleton for ProgramBench compliance, evidence recording, and official sample metadata fetching.

**Architecture:** Keep cleanroom policy, behavior evidence, ProgramBench sample discovery, and execution fixes in separate focused modules. Existing orchestration can adopt these modules incrementally without turning `MetaController` into a god class.

**Tech Stack:** Python 3, Pydantic v2, pytest, stdlib `urllib` for DockerHub metadata.

---

### Task 1: Compliance Scanner

**Files:**
- Create: `core/compliance/__init__.py`
- Create: `core/compliance/models.py`
- Create: `core/compliance/scanner.py`
- Test: `tests/test_compliance_scanner.py`

- [x] Write tests that flag wrapper/source-lookup patterns and allow ordinary CLI parsing code.
- [x] Implement rule models and a small pattern-based scanner.
- [x] Run `pytest tests/test_compliance_scanner.py -q`.

### Task 2: Evidence Store

**Files:**
- Create: `core/evidence/__init__.py`
- Create: `core/evidence/models.py`
- Create: `core/evidence/store.py`
- Create: `core/evidence/recorder.py`
- Test: `tests/test_evidence_store.py`

- [x] Write tests for deterministic test-case fingerprints and persisted evidence records.
- [x] Implement focused evidence models and file-backed storage.
- [x] Run `pytest tests/test_evidence_store.py -q`.

### Task 3: ProgramBench Sample Metadata Fetcher

**Files:**
- Create: `core/programbench/__init__.py`
- Create: `core/programbench/samples.py`
- Create: `scripts/fetch_programbench_samples.py`
- Create: `examples/programbench_samples/README.md`
- Test: `tests/test_programbench_samples.py`

- [x] Write tests for DockerHub repo-name normalization and JSON serialization.
- [x] Implement metadata fetcher that reads DockerHub `programbench` repositories without downloading hidden tests.
- [x] Run `python scripts/fetch_programbench_samples.py --limit 5 --output examples/programbench_samples/samples.json`.

### Task 4: Stable Execution Baseline

**Files:**
- Modify: `utils/executable.py`
- Modify: `main.py`
- Test: `tests/test_executable_baseline.py`

- [x] Write tests proving relative task paths are resolved before temp-directory execution and Python scripts run via the current interpreter.
- [x] Update executable command resolution without changing sandbox behavior.
- [x] Run `pytest tests/test_executable_baseline.py -q`.

### Task 5: Full Verification

**Files:**
- Modify only if tests reveal integration issues.

- [x] Run `pytest -q`.
- [x] Confirm no official hidden evaluation data is downloaded or stored.
