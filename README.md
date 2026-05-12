# ReBuilder Framework

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

- Full unit test suite: `230 passed` in a project-local Python 3.12 `.venv` with `pytest -q`
- GLM-5.1 coding-plan endpoint smoke tested
- Official ProgramBench cleanroom zoxide sample runs end-to-end
- Frozen zoxide local smoke baseline: `16.7%` local differential equivalence
- Latest zoxide cleanroom smoke candidate: `83.3%` local differential
  equivalence, exploration-only and not an official hidden-test result
- Latest stateful WSL zoxide cleanroom smoke candidate: `100.0%` local
  differential equivalence, exploration-only and not an official hidden-test
  result
- Latest holdout-gated WSL zoxide smoke: `76.0%` exploration and `28.6%`
  aggregate internal holdout; static assets materialized, but packaging gate
  still rejected it before official eval
- Reference-only zoxide cleanroom probe check now captures full shell init
  scripts for bash, zsh, fish, and powershell without calling an LLM
- Current zoxide official evaluator baseline: ProgramBench info score `37`
  (`195/531` counted tests) from the static-assets mini-lab candidate
- First non-zoxide official generalization baseline:
  `agourlay__zip-password-finder.704700d` ProgramBench info score `26`
  (`180/680` counted tests) from the assets-disabled mini-lab candidate
- Second non-zoxide official generalization baseline:
  `abishekvashok__cmatrix.5c082c6` ProgramBench info score improved from
  `77` to `82` (`415/508` counted tests; raw eval `674/769`) from the
  assets-disabled manual hotfix retry after assets ablation
- Third non-zoxide official generalization baseline:
  `jarun__nnn.cb2c535` ProgramBench info score `79` (`379/477` counted
  tests; raw eval `1101/1796`) from a closed-loop, assets-disabled candidate
- Fourth non-zoxide official generalization baseline:
  `psampaz__go-mod-outdated.bb79367` ProgramBench info score `15`
  (`43/285` counted tests; raw eval `91/342`) from a holdout-gated min-50
  closed-loop candidate. Local holdout was `11/11`, so this is also a tracked
  local-vs-official generalization gap.
- Fifth non-zoxide official generalization baseline:
  `wfxr__csview.8ac4de0` ProgramBench info score `57` (`190/335` counted
  tests; raw eval `200/348`) from a holdout-gated min-50 closed-loop candidate.
  After fixing stdin forwarding in local differential execution, the refreshed
  local holdout is `8/12`, so the submitted aggregate is retained but the old
  `11/12` local gate is treated as stale.
- Sixth non-zoxide official generalization baseline:
  `mgdm__htmlq.6e31bc8` ProgramBench info score `8` (`118/1455` counted
  tests; raw eval `720/2058`) from a holdout-gated min-50 closed-loop candidate.
  After the stdin fix, refreshed local holdout is `7/11`, so this is retained as
  a stale-gate local-vs-official gap datapoint.
- Seventh non-zoxide official generalization baseline:
  `burntsushi__xsv.f430466` ProgramBench info score `41` (`484/1186` counted
  tests; raw eval `579/1317`) after stdin execution fixes and repair-next
  continuation. Local exploration was `43/45`, with holdout `8/10`.
- Eighth non-zoxide official generalization baseline:
  `tomnomnom__gron.88a6234` ProgramBench info score `26` (`117/457` counted
  tests; raw eval `117/457`) after stdin execution fixes and repair-next
  continuation. Local holdout was `11/11`, while exploration stayed `42/51`.
- Ninth non-zoxide official generalization baseline:
  `clog-tool__clog-cli.7066cba` ProgramBench info score `41` (`236/575`
  counted tests; raw eval `370/778`) after task-profile probing and min-50
  holdout gate. Local holdout was `11/12`.
- Previous zoxide official evaluator baseline: raw `175/974`, score `18`
- Earlier official evaluator candidates remained below the previous baseline:
  `95/577` from the Windows-local validation candidate, `76/577` from the
  WSL/Linux validation candidate, and `78/577` from the stateful WSL candidate
- Mini-lab runner can aggregate multiple cleanroom task runs
- Probe generalization upgraded from sample-count filling to behavior-coverage
  filling: discovered flags, subcommands, stdin/file modes, nonzero exits, and
  missing behavior modes are tracked and logged in result metadata.

The zoxide score is not high, but the important milestone is that the full
cleanroom loop now runs:

```text
task_cleanroom image -> probe reference -> synthesize spec -> design architecture
-> generate replacement -> differential test -> repair -> re-test -> package/report
```

The official score is a single-instance non-zero baseline, not a solved task:
`fully_resolved=False`, `almost_resolved=False`.

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
- Network access for LLM API calls and optional Docker image pulls
- API key for one supported provider

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
- Improved cmatrix official aggregate baseline: `415/508` counted tests,
  ProgramBench info score `82` from the assets-disabled manual hotfix retry
- Official jarun nnn aggregate baseline: `379/477` counted tests,
  ProgramBench info score `79` from a closed-loop, assets-disabled candidate
- Official go-mod-outdated aggregate baseline: `43/285` counted tests,
  ProgramBench info score `15`; retained as an aggregate-only baseline and
  local-vs-official gap datapoint
- Official csview aggregate baseline: `190/335` counted tests,
  ProgramBench info score `57` from a holdout-gated min-50 closed-loop candidate
- Official htmlq aggregate baseline: `118/1455` counted tests,
  ProgramBench info score `8`; retained as an aggregate-only local-vs-official
  gap datapoint
- Official clog-cli aggregate baseline: `236/575` counted tests,
  ProgramBench info score `41` from a task-profile min-50 closed-loop candidate
- Official eval summaries can now print both raw and counted metrics when
  `--instance-id` is supplied, reducing scoring-scope mixups
- Candidate ranking script scans completed `runs/**/result.json` files and
  deprioritizes tasks with existing official eval artifacts or baseline records
- Candidate ranking now deprioritizes low-sample holdout results so unreliable
  local gates do not outrank runs with at least 10 holdout cases
- Task-domain profiling now infers strategy hints such as `network_ping`,
  `csv_table`, `json_transform`, and `html_selector` from docs, CLI surface,
  and probe output, then injects those hints into spec, implementation, and
  repair prompts without overriding exact behavior contracts.
- Docker reference probes now run containers with unique names and force-remove
  timed-out containers, preventing network-style tools from hanging the closed
  loop on long-running commands.
- LLM-generated probe args now clamp count-like run multipliers (`-c`,
  `--count`, `--repeat`, etc.) to bounded positive values so stress and
  zero-count cases do not turn into accidental soak tests.
- Ping-like tasks also guard bare host probes by adding a one-packet count,
  avoiding indefinite default ping behavior during cleanroom exploration.
- `sheepla__pingu.926d475` was rerun with task profiling and the new probe
  safety guards. It failed the local gate (`3/11` holdout, `27.3%`), so the
  official evaluator was not invoked; this is the current network/ping
  generalization gap case.

Next priorities:

- Investigate the local-vs-official gap using only aggregate official results and fresh cleanroom probes
- Improve network/ping implementation strategy using the pingu local gate failure, without using official failure details
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

## 2026-05-11 官方突破进展

- agourlay__zip-password-finder: 首次非 zoxide 任务官方突破，aggregate-only，ProgramBench info 分数 26。
- abishekvashok__cmatrix: 第二个非 zoxide 官方突破，assets-disabled mini-lab ablation 候选，ProgramBench info 分数 77。
- ajeetdsouza__zoxide: 官方分数 37（前为 18），aggregate-only。

当前已实现三个任务的官方分数突破，均已记录基线。后续将继续推进更多任务突破。
