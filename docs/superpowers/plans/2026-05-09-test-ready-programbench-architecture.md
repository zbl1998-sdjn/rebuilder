# Test-Ready ProgramBench Architecture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the ReBuilder architecture to the point where official ProgramBench cleanroom tasks can be prepared, explored, packaged, and measured without touching hidden tests.

**Architecture:** Add missing components as small packages: Docker execution, behavioral coverage, hypothesis graph, probe planner, corpus split, failure clustering, submission packaging, evaluation JSON parsing, and experiment reporting. Each component is independently testable and feeds the existing session/evidence/controller flow without expanding `MetaController` into a god class.

**Tech Stack:** Python 3, Pydantic v2, pytest, stdlib `subprocess`, `tarfile`, `json`, and existing ReBuilder models.

---

### Task 1: Docker Execution Backend

**Files:**
- Create: `core/execution/docker.py`
- Modify: `core/execution/__init__.py`
- Test: `tests/test_docker_execution_backend.py`

- [ ] Write tests for Docker CLI command construction and normal-interface execution boundaries.
- [ ] Implement Docker backend with `--network none`, mounted temp working directory, stdin/stdout/stderr capture, timeout, and output file collection.
- [ ] Run `pytest tests/test_docker_execution_backend.py -q`.

### Task 2: Behavioral Coverage Proxy

**Files:**
- Create: `core/coverage/__init__.py`
- Create: `core/coverage/behavioral.py`
- Test: `tests/test_behavioral_coverage.py`

- [ ] Write tests for flags, stdin, file inputs, exit code classes, stderr, and output-file coverage.
- [ ] Implement coverage summary from behavior samples and CLI surface only.
- [ ] Run `pytest tests/test_behavioral_coverage.py -q`.

### Task 3: Hypothesis Graph

**Files:**
- Create: `core/hypotheses/__init__.py`
- Create: `core/hypotheses/graph.py`
- Test: `tests/test_hypothesis_graph.py`

- [ ] Write tests for evidence-backed claims, status transitions, contradictions, and missing probes.
- [ ] Implement focused graph models without LLM dependencies.
- [ ] Run `pytest tests/test_hypothesis_graph.py -q`.

### Task 4: Probe Planner And Corpus Split

**Files:**
- Create: `core/probing/__init__.py`
- Create: `core/probing/planner.py`
- Create: `core/probing/corpus.py`
- Test: `tests/test_probe_planner.py`
- Test: `tests/test_corpus_split.py`

- [ ] Write tests for deterministic exploration/holdout/adversarial split.
- [ ] Write tests for planner output from uncovered flags and missing hypothesis probes.
- [ ] Implement planner and splitter.
- [ ] Run both tests.

### Task 5: Failure Clustering

**Files:**
- Create: `core/repair/__init__.py`
- Create: `core/repair/clustering.py`
- Test: `tests/test_failure_clustering.py`

- [ ] Write tests classifying stdout/stderr/exit-code/file-output mismatch clusters.
- [ ] Implement deterministic clustering from `DiffReport`.
- [ ] Run `pytest tests/test_failure_clustering.py -q`.

### Task 6: Submission Packaging And Evaluation Parsing

**Files:**
- Create: `core/submission/__init__.py`
- Create: `core/submission/packager.py`
- Create: `core/evaluation/__init__.py`
- Create: `core/evaluation/programbench.py`
- Test: `tests/test_submission_packager.py`
- Test: `tests/test_programbench_eval_parser.py`

- [ ] Write tests for `submission.tar.gz` layout and exclusion of session/evidence/reference artifacts.
- [ ] Write tests for official evaluation JSON pass-rate parsing.
- [ ] Implement packager and parser.
- [ ] Run both tests.

### Task 7: Experiment Runner

**Files:**
- Create: `core/experiments/__init__.py`
- Create: `core/experiments/runner.py`
- Test: `tests/test_experiment_runner.py`

- [ ] Write tests for a no-LLM dry-run report from sample metadata/session paths.
- [ ] Implement reporting scaffold for future ablations.
- [ ] Run `pytest tests/test_experiment_runner.py -q`.

### Task 8: Verification

**Files:**
- Modify docs if commands or boundaries change.

- [ ] Run `pytest -q`.
- [ ] Run `python -m compileall -q .`.
- [ ] Run `python scripts/prepare_programbench_task.py --help`.
