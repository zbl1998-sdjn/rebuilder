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

If external LLM egress is blocked, run through a local OpenAI-compatible
endpoint instead:

```bash
python main.py --task runs/ajeetdsouza__zoxide.67ca1bc/workspace \
  --provider local_openai
```

Configure `llm.local_openai` in `config/settings.yaml` or the active config to
point at a loopback URL such as `http://127.0.0.1:11434/v1`. The provider
rejects non-loopback hosts; `LOCAL_OPENAI_API_KEY` is optional and only needed
for local gateways that require bearer auth.

## Evaluation

Official ProgramBench evaluation is separate from reconstruction. Package final generated code as `submission.tar.gz` and run the official evaluator outside ReBuilder's repair loop.

## Anti-Overfit Policy

ReBuilder can split cleanroom observations into exploration and internal holdout sets. The exploration set may drive specification, implementation, repair, and detailed failure reports. The internal holdout set is aggregate-only by default and must not be used to write repair prompts or targeted fixes for the same run.

Official hidden evaluation is stricter: its failures must never enter reconstruction or repair. Use official eval output only as a final external score summary.

## Task-Domain Strategy Packs

Domain strategy packs live in `core/profiling/rules/*.yaml`. Each pack should
provide implementation guidance, repair guidance, anti-patterns, and a
`validation_playbook` plus `generalization_playbook`. The validation playbook
is for bounded local smoke checks and aggregate failure categories. The
generalization playbook is for reusable local coverage, such as unseen holdout
shapes, CLI dispatch paths, stdin/file modes, error branches, and bounded smoke
cases. Neither playbook may contain official hidden failure details or
task-specific lookup tables.

`task_profile_prompt()` includes the generalization playbook in both
implementation and repair prompts, but exact observed behavior contracts still
take priority over domain guidance.
It also includes the validation playbook so generated code and repairs are
nudged toward cleanroom-local smoke checks rather than single-transcript fixes.

Every strategy-pack domain should also have deterministic adaptive probes in
`core/probing/adaptive.py`. Those probes create local-only `smoke_contract` and
`adaptive_axis` tags for aggregate coverage and holdout splitting. If a new
domain is added to `core/profiling/rules`, add a matching probe family or keep
the domain out of the supported adaptive list until its safe smoke cases are
defined.

Use the local coverage audit as a maintenance gate:

```bash
python scripts/audit_strategy_domain_coverage.py --fail-on-missing
```

Use `--format json` when a batch wrapper or dashboard needs machine-readable
coverage without parsing markdown:

```bash
python scripts/audit_strategy_domain_coverage.py \
  --fail-on-missing \
  --format json
```

The same audit also enforces a cleanroom-policy lint for strategy packs. It
rejects obvious official-eval or hidden-test-set leakage markers such as
`official`, hidden-test details, leaderboard language, eval scores, or concrete
ProgramBench task ids. Domain packs should describe reusable parsing,
dispatch, IO, error, smoke, and holdout categories only. JSON output reports
only per-domain aggregate counts and status; it does not include the strategy
pack text or the matched cleanroom-policy snippets.

## Repair Candidate Integrity Gate

Repair uses the same Python integrity and runtime smoke boundary as
implementation before a generated candidate can become the accepted codebase.
After each repair is applied, ReBuilder checks syntax, imports, entrypoint
dispatch, and bounded runtime smoke cases. A failing candidate is recorded as
`repair_integrity_failed`, the previous accepted codebase is restored, and the
failed repair target is skipped before trying the next cluster. This prevents
syntax-broken or non-dispatching repairs from replacing a working baseline just
because their exploration rate ties a weak score.

Runtime smoke also preserves cleanroom file-input observations in behavior
contracts. Safe relative `input_files` are written into the temporary workdir
for bounded contract smoke cases, so generated Python entrypoints are checked
against file-mode CLI dispatch as well as `<no args>`, `--help`, and stdin-only
forms. Unsafe, oversized, or output-file-producing contracts stay out of this
smoke boundary. Spec synthesis also drops unsafe input-file names and previews
from behavior-observation prompts, and redacts matching unsafe argv values
before they can become exact behavior contracts. File-like argv values that are
absolute, drive-qualified, or contain parent traversal are redacted even when
they did not originate from an `input_files` map.

Environment-sensitive cleanroom probes are handled with the same boundary.
Behavior contracts retain safe, short, valid environment variables such as
`TERM`, `COLUMNS`, `LINES`, and `NO_COLOR`, and runtime smoke forwards only
those filtered variables. Sensitive names containing token, secret, password,
key, credential, or auth markers are not included in prompts or smoke cases.
Runtime-smoke de-duplication includes argv, stdin, input-file content
fingerprints, and environment variables, so env-only probes are not hidden by
the default no-args smoke case.

## Historical Runtime-Smoke Replay Audit

Use `scripts/audit_runtime_smoke_replay.py` when existing `runs/**/result.json`
artifacts predate runtime-smoke metadata and you need to know which candidates
can be replayed locally. The default mode is read-only: it loads generated
Python files, finds the nearest sibling `evidence/` store, reconstructs bounded
behavior contracts, and reports only aggregate readiness/status fields.

```bash
python scripts/audit_runtime_smoke_replay.py \
  --runs runs \
  --require-runtime-smoke-dimensions args,input_files \
  --format json
```

`--execute` actually runs the local Python runtime smoke checks against the
generated files, but it still does not call an external LLM, Docker, packaging,
or official eval. JSON output is aggregate-only: task id, status, file/contract
counts, entrypoint, input-dimension names, failed issue kind, and artifact
paths. It must not include argv values, input-file contents, stdout/stderr,
holdout failures, or official hidden-test details.

When strict candidate ranking is empty and you need to know whether the
runtime-smoke requirement is only a missing-metadata artifact, run the gate
cross-audit:

```bash
python scripts/audit_runtime_smoke_gate_replay.py \
  --runs runs \
  --official-eval-root runs/programbench_official_eval \
  --latest-per-task \
  --min-smoke-contract-axes 1 \
  --require-runtime-smoke-dimensions args,input_files \
  --require-holdout-improvement \
  --min-holdout-improvement-delta 0.02 \
  --execute-replay \
  --format json
```

This joins the candidate gate blockers with local runtime-smoke replay results
without mutating `result.json`. A `metadata_only_runtime_smoke_blocker` row
means replay would remove the last strict-gate blocker; otherwise the row still
needs holdout, improvement, smoke-axis, or official/baseline handling. JSON is
aggregate-only and must not include raw argv, input files, stdout/stderr,
holdout failures, or official hidden-test details.

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
  --ack-external-llm-docker \
  --pull
```

For low-cost smoke runs, use the smoke config and a small limit:

```bash
python scripts/run_programbench_mini_lab.py \
  --limit 2 \
  --runs runs/programbench_mini_lab_smoke \
  --config config/smoke_glm.yaml \
  --max-repairs 1 \
  --prepare-missing \
  --ack-external-llm-docker
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
  --result runs/ajeetdsouza__zoxide.67ca1bc/generated/ajeetdsouza__zoxide.67ca1bc/result.json \
  --min-holdout-rate 0.8 \
  --min-holdout-cases 10 \
  --require-holdout-improvement \
  --holdout-history-root runs \
  --min-holdout-improvement-delta 0.02 \
  --output submissions
```

Use `--require-holdout-improvement` on manual packaging commands when the
candidate must beat the previous reliable aggregate local holdout before any
submission archive is created. This uses the same aggregate-only comparison as
`audit_holdout_improvement.py`.

After official evaluation, summarize the JSON without feeding failures back into ReBuilder repair:

```bash
python scripts/summarize_programbench_eval.py submissions/ajeetdsouza__zoxide.67ca1bc/ajeetdsouza__zoxide.67ca1bc.eval.json
```

Strategy ablations must preserve the same boundary. `scripts/run_official_strategy_ablation.py` runs each variant through
the holdout-gated closed-loop runner and treats exit code `3` as a compliant local-gate skip. Skipped variants are not
submitted to official eval, and their holdout failures must not be converted into implementation hints. Variants that do
reach official eval may write only aggregate registry rows and baseline records. For weak-task ablations, pass
`--require-holdout-improvement --holdout-history-root runs` to require each variant to beat that task's previous reliable
aggregate holdout before any packaging or official-eval path is reachable.

When `scripts/run_official_closed_loop.py` is given a strategy registry, variant selection must use only aggregate rows
and safe scalar strategy params. `--skip-official-eval` runs and local holdout-gate skips must not append registry rows.

Before any manual official-eval command, run `scripts/audit_official_eval_gate.py` against the candidate `result.json`.
The audit reads only aggregate local holdout fields plus existing official eval/baseline markers, prints the gate reason,
and exits non-zero unless the candidate is eligible.
Add `--require-holdout-improvement`, `--holdout-history-root runs`, and
`--min-holdout-improvement-delta N` when official-eval eligibility should also
require a positive margin over that task's previous reliable local holdout best.
With that gate enabled, the audit JSON includes the previous reliable best
aggregate holdout rate, case count, result path, and delta used for the
decision.
The candidate table can apply the same aggregate-only improvement screen:

```bash
python scripts/rank_programbench_candidates.py \
  --official-eligible-only \
  --latest-per-task \
  --require-holdout-improvement \
  --holdout-history-root runs \
  --min-holdout-improvement-delta 0.02
```

Use `--format json` when automation needs the same strict candidate table
without parsing markdown:

```bash
python scripts/rank_programbench_candidates.py \
  --official-eligible-only \
  --latest-per-task \
  --min-smoke-contract-axes 1 \
  --require-holdout-improvement \
  --min-holdout-improvement-delta 0.02 \
  --format json
```

The JSON payload reports `schema_version`, selected/total row counts, gate
reason, aggregate local rates/counts, smoke/adaptive axis counts, status,
result path, and official/baseline marker status. It must not include holdout
failure details, official hidden-test details, or raw failure payloads. An
empty strict result should be represented as `row_count=0` and `rows=[]`, not
as a human table with only headers.

By default, existing official-eval or recorded-baseline tasks are blocked as
`already_official`. For an intentional baseline upgrade audit, add
`--allow-existing-official`; passing rows are marked
`eligible_baseline_upgrade` while still using only aggregate local holdout and
smoke-axis metadata. Combine it with `--require-holdout-improvement` when the
rerun must beat previous reliable local holdout before any official re-eval is
considered.

To check whether existing official eval artifacts contain aggregate results
that have not been frozen as baselines, run:

```bash
python scripts/audit_official_baseline_candidates.py \
  --official-eval-root runs/programbench_official_eval \
  --baseline-root baselines/programbench \
  --actionable-only
```

This reports only aggregate official score/counts versus recorded baseline
scores. It is for bookkeeping and upgrade audits; it does not make a weak local
gate acceptable for a fresh official submission.

To decide which already-recorded official baseline is most worth improving next,
combine official aggregate scores with local latest/best reliable holdout trends:

```bash
python scripts/plan_official_breakthrough_targets.py \
  --runs runs \
  --baseline-root baselines/programbench \
  --limit 20 \
  --include-next-command \
  --baseline-upgrade-min-smoke-contract-axes 1 \
  --baseline-upgrade-require-holdout-improvement \
  --baseline-upgrade-min-holdout-improvement-delta 0.02 \
  --include-restore-ablation-command \
  --restore-ablation-root runs/restore_axis_ablation_dryrun \
  --restore-ablation-min-smoke-contract-axes 1 \
  --include-missing-holdout-command \
  --missing-holdout-rerun-root runs/missing_holdout_cleanroom_next \
  --missing-holdout-min-smoke-contract-axes 1 \
  --rerun-root runs/weak_task_cleanroom_next \
  --rerun-min-smoke-contract-axes 1 \
  --rerun-min-holdout-improvement-delta 0.02
```

The target classes are aggregate-only:
`ready_baseline_gate` means the latest reliable local run is at or above the
holdout gate, `restore_historical_gate` means an older reliable run crossed the
gate but the latest run regressed, `weak_cleanroom_rerun` means the task still
needs a local-only guarded rerun, and `missing_reliable_holdout` means the
recorded official baseline has no current reliable holdout trend.
With `--include-next-command`, ready rows print a baseline-upgrade candidate
ranking command, restore rows normally print an `audit_official_eval_gate.py`
command for the historical best `result.json`, and weak rows print a guarded
`run_weak_task_cleanroom_rerun.py --dry-run` command. Add
`--baseline-upgrade-min-smoke-contract-axes`,
`--baseline-upgrade-require-holdout-improvement`, and
`--baseline-upgrade-min-holdout-improvement-delta` when ready rows should print
the same strict aggregate gates used by the final official-eligible audit. Add
`--include-missing-holdout-command` when `missing_reliable_holdout` rows should
print guarded `run_missing_holdout_cleanroom_rerun.py --dry-run` commands that
build reliable local holdout signal with official eval disabled and no
holdout-improvement gate yet. Add
`--include-restore-ablation-command` when the restore rows should instead print
guarded `run_official_strategy_ablation.py --dry-run` commands with
`--skip-official-eval`, `--require-holdout-improvement`,
`--max-generalization-risk low`, and a smoke-axis gate.

Use `--format json` when an orchestrator or dashboard needs the same
aggregate-only official breakthrough queue without parsing markdown. The JSON
payload includes task class, official aggregate counts, latest/best reliable
holdout aggregates, result paths, and optional guarded dry-run next commands:

```bash
python scripts/plan_official_breakthrough_targets.py \
  --runs runs \
  --baseline-root baselines/programbench \
  --include-next-command \
  --baseline-upgrade-min-smoke-contract-axes 1 \
  --baseline-upgrade-require-holdout-improvement \
  --baseline-upgrade-min-holdout-improvement-delta 0.02 \
  --include-restore-ablation-command \
  --include-missing-holdout-command \
  --restore-ablation-min-smoke-contract-axes 1 \
  --missing-holdout-min-smoke-contract-axes 1 \
  --rerun-min-smoke-contract-axes 1 \
  --rerun-min-holdout-improvement-delta 0.02 \
  --limit 12 \
  --format json
```

For a safer restore-axis batch entrypoint, use the wrapper. It selects only
`restore_historical_gate` rows from the aggregate-only planner and defaults to
printing commands without running child processes:

```bash
python scripts/run_restore_axis_ablation_batch.py \
  --runs runs \
  --baseline-root baselines/programbench \
  --output-root runs/restore_axis_ablation_next \
  --limit 7
```

Add `--execute` only after explicit authorization for external LLM and Docker
use, and pair it with `--ack-external-llm-docker`. The generated strategy
ablation commands still include `--dry-run` unless `--execute` is present on
the wrapper; real wrapper execution forwards the acknowledgement to the child
strategy-ablation entrypoint.

To focus a restore batch on one cleanroom axis domain, filter through the
aggregate restore audit action:

```bash
python scripts/run_restore_axis_ablation_batch.py \
  --runs runs \
  --baseline-root baselines/programbench \
  --axis-action-domain csv_table \
  --show-axis-action \
  --limit 7
```

This still only prints guarded dry-run commands by default. The filter matches
domains from `axis_delta_action`, such as
`ablate_added_axis_domains:csv_table`, and does not inspect hidden failures or
per-test official details.

Add `--format json` when automation needs the same dry-run command plan without
parsing human banners. JSON output is limited to command plans; it refuses
non-dry-run execution so child process logs cannot mix with the JSON payload:

```bash
python scripts/run_restore_axis_ablation_batch.py \
  --runs runs \
  --baseline-root baselines/programbench \
  --axis-action-domain csv_table \
  --show-axis-action \
  --limit 7 \
  --format json
```

For the restore subset, print a compact aggregate audit table:

```bash
python scripts/audit_restore_targets.py \
  --runs runs \
  --baseline-root baselines/programbench \
  --limit 20
```

Use `--format json` when a batch wrapper or dashboard needs the same
cleanroom-safe restore actions without parsing markdown:

```bash
python scripts/audit_restore_targets.py \
  --runs runs \
  --baseline-root baselines/programbench \
  --limit 20 \
  --format json
```

This table compares each restore target's latest reliable holdout against its
historical best reliable holdout, checks both local gate reasons with
`audit_official_eval_gate.py`, and reports only aggregate regression, gate
reason, local probe-axis metadata, and result paths. The `added axes` and
`removed axes` columns compare cleanroom-local `probe_axis_coverage` axis names,
such as `csv_table.delimiter_mode` or `html_selector.attribute_selector`, and
filter out free-form strings. The `axis action` column rolls those axis names
up to cleanroom domains, for example `ablate_added_axis_domains:csv_table`; rows
with no axis delta but regressed holdout are marked
`inspect_same_axis_strategy_regression`. `new_axis_expansion_regression` means
the latest run added smoke/adaptive axes while local holdout regressed; that is
a restore/ablation target, not evidence to submit the latest run.

Before any official-eval attempt, run the aggregate-only generalization risk
gate:

```bash
python scripts/audit_generalization_risk.py \
  --runs runs \
  --baseline-root baselines/programbench \
  --limit 20 \
  --fail-on-risk high
```

This is an anti-overfitting guard. High-risk rows include missing reliable
holdout, weak tasks below gate, same-axis holdout regression, and new-axis
expansion regression. A high-risk row blocks official eval and should be handled
with local restore/ablation first. Low-risk rows are not automatic submissions;
they may only proceed to the normal baseline-upgrade and holdout-improvement
audits.

Use `--format json` when an orchestrator needs the same aggregate-only
generalization-risk payload without parsing markdown:

```bash
python scripts/audit_generalization_risk.py \
  --runs runs \
  --baseline-root baselines/programbench \
  --limit 20 \
  --fail-on-risk high \
  --format json
```

The JSON payload contains `schema_version`, selected/total row counts, official
aggregate scores/counts, target class, risk level/reason, holdout aggregates,
result paths, and the required next action. `--fail-on-risk` still exits
non-zero when selected rows exceed the threshold, but stdout remains valid JSON
for automation. It must not include holdout failure details, official hidden
test details, or raw failure payloads.

For automated closed-loop runs, put the same ceiling on the runner. It forwards
the aggregate-only risk gate to `package_submission.py`, so a high-risk candidate
stops before archive creation or official eval:

```bash
python scripts/run_official_closed_loop.py <instance_id> \
  --ack-external-llm-docker \
  --max-generalization-risk low \
  --generalization-risk-root runs \
  --baseline-root baselines/programbench
```

Strategy ablations accept the same flags and forward them to each closed-loop
variant:

```bash
python scripts/run_official_strategy_ablation.py <instance_id> \
  --ack-external-llm-docker \
  --max-generalization-risk low \
  --generalization-risk-root runs \
  --baseline-root baselines/programbench
```

Direct `run_official_closed_loop.py` and non-dry-run
`run_official_strategy_ablation.py` require `--ack-external-llm-docker` before
they run any child command. `--skip-official-eval` only disables official
evaluation; reconstruction can still call an external LLM and Docker.

When a run should require local smoke-contract breadth before official eval,
add `--min-smoke-contract-axes N` to the ranking, audit, package,
closed-loop, ablation, or weak-task wrapper command. The gate reads only
`implementation_metadata.probe_axis_coverage.smoke_contract_axis_count` from
`result.json`; it does not inspect stdout, stderr, holdout failures, or official
hidden-test details.

Generated Python candidates also record aggregate-only runtime-smoke execution
coverage under `implementation_metadata.runtime_smoke`. That payload reports
case counts and input dimensions actually executed during implementation smoke
(`args`, `stdin`, `input_files`, `env_vars`, `default`) without storing argv
values, file contents, stdout, stderr, holdout failures, or official hidden-test
details. Use it to audit whether implementation smoke exercised the intended
input modes before spending rerun budget; keep `probe_axis_coverage` as the
official-eval gate until runtime-smoke coverage has enough historical evidence.
Candidate ranking can optionally require these execution dimensions before a
row is considered official-eligible:

```bash
python scripts/rank_programbench_candidates.py \
  --official-eligible-only \
  --latest-per-task \
  --min-smoke-contract-axes 1 \
  --require-runtime-smoke-dimensions args,input_files \
  --require-holdout-improvement \
  --min-holdout-improvement-delta 0.02
```

The runtime-smoke dimension gate is off by default. When enabled it requires
`runtime_smoke.status == "passed"` and the requested aggregate input dimensions
to be present; it still does not inspect raw inputs or hidden failures.

When using the breakthrough planner to prepare ready-baseline upgrade commands,
thread the same runtime-smoke requirement into the generated candidate-ranker
command so the dry-run queue reflects the final local gate:

```bash
python scripts/plan_official_breakthrough_targets.py \
  --include-next-command \
  --baseline-upgrade-min-smoke-contract-axes 1 \
  --baseline-upgrade-require-runtime-smoke-dimensions args,input_files \
  --baseline-upgrade-require-holdout-improvement \
  --baseline-upgrade-min-holdout-improvement-delta 0.02 \
  --include-restore-ablation-command \
  --include-missing-holdout-command \
  --limit 12 \
  --format json
```

This is planner-only. It emits aggregate next-command rows and does not run
official eval, Docker, or an external LLM.

The same aggregate gate can be enforced at packaging and closed-loop entrypoints:

```bash
python scripts/package_submission.py <instance_id> \
  --generated <generated_dir> \
  --result <result.json> \
  --require-runtime-smoke-dimensions args,input_files

python scripts/run_official_closed_loop.py <instance_id> \
  --require-runtime-smoke-dimensions args,input_files \
  --skip-official-eval \
  --ack-external-llm-docker
```

Guarded wrappers that build child closed-loop commands also forward
`--require-runtime-smoke-dimensions`, including strategy ablation, restore-axis
batch, weak-task rerun, weak-task batch, and missing-holdout rerun. Their default
mode remains dry-run unless the wrapper explicitly documents otherwise.

Before spending another local rerun on a weak task, compare latest-vs-best
aggregate holdout trends:

```bash
python scripts/summarize_holdout_trends.py --runs runs --limit 20 --min-holdout-cases 10
```

This reads only `result.json` aggregate fields. A regressed row means the next
cleanroom rerun should first beat the best reliable local holdout before any
official-eval discussion.
Add `--recommend-weak-reruns` to print aggregate-only rerun targets whose
historical best reliable holdout is still below the local gate. The recommendation
table includes the mandatory `--skip-official-eval --require-holdout-improvement`
flags for the next local rerun.
Add `--include-rerun-command --rerun-root runs/weak_task_cleanroom_next` when
you want each recommendation to include a guarded wrapper dry-run command.
Add `--rerun-min-smoke-contract-axes N` to include the same optional
smoke-axis gate in those generated commands.
Add `--rerun-min-holdout-improvement-delta N` when the generated command
should require a minimum positive margin over the previous reliable holdout
best.

Use `--format json` when automation needs the trend table and weak-task queue
without parsing markdown:

```bash
python scripts/summarize_holdout_trends.py \
  --runs runs \
  --limit 3 \
  --min-holdout-cases 10 \
  --recommend-weak-reruns \
  --include-rerun-command \
  --rerun-root runs/weak_task_cleanroom_next \
  --rerun-min-smoke-contract-axes 1 \
  --rerun-min-holdout-improvement-delta 0.02 \
  --format json
```

The JSON payload reports selected/total trend counts, latest/best aggregate
holdout rates and case counts, trend status, result paths, and an optional
`recommendations` block with required flags plus guarded dry-run commands. It
does not include holdout failure details, official hidden-test details, or raw
failure payloads.

For a single rerun, enforce that rule directly:

```bash
python scripts/audit_holdout_improvement.py runs/path/to/result.json --runs runs --min-holdout-cases 10
```

This exits non-zero unless the current aggregate holdout beats the previous
reliable best for the same task.
Use `--min-delta N` to require a positive margin larger than `N`, not just any
small floating-point improvement.

The closed-loop runner can enforce the same rule before packaging:

```bash
python scripts/run_official_closed_loop.py <instance_id> \
  --ack-external-llm-docker \
  --require-holdout-improvement \
  --min-holdout-improvement-delta 0.02 \
  --holdout-history-root runs \
  --skip-official-eval
```

For weak-task local reruns, prefer the guarded wrapper:

```bash
python scripts/run_weak_task_cleanroom_rerun.py <instance_id> \
  --runs runs/weak_task_cleanroom_next \
  --dry-run
```

The wrapper always adds `--skip-official-eval` and
`--require-holdout-improvement`, and it does not expose official eval run-name
or output-root options. It defaults to dry-run; add `--execute` only after
explicit authorization for external LLM and Docker use, and pair real execution
with `--ack-external-llm-docker` so the underlying closed-loop entrypoint also
receives the acknowledgement.

For a batch of weak-task recommendations, use the batch wrapper. It selects the
aggregate-only weak-task queue, defaults to dry-run, and prints child
`run_weak_task_cleanroom_rerun.py` commands:

```bash
python scripts/run_weak_task_cleanroom_rerun_batch.py \
  --runs runs \
  --output-root runs/weak_task_cleanroom_next \
  --limit 3 \
  --min-smoke-contract-axes 1 \
  --min-holdout-improvement-delta 0.02 \
  --format json
```

`--format json` is limited to dry-run command plans. Real execution requires
`--execute --ack-external-llm-docker`; the child commands keep official eval
disabled through the single-task wrapper.

For tasks with a recorded official aggregate baseline but no reliable local
holdout trend, first build fresh local signal through the missing-holdout
wrapper:

```bash
python scripts/run_missing_holdout_cleanroom_rerun.py <instance_id> \
  --runs runs/missing_holdout_cleanroom_next/<instance_id> \
  --min-smoke-contract-axes 1 \
  --dry-run
```

This wrapper always adds `--skip-official-eval` but intentionally does not add
`--require-holdout-improvement`, because there is no reliable previous local
holdout baseline to beat yet. It defaults to dry-run and requires
`--execute --ack-external-llm-docker` before any external LLM or Docker work.

The ablation runner can pass the same gates through to every variant. Use
`--dry-run` first when preparing restore-axis experiments; it prints the child
closed-loop commands without invoking the external LLM, Docker, packaging, or
official eval:

```bash
python scripts/run_official_strategy_ablation.py <instance_id> \
  --runs runs/restore_axis_ablation/<slug> \
  --variants baseline_no_adaptive adaptive_profile adaptive_deep \
  --require-holdout-improvement \
  --holdout-history-root runs \
  --max-generalization-risk low \
  --min-smoke-contract-axes 1 \
  --skip-official-eval \
  --dry-run
```

For fair pairwise ablations, the ablation runner automatically passes the
parent `--runs` directory as `--holdout-history-exclude-root` to each child
closed-loop command. That lets the improvement gate compare against historical
aggregate runs without letting earlier variants from the same in-flight ablation
become the "previous best". If you call `run_official_closed_loop.py` directly,
pass `--holdout-history-exclude-root <current-experiment-root>` yourself. Omit
`--dry-run` only after explicit authorization for external LLM and Docker use,
and add `--ack-external-llm-docker` for the real run.

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
