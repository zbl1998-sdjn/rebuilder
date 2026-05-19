# ProgramBench Optimization Iteration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve ReBuilder's cleanroom ProgramBench iteration quality by strengthening local generalization signals before any official hidden evaluation.

**Architecture:** Keep official evaluation gated behind aggregate-only local evidence. First improve corpus splitting so holdout covers distinct behavior dimensions instead of depending mostly on stable hash order, then use the improved signal to guide repair selection and weak-task reruns.

**Tech Stack:** Python 3.12, Pydantic models, pytest, existing ProgramBench cleanroom scripts.

---

### Task 1: Dimension-Aware Holdout Split

**Files:**
- Modify: `core/probing/corpus.py`
- Modify: `tests/test_corpus_split.py`

- [x] **Step 1: Write the failing test**

Add a test that builds samples across help, stdin, file input, error, and domain-profile tags, then asserts the holdout contains multiple behavior dimensions when enough cases are available.

- [x] **Step 2: Run the focused test to verify RED**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_corpus_split.py::test_corpus_split_prefers_behavior_dimension_coverage -q`

Expected: FAIL before implementation because the current splitter selects by group hash only.

- [x] **Step 3: Implement minimal dimension-aware ordering**

In `CorpusSplitter`, derive stable dimension keys from `BehaviorSample` tags, `TestCase.args`, `stdin`, `input_files`, and `TestResult` output/exit shape. Select groups by round-robin dimensions while preserving stateful atomic groups and deterministic seed behavior.

- [x] **Step 4: Run focused corpus tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_corpus_split.py -q`

Expected: all corpus split tests pass.

### Task 2: Verify Project Baseline

**Files:**
- No source edits.

- [x] **Step 1: Run full tests**

Run: `.\.venv\Scripts\python.exe -m pytest -q`

Expected: all tests pass.

- [x] **Step 2: Re-run candidate readiness**

Run: `python scripts\rank_programbench_candidates.py --limit 20 --official-eligible-only --latest-per-task`

Expected: no official eval is triggered; output is only aggregate candidate readiness.

### Task 3: Next Iteration Backlog

**Files:**
- Candidate future modifications: `core/repair_loop.py`, `core/repair/clustering.py`, `scripts/summarize_holdout_trends.py`

- [x] **Step 1: Add repair decision telemetry**

Record aggregate-safe repair candidate selection metadata: cluster id, pre/post exploration rate, whether holdout was evaluated, and reject reason. Do not persist detailed holdout failures.

- [x] **Step 2: Add per-domain smoke contract checks**

Create compact local-only contract suites for high-signal domains such as JSON transform, HTML selector, CSV/table, network ping, archive/compression, and binary/hexdump.

- [x] **Step 3: Propagate smoke contract axes into probe tags**

Keep local `smoke_contract:<domain>.<axis>` and `adaptive_axis:<domain>.<axis>` markers on deterministic probe samples so exact cleanroom contracts and repair prompts can identify which local smoke axis a sample covers without exposing holdout or official hidden failures.

- [x] **Step 4: Record aggregate-safe probe axis coverage**

Summarize smoke/adaptive axis names, domain names, and counts in `TaskResult.implementation_metadata` so future candidate ranking and audits can reason about local probe coverage without storing stdout, stderr, holdout failures, or official hidden-test details.

- [x] **Step 5: Add optional smoke-axis official gate**

Expose `probe_axis_coverage` in candidate ranking and official-gate audit output. Keep the default gate unchanged, but support `--min-smoke-contract-axes` so official eligibility can require aggregate-safe local smoke coverage when desired.

- [x] **Step 6: Carry the smoke-axis gate through packaging paths**

Extend the optional `--min-smoke-contract-axes` gate through `package_submission.py`, `run_official_closed_loop.py`, `run_official_strategy_ablation.py`, and `run_weak_task_cleanroom_rerun.py`. Keep default behavior unchanged, but make explicit smoke-axis coverage requirements block packaging and official-eval paths using aggregate metadata only.

- [x] **Step 7: Stabilize repair cluster sample order**

Sort reports inside each `FailureCluster` by stable test-case fields before repair target selection. This keeps LLM repair prompts and repair decision telemetry deterministic when the same failures arrive in a different input order.

- [x] **Step 8: Add smoke-axis gate to weak-task recommendations**

Let `summarize_holdout_trends.py --include-rerun-command` render guarded weak-task wrapper commands with an optional `--rerun-min-smoke-contract-axes` value. This keeps aggregate-only recommendations aligned with the stricter packaging and official-eval gates without executing any external work.

- [x] **Step 9: Make repair exclusion keys argument-aware**

Include stable test-case args and descriptions in `FailureClusterer.target_key()` so a regressive repair does not accidentally exclude a later failure target that reuses the same test-case name with different behavior. Hash the structured key before recording aggregate-safe repair decision telemetry.

- [x] **Step 10: Expose a minimum holdout-improvement delta gate**

Thread the existing `audit_holdout_improvement.py --min-delta` check through `run_official_closed_loop.py`, `run_official_strategy_ablation.py`, `run_weak_task_cleanroom_rerun.py`, and guarded weak-task recommendation commands. Defaults remain unchanged, but local reruns can now require a positive margin over the previous reliable holdout best before packaging or official-eval paths continue.

- [x] **Step 11: Distinguish below-threshold holdout gains**

Return `delta_below_min` from `audit_holdout_improvement.py` when the current result beats the previous reliable best but does not exceed the configured `--min-delta`. This keeps closed-loop skip logs more actionable without changing pass/fail behavior.

- [x] **Step 12: Add holdout-improvement checks to official audit**

Let `audit_official_eval_gate.py` optionally require aggregate local holdout improvement over historical reliable runs before reporting a candidate as official-eval eligible. This gives the final manual official-eval audit one place to enforce holdout rate, holdout case count, smoke-axis coverage, existing official/baseline records, and improvement margin.

- [x] **Step 13: Add holdout-improvement checks to manual packaging**

Let `package_submission.py` optionally require aggregate local holdout improvement over historical reliable runs before creating a submission archive. This closes the manual packaging path with the same aggregate-only improvement gate used by closed-loop and official audit flows.

- [x] **Step 14: Add holdout-improvement checks to candidate ranking**

Let `rank_programbench_candidates.py --official-eligible-only` optionally require aggregate local holdout improvement over historical reliable runs before listing a result as official-eval eligible. This keeps the candidate table aligned with the stricter manual audit and packaging gates.

- [x] **Step 15: Include previous-best aggregate evidence in official audit**

When `audit_official_eval_gate.py --require-holdout-improvement` runs, include the previous reliable best holdout rate, case count, result path, and delta in the JSON output. This improves manual review evidence without exposing holdout failures or official hidden-test details.

- [x] **Step 16: Stabilize holdout trend tie ordering**

Sort `summarize_holdout_trends.py` rows by aggregate rates and case counts, then by task id, so equally scored tasks do not inherit filesystem traversal order. This keeps weak-task queue review deterministic.

- [x] **Step 17: Stabilize candidate ranking tie ordering**

Sort `rank_programbench_candidates.py` rows by the existing aggregate ranking metrics and then by task id, so equally scored official-eval candidates do not inherit filesystem traversal order.

- [x] **Step 18: Stabilize holdout trend best/latest tie ordering**

When a task has multiple `result.json` files with identical aggregate holdout metrics and modified times, break best/latest ties by result path. This keeps aggregate trend evidence stable across filesystem traversal order.

- [x] **Step 19: Stabilize holdout improvement previous-best tie ordering**

When multiple historical reliable runs have identical aggregate holdout metrics and modified times, break previous-best ties by result path in `audit_holdout_improvement.py`. This keeps official audit improvement evidence stable across filesystem traversal order.

- [x] **Step 20: Stabilize candidate same-task result tie ordering**

When a task has multiple candidate `result.json` files with identical aggregate ranking metrics and modified times, break same-task selection ties by result path in `rank_programbench_candidates.py`. This keeps official candidate evidence stable across filesystem traversal order.

- [x] **Step 21: Harden candidate metadata parsing for gate tools**

Treat malformed `implementation_metadata` or `probe_axis_coverage` fields in `result.json` as empty metadata in `rank_programbench_candidates.py`. This keeps candidate ranking and official gate audits from crashing on malformed aggregate metadata while still requiring explicit smoke-axis counts when that gate is enabled.

- [x] **Step 22: Harden candidate aggregate numeric parsing for gate tools**

Treat malformed aggregate numeric fields such as `holdout_cases`, `probes_conducted`, and `iterations_used` as zero in `rank_programbench_candidates.py`. This keeps official candidate ranking and gate audits available even when a malformed local `result.json` contains unusable numeric metadata, while still failing the relevant aggregate gates.

- [x] **Step 23: Harden holdout trend numeric parsing**

Treat malformed `holdout_cases` values as zero in `summarize_holdout_trends.py`, causing those local history rows to be filtered instead of crashing trend summaries or downstream holdout-improvement audits. This keeps weak-task recommendations available when a malformed aggregate `result.json` exists in the run history.

- [x] **Step 24: Ignore non-object aggregate result payloads**

Ignore `result.json` files whose JSON payload is not an object in `rank_programbench_candidates.py` and `summarize_holdout_trends.py`. This keeps official candidate ranking, weak-task recommendations, and holdout-improvement audits available when malformed but syntactically valid JSON files exist under `runs`.

- [x] **Step 25: Harden submission holdout gate malformed payload handling**

Reject malformed aggregate numeric values and non-object `result.json` payloads with `HoldoutGateError` in `core/submission/gate.py`. This keeps manual packaging and closed-loop packaging paths on the explicit aggregate gate failure path instead of leaking low-level parsing exceptions.

- [x] **Step 26: Return structured official audit failures for invalid results**

Return an aggregate-only `invalid_result` audit object from `audit_official_eval_gate.py` when a local `result.json` cannot be read as a candidate row. This keeps manual official-readiness checks JSON-shaped and non-leaky even for malformed local artifacts.

- [x] **Step 27: Harden recorded-baseline discovery against malformed payloads**

Ignore `.baseline.json` files whose JSON payload is not an object in `rank_programbench_candidates.py`. This keeps official candidate ranking and manual official-readiness checks available when a malformed recorded-baseline artifact exists.

- [x] **Step 28: Harden submission holdout gate invalid JSON handling**

Reject syntactically invalid `result.json` files with `HoldoutGateError` in `core/submission/gate.py`. This keeps manual packaging and closed-loop packaging paths on explicit aggregate gate failures instead of leaking JSON parser tracebacks.

- [x] **Step 29: Harden closed-loop result payload parsing**

Treat unreadable, syntactically invalid, non-object, and malformed aggregate numeric `result.json` payloads as missing local holdout evidence in `run_official_closed_loop.py`. This keeps the official closed-loop path on the existing local holdout gate and prevents malformed local artifacts from crashing before packaging or official eval gating.

- [x] **Step 30: Harden mini-lab aggregate result collection**

Treat malformed aggregate numeric fields, malformed metadata, syntactically invalid JSON, and non-object `result.json` payloads as missing local evidence in `MiniLabResultCollector`. Invalid payloads are preserved as aggregate-only `invalid_result` rows so mini-lab batch summaries continue without exposing holdout or official hidden-test details.

- [x] **Step 31: Harden baseline local-result recording**

Treat malformed aggregate numeric fields and unreadable or invalid local `result.json` payloads as missing evidence in `BaselineRecorder`. Baseline records now preserve official aggregate summaries while sanitizing the local aggregate section to zero or `invalid_result` instead of storing malformed values or crashing.

- [x] **Step 32: Harden official eval aggregate parsing**

Treat malformed official eval result items as aggregate failures instead of crashing, filter malformed items out of branch-specific official summaries, and convert unreadable or invalid official eval JSON into a zero-test `invalid_eval_payload` summary. This keeps baseline and strategy records aggregate-only and non-leaky even when official eval artifacts are malformed.

- [x] **Step 33: Harden run pruning aggregate readers**

Ignore non-object baseline and local `result.json` payloads in `scripts/prune_runs.py`. This keeps dry-run/apply pruning reports available when malformed aggregate artifacts exist, while preserving baseline-referenced path protection from valid records.

- [x] **Step 34: Harden aggregate experiment registry loading**

Skip syntactically invalid JSONL rows and non-object rows in `ExperimentRegistry.load()` while continuing to reject object rows that contain hidden per-test details. This keeps aggregate-only strategy selection available when a registry file has malformed rows without weakening the cleanroom boundary.

- [x] **Step 35: Normalize official eval warning aggregates**

Treat malformed official eval `warnings` payloads as empty and keep only string warning entries in `ProgramBenchEvalParser`. This prevents malformed warning fields from crashing aggregate summaries or carrying non-aggregate structures into baseline and strategy records.

- [x] **Step 36: Harden ProgramBench sample catalog loading**

Require the ProgramBench sample catalog payload to be a JSON list and skip malformed individual sample entries while preserving valid entries. This keeps cleanroom batch selection and official closed-loop entrypoints from failing on one bad catalog row, while still failing clearly when the catalog file shape is wrong.

- [x] **Step 37: Harden ProgramBench sample metadata fetch parsing**

Validate that the DockerHub metadata response contains a JSON list of repository results and skip malformed individual repository entries during public sample metadata fetches. This prevents one bad public metadata row from blocking catalog generation while still failing clearly when the API response shape is not usable.

- [x] **Step 38: Stabilize repair prompt file ordering**

Sort existing codebase file names in repair diagnosis prompts and sort target file context before applying a repair. This keeps equivalent repair decisions from producing different LLM prompt file order when codebase dictionaries or strategy target-file lists arrive in different orders.

- [x] **Step 39: Keep holdout atomic groups closer to budget**

When multiple atomic groups provide equivalent new holdout dimensions, prefer smaller groups and avoid selecting an oversized group once smaller groups can fill the remaining holdout budget. This preserves stateful-plan atomicity while reducing cases where a large group starves exploration and weakens local repair signal.

- [x] **Step 40: Harden submission archive hygiene**

Exclude local repository metadata, cache directories, virtual environments, `node_modules`, and stale `submission.tar.gz` artifacts from ProgramBench submission archives. This reduces the risk of official-eval submissions carrying generated-run debris or local tooling state.

- [x] **Step 41: Make submission archives reproducible**

Normalize gzip header metadata and tar member mtime, ownership, names, and modes when creating ProgramBench submission archives. This makes identical generated sources produce byte-identical `submission.tar.gz` files, improving manual review and official-submission artifact traceability.

- [x] **Step 42: Reject empty ProgramBench sample fetch output**

Fail `fetch_programbench_samples.py` before writing an output file when a positive `--limit` produces zero valid public metadata records. This prevents cleanroom batch and official closed-loop entrypoints from treating an empty generated catalog as a successful setup artifact.

- [x] **Step 43: Skip malformed ProgramBench repository names**

Reject non-string or empty DockerHub repository names as malformed public metadata rows during ProgramBench sample fetches. This keeps catalog generation available when DockerHub returns a bad row before later valid repositories, without inspecting hidden tests or task images.

- [x] **Step 44: Reject duplicate ProgramBench sample ids**

Raise a clear catalog loading error when multiple valid ProgramBench sample rows share the same `instance_id`. This prevents cleanroom batch and official closed-loop sample selection from silently depending on catalog row order.

- [x] **Step 45: Normalize invalid ProgramBench catalog JSON errors**

Convert syntactically invalid ProgramBench sample catalog JSON into a clear catalog-level `ValueError`. This keeps cleanroom batch and official closed-loop entrypoints failing at the catalog boundary instead of exposing raw JSON parser text.

- [x] **Step 46: Reject non-positive sample fetch limits**

Validate `fetch_programbench_samples.py --limit` as a positive integer before fetching public metadata or writing output. This prevents setup commands from intentionally or accidentally producing an empty catalog through `--limit 0`.

- [x] **Step 47: Distinguish repair targets by input payload**

Include stable stdin, input-file, and environment summaries in the structured repair target key before hashing. This prevents regressive repair exclusion from skipping a same-name/same-args local failure that uses a different input payload.

- [x] **Step 48: Remove raw input values from repair target keys**

Use the existing `test_case_fingerprint()` as the repair target key's input payload identity. This keeps exclusion keys sensitive to stdin, input files, and environment differences without carrying raw stdin or environment variable values before metadata hashing.

- [x] **Step 49: Reject negative weak-rerun gate thresholds**

Validate weak-task local rerun holdout, smoke-axis, and improvement gate thresholds as non-negative values. This prevents an authorized rerun command from accidentally weakening local-only gates before `run_official_closed_loop.py` is invoked.

- [x] **Step 50: Reject negative weak-rerun recommendation gates**

Validate `summarize_holdout_trends.py` holdout and rerun gate thresholds as non-negative before rendering aggregate-only weak-task rerun recommendations. This prevents recommendation output from suggesting a weakened local rerun command.

- [x] **Step 51: Reject negative holdout-improvement audit thresholds**

Validate `audit_holdout_improvement.py` `min_delta` and `min_holdout_cases` as non-negative at both the CLI boundary and direct function boundary. This prevents downstream official gate, ranking, packaging, and closed-loop callers from weakening the aggregate improvement check.

- [x] **Step 52: Reject negative official-audit gate thresholds**

Validate `audit_official_eval_gate.py` holdout, smoke-axis, and holdout-improvement thresholds as non-negative at both the CLI boundary and direct function boundary. This prevents the manual official-readiness audit from approving candidates under weakened aggregate local gates.

- [x] **Step 53: Reject negative candidate-ranking gate thresholds**

Validate `rank_programbench_candidates.py` holdout, smoke-axis, and holdout-improvement thresholds as non-negative at the CLI boundary, candidate collection boundary, and official gate reason boundary. This prevents ranking or `--official-eligible-only` output from being computed with weakened aggregate gates.

- [x] **Step 54: Reject negative submission-packaging gate thresholds**

Validate `package_submission.py` holdout, smoke-axis, and holdout-improvement thresholds as non-negative at the CLI boundary, and reject negative `SubmissionHoldoutGate` thresholds before packaging. This prevents manual submission archives from being created under weakened local gates.

- [x] **Step 55: Reject negative official closed-loop gate thresholds**

Validate `run_official_closed_loop.py` holdout, smoke-axis, and holdout-improvement thresholds as non-negative during argument parsing. This prevents automated closed-loop runs from preparing tasks, generating code, packaging submissions, or reaching official eval with weakened aggregate gates.

- [x] **Step 56: Reject negative strategy-ablation gate thresholds**

Validate `run_official_strategy_ablation.py` holdout, smoke-axis, and holdout-improvement thresholds as non-negative during argument parsing. This prevents batch strategy-ablation runs from constructing closed-loop commands with weakened aggregate gates.

- [x] **Step 57: Reject non-finite floating gate thresholds**

Upgrade holdout-rate and holdout-improvement-delta threshold parsing across official audit, ranking, packaging, closed-loop, strategy ablation, weak-rerun, trend, and holdout-improvement audit entrypoints from merely non-negative to finite-and-non-negative. This blocks `nan`/`inf` values from bypassing aggregate gate comparisons.

- [x] **Step 58: Treat non-finite aggregate rates as malformed**

Normalize `nan`/`inf` local aggregate rates from `result.json` before they reach candidate ranking, holdout trend/improvement audits, submission packaging gates, official closed-loop gates, baseline recording, or mini-lab summaries. Non-finite plain resolved rates become `0.0`; non-finite holdout rates become missing holdout evidence.

- [x] **Step 59: Validate weak-rerun helper gates at direct-call boundaries**

Push finite/non-negative threshold validation below the `summarize_holdout_trends.py` CLI boundary into `recommend_weak_reruns()` and `build_guarded_rerun_command()`. Direct callers now reject non-finite or negative holdout-rate gates, negative or fractional smoke-axis gates, and non-finite or negative holdout-improvement deltas instead of silently rendering weakened guarded rerun commands.

- [x] **Step 60: Reject packaging gate threshold down-clamping**

Tighten `SubmissionHoldoutGate` and `package_submission.py` so manual packaging cannot silently weaken caller-specified thresholds. Holdout-rate gates above `1.0` are rejected instead of clamped to `1.0`, and direct integer thresholds reject fractional holdout-case or smoke-axis values instead of truncating them.

- [x] **Step 61: Reject non-finite and fractional official integer gates**

Extend direct-call threshold validation in `audit_holdout_improvement.py`, `audit_official_eval_gate.py`, and `rank_programbench_candidates.py` so aggregate gate integer thresholds must be finite whole numbers. This prevents `nan` or fractional holdout-case/smoke-axis thresholds from bypassing comparisons when callers invoke helpers directly instead of through `argparse`.

- [x] **Step 62: Bound aggregate strategy feedback rates**

Validate aggregate experiment registry feedback so `official.score` and `official.pass_rate` must be finite rates between `0` and `1`. This keeps strategy-bandit selection from averaging or comparing malformed aggregate scores such as `nan`, `inf`, negative values, or greater-than-one rates.

- [x] **Step 63: Validate strategy-bandit holdout-case threshold**

Reject negative, non-finite, or fractional `StrategyBandit(min_holdout_cases=...)` values before filtering aggregate registry history. This keeps direct callers from accidentally weakening the minimum local holdout evidence required for learned strategy selection.

- [x] **Step 64: Validate aggregate official count fields**

Reject negative official aggregate `passed_tests`, `total_tests`, and `warning_count` values, and reject `passed_tests > total_tests` in the aggregate experiment registry. This keeps strategy history from storing malformed official aggregate count evidence while preserving the no hidden per-test details boundary.

- [x] **Step 65: Validate aggregate strategy numeric params**

Reject negative numeric strategy parameters for probe budgets, sample floors, repair attempt counts, token/time limits, and temperature, and require `min_coverage`/`top_p` to be finite rates between `0` and `1`. This keeps learned strategy registry rows from recording weakened or malformed aggregate-only run controls.

- [x] **Step 66: Validate aggregate registry holdout case counts**

Reject negative local aggregate `holdout_cases` values when constructing `ExperimentRun` rows and when loading registry JSONL. This keeps learned strategy history from storing malformed local holdout evidence counts.

- [x] **Step 67: Normalize repair strategy target files**

Normalize repair-strategy `target_files` from LLM JSON before constructing `RepairStrategy`: accept a single target-file string, drop empty or non-string entries, and deduplicate/sort the final target list. This prevents malformed repair strategy output from crashing parsing or introducing unstable target ordering.

- [x] **Step 68: Normalize repair strategy text fields**

Normalize malformed repair-strategy text fields from LLM JSON before constructing `RepairStrategy`: default empty or non-string `strategy_type` values to `fix_algorithm`, and serialize non-string `description` values to stable JSON text. This prevents repair parsing from crashing on mildly malformed strategy output.

- [x] **Step 69: Restrict targeted repair merges to target files**

When a repair strategy specifies `target_files`, only merge LLM-returned updates for those files back into the codebase. This prevents targeted repair from adding or changing unrelated files while preserving the existing full-merge fallback for strategies that do not declare target files.

- [x] **Step 70: Preserve build metadata during targeted repair**

When a repair strategy specifies `target_files`, preserve the existing `build_script` and `executable_path` instead of adopting LLM-returned build metadata. This prevents a targeted source-file repair from silently redirecting execution while preserving the existing broad regeneration behavior for strategies that do not declare target files.

- [x] **Step 71: Normalize direct target files during repair application**

Normalize `RepairStrategy.target_files` inside `apply_repair` before selecting prompt context, merging returned files, or deciding whether build metadata should be preserved. This gives direct callers the same trim, dedupe, and stable-order behavior as strategies parsed from LLM JSON.

- [x] **Step 72: Normalize repair target file paths consistently**

Reuse the implementation output path normalizer for repair target files before prompt context selection and returned-file merging. This lets `src\\main.py` and `./src/main.py` match the same returned file as `src/main.py`, while dropping unsafe absolute or parent-traversal paths.

- [x] **Step 73: Treat malformed candidate aggregate counts as zero**

Tighten candidate-ranking aggregate integer parsing so negative, non-finite, fractional, boolean, or otherwise malformed count fields are treated as zero. This keeps official-eligibility ranking and gate output from carrying malformed holdout, probe, iteration, or probe-axis counts forward.

- [x] **Step 74: Filter malformed weak-trend holdout counts**

Tighten weak-task trend aggregate integer parsing so negative, non-finite, fractional, boolean, or otherwise malformed `holdout_cases` values are treated as zero and filtered from trend/recommendation rows. This prevents malformed local history from entering weak-task rerun recommendations.

- [x] **Step 75: Bound candidate aggregate rates**

Tighten candidate-ranking aggregate rate parsing so local `resolved_rate` and `holdout_resolved_rate` must be finite rates between `0` and `1`. Out-of-range plain rates become zero and out-of-range holdout rates become missing holdout evidence, preventing malformed local results from passing official-eligibility gates.

- [x] **Step 76: Bound weak-trend aggregate rates**

Tighten weak-task trend aggregate rate parsing so local `resolved_rate` and `holdout_resolved_rate` must be finite rates between `0` and `1`. Out-of-range plain rates become zero and out-of-range holdout rates become missing holdout evidence, preventing malformed local history from entering weak-task recommendations or holdout-improvement audits.

- [x] **Step 77: Harden closed-loop aggregate parsing**

Tighten `run_official_closed_loop.py` aggregate helpers so local holdout rates must be finite rates between `0` and `1`, and holdout/smoke-axis counts must be finite non-negative integers. Malformed local results now fail through zeroed or missing aggregate evidence before packaging or official eval.

- [x] **Step 78: Harden submission packaging aggregate parsing**

Tighten `SubmissionHoldoutGate` aggregate parsing so local holdout rates must be finite rates between `0` and `1`, and holdout/smoke-axis counts must be finite non-negative integers. Malformed local results now fail before submission archive creation.

- [x] **Step 79: Harden baseline and mini-lab aggregate parsing**

Tighten `BaselineRecorder` and `MiniLabResultCollector` aggregate helpers so local rates must be finite rates between `0` and `1`, and local count fields must be finite non-negative integers. Malformed experiment summaries now preserve aggregate-only rows while zeroing or dropping invalid local evidence.

- [x] **Step 80: Remove raw args from repair target keys**

Keep repair target selection and report ordering deterministic, but change `FailureClusterer.target_key()` to use test-case fingerprints instead of raw command args. Regressive repair exclusion still distinguishes same-name/different-args local failures without carrying raw args in structured target keys before metadata hashing.

- [x] **Step 81: Hash descriptions in repair target keys**

Keep same-description and different-description repair targets distinguishable, but store a stable description fingerprint inside `FailureClusterer.target_key()` instead of raw description text. This prevents local probe descriptions from being carried in structured repair exclusion keys before aggregate-safe metadata hashing.

- [x] **Step 82: Validate official and weak wrapper execution controls**

Validate closed-loop, strategy-ablation, and weak-rerun execution controls before command construction: probe/repair/retry counts must be non-negative, and worker/CPU counts must be positive. This prevents official or local-only wrapper commands from carrying invalid execution controls into cleanroom runs.

- [x] **Step 83: Bound official and weak rate/timeout controls**

Validate closed-loop, strategy-ablation, and weak-rerun rate controls before command construction: holdout-rate thresholds must be finite rates between `0` and `1`, and wrapper command timeouts must be positive finite values. This prevents official or local-only wrapper commands from carrying impossible local gates or invalid timeout controls.

- [x] **Step 84: Bound audit, ranking, and weak-trend holdout gates**

Validate official audit, candidate ranking, and weak-task trend holdout-rate gates as finite rates between `0` and `1` at both CLI and direct-helper boundaries. This prevents impossible `--min-holdout-rate` values from producing misleading empty official-candidate tables or unreachable weak-task rerun targets.

- [x] **Step 85: Reject misleading non-positive report limits**

Validate candidate-ranking and weak-task trend `--limit` values as positive integers before rendering markdown. This prevents `--limit 0` or negative limits from creating empty official-candidate or weak-rerun tables that look like true absence of evidence.
