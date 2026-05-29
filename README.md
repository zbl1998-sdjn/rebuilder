# ReBuilder Framework

[![CI](https://github.com/zbl1998-sdjn/rebuilder/actions/workflows/ci.yml/badge.svg)](https://github.com/zbl1998-sdjn/rebuilder/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![Tests](https://img.shields.io/badge/tests-776%20passing-brightgreen)
![License](https://img.shields.io/badge/license-Apache%202.0-green)

ReBuilder is a cleanroom program reconstruction agent architecture for
ProgramBench-style tasks. It tries to rebuild a program from bundled
documentation and normal black-box execution of the reference executable,
without source lookup, decompilation, binary wrapping, or hidden-test feedback.

The research goal is narrow and explicit: test whether better agent
architecture can improve reconstruction performance on tasks where simply
scaling model parameters has not been enough.

## Current Status

This repository is an active research prototype.

Verified locally on Windows with Docker Desktop:

- Full unit test suite: `776 passed` in a project-local Python 3.12 `.venv` with `pytest -q`
- GLM-5.1 and Kimi API endpoints smoke tested; `local_openai` loopback provider available for Ollama/LM Studio
- `file_bridge` LLM provider available for no-external-LLM subagent reconstruction workflows
- Full cleanroom loop (probe → spec → implement → diff-test → repair → package) runs end-to-end
- **13 official ProgramBench aggregate baselines** across 13 distinct task families (see table below)
- Highest single-task score: `agourlay__zip-password-finder` score **98** (`667/680` counted; raw eval `778/792`)
- All baselines are `fully_resolved=false`; none are solved tasks
- Runtime smoke gate (args/stdin/input_files/env_vars dimensions) integrated into packaging and candidate ranking
- Behavior-coverage-driven probing, internal holdout gating, and non-regressive repair all active
- 11 task-domain strategy packs with generalization and validation playbooks
- Anti-overfit cleanroom boundary enforced: no hidden-test details, no hardcoded lookup tables for stateful/query behavior

The full cleanroom loop:

```text
task_cleanroom image -> probe reference -> synthesize spec -> design architecture
-> generate replacement -> differential test -> repair -> re-test -> package/report
```

All official baselines are aggregate-only, `fully_resolved=False`, `almost_resolved=False`.

## Benchmark Interpretation

ProgramBench-style cleanroom reconstruction is intentionally much harder than a
normal code-generation benchmark. The agent must rebuild an executable program
from bundled documentation and black-box behavior only, without source lookup,
decompilation, binary wrapping, hidden-test failure details, or official
feedback in the repair loop. Under that constraint, many direct large-model
attempts are expected to score near zero because they must infer CLI semantics,
I/O behavior, edge cases, formatting, state, and file-system effects without
seeing the implementation.

ReBuilder should therefore be judged as an agent architecture experiment, not
as a solved-program generator. The current official baselines show that the
architecture can consistently produce non-zero cleanroom results across
multiple task families, with strong individual signals such as `zip-password-finder`
score `98`, `cmatrix` score `95`, `htmlq` score `91`, `chmln__sd` score `86`,
`nnn` score `79`, `csview` score `87`, `clog-cli` score `75`, `xsv` score `70`,
`zoxide` score `67`, and `gron` score `62`. This is meaningful progress beyond a
naive single-shot prompt, but it is not yet a general solution.

Current system assessment: ReBuilder is an approximately `8/10` research
prototype. Its strengths are compliance-aware cleanroom boundaries,
behavior-coverage-driven probing, internal holdout gating, non-regressive repair
selection, aggregate-only official evaluation, task-domain profiling, and
execution-safety guardrails. Its main weaknesses are the remaining
local-vs-official gap, shallow domain-specific implementation strategies for
HTML/JSON/network-style tools, occasional repair prompt parse failures, and the
need for stronger reusable strategy packs before broad ProgramBench
generalization can be claimed.

## Cleanroom Boundary

ReBuilder treats ProgramBench compliance as a top-level constraint.

Allowed during reconstruction:

- Documentation bundled in the cleanroom workspace
- Normal user-interface execution of the reference executable
- CLI args, stdin, stdout, stderr, exit codes, and file-system side effects
- Artifacts bundled in the cleanroom task workspace

Forbidden during reconstruction:

- Original source code, forks, mirrors, package source, or local dependency caches
- Decompilation, disassembly, tracing, or binary instrumentation
- Wrapping, invoking, copying, or shipping the reference executable
- Official hidden evaluation failures in the repair loop
- Pulling or inspecting ProgramBench `:task` images during inference

See:

- `docs/programbench-compliance.md`
- `docs/programbench-cleanroom-runbook.md`
- `docs/handoff.md`

## Anti-Overfit Policy

The project has an explicit anti-overfit boundary.

ReBuilder may split cleanroom observations into:

- `exploration`: may drive spec synthesis, implementation, repair, and detailed
  failure reports
- `internal holdout`: aggregate-only local generalization estimate
- official hidden eval: final external score summary only

Detailed holdout failures are not written by default and are not fed into repair.
Official hidden evaluation failures must never be used to tune or repair the
same reconstruction run.

Static output assets are restricted to a narrow anti-overfit policy. ReBuilder
may materialize only long, documented, deterministic default `init <shell>`
outputs with exit code `0` and empty stderr. It must not turn `query`, `add`,
`remove`, `import`, file transformations, stateful behavior, shell-init flag
variants, holdout failures, or official hidden failures into lookup tables.
Asset-enabled runs should be compared against asset-disabled ablations before
claiming a general architecture improvement.

## Architecture

The core pipeline is orchestrated by `MetaController`.

```text
ProbeEngine
  -> SpecSynthesizer
  -> ArchitectAgent
  -> ImplementerAgent
  -> DifferentialTester
  -> RepairLoop
```

Supporting systems:

- `core/evidence`: evidence records for observed reference behavior
- `core/codebase`: generated-code integrity checks
- `core/session`: reproducible run-session directory layout
- `core/programbench`: sample metadata, cleanroom workspace export, adapters
- `core/execution`: local and Docker execution backends
- `core/probing`: deterministic corpus splitting, stateful plans, shell-init probe planning, and file I/O probe planning
- `core/coverage`: behavior-only coverage reports that drive coverage-gap probing
- `core/profiling`: task-domain strategy hints for spec, implementation, and repair prompts
- `core/implementation`: implementation-time generated asset guardrails
- `core/repair`: failure clustering
- `core/evaluation`: official eval summaries and exploration failure reports
- `core/submission`: ProgramBench-style submission packaging
- `core/experiments`: dry-run and mini-lab experiment reporting

## Requirements

- Python 3.12 recommended for the local Windows baseline
- Docker Desktop or Docker Engine for official ProgramBench cleanroom images
- Network access for external LLM API calls and optional Docker image pulls
- API key for one external provider, or a local OpenAI-compatible endpoint

Install dependencies:

```powershell
cd C:\Users\Administrator\Desktop\ReBuilder
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Ignore the legacy `.venv-programbench` folder for Windows-local development; it is a Linux-style environment artifact and is not used by the local test baseline.

Create local secrets:

```powershell
copy .env.example .env
```

Then edit `.env`:

```text
GLM_API_KEY=your-key-here
KIMI_API_KEY=your-key-here
LOCAL_OPENAI_API_KEY=
```

`.env` is ignored by git.

## LLM Configuration

Default config is in `config/settings.yaml`.

GLM-5.1 coding-plan endpoint:

```yaml
llm:
  provider: "glm"
  glm:
    api_key: "${GLM_API_KEY}"
    base_url: "https://api.z.ai/api/coding/paas/v4"
    model: "glm-5.1"
    timeout: 300
    max_retries: 5
    retry_delay: 2
    thinking:
      type: "disabled"
```

Loopback OpenAI-compatible endpoint for Ollama, LM Studio, vLLM, or a local
gateway:

```yaml
llm:
  provider: "local_openai"
  local_openai:
    api_key: ""
    base_url: "http://127.0.0.1:11434/v1"
    model: "qwen2.5:7b"
    timeout: 300
```

`local_openai` is restricted to loopback hosts by default so cleanroom prompts
and code context are not sent to external services. Set
`LOCAL_OPENAI_API_KEY` only if your local gateway requires bearer auth.

The default architect configuration constrains generation to Python and a
single module. This keeps ProgramBench mini-lab runs on the most reliable
implementation path and avoids native-language or multi-module drift unless a
specific experiment opts into it.

Low-cost smoke config:

```text
config/smoke_glm.yaml
```

The smoke config uses fewer probe and repair iterations, but still keeps an
aggregate-only internal holdout split before packaging decisions.

Static output assets are enabled by default and recorded in every result:

```yaml
implementation:
  static_output_assets: true
```

## Run Local Mock Task

Use this first to verify the local pipeline and API config.

```powershell
python main.py --task examples\mock_task --config config\smoke_glm.yaml --output runs\smoke_glm_mock --max-repairs 1
```

## Prepare An Official Cleanroom Task

Fetch sample metadata:

```powershell
python scripts\fetch_programbench_samples.py --limit 5 --output examples\programbench_samples\samples.json
```

Prepare a cleanroom workspace from the official `:task_cleanroom` image:

```powershell
python scripts\prepare_programbench_task.py ajeetdsouza__zoxide.67ca1bc --runs runs\programbench_smoke --pull
```

This writes:

```text
runs/programbench_smoke/<instance_id>/
  session.json
  workspace/
  evidence/
  generated/
  reports/
  compliance/
  logs/
```

## Run ReBuilder On A Cleanroom Task

On Windows, official ProgramBench executables are Linux binaries. Use the Docker
reference backend. For path/state-heavy tasks, run the generated replacement
through WSL so local differential testing is closer to the official Linux
environment:

```powershell
python main.py `
  --task runs\programbench_smoke\ajeetdsouza__zoxide.67ca1bc\workspace `
  --config config\smoke_glm.yaml `
  --max-repairs 1 `
  --reference-docker-image programbench/ajeetdsouza_1776_zoxide.67ca1bc:task_cleanroom `
  --replacement-executor wsl
```

The Docker reference backend runs with `--network none` and only accepts
`:task_cleanroom` images.

## Run Static Asset Ablation

For clean comparisons, run the same task twice and only change the static asset
toggle:

```powershell
python main.py `
  --task runs\programbench_smoke\ajeetdsouza__zoxide.67ca1bc\workspace `
  --config config\smoke_glm.yaml `
  --output runs\ablation_assets_on `
  --max-repairs 1 `
  --reference-docker-image programbench/ajeetdsouza_1776_zoxide.67ca1bc:task_cleanroom `
  --replacement-executor wsl `
  --static-output-assets enabled

python main.py `
  --task runs\programbench_smoke\ajeetdsouza__zoxide.67ca1bc\workspace `
  --config config\smoke_glm.yaml `
  --output runs\ablation_assets_off `
  --max-repairs 1 `
  --reference-docker-image programbench/ajeetdsouza_1776_zoxide.67ca1bc:task_cleanroom `
  --replacement-executor wsl `
  --static-output-assets disabled
```

Each `result.json` records `implementation_metadata.static_output_assets_enabled`
and `contract_asset_status`. Mini-lab summaries include an `assets` column.

## Run A Mini-Lab

Mini-lab runs multiple cleanroom samples and writes aggregate reports.

Low-cost smoke:

```powershell
python scripts\run_programbench_mini_lab.py `
  --limit 2 `
  --runs runs\programbench_mini_lab_smoke `
  --config config\smoke_glm.yaml `
  --max-repairs 1 `
  --prepare-missing `
  --pull
```

Stable explicit sample set:

```powershell
python scripts\run_programbench_mini_lab.py `
  --instances ajeetdsouza__zoxide.67ca1bc agourlay__zip-password-finder.704700d `
  --runs runs\programbench_mini_lab `
  --config config\settings.yaml `
  --prepare-missing `
  --pull
```

Pair static-assets ablation in one command:

```powershell
python scripts\run_programbench_mini_lab.py `
  --instances ajeetdsouza__zoxide.67ca1bc agourlay__zip-password-finder.704700d `
  --runs runs\programbench_mini_lab_ablation `
  --config config\smoke_glm.yaml `
  --max-repairs 1 `
  --static-output-assets both `
  --prepare-missing `
  --pull
```

Reports are written to:

```text
<runs>/mini_lab/mini_lab_summary.json
<runs>/mini_lab/mini_lab_summary.md
```

When `--static-output-assets both` is used, ReBuilder writes:

```text
<runs>/assets_enabled/mini_lab/mini_lab_summary.json
<runs>/assets_disabled/mini_lab/mini_lab_summary.json
<runs>/mini_lab_ablation/mini_lab_ablation_summary.json
<runs>/mini_lab_ablation/mini_lab_ablation_summary.md
```

The mini-lab summary contains aggregate metrics only. It does not expose hidden
evaluation failures or detailed holdout failures.

## Package A Submission

Package generated code for an official evaluator:

```powershell
python scripts\package_submission.py ajeetdsouza__zoxide.67ca1bc `
  --generated runs\programbench_smoke\ajeetdsouza__zoxide.67ca1bc\generated\ajeetdsouza__zoxide.67ca1bc `
  --result runs\programbench_smoke\ajeetdsouza__zoxide.67ca1bc\generated\ajeetdsouza__zoxide.67ca1bc\result.json `
  --min-holdout-rate 0.8 `
  --output submissions
```

The packager excludes reference artifacts, evidence, logs, reports, and
`result.json`. By default it refuses to package official-eval candidates unless
`result.json` contains an aggregate internal holdout result meeting the minimum
rate. `--allow-unverified` exists only for local debugging.

Summarize official evaluation JSON without feeding details back into repair:

```powershell
python scripts\summarize_programbench_eval.py submissions\ajeetdsouza__zoxide.67ca1bc\ajeetdsouza__zoxide.67ca1bc.eval.json
```

When an instance id is available, include counted-test filtering to avoid
mixing raw eval totals with the ProgramBench scoring subset:

```powershell
python scripts\summarize_programbench_eval.py `
  runs\programbench_official_eval\submission_hotfix_retry\abishekvashok__cmatrix.5c082c6\abishekvashok__cmatrix.5c082c6.eval.json `
  --instance-id abishekvashok__cmatrix.5c082c6
```

## Record A Baseline

After official evaluation, freeze aggregate metrics and the submission hash:

```powershell
python scripts\record_programbench_baseline.py ajeetdsouza__zoxide.67ca1bc `
  --local-result runs\programbench_smoke\ajeetdsouza__zoxide.67ca1bc\generated\ajeetdsouza__zoxide.67ca1bc\result.json `
  --official-eval runs\programbench_official_eval\submission\ajeetdsouza__zoxide.67ca1bc\ajeetdsouza__zoxide.67ca1bc.eval.json `
  --submission runs\programbench_smoke\ajeetdsouza__zoxide.67ca1bc\submission\ajeetdsouza__zoxide.67ca1bc\submission.tar.gz `
  --output baselines\programbench `
  --model glm-5.1 `
  --config config\smoke_glm.yaml `
  --notes "First non-zero official zoxide evaluator baseline; aggregate-only."
```

The baseline record intentionally excludes official hidden-test details.

## Project Structure

```text
ReBuilder/
  config/
    settings.yaml
    smoke_glm.yaml
  core/
    compliance/
    codebase/
    evidence/
    evaluation/
    execution/
    experiments/
    hypotheses/
    probing/
    programbench/
    repair/
    session/
    submission/
    architect_agent.py
    data_models.py
    differential_tester.py
    implementer_agent.py
    meta_controller.py
    probe_engine.py
    repair_loop.py
    spec_synthesizer.py
  docs/
    handoff.md
    programbench-cleanroom-runbook.md
    programbench-compliance.md
  examples/
    mock_task/
    programbench_samples/
  llm_clients/
  scripts/
  tests/
  utils/
  main.py
```

## Key Commands

Run all tests:

```powershell
.\\.venv\\Scripts\\Activate.ps1
pytest -q
```

Run the GLM smoke config:

```powershell
python main.py --task examples\mock_task --config config\smoke_glm.yaml --max-repairs 1
```

Generate a mini-lab report from existing results without new model calls:

```powershell
$script = @'
from pathlib import Path
from core.experiments.mini_lab import MiniLabResultCollector, MiniLabReportWriter

run_root = Path("runs/programbench_smoke")
report = MiniLabResultCollector().collect(run_root, ["ajeetdsouza__zoxide.67ca1bc"])
paths = MiniLabReportWriter().write(report, run_root / "mini_lab")
print(paths.json_path)
print(paths.markdown_path)
'@
$script | python -
```

Rank completed runs for the next official-eval candidates:

```powershell
python scripts\rank_programbench_candidates.py --limit 10 --only-unofficial
```

Show only candidates that are both unofficial and past the local aggregate holdout gate:

```powershell
python scripts\rank_programbench_candidates.py --limit 10 --official-eligible-only --latest-per-task
```

For a possible baseline upgrade on a task that already has official aggregate
history, opt in explicitly:

```powershell
python scripts\rank_programbench_candidates.py --limit 10 `
  --official-eligible-only `
  --allow-existing-official `
  --latest-per-task
```

If this table is empty, keep improving cleanroom probes/repair locally instead of invoking official eval.
The `official gate` column explains the aggregate blocker: `eligible`, `already_official`,
`eligible_baseline_upgrade`, `missing_holdout`, `too_few_holdout_cases`, or
`low_holdout_rate`.

Audit a single `result.json` before any manual official-eval step:

```powershell
python scripts\audit_official_eval_gate.py runs\path\to\result.json `
  --min-holdout-rate 0.8 `
  --min-holdout-cases 10
```

The audit prints aggregate JSON and exits non-zero unless the candidate is `eligible`.
Use `--allow-existing-official` only when intentionally auditing a baseline
upgrade candidate for an already evaluated task; a passing result is reported as
`eligible_baseline_upgrade`.

Audit whether a weak-task rerun actually improves over that task's previous
best reliable local holdout:

```powershell
python scripts\audit_holdout_improvement.py runs\path\to\result.json `
  --runs runs `
  --min-holdout-cases 10
```

This reads only aggregate `result.json` fields and exits non-zero unless the
current result beats the previous reliable best for the same task.

Summarize reliable local holdout trends before rerunning a weak task:

```powershell
python scripts\summarize_holdout_trends.py --runs runs --limit 20 --min-holdout-cases 10
```

This table compares the latest aggregate holdout result with the best reliable
aggregate holdout result per task. It reads only `result.json` aggregate fields
and helps avoid treating a low-sample or regressed run as progress.
Add `--recommend-weak-reruns` to print aggregate-only local rerun targets whose
historical best reliable holdout is still below the gate, along with the required
`--skip-official-eval --require-holdout-improvement --holdout-history-root ...`
flags for the next cleanroom rerun.
Add `--include-rerun-command --rerun-root runs\weak_task_cleanroom_next` to
print a guarded `run_weak_task_cleanroom_rerun.py ... --dry-run` command for
each recommended task.

Prepare a local-only weak-task rerun command without exposing official eval paths:

```powershell
python scripts\run_weak_task_cleanroom_rerun.py sharkdp__hexyl.2e26437 `
  --runs runs\weak_hexyl_cleanroom_next `
  --dry-run
```

The wrapper always delegates to `run_official_closed_loop.py` with
`--skip-official-eval --require-holdout-improvement`, so it is the preferred
entrypoint after explicit authorization for an external-LLM/Docker local rerun.
It defaults to dry-run; add `--execute` only after explicit authorization.

Run a full gated closed loop for one candidate:

```powershell
python scripts\run_official_closed_loop.py burntsushi__xsv.f430466 `
  --runs runs\closed_loop_official_20260512_xsv `
  --eval-run-name submission_xsv_closed_loop_20260512 `
  --pull `
  --force
```

The closed-loop runner keeps official eval gated behind local holdout. It defaults to `--probe-iterations 10` plus
`--min-probe-samples 50`, so a small number of LLM-guided probes is supplemented by deterministic cleanroom probes until
the internal split can produce enough holdout cases. It requires both a passing holdout rate
(`--min-holdout-rate`, default `0.8`) and enough holdout cases (`--min-holdout-cases`, default `10`) before packaging.
If a run lands in the near-miss band (`--near-miss-holdout-rate`, default `0.75`) but below the holdout-rate gate, it
automatically performs one deeper local repair retry with `--near-miss-max-repairs` (default `5`) before deciding whether
to package and submit.
For weak-task reruns, add `--require-holdout-improvement --holdout-history-root runs` so the runner also blocks packaging
unless the current aggregate holdout beats the task's previous reliable best.

Run an aggregate-only official strategy ablation for one candidate:

```powershell
python scripts\run_official_strategy_ablation.py abishekvashok__cmatrix.5c082c6 `
  --catalog examples\programbench_samples\resolved_push_candidates_20260512.json `
  --runs runs\official_strategy_ablation_cmatrix `
  --static-output-assets disabled `
  --min-probe-samples 50 `
  --min-holdout-cases 10 `
  --min-holdout-rate 0.8 `
  --replacement-executor wsl `
  --pull `
  --keep-going
```

The ablation runner treats closed-loop exit code `3` as a holdout-gate skip, not as an infrastructure failure. That means
a weak variant can be blocked before official eval while the remaining variants continue; only aggregate registry rows and
baseline records are written for variants that actually reach official eval.
For weak-task ablations, add `--require-holdout-improvement --holdout-history-root runs`; each variant must then beat the
task's previous reliable aggregate holdout before packaging or official-eval paths can be reached.
For fair pairwise ablations, point `--holdout-history-root` at a history directory that does not include the current
ablation output root; otherwise later variants may be compared against earlier variants from the same ablation run.

## Current Roadmap

Completed:

- Six-phase reconstruction pipeline
- GLM and Kimi client layer
- Project `.env` loading
- Docker reference backend for Linux cleanroom executables on Windows hosts
- Evidence store and run-session layout
- ProgramBench sample metadata fetch and cleanroom workspace preparation
- Submission packaging
- Internal exploration/holdout split
- Exploration-only failure cluster reports
- Mini-lab aggregate reporting
- Project-local Python 3.12 `.venv` baseline with `pytest.ini` collecting only `tests/`
- Official zoxide aggregate baseline: `175/974`, score `18`
- Failure-cluster-driven repair target selection
- Non-regressive repair acceptance and rollback
- Configured architecture language constraints for smoke runs
- Generated-code integrity checks for missing imports and unusable entrypoints
- Robust implementer parsing for JSON, JSON-ish manifests, and nested code fences
- Truncated JSON-ish manifest recovery to avoid `no_files` collapse when long model outputs are cut off
- GLM transient connection retry
- Staged Python implementation generation: runnable CLI entrypoint first, support modules second
- Exact behavior contracts from cleanroom exploration injected into implementation and repair prompts
- Contract-guided zoxide cleanroom smoke validation: `83.3%` local differential equivalence
- WSL replacement execution backend for Linux-parity local differential checks
- Robust repair-strategy parsing from JSON embedded in explanatory model text
- Stateful cleanroom probes with shared workdirs for documented add/query/remove flows
- Stateful differential replay in shared workdirs
- Shell init full-output probes for documented `init <shell>` commands
- Static default shell-init outputs can be materialized under a narrow anti-overfit asset policy
- Static output assets can be toggled from CLI and are recorded in result metadata
- Static asset mode constrains implementation prompts to compact CLI skeletons
  instead of hand-writing long shell init templates
- File I/O side-effect probes for documented input/output files and flags
- Output file content previews are included in exact behavior contracts
- File I/O probes now cover documented output directories in addition to single-file outputs
- Submission packaging now prefers main-like Python entrypoints such as `main.main.py`
- Submission packaging is gated by aggregate internal holdout metrics
- Stateful plans are kept atomic across exploration/holdout splits
- Holdout-gated zoxide smoke prevented packaging weak-generalization
  candidates, most recently `76.0%` exploration with `2/7` holdout
- Official zoxide candidate checks remain below frozen official baseline:
  `95/577`, `76/577`, and `78/577`
- Phase-level LLM usage metadata is now recorded when provider responses expose usage
- Improved cmatrix official aggregate baseline: `481/508` counted tests,
  ProgramBench info score `95` from a cleanroom-local patch on the historical
  adaptive-profile candidate; local post-patch replay was `64/64` exploration
  and `16/16` holdout, and `fully_resolved` remains false
- Official jarun nnn aggregate baseline: `379/477` counted tests,
  ProgramBench info score `79` from a closed-loop, assets-disabled candidate
- Official chmln sd aggregate baseline: `699/810` counted tests, ProgramBench
  info score `86`; latest local holdout was `12/12`, runtime smoke passed, but
  `fully_resolved` and `almost_resolved` are still false
- Improved zip-password-finder official aggregate baseline: `248/680` counted
  tests, ProgramBench info score `36` from an archive/clap strategy-pack
  closed-loop candidate
- Official go-mod-outdated aggregate baseline: `43/285` counted tests,
  ProgramBench info score `15`; retained as an aggregate-only baseline and
  local-vs-official gap datapoint
- Official csview aggregate baseline: `190/335` counted tests,
  ProgramBench info score `57` from a holdout-gated min-50 closed-loop candidate
- Improved htmlq official aggregate baseline: `1330/1455` counted tests,
  ProgramBench info score `91` from a no-external-LLM file_bridge restoration
  patch; local exploration was `48/49`, holdout was `14/15`, and runtime smoke
  passed across `args`, `stdin`, `input_files`, and default dimensions
- Official clog-cli aggregate baseline: `236/575` counted tests,
  ProgramBench info score `41` from a task-profile min-50 closed-loop candidate
- Improved xsv official aggregate baseline: `518/1186` counted tests,
  ProgramBench info score `44` from CSV/xsv strategy-pack refinement
- Improved gron official aggregate baseline: `140/224` counted tests,
  ProgramBench info score `62` from a no-external-LLM file_bridge restoration
  patch; local exploration was `45/45`, holdout was `13/14`, and runtime smoke
  passed across `args`, `stdin`, `input_files`, and default dimensions
- Official eval summaries can now print both raw and counted metrics when
  `--instance-id` is supplied, reducing scoring-scope mixups
- Candidate ranking script scans completed `runs/**/result.json` files and
  deprioritizes tasks with existing official eval artifacts or baseline records
- Candidate ranking now deprioritizes low-sample holdout results so unreliable
  local gates do not outrank runs with at least 10 holdout cases
- Candidate ranking can now be filtered to official-eligible rows only, requiring
  no existing official eval plus aggregate local holdout rate/case thresholds.
- Candidate ranking now prints an aggregate `official gate` reason, so weak
  candidates are blocked explicitly without inspecting hidden or holdout details.
- Existing official eval artifacts can now be audited against recorded baselines
  with `scripts\audit_official_baseline_candidates.py`; it reports only
  aggregate unrecorded or upgrade candidates, then stays empty after the
  historical chroma baseline plus current elfcat and chmln sd baselines are
  frozen.
- Single-result official eval readiness can now be audited with
  `scripts\audit_official_eval_gate.py`; it returns a non-zero exit code for
  aggregate blockers such as `low_holdout_rate`.
- Local aggregate holdout trends can now be summarized with
  `scripts\summarize_holdout_trends.py`, comparing each task's latest reliable
  run against its best reliable holdout without reading detailed failures.
- Single-result weak-task improvement can now be audited with
  `scripts\audit_holdout_improvement.py`; it exits non-zero unless the current
  aggregate holdout beats the previous reliable best for that task.
- The closed-loop runner can select safe scalar strategy variants from an
  aggregate-only registry before reconstruction starts; skip-official and
  holdout-gate exits are covered so they do not append strategy feedback rows.
- The closed-loop runner can also require aggregate holdout improvement before
  packaging with `--require-holdout-improvement`, preventing regressed weak-task
  reruns from reaching official-eval paths.
- Task-domain profiling now infers strategy hints such as `network_ping`,
  `csv_table`, `json_transform`, and `html_selector` from docs, CLI surface,
  and probe output, then injects those hints into spec, implementation, and
  repair prompts without overriding exact behavior contracts.
- Task-domain profiles now include structured strategy packs with
  implementation playbooks, repair playbooks, and anti-patterns. The first
  packs cover network/ping, CSV/table, JSON transform, HTML selector,
  archive/compression, terminal UI, filesystem tools, and binary/hexdump tools.
- Adaptive deterministic probes now cover binary/hexdump byte-layout axes such
  as empty stdin, raw binary files, length/skip offsets, panel layout, and
  invalid color-scheme diagnostics for hexyl-style tasks.
- Strategy packs now include sharper JSON/gron, HTML selector, Rust/clap archive,
  and Go dependency-report guidance. The archive/clap guidance lifted
  `agourlay__zip-password-finder.704700d` from official score `26` to `36`.
- CSV/table strategy guidance now includes xsv-style subcommand variant order and
  sample-command semantics; this lifted `burntsushi__xsv.f430466` from official
  score `41` to `44`.
- Official cmatrix strategy ablation produced an aggregate baseline/no-adaptive
  score `88` (`445/508` counted; raw eval `705/769`) and an adaptive-profile
  score `93` (`471/508` counted; raw eval `729/769`). The deeper adaptive run
  was correctly held back because local holdout was `16/21` (`76.2%`), below
  the `80%` gate.
- A later cleanroom-local patch on that historical adaptive-profile candidate
  raised the official aggregate baseline to score `95` (`481/508` counted; raw
  eval `739/769`) with local post-patch replay at `64/64` exploration and
  `16/16` holdout. `fully_resolved` remains false.
- Docker reference probes now run containers with unique names and force-remove
  timed-out containers, preventing network-style tools from hanging the closed
  loop on long-running commands.
- LLM-generated probe args now clamp count-like run multipliers (`-c`,
  `--count`, `--repeat`, etc.) to bounded positive values so stress and
  zero-count cases do not turn into accidental soak tests.
- Ping-like tasks also guard bare host probes by adding a one-packet count,
  avoiding indefinite default ping behavior during cleanroom exploration.
- `sheepla__pingu.926d475` improved under the structured network/ping strategy
  pack from the previous `3/11` holdout (`27.3%`) to `7/12` (`58.3%`), but it
  still failed the `80%` local gate, so the official evaluator was not invoked.
  This remains the current network/ping generalization gap case.
- The latest pingu v3 local cleanroom rerun used `--skip-official-eval` and
  produced `3/14` holdout (`21.4%`) with `low_holdout_rate` as the official
  gate blocker; no official evaluator was invoked. The network/ping strategy
  pack now emphasizes special address failure taxonomy, Go/net-style resolver
  wording, zero-transmitted network-error transcripts, and complete packet
  statistics rendering, pingu dot-art packet-line prefixes, and `-c, --count`
  Go-style parse-error aliases. The address-category state machine guidance is
  present in the implementation playbook, not only repair, before any further
  official eval attempt. The current trend audit marks this as a regression
  from the best reliable `7/12` (`58.3%`) run, so the next local pingu rerun
  must beat `58.3%` before it counts as a weak-task holdout improvement.

Next priorities:

- Investigate the local-vs-official gap using only aggregate official results and fresh cleanroom probes
- Validate and refine domain strategy packs on pingu/htmlq/gron/xsv-style reruns without using official failure details
- Run asset-enabled vs asset-disabled ablations before attributing score gains
- Broaden file I/O probes to directory outputs and config/cache side effects
- Shell init parity validation across more task shells and init flags
- Expand the mini-lab to additional cleanroom tasks for cross-task signal
- Build/execution isolation for generated compiled-language submissions
- Cost and token accounting per phase

## Research Notes

ReBuilder is designed to test the architecture-vs-parameters hypothesis:

```text
For long-horizon, unstructured software engineering tasks, agent process and
architecture may contribute more to performance than simply scaling the base
model.
```

The framework should be judged by cleanroom, aggregate, reproducible results
across task types, not by hand-tuning a single task until it passes.

## License

MIT License.

## 2026-05 官方突破进展

当前已固化 13 条官方 aggregate baseline（取自 `baselines/programbench/*.baseline.json`，按 ProgramBench info score 排序；均为 aggregate-only，`fully_resolved=false`，不是 solved task）：

| score | task | counted | 备注 |
| ----: | ---- | ------- | ---- |
| 98 | agourlay__zip-password-finder | 667/680 | 无外部 LLM file_bridge：纯 stdlib WinZip AES PBKDF2 校验 + 输出/退出/错误契约（40→98；raw 778/792） |
| 95 | abishekvashok__cmatrix | 481/508 | adaptive-profile cleanroom-local patch（77→95） |
| 94 | psampaz__go-mod-outdated | 267/285 | go-mod markdown table 闭环 |
| 91 | mgdm__htmlq | 1330/1455 | 无外部 LLM file_bridge restoration（8→91） |
| 87 | wfxr__csview | 291/335 | csview axis 修复（57→87） |
| 86 | chmln__sd | 699/810 | file_bridge `baseline_regex_patch1` |
| 79 | jarun__nnn | 379/477 | 闭环候选 |
| 75 | clog-tool__clog-cli | 432/575 | 无外部 LLM file_bridge from_latest_patch7（45→75；raw 567/778；help/missing-file/semver + .clog.toml 配置错误契约） |
| 70 | burntsushi__xsv | 832/1186 | 无外部 LLM file_bridge restore_patch8 broad subcommand 重写（50→70；raw 953/1317） |
| 67 | ajeetdsouza__zoxide | 357/531 | 无外部 LLM 重建：9 个 shell 的 init 字节级复现（允许的 static asset）+ 通用 db 算法（37→67；raw 396/577） |
| 66 | rbakbashev__elfcat | 371/564 | file_bri