# ProgramBench Cleanroom Runbook

This runbook keeps ReBuilder aligned with the ProgramBench inference boundary.

## Boundary

Use only official `task_cleanroom` images for reconstruction. Do not pull or inspect `task` evaluation images during inference. Do not download test blobs, hidden tests, original source code, or package-manager source for the target project.

## Prepare Sample Metadata

```bash
python scripts/fetch_programbench_samples.py --limit 5 --output examples/programbench_samples/samples.json
```

This records DockerHub image metadata only.

## Prepare A Cleanroom Workspace

```bash
python scripts/prepare_programbench_task.py ajeetdsouza__zoxide.67ca1bc --runs runs --pull
```

The script uses the sample's `task_cleanroom` image and writes:

```text
runs/
  ajeetdsouza__zoxide.67ca1bc/
    session.json
    workspace/
    evidence/
    generated/
    reports/
    compliance/
    logs/
```

Official ProgramBench images are Linux amd64. Use a Linux x86_64 host for real inference runs.

## Run ReBuilder On The Prepared Workspace

```bash
python main.py --task runs/ajeetdsouza__zoxide.67ca1bc/workspace --provider kimi
```

When `main.py` sees a task path ending in `workspace` with a sibling `session.json`, it automatically writes evidence into the session's `evidence/` directory and generated code into `generated/`.

## Evaluation

Official ProgramBench evaluation is separate from reconstruction. Package final generated code as `submission.tar.gz` and run the official evaluator outside ReBuilder's repair loop.

## Anti-Overfit Policy

ReBuilder can split cleanroom observations into exploration and internal holdout sets. The exploration set may drive specification, implementation, repair, and detailed failure reports. The internal holdout set is aggregate-only by default and must not be used to write repair prompts or targeted fixes for the same run.

Official hidden evaluation is stricter: its failures must never enter reconstruction or repair. Use official eval output only as a final external score summary.

## Static Output Asset Policy

Some CLI tools expose large static templates through documented commands. A
replacement may materialize these as generated support assets only under the
repository policy in `docs/programbench-compliance.md`.

Current implementation policy is intentionally narrow: only long, successful,
stderr-free default `init <shell>` outputs for documented shell-init probes may
be materialized. Variants such as `--cmd`, `--hook`, `--no-cmd`, stateful
commands, file I/O commands, and hidden-eval-derived behavior must stay as
logic, not lookup tables.

When comparing results, record whether static output assets were enabled and
prefer an ablation pair before claiming an architecture improvement.

Use the CLI override to keep every other config value unchanged:

```bash
python main.py --task runs/ajeetdsouza__zoxide.67ca1bc/workspace \
  --config config/smoke_glm.yaml \
  --reference-docker-image programbench/ajeetdsouza_1776_zoxide.67ca1bc:task_cleanroom \
  --static-output-assets enabled

python main.py --task runs/ajeetdsouza__zoxide.67ca1bc/workspace \
  --config config/smoke_glm.yaml \
  --reference-docker-image programbench/ajeetdsouza_1776_zoxide.67ca1bc:task_cleanroom \
  --static-output-assets disabled
```

The resulting `result.json` files include
`implementation_metadata.static_output_assets_enabled` and
`contract_asset_status`.

## Run A Mini-Lab

The mini-lab runner batches several cleanroom tasks and writes aggregate reports. It uses only `task_cleanroom` images as reference executables.

Use explicit instances when you want a stable comparison set:

```bash
python scripts/run_programbench_mini_lab.py \
  --instances ajeetdsouza__zoxide.67ca1bc agourlay__zip-password-finder.704700d \
  --runs runs/programbench_mini_lab \
  --config config/settings.yaml \
  --prepare-missing \
  --pull
```

For low-cost smoke runs, use the smoke config and a small limit:

```bash
python scripts/run_programbench_mini_lab.py \
  --limit 2 \
  --runs runs/programbench_mini_lab_smoke \
  --config config/smoke_glm.yaml \
  --max-repairs 1 \
  --prepare-missing
```

The runner writes:

```text
runs/programbench_mini_lab/
  <instance_id>/
    workspace/
    evidence/
    generated/
    reports/
  mini_lab/
    mini_lab_summary.json
    mini_lab_summary.md
```

The summary includes per-task aggregate rates, probe counts, repair counts, and holdout rates when available. It does not include official hidden-test failures or detailed holdout failures.

```bash
python scripts/package_submission.py ajeetdsouza__zoxide.67ca1bc \
  --generated runs/ajeetdsouza__zoxide.67ca1bc/generated/ajeetdsouza__zoxide.67ca1bc \
  --output submissions
```

After official evaluation, summarize the JSON without feeding failures back into ReBuilder repair:

```bash
python scripts/summarize_programbench_eval.py submissions/ajeetdsouza__zoxide.67ca1bc/ajeetdsouza__zoxide.67ca1bc.eval.json
```

## Record A Baseline

Freeze aggregate local and official metrics after an evaluation run:

```bash
python scripts/record_programbench_baseline.py ajeetdsouza__zoxide.67ca1bc \
  --local-result runs/programbench_smoke/ajeetdsouza__zoxide.67ca1bc/generated/ajeetdsouza__zoxide.67ca1bc/result.json \
  --official-eval runs/programbench_official_eval/submission/ajeetdsouza__zoxide.67ca1bc/ajeetdsouza__zoxide.67ca1bc.eval.json \
  --submission runs/programbench_smoke/ajeetdsouza__zoxide.67ca1bc/submission/ajeetdsouza__zoxide.67ca1bc/submission.tar.gz \
  --output baselines/programbench \
  --model glm-5.1 \
  --config config/smoke_glm.yaml \
  --notes "First non-zero official zoxide evaluator baseline; aggregate-only."
```

Baseline records must include aggregate scores and hashes only. Do not copy hidden-test failures into baselines, prompts, reports, or repair loops.
