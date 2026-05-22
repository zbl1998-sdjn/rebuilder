# ReBuilder Public Release Material Notes

This file collects publishable source material from ReBuilder development work.
It intentionally avoids hidden ProgramBench failure details, raw prompts, API
keys, and non-aggregate official eval evidence.

## 2026-05-22 Elfcat Patch4 Official Aggregate Upgrade

### Publishable Summary

This pass continued the no-external-LLM official-standard route inside
ReBuilder's `file_bridge` architecture for `rbakbashev__elfcat.52f8cc7`.
No Kimi, GLM, local OpenAI endpoint, or external LLM API was used for candidate
generation or evaluation handoff. The candidate stayed inside the local
ReBuilder harness and was then packaged for the official ProgramBench evaluator.

The first follow-up, `reference_html_patch3`, remained strong locally but did
not produce an official aggregate. Local ReBuilder evidence was exploration
`119/119`, holdout `17/18`, with runtime smoke covering
`args/default/input_files/stdin`. ProgramBench official eval timed out after
`3600` seconds without writing an eval JSON, so it is recorded only as an
official-eval operational failure.

`reference_html_patch4` addressed the operational risk by bounding the HTML
bytes panel for large files. For files larger than the configured limit, the
renderer keeps the header byte spans but does not emit a full-file highlighted
byte panel. This is a public performance/generalization hardening change; it
does not rely on hidden official failure details.

The patch4 official ProgramBench aggregate completed. Counted result was
`371/564`, score `66`; raw result was `445/646`, score `69`. This upgrades the
recorded `elfcat` official aggregate baseline from score `56` to score `66`.
It is still not a solved task and should not be described as fully resolved.

### Evidence

- Local no-external result:
  `runs\file_bridge_no_external_elfcat_20260522_reference_html_patch4\rbakbashev__elfcat.52f8cc7\generated\rbakbashev__elfcat.52f8cc7\rbakbashev__elfcat.52f8cc7\result.json`
  with exploration `119/119`, holdout `17/18`, and provider `file_bridge`.
- Official aggregate eval JSON:
  `runs\programbench_official_eval\submission_elfcat_reference_html_patch4_20260522\rbakbashev__elfcat.52f8cc7\rbakbashev__elfcat.52f8cc7.eval.json`.
- Baseline record:
  `baselines\programbench\rbakbashev__elfcat.52f8cc7.baseline.json`
  now records model `codex-file-bridge-elfcat-reference_html_patch4`, counted
  `371/564`, score `66`, raw `445/646`, score `69`, and submission SHA-256
  `1ed17b9d3c85b4b987a0f92be921e63cf42a169fa756f8a92eb91d9d1b35dbf9`.
- Patch3 failure report:
  `runs\programbench_official_eval\submission_elfcat_reference_html_patch3_20260521\official_eval_failure_report.json`
  records an official eval attempt without an aggregate eval JSON.
- Strict official-ready ranking after the patch4 baseline update still
  returned `row_count=0`; the same candidate is now blocked by
  `official_not_above_baseline`, meaning it equals the current recorded
  baseline.

### Verification

- `.\.venv\Scripts\python.exe -m py_compile output\file_bridge_manual\run_elfcat_file_bridge.py tests\test_elfcat_file_bridge_harness.py`
  passed.
- `python -m ruff check --no-cache output\file_bridge_manual\run_elfcat_file_bridge.py tests\test_elfcat_file_bridge_harness.py`
  passed.
- Elevated focused pytest:
  `.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp C:\tmp\rebuilder_elfcat_patch4_pytest_20260522 tests\test_elfcat_file_bridge_harness.py`
  -> `12 passed`.
- Local runner:
  `.\.venv\Scripts\python.exe output\file_bridge_manual\run_elfcat_file_bridge.py reference_html_patch4 --force --pull`
  reached exploration `119/119`, holdout `17/18`, and runtime smoke
  `args/default/input_files/stdin`.
- Official runner:
  `.\.venv\Scripts\python.exe output\file_bridge_manual\run_elfcat_file_bridge.py reference_html_patch4 --official-eval --force --pull`
  produced the counted `371/564`, score `66` official aggregate.

### Safe External Narrative

Useful public phrasing:

> We kept the `elfcat` follow-up on ReBuilder's no-external `file_bridge`
> route, bounded a large-file HTML rendering path, and completed a new
> ProgramBench official aggregate eval. The counted baseline improved from
> score 56 to score 66, while the task remains unsolved.

Avoid claiming:

- that `elfcat` is solved, fully resolved, or almost resolved;
- that hidden official failure details were used for the repair;
- that patch3 produced an official score;
- that local exploration/holdout results are equivalent to official aggregate
  evidence.

## 2026-05-22 Xsv Local-Generalization Gate Stop

### Publishable Summary

This pass continued the no-external-LLM route inside ReBuilder's `file_bridge`
architecture. No Kimi, GLM, local OpenAI endpoint, or external LLM API was used
for candidate generation. The work focused on an `xsv` local-generalization gap
that the planner/ranker now surfaces as `local_holdout_gap_too_high`.

The operational path was repaired first. Docker Desktop was not running on the
machine, so the local cleanroom loop initially failed before candidate
execution because `npipe:////./pipe/dockerDesktopLinuxEngine` did not exist.
After starting `com.docker.service` and Docker Desktop, the ReBuilder
`file_bridge` loop could pull/use the cleanroom image and run locally.

Two `xsv frequency` follow-up experiments were tried from public local
exploration evidence only. `restore_patch5` made equal-count frequency ties use
value-lexical order, and `restore_patch6` tried to split stdin and file-input
tie behavior. Repeated local runs showed the public signal is unstable: one
visible frequency case favored lexical order, another favored first-seen order,
and a later rerun of `restore_patch5` did not preserve the apparent improvement.
The final retained evidence is therefore a gate stop, not a breakthrough.

No ProgramBench official aggregate evaluation was run for these xsv follow-ups.
The latest local `restore_patch5` run remained at exploration `100/102`,
holdout `12/15`, runtime-smoke dimensions `args/input_files/stdin`, and
`risk_reason=local_holdout_gap_too_high`. Strict official-ready ranking with
`--max-local-holdout-gap 0.15` still returned `row_count=0`.

### Evidence

- Latest local result:
  `runs\file_bridge_no_external_xsv_20260522_restore_patch5\burntsushi__xsv.f430466\generated\burntsushi__xsv.f430466\burntsushi__xsv.f430466\result.json`
  with exploration `100/102`, holdout `12/15`, and provider `file_bridge`.
- Latest local failure report:
  `runs\file_bridge_no_external_xsv_20260522_restore_patch5\burntsushi__xsv.f430466\reports\burntsushi__xsv.f430466.exploration.failures.json`.
- Generalization audit:
  `risk_level=high`, `risk_reason=local_holdout_gap_too_high`,
  `block_official_eval=true`, latest local holdout gap about `0.1804`.
- Strict official-ready ranker on the latest local run returned `row_count=0`.

### Verification

- `.\.venv\Scripts\python.exe -m pytest tests\test_xsv_file_bridge_harness.py -q -p no:cacheprovider --basetemp C:\tmp\rebuilder_xsv_tests_reverted`
  -> `8 passed`.
- `.\.venv\Scripts\python.exe -m py_compile output\file_bridge_manual\run_xsv_file_bridge.py tests\test_xsv_file_bridge_harness.py`
  passed during the patch5/patch6 experiments.
- `python -m ruff check --no-cache output\file_bridge_manual\run_xsv_file_bridge.py tests\test_xsv_file_bridge_harness.py`
  passed during the patch5/patch6 experiments.
- `.\.venv\Scripts\python.exe output\file_bridge_manual\run_xsv_file_bridge.py restore_patch5 --pull`
  completed the local no-external `file_bridge` loop after Docker Desktop was
  started.

### Safe External Narrative

Useful public phrasing:

> We continued the no-external ReBuilder `file_bridge` path for `xsv` and
> deliberately stopped before official aggregate evaluation. The local
> frequency-ordering signal was inconsistent across public exploration cases,
> and the holdout gap remained too high for the current official-ready gate.

Avoid claiming:

- that `xsv restore_patch5` or `restore_patch6` improved the official aggregate;
- that either candidate is solved or official-ready;
- that external LLMs were used;
- that the observed equal-count frequency ordering is a stable public contract.

## 2026-05-20 Subagent Official-Standard Loop Hardening

### Publishable Summary

ReBuilder's no-external-LLM testing path now has a stronger bridge between
subagent-produced adversarial tests and the framework's differential tester.
The `file_bridge` provider lets a local Codex subagent or human responder fill
ReBuilder LLM requests through local files, so the reconstruction loop can still
run inside the ReBuilder architecture without sending cleanroom context to an
external LLM API.

During a ProgramBench official-standard attempt, a real failure mode appeared:
subagent responses could include JSON-safe file fixtures such as
`{"__type__": "bytes", "base64": "..."}` in `input_files`. ReBuilder wrote
the same shape in evidence JSON, but the LLM output parser did not decode it
when reading generated adversarial test cases. Pydantic then rejected the whole
test case, and differential testing skipped the adversarial generation batch.

The fix in `core/llm_output.py` normalizes LLM-generated `input_files` before
constructing `TestCase` objects:

- decodes JSON-safe bytes payloads into real `bytes`;
- encodes plain string file contents as UTF-8 bytes;
- skips unmaterializable entries such as `{"__type__": "directory"}`;
- preserves the existing unsafe-path filtering in the executor layer.

This is a mechanism-level hardening fix. It improves the local cleanroom loop's
ability to test file-input behavior, but it is not an official ProgramBench
breakthrough by itself.

The official closed-loop runner also now supports an explicit
`--official-eval-timeout-seconds` guard for ProgramBench evaluation. The default
behavior is unchanged, but release/benchmark operators can opt into a bounded
official eval run and receive a clear timeout error when Docker or ProgramBench
does not finish. This addresses the previous "hang with no aggregate JSON"
failure mode without changing score interpretation.

A read-only subagent audit recommended `chmln__sd.87d1ba5` as the next
no-external-LLM `file_bridge` official-standard target because it is the current
strict eligible task with strong local gates and an existing
`config/smoke_file_bridge_subagent_chmln.yaml` path. The evidence boundary is
unchanged: the latest official aggregate remains score 86, not fully resolved,
so it is a suitable closed-loop benchmark target rather than a new breakthrough.

The 2026-05-20 follow-up run executed that target end to end through ReBuilder's
`file_bridge` architecture. A Codex subagent responded to 11 local bridge
requests, ReBuilder produced a candidate, package gating passed, and ProgramBench
official eval completed. The result was weaker than the existing baseline:
local exploration `43/49` (`87.8%`), holdout `12/14` (`85.7%`), official raw
`701/869` (score 81), official counted `651/810` (score 80), not fully
resolved. This is a valid official-standard no-external-LLM test run, but it is
not an official breakthrough.

That run also exposed a baseline-registry safety issue: the closed-loop runner
recorded the lower score-80 official result over the existing score-86 chmln
baseline. The score-86 baseline was restored, and `BaselineRecorder` now ranks
candidate official aggregates before overwriting an existing record. A lower
score cannot replace a stronger baseline; same-score candidates must improve
counted passed tests or pass rate to supersede the existing record.

The cleanroom preparation path now also exposes
`--docker-command-timeout-seconds`. The default remains 60 seconds, but
official-standard reruns can raise the bound for slow first-time image pulls
without bypassing the cleanroom image policy. Docker command timeouts are now
reported as explicit `RuntimeError("Command timed out...")` messages instead
of surfacing as low-level subprocess tracebacks.

The official-candidate ranking gate was also tightened after a dry-run planning
review showed that existing official/baseline tasks could be labeled
`eligible_baseline_upgrade` from local holdout/runtime-smoke evidence alone.
Closed-loop official eval now writes an aggregate-only `official_eval_summary`
back into the candidate `result.json`, and the ranking gate requires that
embedded official aggregate to beat the recorded baseline before an existing
official task can be treated as a baseline upgrade. Local gates can still rank
a target for audit, but they no longer count as evidence that an official
baseline is already improved.

A later no-external `file_bridge` subagent run targeted
`alecthomas__chroma.8d04def` under the same ReBuilder closed-loop architecture.
The local ReBuilder candidate reached aggregate holdout readiness
(`15/18`, `83.3%`) and covered runtime-smoke dimensions including args,
stdin, input files, and the default path. ProgramBench official eval was
started, but repeated Docker-side hangs initially prevented an aggregate eval
JSON from being written. A later long retry on the stronger `restore_patch2`
candidate did produce an aggregate official JSON, and the result was negative:
counted `0/515`, score 0; raw `0/531`, score 0. That is below the recorded
score-3 chroma baseline, so it is not an official breakthrough and must not be
described as a baseline upgrade.

The closed-loop runner now performs bounded cleanup after that failure mode:
when ProgramBench eval raises before writing the aggregate eval JSON, it stops
still-running `programbench-*` containers whose image matches the current
instance. This prevents timed-out official-standard attempts from leaving
orphaned Docker branches while preserving the original failure as the reported
error.

A follow-up audit used a read-only subagent to independently check the
`tomnomnom__gron.88a6234` no-external `file_bridge` candidate provenance before
running official ProgramBench evaluation. The subagent confirmed that the patch6
candidate came from the local bridge path, with local file request/response
evidence and no external LLM API key. Official ProgramBench aggregate evaluation
then completed successfully for that packaged candidate, but the result was
equal to the existing baseline rather than an upgrade: official counted
`140/224` (score 62), raw `148/233` (score 64), not fully resolved.

That result exposed a second planning issue: the planner's JSON
`baseline_upgrade_gate` was re-reading candidate rows without the recorded
baseline official ranks, so an equal official score could still appear eligible
as a baseline upgrade. `plan_official_breakthrough_targets.py` now passes the
same baseline rank context into the candidate gate that
`rank_programbench_candidates.py` uses. Equal or lower official summaries are
classified as `official_not_above_baseline`.

The same baseline-rank context now also flows through the single-candidate
`audit_official_eval_gate.py` path. This was fixed after the `chroma`
score-0 result showed that the strict ranking gate correctly returned no rows
while the one-off audit still reported `eligible_baseline_upgrade`. The audit
now reports `official_not_above_baseline` for that real candidate. Focused
gate tests passed as `98 passed` when run outside the restrictive shell
sandbox; inside the sandbox, pytest temporary directory creation was blocked by
Windows `WinError 5`, which is an environment constraint rather than a gate
logic failure.

Existing aggregate-only official summaries were also backfilled into candidate
`result.json` files where the official eval JSON already existed. The backfill
keeps the planner honest for previously evaluated no-external or candidate runs:
`gron` remains equal to baseline, `nnn` remains equal to its score-79 baseline
and still lacks runtime-smoke/input-file evidence, `htmlq` remains one counted
pass below the recorded score-91 baseline, `chmln` remains below the score-86
baseline, and the no-external `cmatrix` file-bridge candidate remains below the
later score-95 baseline. After these backfills, the strict official-ready
ranking gate still returns no rows.

A later no-external `file_bridge` run targeted
`psampaz__go-mod-outdated.bb79367` table rendering. A local subagent prepared
the first `table_patch4` bridge response, then the main loop added a narrow
differential-tester normalization for Go log timestamp drift. The final
ReBuilder run used four local bridge responses, no external LLM, and reached
local exploration `23/23` plus holdout `7/7`; runtime smoke passed across
args, stdin, input files, and default execution. ProgramBench official eval then
completed with counted `229/285`, score 80; raw `277/342`, score 81; not fully
resolved. This is a real aggregate baseline upgrade over the previously
recorded go-mod score-15 baseline, but it is not a solved task.

The go-mod repair was intentionally mechanism-scoped. The generated candidate
handles `-` as stdin, pretty and concatenated Go module JSON, invalid/binary
JSON stderr, fixed-width ASCII header centering, and Markdown table output. The
framework fix in `core/differential_tester.py` only tolerates tiny Go log
timestamp differences when the log message body is identical and timestamps are
within two seconds; it does not ignore arbitrary stderr differences.

A follow-up no-external `file_bridge` run targeted
`agourlay__zip-password-finder.704700d` from the restore/ablation queue. The
candidate restored the historical local artifact and applied a narrow,
mechanism-level CLI usage repair for missing required `--inputFile` diagnostics.
The ReBuilder local gate passed with exploration `92/98` (`93.9%`), holdout
`13/16` (`81.2%`), and runtime smoke across args, stdin, input files, and
default execution. ProgramBench official eval then completed, but the official
aggregate remained equal to the recorded baseline: counted `248/680`, score 36;
raw `340/792`, score 43; not fully resolved. This is not a breakthrough. It is
useful negative evidence showing that a stronger local gate can still fail to
improve official aggregate rank.

A same-axis no-external `file_bridge` restore attempt then targeted
`wfxr__csview.8ac4de0`, starting from the strongest historical local artifact.
The bridge restored the prior implementation and applied narrow CLI parsing,
stdin, quote-handling, table-rendering, Unicode-width, and clap-style diagnostic
repairs. The final local variant, `restore_patch8`, reached exploration `49/49`,
but holdout remained `8/14`, and runtime smoke covered args, stdin, and default
execution but not input files. Because it failed the configured
holdout/runtime-smoke entry gate, ProgramBench official eval was correctly
skipped. This should be published as local negative evidence for the restore
path: exact exploration repair did not generalize to the held-out split.

## 2026-05-21 Elfcat Reference HTML Patch2 Official-Standard Attempt

### Publishable Summary

A no-external `file_bridge` run targeted `rbakbashev__elfcat.52f8cc7` through
the ReBuilder closed-loop architecture. The loop used local file-bridge
responses only; no Kimi/GLM/external LLM API was used. A read-only subagent
audit first identified the remaining local failure clusters as HTML output
compatibility issues around ELF section/program table rendering, Rust-style
panic shapes, directory/path diagnostics, and exact byte-dump line endings.

The final `reference_html_patch2` candidate repaired the local visible
official-standard set without copying or calling the reference executable:

- mapped GNU/Linux OSABI and ABI-version rows to the reference HTML shape;
- preserved Linux-style path diagnostics for backslash paths and directories;
- matched reference Rust panic locations for out-of-range section-string-table
  and exact-boundary section-header failures;
- rendered ELF64 section header byte spans, section info tables, and arrow
  connections;
- rendered ELF64 program header byte spans, segment info tables, and arrow
  connections;
- matched the reference newline rule for exact 16-byte tail rows after a
  structured ELF header;
- cached parsed section header records when building info tables to avoid an
  avoidable O(n^2) hidden-eval performance risk.

Local ReBuilder verification now reports `119/119` behavioral equivalence
(`100.0%`) on the visible official-standard sample set, with holdout `17/18`
(`94.4%`), runtime smoke passed across args, stdin, input files, and default
execution, static assets disabled, and `5` file-bridge harness calls. The
submission package was generated at
`runs\file_bridge_no_external_elfcat_20260521_reference_html_patch2_submission\file_bridge_no_external_elfcat_20260521_reference_html_patch2_eval\rbakbashev__elfcat.52f8cc7\submission.tar.gz`.

This is **not** an official aggregate breakthrough yet. ProgramBench official
eval was attempted twice for
`runs\programbench_official_eval\submission_elfcat_reference_html_patch2_20260521`,
and both attempts timed out after `1200` seconds before writing
`rbakbashev__elfcat.52f8cc7.eval.json`. The latest failure report is
`runs\programbench_official_eval\submission_elfcat_reference_html_patch2_20260521\official_eval_failure_report.json`
with reason `official_eval_failed_without_eval_json`. The wrapper stopped the
timed-out eval container and removed the compiled image. Because no official
aggregate JSON exists for patch2, the recorded elfcat baseline remains the
previous aggregate baseline: counted `316/564`, score `56`; raw `390/646`,
score `60`; not fully resolved.

The main operational difficulties were environmental and evaluator-boundary
issues: sandboxed Docker access made the cleanroom image appear unavailable
until the command was rerun with Docker access; sandboxed pytest temporary
directory creation hit Windows `WinError 5`; Git reported `safe.directory`
ownership warnings; and ProgramBench official eval did not emit stdout/stderr
log files before timing out. These are recorded as release caveats, not as
candidate score evidence.

### Verification Evidence

- Elfcat focused harness:
  `.\.venv\Scripts\python.exe -m pytest tests\test_elfcat_file_bridge_harness.py -q`
  -> `11 passed`.
- Elfcat focused lint/syntax checks:
  `python -m ruff check --no-cache output\file_bridge_manual\run_elfcat_file_bridge.py tests\test_elfcat_file_bridge_harness.py`
  -> `All checks passed!`;
  `.\.venv\Scripts\python.exe -m py_compile output\file_bridge_manual\run_elfcat_file_bridge.py tests\test_elfcat_file_bridge_harness.py`
  -> passed.
- Elfcat no-external closed-loop local run:
  `.\.venv\Scripts\python.exe output\file_bridge_manual\run_elfcat_file_bridge.py reference_html_patch2 --force`
  -> status `SUCCESS`, behavioral equivalence `119/119`, holdout `17/18`,
  runtime smoke passed, packaged submission created.
- Elfcat official aggregate attempts:
  `.\.venv\Scripts\python.exe output\file_bridge_manual\run_elfcat_file_bridge.py reference_html_patch2 --official-eval --force`
  was run twice. Both attempts reached local `119/119`, packaged the official
  submission, started ProgramBench eval, and then timed out after `1200`
  seconds without `eval.json`. Latest failure report:
  `runs\programbench_official_eval\submission_elfcat_reference_html_patch2_20260521\official_eval_failure_report.json`.
- New focused regressions first failed, then passed:
  `.\.venv\Scripts\python.exe -m pytest tests\test_differential_tester_backends.py::test_differential_tester_parses_json_safe_bytes_input_files tests\test_differential_tester_backends.py::test_differential_tester_filters_unmaterializable_directory_input_files -q`
  -> `2 passed`.
- Full related differential tester slice:
  `.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests\test_differential_tester_backends.py -q`
  -> `11 passed`.

## 2026-05-21 Elfcat Reference HTML Patch3 Official Eval Error

### Publishable Summary

A follow-up no-external `file_bridge` run targeted
`rbakbashev__elfcat.52f8cc7` after the `reference_html_patch2` official eval
timeouts. The run stayed inside the ReBuilder architecture and used local
file-bridge responses only; no Kimi, GLM, or external LLM API was used.

The patch3 repair was deliberately narrow and performance-oriented:

- kept the patch2 HTML compatibility behavior unchanged;
- computed ELF64 program-header and section-header records once per render;
- passed the cached records into byte-span rendering, info-table rendering, and
  arrow-connection generation;
- added a distinct `reference_html_patch3` variant instead of overwriting the
  patch2 evidence trail;
- raised the patch3 official-eval wrapper limits to `3600` seconds for the
  ProgramBench eval and `300` seconds for Docker commands.

Focused verification passed before official eval: `py_compile` passed, `ruff`
passed, and the focused elfcat harness passed `11/11`. The local ReBuilder
closed-loop run again reached `119/119` behavioral equivalence, holdout `17/18`
(`94.4%`), runtime smoke across args, stdin, input files, and default, with
static assets disabled. The packaged official submission was:
`runs\programbench_official_eval\submission_elfcat_reference_html_patch3_20260521\rbakbashev__elfcat.52f8cc7\submission.tar.gz`.

This is **not** an official aggregate breakthrough. The official ProgramBench
eval started and ran the hidden pytest suite for about `47:51`, but the first
branch attempt ended as `results_read_failed`. The retry then failed to start a
fresh container because Docker Desktop's Linux engine pipe was unavailable:
`npipe:////./pipe/dockerDesktopLinuxEngine`. ProgramBench reported
`ERROR: RuntimeError` and emitted `raw=0/0 score=0`, `counted=0/0 score=0`.
No `.eval.json` was written under
`runs\programbench_official_eval\submission_elfcat_reference_html_patch3_20260521`.
An orphaned ProgramBench eval container remained high-CPU after the wrapper
process exited and was stopped manually.

The release boundary is therefore: patch3 is a local performance-risk repair
with strong visible/holdout evidence, but the official aggregate result is an
operational evaluator failure, not score evidence. The recorded elfcat baseline
remains the previous official aggregate baseline: counted `316/564`, score
`56`; raw `390/646`, score `60`; not fully resolved.

Follow-up framework repair: `scripts\run_official_closed_loop.py` now treats a
ProgramBench command that returns without writing the expected aggregate
`.eval.json` as an official-eval operational failure. The runner stops matching
`programbench-*` containers, removes matching compiled images where possible,
writes `official_eval_failure_report.json`, and raises a clear `RuntimeError`
instead of letting the pipeline summarize a missing file as `0/0`. The aggregate
summarizer also now refuses a missing eval JSON directly.

### Difficulties Recorded

- The official hidden pytest run consumed about `47:51` before the first branch
  ended as `results_read_failed`; this was not an idle shell stall.
- Docker Desktop's Linux engine pipe disappeared before the retry container
  could start, so the ProgramBench wrapper reported `ERROR: RuntimeError`
  without a usable aggregate eval JSON.
- The old runner only wrote a failure report on raised subprocess errors. This
  run exposed the additional failure mode where the ProgramBench command can
  return but still not produce the aggregate eval JSON.
- Ordinary sandboxed pytest again hit Windows `C:\tmp` basetemp ACL
  `WinError 5`; the focused regression suite was rerun with elevated access.

### Verification Evidence

- Syntax:
  `.\.venv\Scripts\python.exe -m py_compile output\file_bridge_manual\run_elfcat_file_bridge.py tests\test_elfcat_file_bridge_harness.py`
  -> passed.
- Lint:
  `python -m ruff check --no-cache output\file_bridge_manual\run_elfcat_file_bridge.py tests\test_elfcat_file_bridge_harness.py`
  -> `All checks passed!`.
- Focused harness:
  `.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp C:\tmp\rebuilder_elfcat_patch3_pytest_20260521 tests\test_elfcat_file_bridge_harness.py`
  -> `11 passed`.
- No-external local closed-loop:
  `.\.venv\Scripts\python.exe output\file_bridge_manual\run_elfcat_file_bridge.py reference_html_patch3 --force`
  -> status `SUCCESS`, behavioral equivalence `119/119`, holdout `17/18`.
- Generalization risk audit:
  `.\.venv\Scripts\python.exe scripts\audit_generalization_risk.py --task rbakbashev__elfcat.52f8cc7 --runs runs --baseline-root baselines\programbench --official-eval-root runs\programbench_official_eval --format json`
  -> `risk_level=low`, `block_official_eval=false`.
- Official eval attempt:
  `.\.venv\Scripts\python.exe output\file_bridge_manual\run_elfcat_file_bridge.py reference_html_patch3 --official-eval --force`
  -> ProgramBench summary `ERROR: RuntimeError`, `raw=0/0 score=0`,
  `counted=0/0 score=0`; logs:
  `runs\programbench_official_eval\elfcat_patch3_official_20260521.out.log`
  and
  `runs\programbench_official_eval\elfcat_patch3_official_20260521.err.log`.
- Missing-eval-json runner regression:
  `.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp C:\tmp\rebuilder_run_official_pytest_20260521 tests\test_run_official_closed_loop.py::test_run_programbench_eval_cleans_matching_containers_after_success_without_eval_json tests\test_run_official_closed_loop.py::test_run_programbench_eval_cleans_matching_containers_after_failed_eval_without_json tests\test_run_official_closed_loop.py::test_run_programbench_eval_continues_when_eval_json_exists tests\test_run_official_closed_loop.py::test_run_programbench_eval_passes_configured_timeout`
  -> `4 passed`.
- Runner syntax/lint:
  `.\.venv\Scripts\python.exe -m py_compile scripts\run_official_closed_loop.py tests\test_run_official_closed_loop.py`
  -> passed;
  `python -m ruff check --no-cache scripts\run_official_closed_loop.py tests\test_run_official_closed_loop.py`
  -> `All checks passed!`.

## 2026-05-21 Official Failure Attribution Repair

### Publishable Summary

After the patch3 official-eval failure, the planner still had one evidence
attribution problem: a latest candidate could inherit an older
`official_eval_failure_report.json` from the shared official-eval root when the
task id matched. In practice, `elfcat reference_html_patch3` was being linked to
the `reference_html_patch2` failure report even though patch3's own failed eval
had not produced that machine report.

The fix keeps failure evidence candidate-scoped. `rank_programbench_candidates.py`
now only accepts a failure report when it lives under the candidate's own
submission root, or when the report's aggregate metadata points back inside that
same submission root. Shared official-eval reports for the same task no longer
attach to newer candidates by task id alone.

The same pass also fixed a second misclassification. A failed ProgramBench eval
can leave an embedded aggregate summary shaped like `0/0` with
`error_code=invalid_eval_payload`. That is operational failure evidence, not an
official score of zero. The ranker now treats invalid embedded official
summaries as `official_eval_failed_without_eval_json`, so the planner routes the
candidate to `official_eval_operational_failure` instead of
`official_generalization_gap`.

Current aggregate queue after the repair is:

- strict official-ready ranker remains empty: `row_count=0`;
- `chroma patch3` is still the top operational official-eval failure, with its
  own adjacent failure report;
- `zip patch3` and `xsv patch4` remain local-generalization gaps due to high
  local-vs-holdout gap;
- `elfcat patch3` is now correctly classified as operational official-eval
  failure from its own invalid/missing-eval-json evidence, with no stale
  patch2 failure-report path.

This is a release-quality evidence-boundary repair. It does not create a new
official ProgramBench breakthrough, and it does not change any official score.

### Difficulties Recorded

- Real official-eval evidence can be split between `result.json` and
  `official_eval_failure_report.json`; both paths must be interpreted without
  reading hidden failure details.
- Task-id-only matching is too coarse once multiple candidate submissions exist
  for the same ProgramBench instance.
- ProgramBench's `raw=0/0` / `counted=0/0` output after evaluator failure is not
  a usable aggregate score and must stay separate from true official summaries.
- Sandboxed pytest still cannot create the configured user temp directory on
  this Windows host (`WinError 5`), so focused pytest was rerun with elevated
  access. That is an environment constraint, not a test failure.

### Verification Evidence

- Syntax:
  `.\.venv\Scripts\python.exe -m py_compile scripts\rank_programbench_candidates.py`
  -> passed.
- Lint:
  `python -m ruff check --no-cache scripts\rank_programbench_candidates.py tests\test_rank_programbench_candidates.py`
  -> `All checks passed!`.
- Focused ranker tests:
  `.\.venv\Scripts\python.exe -m pytest tests\test_rank_programbench_candidates.py -q`
  -> `70 passed`.
- Focused planner tests:
  `.\.venv\Scripts\python.exe -m pytest tests\test_plan_official_breakthrough_targets.py -q`
  -> `16 passed`.
- Current strict ranker:
  `.\.venv\Scripts\python.exe scripts\rank_programbench_candidates.py --runs runs --official-eval-root runs\programbench_official_eval --baseline-root baselines\programbench --official-eligible-only --allow-existing-official --latest-per-task --require-runtime-smoke-dimensions args,input_files,stdin --max-local-holdout-gap 0.15 --format json --limit 20`
  -> `row_count=0`, `total_row_count=0`.
- Current planner:
  `.\.venv\Scripts\python.exe scripts\plan_official_breakthrough_targets.py --runs runs --official-eval-root runs\programbench_official_eval --baseline-root baselines\programbench --baseline-upgrade-require-runtime-smoke-dimensions args,input_files,stdin --baseline-upgrade-max-local-holdout-gap 0.15 --restore-ablation-require-runtime-smoke-dimensions args,input_files,stdin --restore-ablation-max-local-holdout-gap 0.15 --format json --limit 12`
  -> `elfcat patch3` classified as `official_eval_operational_failure` with
  `official_eval_failure_report_path=null`, confirming the stale patch2 report
  is no longer attached.

## 2026-05-21 Xsv Restore Patch2 Local Gate Follow-Up

### Publishable Summary

A no-external `file_bridge` follow-up targeted `burntsushi__xsv.f430466`
inside the ReBuilder closed-loop architecture. The run used local bridge
responses only; no Kimi, GLM, or external LLM API was used. A read-only
subagent audit independently concluded that no official-ready candidate existed
yet, and that `xsv restore_patch2` was the best next local mechanism-repair
target before any further official ProgramBench evaluation.

The repair improved the visible local official-standard behavior without
claiming hidden-eval knowledge:

- restored observed full subcommand help text from local reference evidence for
  the covered `xsv <subcommand> --help` surface;
- matched missing-argument usage diagnostics for `xsv partition` and
  `xsv sample`;
- kept `frequency` tie ordering on a deterministic count-then-lexical fallback
  after local reference evidence showed equal-count order can vary across runs;
- changed `stats --everything` float sum/mean calculation to explicit
  left-to-right streaming accumulation, matching the previously failing
  `84.80000000000001` display without hard-coding that value.

Focused verification passed:

- `.\.venv\Scripts\python.exe -m py_compile output\file_bridge_manual\run_xsv_file_bridge.py tests\test_xsv_file_bridge_harness.py`
  -> passed.
- `python -m ruff check --no-cache output\file_bridge_manual\run_xsv_file_bridge.py tests\test_xsv_file_bridge_harness.py`
  -> `All checks passed!`.
- `.\.venv\Scripts\python.exe -m pytest tests\test_xsv_file_bridge_harness.py -q`
  required elevated execution because normal pytest temp-directory creation hit
  Windows `WinError 5`; with the same focused test slice elevated, it reported
  `6 passed`.

The final no-external ReBuilder local closed-loop run reported exploration
`99/102` (`97.1%`), holdout `12/15` (`80.0%`), `almost_resolved=true`,
runtime smoke passed across args, stdin, input files, and default execution,
and packaged a submission at
`runs\file_bridge_no_external_xsv_20260521_restore_patch2_submission\file_bridge_no_external_xsv_20260521_restore_patch2_eval\burntsushi__xsv.f430466\submission.tar.gz`.
The remaining exact-output mismatch is now concentrated in `xsv frequency`
equal-count ordering: the same reference command has been observed with
different tie orders across local evidence records, so this pass intentionally
did not replace the implementation with a per-evidence lookup or randomized
ordering.

This is **not** an official aggregate breakthrough. The one-candidate official
gate returned `eligible=false` with reason
`missing_official_candidate_summary`, and the strict official-ready ranker still
returned `row_count=0`. ProgramBench official eval was therefore not run for
this candidate in this pass. The recorded xsv official baseline remains the
existing score-44 aggregate until a future candidate produces aggregate
official evidence that beats it.

### Difficulties Recorded

- Equal-count `xsv frequency` output is not a reliable exact-output repair
  target by itself: the same stdin has local reference records with multiple
  tie orders, so treating any one order as a general rule would overfit.
- The prior visible `stats --everything` floating-point gap is fixed by
  streaming float accumulation, but this does not change the official-eval
  boundary because the candidate still lacks an aggregate official summary.
- The official-ready gate correctly blocked escalation because the candidate
  has no embedded aggregate official summary; local `99/102` and holdout
  `80.0%` are not sufficient to claim an official breakthrough.
- Normal sandboxed pytest remains affected by the local Windows temp-directory
  ACL issue (`C:\Users\Administrator\.codex-tmp\pytest-of-Administrator`),
  so focused pytest evidence must distinguish ACL failure from code failure.
- Static/lint checks:
  `python -m ruff check core\llm_output.py tests\test_differential_tester_backends.py`
  -> `All checks passed!`.
- Syntax check:
  `python -m py_compile core\llm_output.py tests\test_differential_tester_backends.py`
  -> passed.
- Official eval timeout focused tests:
  `.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests\test_run_official_closed_loop.py::test_run_command_passes_timeout_when_requested tests\test_run_official_closed_loop.py::test_run_command_reports_timeout tests\test_run_official_closed_loop.py::test_run_programbench_eval_passes_configured_timeout tests\test_run_official_closed_loop.py::test_parse_args_rejects_negative_official_gate_thresholds -q`
  -> `11 passed`.
- Official eval timeout lint/syntax checks:
  `python -m ruff check scripts\run_official_closed_loop.py tests\test_run_official_closed_loop.py`
  -> `All checks passed!`;
  `.\.venv\Scripts\python.exe -m py_compile scripts\run_official_closed_loop.py tests\test_run_official_closed_loop.py`
  -> passed.
- Baseline anti-regression focused tests:
  `.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests\test_baseline_registry.py::test_baseline_recorder_ranks_lower_official_candidate_below_existing tests\test_baseline_registry.py::test_baseline_recorder_ranks_same_score_more_passed_tests_as_upgrade -q`
  -> `2 passed`.
- Baseline anti-regression lint/syntax checks:
  `python -m ruff check core\experiments\baseline.py tests\test_baseline_registry.py`
  -> `All checks passed!`;
  `.\.venv\Scripts\python.exe -m py_compile core\experiments\baseline.py tests\test_baseline_registry.py`
  -> passed.
- Docker cleanroom preparation timeout focused tests:
  `.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests\test_programbench_adapter.py::test_subprocess_docker_client_reports_docker_command_timeout tests\test_programbench_adapter.py::test_subprocess_docker_client_reports_inspect_timeout tests\test_programbench_catalog.py::test_prepare_programbench_task_parse_args_accepts_docker_timeout tests\test_programbench_catalog.py::test_prepare_programbench_task_parse_args_rejects_invalid_docker_timeout tests\test_run_official_closed_loop.py::test_build_prepare_command_passes_docker_command_timeout tests\test_run_official_closed_loop.py::test_parse_args_rejects_negative_official_gate_thresholds -q`
  -> `18 passed`.
- Docker cleanroom preparation timeout lint check:
  `python -m ruff check core\programbench\adapter.py scripts\prepare_programbench_task.py scripts\run_official_closed_loop.py tests\test_programbench_adapter.py tests\test_programbench_catalog.py tests\test_run_official_closed_loop.py`
  -> `All checks passed!`.
- Official baseline-upgrade ranking gate checks:
  `python -m ruff check scripts\rank_programbench_candidates.py tests\test_rank_programbench_candidates.py scripts\run_official_closed_loop.py tests\test_run_official_closed_loop.py`
  -> `All checks passed!`;
  `.\.venv\Scripts\python.exe -m py_compile scripts\rank_programbench_candidates.py tests\test_rank_programbench_candidates.py scripts\run_official_closed_loop.py tests\test_run_official_closed_loop.py`
  -> passed;
  a manual fixture validation under `runs\manual_validation_rank_gate_*`
  covered missing embedded official summary, above-baseline official summary,
  below-baseline official summary, and writing counted/raw official aggregates
  back into `result.json`.
- Real ranking gate smoke after the fix:
  `.\.venv\Scripts\python.exe scripts\rank_programbench_candidates.py --runs runs --official-eval-root runs\programbench_official_eval --baseline-root baselines\programbench --official-eligible-only --allow-existing-official --latest-per-task --require-runtime-smoke-dimensions args,input_files --format json --limit 30`
  -> `row_count=0`, `total_row_count=0`.
- Real planner dry-run after the fix:
  `.\.venv\Scripts\python.exe scripts\plan_official_breakthrough_targets.py --runs runs --official-eval-root runs\programbench_official_eval --baseline-root baselines\programbench --baseline-upgrade-require-runtime-smoke-dimensions args,input_files --format json --limit 20`
  still lists high-value audit targets such as `alecthomas__chroma.8d04def`,
  but their `baseline_upgrade_gate.eligible` is `false` with blocker
  `missing_official_candidate_summary` until a successful official aggregate is
  embedded in the candidate result.
- ProgramBench eval cleanup focused tests:
  `.\.venv\Scripts\python.exe -m pytest tests\test_run_official_closed_loop.py::test_run_programbench_eval_cleans_matching_containers_after_failed_eval_without_json tests\test_run_official_closed_loop.py::test_cleanup_programbench_eval_containers_stops_only_matching_instance -q`
  -> `2 passed`.
- ProgramBench eval cleanup lint/syntax checks:
  `python -m ruff check scripts\run_official_closed_loop.py tests\test_run_official_closed_loop.py`
  -> `All checks passed!`;
  `.\.venv\Scripts\python.exe -m py_compile scripts\run_official_closed_loop.py tests\test_run_official_closed_loop.py`
  -> passed.
- Docker residual-state check after manually stopping the stuck eval branches:
  `docker ps --format "{{.ID}}\t{{.Image}}\t{{.Names}}\t{{.Status}}"`
  -> no running `programbench-*` containers.
- Official follow-up eval artifact:
  `runs\programbench_official_eval\submission_chmln_sd_87d1ba5_subagent_20260520_afterpull\chmln__sd.87d1ba5\chmln__sd.87d1ba5.eval.json`
  -> counted `651/810`, score 80; raw `701/869`, score 81.
- Official `gron` patch6 follow-up eval:
  `runs\file_bridge_no_external_gron_20260517_patch6_submission\file_bridge_no_external_gron_20260517_patch6_eval\tomnomnom__gron.88a6234\tomnomnom__gron.88a6234.eval.json`
  -> counted `140/224`, score 62; raw `148/233`, score 64. This matched the
  recorded baseline score and was not a breakthrough.
- Official `go-mod-outdated` table_patch4 follow-up eval:
  `runs\programbench_official_eval\submission_go_mod_outdated_table_patch4_20260520\psampaz__go-mod-outdated.bb79367\psampaz__go-mod-outdated.bb79367.eval.json`
  -> counted `229/285`, score 80; raw `277/342`, score 81. This upgraded the
  recorded go-mod aggregate baseline from score 15, but remained not fully
  resolved.
- `zip-password-finder` no-external `file_bridge` local gate:
  `runs\file_bridge_no_external_zip_20260520_usage_patch1\agourlay__zip-password-finder.704700d\generated\agourlay__zip-password-finder.704700d\agourlay__zip-password-finder.704700d\result.json`
  -> exploration `92/98`, holdout `13/16`, runtime smoke passed with args,
  stdin, input files, and default dimensions.
- Official `zip-password-finder` usage_patch1 follow-up eval:
  `runs\programbench_official_eval\submission_zip_password_finder_usage_patch1_20260520\agourlay__zip-password-finder.704700d\agourlay__zip-password-finder.704700d.eval.json`
  -> counted `248/680`, score 36; raw `340/792`, score 43. This matched the
  recorded score-36 baseline and was not a breakthrough.
- `xsv` no-external `file_bridge` restore_patch1 local gate:
  `runs\file_bridge_no_external_xsv_20260520_restore_patch1\burntsushi__xsv.f430466\generated\burntsushi__xsv.f430466\burntsushi__xsv.f430466\result.json`
  -> holdout `12/15` (`80.0%`), runtime smoke passed with args, stdin,
  input-files, and default dimensions; packaging was allowed.
- Official `xsv` restore_patch1 follow-up eval:
  `runs\programbench_official_eval\submission_xsv_restore_patch1_20260520\burntsushi__xsv.f430466\burntsushi__xsv.f430466.eval.json`
  -> counted `527/1186`, score 44; raw `604/1317`, score 46. This improved
  counted passed tests over the older score-44 record but did not improve the
  rounded official score, so it is an aggregate refinement, not a score
  breakthrough.
- Official `chroma` restore_patch2 long follow-up eval:
  `runs\programbench_official_eval\submission_chroma_restore_patch2_long_20260520\alecthomas__chroma.8d04def\alecthomas__chroma.8d04def.eval.json`
  -> counted `0/515`, score 0; raw `0/531`, score 0. This is lower than the
  historical score-3 chroma baseline, so it is negative official aggregate
  evidence and not a baseline upgrade.
- `csview` no-external `file_bridge` restore_patch4 local gate:
  `runs\file_bridge_no_external_csview_20260520_restore_patch4\wfxr__csview.8ac4de0\generated\wfxr__csview.8ac4de0\wfxr__csview.8ac4de0\result.json`
  -> exploration `43/49`, holdout `8/14`; runtime smoke passed but only covered
  args, stdin, and default execution. The required input-files dimension was
  missing, so official eval was skipped.
- `csview` no-external `file_bridge` restore_patch8 recheck:
  `runs\file_bridge_no_external_csview_20260520_restore_patch8\wfxr__csview.8ac4de0\generated\wfxr__csview.8ac4de0\wfxr__csview.8ac4de0\result.json`
  -> exploration `49/49`, holdout `8/14`; runtime smoke still covered only
  args, stdin, and default execution, so the required input-files dimension was
  still missing. Official eval was skipped again.
- Go log timestamp normalization regressions:
  `.\.venv\Scripts\python.exe -m pytest tests\test_differential_tester_backends.py -q`
  -> `13 passed` with the existing `.pytest_cache` ACL warning.
- Planner equal-official-summary regression:
  `.\.venv\Scripts\python.exe -m pytest tests\test_plan_official_breakthrough_targets.py::test_json_ready_rows_block_equal_official_summary_as_not_above_baseline -q`
  -> `1 passed`.
- Planner/ranking static and syntax checks:
  `python -m ruff check scripts\plan_official_breakthrough_targets.py tests\test_plan_official_breakthrough_targets.py scripts\rank_programbench_candidates.py tests\test_rank_programbench_candidates.py`
  -> `All checks passed!`;
  `.\.venv\Scripts\python.exe -m py_compile scripts\plan_official_breakthrough_targets.py tests\test_plan_official_breakthrough_targets.py scripts\rank_programbench_candidates.py tests\test_rank_programbench_candidates.py`
  -> passed.
- Real strict ranking gate after the equal-score fix and summary backfills:
  `.\.venv\Scripts\python.exe scripts\rank_programbench_candidates.py --runs runs --official-eval-root runs\programbench_official_eval --baseline-root baselines\programbench --official-eligible-only --allow-existing-official --latest-per-task --require-runtime-smoke-dimensions args,input_files --format json --limit 30`
  -> `row_count=0`, `total_row_count=0`.
- Real strict ranking gate after the go-mod official eval and baseline update:
  `.\.venv\Scripts\python.exe scripts\rank_programbench_candidates.py --runs runs --official-eval-root runs\programbench_official_eval --baseline-root baselines\programbench --official-eligible-only --allow-existing-official --latest-per-task --require-runtime-smoke-dimensions args,input_files,stdin --format json --limit 20`
  -> `row_count=0`, `total_row_count=0`.
- Real planner dry-run after the equal-score fix and summary backfills:
  `.\.venv\Scripts\python.exe scripts\plan_official_breakthrough_targets.py --runs runs --official-eval-root runs\programbench_official_eval --baseline-root baselines\programbench --baseline-upgrade-require-runtime-smoke-dimensions args,input_files --format json --limit 6`
  -> `gron`, `nnn`, `htmlq`, `chmln`, and `cmatrix` are blocked by
  `official_not_above_baseline` (with `nnn` also blocked by
  `runtime_smoke_not_passed`); `chroma` still lacks an official aggregate
  summary because the official eval did not produce an eval JSON.
- Generalization-risk official-summary blocker regression:
  `.\.venv\Scripts\python.exe -m pytest tests\test_audit_generalization_risk.py -q`
  -> `6 passed` when run through the repository `.venv` outside the restrictive
  temp-directory sandbox. The non-elevated attempt hit the known Windows
  pytest temp ACL failure, and global Python 3.14 could not import the local
  `scripts` package.
- Generalization-risk lint/syntax checks:
  `python -m ruff check scripts\audit_generalization_risk.py tests\test_audit_generalization_risk.py`
  -> `All checks passed!`;
  `.\.venv\Scripts\python.exe -m py_compile scripts\audit_generalization_risk.py tests\test_audit_generalization_risk.py`
  -> passed.
- Real generalization-risk smoke after the official-summary blocker fix:
  `.\.venv\Scripts\python.exe scripts\audit_generalization_risk.py --runs runs --baseline-root baselines\programbench --official-eval-root runs\programbench_official_eval --format json --limit 20`
  -> ready rows whose embedded official summaries are tied with or below their
  recorded baselines are now high-risk official-entry blockers with
  `official_not_above_baseline`, not low-risk candidates.
- `nnn` runtime-smoke gate replay audit:
  `.\.venv\Scripts\python.exe scripts\audit_runtime_smoke_gate_replay.py --runs runs --official-eval-root runs\programbench_official_eval --baseline-root baselines\programbench --task jarun__nnn.cb2c535 --allow-existing-official --latest-per-task --require-runtime-smoke-dimensions args,input_files --execute-replay --format json --limit 10`
  -> `replay_status=insufficient_contract_artifacts`, missing required
  dimension `input_files`.

### Difficulties And Boundaries

- Official-standard testing means running inference inside ReBuilder's
closed-loop architecture, then using the same holdout/package/official eval
gates. A subagent outside the loop is only a responder unless it is connected
through `file_bridge` or an equivalent provider.
- The 2026-05-20 `clog-tool__clog-cli.7066cba` restore-axis attempt followed
this same boundary: ReBuilder ran the official-standard local loop through
`file_bridge`, using local request/response files as the LLM inference surface
inside the architecture. No external Kimi/GLM request was used in this run
because the local bridge remained usable.
- That earlier `clog` restore-axis run did not pass the official-entry gate. The first
`adaptive_profile` pass reached exploration `33/60` (`55.0%`) and holdout
`14/18` (`77.8%`), then retried as a near miss with `--max-repairs=5`. The
retry's best accepted candidate reached exploration `41/60` (`68.3%`) but the
holdout stayed `14/18` (`77.8%`), below the configured `0.8` threshold, so
official eval was correctly skipped.
- A later manual `file_bridge` patch5 for the same `clog` task did pass the
official-entry gate and completed official eval. It should be recorded
separately from the failed restore-axis retry: ReBuilder local was exploration
`105/106`, holdout `15/16`, runtime smoke covered
args/default/input-files/stdin, strict packaging with
`--max-local-holdout-gap 0.15` succeeded, and official aggregate was score `45`
(`260/575` counted; raw `394/778`, score `51`). The baseline was updated only
because counted passed tests improved within the same score bucket; this is not
an official score breakthrough.
- The main behavioral difficulty in that `clog` run was exact output matching
around branch-sensitive `changelog written. (took N ms)` lines. Multiple clean
repair attempts improved or worsened stdout by only a few exact milliseconds,
and some cases combined stdout timing with file-output differences for paths
with spaces or Unicode names. This made the last-mile repair unstable even
though the candidate preserved exit codes and many structural outputs.
- Patch5 reduced those visible local mismatches to one remaining file-output
case for a git-repo outfile path. The timing and text-file newline fixes belong
to the local differential harness; they should be described as cleanroom
comparison hardening, not as hidden official-test knowledge.
- The same run also surfaced parser-precedence edge cases around `--version`
combined with invalid values and conflict errors. A repair that delayed version
return until after validation was tested, but the pass did not beat the best
accepted candidate and was rejected by ReBuilder's non-regression rule.
- Subagent execution was not fully reliable during the `clog` rerun: previous
responder streams disconnected or failed, so the main session filled the
remaining `file_bridge` responses directly. This is an operational weakness of
the responder path, not evidence that external Kimi was required.
- The go-mod official run exposed a small but important local/official evidence
boundary: the candidate had only seven internal holdout cases. We allowed the
official eval with an explicit `--min-holdout-cases 7` because all available
local holdout cases passed and runtime smoke covered args/stdin/input-files, but
this should be described as a bounded task-specific gate, not a stronger
ten-case default gate.
- Docker remained an operational dependency for official-standard testing. The
go-mod cleanroom image had to be present locally, the official eval required
elevated Docker access from this Windows environment, and the run emitted HF Hub
unauthenticated-rate warnings while fetching ProgramBench assets. None of these
changed the aggregate score, but they are reproducibility notes.
- Go log stderr includes a current timestamp, so strict byte-for-byte stderr
comparison can produce false negatives when original and replacement commands
run seconds apart. The adopted normalization is deliberately narrow: same line
count, same non-timestamp body, parseable Go log timestamps, and drift no larger
than two seconds.
- The `zip-password-finder` restore sequence exposed both sides of the local
  gate. `usage_patch1` passed the configured package gate but official aggregate
  stayed at score 36, so that run remains negative evidence for the gate. A
  follow-up public-parser repair, `usage_patch2`, cleared the local exploration
  failures and upgraded official aggregate score to 40.
- The zip parser/validation precedence fixes came from local exploration
  failures around charset option handling, missing value diagnostics, and u64
  type validation. Those are cleanroom-local repair signals; they should not be
  presented as official hidden failure reasons.
- The zip cleanroom image was not present locally at first. It had to be pulled
  with Docker, and the closed loop had to run with elevated Docker access
  because the sandboxed process still could not see the pulled image. This is a
  reproducibility/operations note, not a model or algorithmic result.
- Two spawned helper agents for the zip target did not return usable artifacts
  within the wait window and were shut down. The main session completed the
  `file_bridge` harness afterward. This is a responder orchestration weakness;
  it is not evidence that external Kimi K2.6 was required.
- The `xsv` restore run showed why the package gate is a necessary but
  insufficient predictor. The local bridge candidate reached the configured
  holdout threshold exactly at `12/15` and passed runtime-smoke dimensions, yet
  the official rounded score stayed at 44. Public material may mention the
  counted pass improvement from `518/1186` to `527/1186`, but should not call it
  an official-score breakthrough.
- The `xsv` local repair sequence was iterative and partly negative: a first
  local patch dropped holdout to `9/15`, a narrower second pass reached
  `11/15`, and only the third pass reached `12/15`. The useful fix pattern was
  not "more repair loops"; it was local aggregate failure clustering around
  CSV command dispatch, sidecar file output, stdin/file precedence, and exact
  frequency/stat formatting.
- The `xsv` cleanroom image was also missing from the sandbox-visible Docker
  image set. It had to be pulled with `docker pull
  programbench/burntsushi_1776_xsv.f430466:task_cleanroom`, and the closed loop
  required elevated Docker access because the sandboxed process could not see
  the pulled image.
- The `csview` restore attempt ultimately raised local exploration to `49/49`
  after tightening positional `-` parsing, missing-value diagnostics,
  clap-style invalid flag/value diagnostics, CSV quote handling, empty-table
  rendering, and control-character width behavior, but the holdout stayed at
  `8/14`. This is exactly the kind of local/holdout split the package gate is
  meant to catch before official eval.
- The follow-up gate hardening turned that split into an explicit aggregate
  signal. Candidate ranking now reports `local_holdout_gap` and supports
  `--max-local-holdout-gap`; `audit_generalization_risk.py` now reports
  `latest_local_resolved_rate` / `latest_local_holdout_gap` and blocks otherwise
  gate-ready rows when local resolved rate is much higher than internal
  holdout. Real `runs` strict official-ready ranking with
  `--max-local-holdout-gap 0.15` still returns `row_count=0`. The latest
  `csview` row shows local `1.0`, holdout `0.5714`, gap `0.4286`, and remains
  blocked by low holdout plus missing `input_files` runtime-smoke coverage.
  This is an anti-overclaim gate, not official ProgramBench evidence.
- The same risk audit now also treats tied-or-lower official aggregates as
  entry blockers. If a ready-baseline candidate already has an embedded
  aggregate official summary but that summary does not outrank the recorded
  baseline, `audit_generalization_risk.py` reports
  `official_not_above_baseline` and requires another candidate improvement
  before any new official submission. This keeps the public narrative aligned
  with the strict ranking gate: local readiness is not an upgrade when the
  aggregate official result is equal or worse.
- The same gap policy is now visible at official-entry boundaries:
  `package_submission.py`, `run_official_closed_loop.py`,
  `run_official_strategy_ablation.py`, and `run_restore_axis_ablation_batch.py`
  accept or forward `--max-local-holdout-gap`. Manual entrypoint verification
  showed packaging rejects a gate-ready local artifact with
  `local_holdout_gap_too_high`, and a real restore-axis JSON dry-run for
  `clog-tool__clog-cli.7066cba` included `--max-local-holdout-gap 0.15` in the
  child command. This keeps the anti-overfit policy attached to the path that
  can eventually trigger packaging or official eval.
- The planner layer now emits the same anti-overfit gate in generated command
  plans. `plan_official_breakthrough_targets.py` accepts
  `--baseline-upgrade-max-local-holdout-gap` and
  `--restore-ablation-max-local-holdout-gap`, includes
  `max_local_holdout_gap` in the ready-baseline gate JSON, passes the threshold
  into `official_gate_blockers()`, and renders guarded ready/restore next
  commands with `--max-local-holdout-gap`. Real `runs` planner smoke returned
  `row_count=13`, with 8 ready commands and 3 restore commands carrying
  `--max-local-holdout-gap 0.15`. A synthetic official-summary-above-baseline
  fixture still blocked as `local_holdout_gap_too_high` when local `1.0`
  exceeded holdout `0.85` beyond the configured `0.1` gap.
- The same `csview` attempt also exposed an implementation-harness difficulty:
  one intermediate bridge patch generated syntactically invalid Python and
  scored `0/49` locally before the syntax was corrected and rerun. Public
  material should describe that as manual bridge engineering friction, not as
  model evidence or official evidence.
- The latest `csview` result directory has no aggregate holdout failure report
  under `reports`, so there is no publishable or cleanroom-safe hidden-detail
  diagnosis to reuse. The next valid `csview` step is to recover historical
  best-level local holdout and add input-files runtime-smoke coverage before
  any official eval attempt, not to package the current `restore_patch8`
  artifact.
- The current environment policy blocked direct external Kimi/GLM-style fallback
because it would send local task/code context to a third-party LLM API. That is
a data egress boundary, not a model-quality result. External Kimi K2.6 testing
requires explicit approval and should be described separately from the local
no-external-LLM path.
- A previous official eval attempt reached the ProgramBench toolchain but did
  not produce a new aggregate eval JSON after a Docker-side hang. Without an
  aggregate eval JSON, there is no official score to claim. The new timeout
  guard makes this failure mode explicit but does not turn a timed-out run into
  official evidence.
- The chroma official-standard attempt repeated this class of Docker-side hang:
  the no-external subagent path produced a local candidate and entered
  ProgramBench official eval, but no aggregate eval JSON was produced. The
  correct public boundary is "official eval attempted, no official aggregate",
  not "official score pending" or "breakthrough".
- A later `chroma` `restore_patch2` no-external bridge pass materially
  strengthened local evidence before official evaluation: public/evidence replay
  matched `122/122`, ReBuilder local exploration was `95/95`, holdout was
  `31/31`, and runtime smoke covered args/stdin/input-files/default. This is
  strong local cleanroom evidence, but it remains below official aggregate
  evidence until ProgramBench writes a `*.eval.json`. A 30-minute official eval
  attempt again produced no aggregate JSON and left a ProgramBench container to
  stop manually. Its Python eval process also survived the shell timeout, so it
  had to be killed before the longer follow-up eval could safely continue on
  the same submission directory. The follow-up eval also stalled without
  writing aggregate JSON and was cleaned up. Public copy should call this an
  official-eval operations blocker, not an official score.
- A bounded follow-up retry on the same `chroma restore_patch2` submission used
  the existing `submission.tar.gz`, did not re-run the LLM/file_bridge path, and
  set ProgramBench eval to `workers=1`, `branch_workers=1`, `docker_cpus=4`,
  `branch_retries=1`, `force=True`, with a 600-second timeout. It reproduced
  the same stall after `Fetching ... files: 3it`, wrote no
  `alecthomas__chroma.8d04def.eval.json`, and the runner stopped one matching
  ProgramBench eval container. Follow-up checks found no running
  `programbench`/`chroma` Docker containers and no stale ProgramBench Python
  process. This strengthens the evidence that the current blocker is official
  eval operations, not local reconstruction quality.
- A second bounded retry reused the same `chroma restore_patch2` package with
  `workers=1`, `branch_workers=1`, `docker_cpus=1`, `branch_retries=1`,
  `force=True`, and an 1800-second timeout. It again stalled after
  `Fetching ... files: 3it`, produced no
  `alecthomas__chroma.8d04def.eval.json`, stopped one matching ProgramBench
  eval container, and removed seven matching
  `programbench-compiled/alecthomas__chroma.8d04def:*` images. Follow-up
  Docker checks found no running ProgramBench containers and no remaining
  chroma compiled images. This is still an official-eval operations blocker,
  not an official score or pending breakthrough.
- A later long retry repackaged the same no-external `chroma restore_patch2`
  generated code under
  `runs\programbench_official_eval\submission_chroma_restore_patch2_long_20260520`
  and ran ProgramBench official eval with `workers=1`, `branch_workers=1`,
  `docker_cpus=2`, `branch_retries=1`, and `force=True`. The shell command hit
  the 7200-second wrapper timeout, but ProgramBench had written the aggregate
  eval JSON by then. The official result was counted `0/515`, score 0; raw
  `0/531`, score 0. This is below the historical score-3 baseline. The
  candidate result now embeds that aggregate-only summary so planner/ranking
  gates classify the row as not above baseline instead of treating it as an
  untested ready candidate.
- The closed-loop runner now writes an aggregate-only
  `official_eval_failure_report.json` when ProgramBench eval fails without an
  aggregate JSON. The report records command parameters, timeout, stopped
  container IDs, removed compiled-image refs, and file metadata for the
  submission, eval JSON, and root stdout/stderr logs; it does not read or
  summarize official test details. This gives public-release triage a durable
  operations record for Docker/eval hangs without converting them into
  benchmark evidence.
- The gron patch6 official eval is the opposite failure mode: the official eval
  did complete, but it only matched the existing score-62 aggregate baseline.
  Strong local bridge evidence and local holdout are still not sufficient to
  claim a breakthrough when official aggregate rank is equal.
- The later `clog-tool__clog-cli.7066cba` patch5 pass is another same-score
  refinement case. It ran through ReBuilder's no-external-LLM `file_bridge`
  path, passed the strict local package gate, and completed ProgramBench
  official eval. Local ReBuilder evidence was exploration `105/106`, holdout
  `15/16`, status `success`, runtime smoke over args/default/input-files/stdin,
  and a local-holdout gap of `0.0531`. Official aggregate evidence was counted
  `260/575`, score `45`; raw `394/778`, score `51`; `fully_resolved=false`.
  This improves the previous clog score-45 counted baseline of `257/575`, but
  the rounded official score did not improve. Public copy may describe it as an
  aggregate-count refinement, not as an official score breakthrough or solved
  task. The submission SHA-256 was
  `ab2011ab685708df8fa9b280a880bc9b191ac472f782faa2ed5661ed2df62bac`.
- Historical candidate result files can be misleading if official summaries are
  not embedded. The planner now treats missing summaries as blockers and treats
  equal/lower summaries as `official_not_above_baseline`; public material should
  preserve that gate distinction instead of reporting "eligible" from local
  evidence alone.
- The latest `chroma` result is the sharpest example of that boundary: local
  exploration and holdout were both `100%`, but the official aggregate score
  was `0`. It should be used as negative evidence for over-trusting local
  gates, not as a near miss.
- Local holdout success and local replay success remain weaker evidence than
official aggregate ProgramBench results. Release copy must keep that distinction
plain.
- The follow-up chmln run passed the packaging gate even though the local task
  status was `FAILED`, because package admission is based on configured holdout
  and runtime-smoke thresholds. This is acceptable for aggregate experiments but
  should not be described as a locally solved reconstruction.
- Windows sandbox ACL issues interfered with broad pytest temp-directory usage:
  `C:\Users\Administrator\.codex-tmp`, `C:\tmp`, and one repository basetemp
  attempt produced `PermissionError` / `Access denied` failures. A later
  `--basetemp=runs\pytest_tmp_rank_gate` attempt also became non-listable and
  had to be removed after verification. The focused tests and manual fixture
  checks above avoided that path. A full
  `tests\test_run_official_closed_loop.py` run still fails in `tmp_path` fixture
  setup under the current sandbox, even though the no-`tmp_path` focused timeout
  slice passes.
- A second full `tests\test_run_official_closed_loop.py` attempt with
  `--basetemp=output\pytest_tmp_run_official_closed_loop_cleanup` hit the same
  ACL problem during pytest tmp cleanup. The generated temp directory was
  removed after verifying it was inside the workspace.
- The local-holdout gap follow-up hit the same pytest temp ACL class in
  `tests\test_rank_programbench_candidates.py` and
  `tests\test_audit_generalization_risk.py`: pytest-created basetemp
  directories under `C:\Users\Administrator\.codex-tmp`, `C:\tmp`, and
  workspace `output\pytest_tmp*` became inaccessible during session finish.
  Verification therefore used `python -m ruff check`, `py_compile`, a manual
  aggregate-only fixture harness under `output\pytest_tmp2`, and real `runs`
  JSON smoke checks instead of claiming a full focused pytest pass.
- Follow-up entrypoint verification used the same workaround: `ruff` and
  `py_compile` passed for the touched package/closed-loop/ablation files, and a
  manual harness under `output\pytest_tmp2` verified both package rejection and
  command propagation. Broad pytest remains blocked by the same temp ACL class.
- The `clog` patch5 follow-up exposed two local-framework noise classes that
  were hiding real progress in Windows-vs-Docker comparison: volatile elapsed
  counters like `changelog written. (took N ms)` and CRLF/LF drift in UTF-8
  text file outputs. `core\differential_tester.py` now normalizes only that
  narrow elapsed-counter shape and tolerates line-ending-only text file output
  drift; binary file outputs and changed non-timing text remain strict.
  Verification passed with `python -m ruff check
  core\differential_tester.py tests\test_differential_tester_backends.py`,
  `.venv` `py_compile`, and
  `.venv\Scripts\python.exe -m pytest
  tests\test_differential_tester_backends.py -q --basetemp
  output\pytest_tmp\differential_noise_20260520` as `17 passed`, with only the
  existing `.pytest_cache` ACL warning.
- The same `clog` follow-up also required cleanroom-local implementation fixes
  in the bridge patch: empty version headers should not silently become
  `0.0.0`, default git-context behavior needs a bounded empty-git fallback when
  the replacement temp dir lacks `.git`, and generated changelog/outfile writes
  must use LF newlines. One local exploration file-output mismatch remains for
  a visible git-repo outfile case; that is local cleanroom evidence, not hidden
  official-failure evidence.
- Planner-level verification used the same evidence boundary: `ruff` and
  `.venv` `py_compile` passed for `scripts\plan_official_breakthrough_targets.py`
  and `tests\test_plan_official_breakthrough_targets.py`; real planner JSON
  smoke and the synthetic local/holdout-gap fixture passed. A focused
  `pytest tests\test_plan_official_breakthrough_targets.py -q --basetemp
  output\pytest_tmp2\plan_gap_pytest_20260520` attempt failed at pytest
  session cleanup with `WinError 5` on the generated basetemp directory, which
  was then removed after verifying it was inside the workspace. Do not record
  that pytest run as passed.
- Official-eval failure-report verification followed the same pattern:
  `python -m ruff check scripts\run_official_closed_loop.py
  tests\test_run_official_closed_loop.py` and `.venv` `py_compile` passed; a
  manual harness under `output\manual_smoke\official_eval_failure_report_20260520`
  simulated a ProgramBench eval timeout and confirmed the report fields. A
  focused pytest attempt for the report/timeout tests again hit `WinError 5`
  during basetemp cleanup and was not counted as passing.
- The later compiled-image cleanup change was verified with the same evidence
  boundary: `python -m ruff check scripts\run_official_closed_loop.py
  tests\test_run_official_closed_loop.py` and `.venv` `py_compile` passed.
  The isolated unit test
  `.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests\test_run_official_closed_loop.py::test_cleanup_programbench_eval_images_removes_only_matching_instance -q`
  passed as `1 passed`.
  The real `chroma restore_patch2` CPU1 retry wrote
  `runs\programbench_official_eval\submission_chroma_restore_patch2_cpu1_20260520\official_eval_failure_report.json`
  with `removed_compiled_image_count=7`. A focused pytest attempt covering the
  image cleanup path again hit the current Windows basetemp ACL problem during
  session cleanup and should not be reported as a passing pytest run.
- The first 2026-05-20 official-standard attempt could not start because the
  local cleanroom Docker image was missing. `--pull` then hit the ProgramBench
  adapter's 60-second Docker pull timeout. A direct `docker pull
  programbench/chmln_1776_sd.87d1ba5:task_cleanroom` completed successfully and
  allowed the no-`--pull` closed loop to run. The timeout is now configurable via
  `--docker-command-timeout-seconds` for future official-standard reruns.
- `python -m mypy core\llm_output.py` was blocked by pre-existing
  `core\data_models.py` errors on `TestResult.__test__` and `TestCase.__test__`;
  this was not introduced by the parser fix.

### 2026-05-20 Elfcat File-Bridge Missing-Holdout Probe

- `rbakbashev__elfcat.52f8cc7` was run through ReBuilder's no-external
  `file_bridge` provider using
  `output\file_bridge_manual\smoke_file_bridge_elfcat_holdout_probe1.yaml`.
  The responder was the local subagent-backed model name
  `codex-subagent-file-bridge-elfcat-holdout-probe1`; external Kimi/GLM was
  not used.
- The first execution could not start because the cleanroom image was missing.
  Re-running the wrapper with `--pull` prepared the image and allowed the
  ReBuilder closed loop to continue.
- The first completed pass used 56 probes and stopped below the holdout gate:
  local holdout `11/14` (`78.6%`), so official eval was skipped.
- The near-miss retry expanded to 68 probes. Final local aggregate was
  exploration `36/56` (`64.3%`) and holdout `14/16` (`87.5%`), with task
  status `FAILED` and `almost_resolved=false`. The missing-holdout wrapper first
  packaged the candidate with `--skip-official-eval`; a later bounded manual
  official eval reused that package without re-running the LLM path.
- The packaged artifact is
  `runs\programbench_official_eval\submission_rbakbashev_elfcat_52f8cc7\rbakbashev__elfcat.52f8cc7\submission.tar.gz`.
  The official aggregate eval JSON is
  `runs\programbench_official_eval\submission_rbakbashev_elfcat_52f8cc7\rbakbashev__elfcat.52f8cc7\rbakbashev__elfcat.52f8cc7.eval.json`.
  Counted result: `215/564`, score `38`; raw result: `288/646`, score `45`.
  This upgrades the recorded `elfcat` aggregate baseline from historical score
  `17` to score `38`, but it is still not fully resolved.
- Repair lessons: implementation responses through `file_bridge` must be
  returned as a manifest or file-block payload, not naked source code, otherwise
  ReBuilder rejects the generation as `missing_entrypoint`; JSON-safe bytes in
  `input_files` were usable for adversarial probes after the decoder fix; exact
  stderr strings for unsupported ELF class/data remained behaviorally important.
- Difficulty boundary: stdout, stderr, and exit behavior improved, but the
  dominant unresolved cluster stayed in local `file_output` / HTML byte
  equivalence. Some file-output repairs regressed and were rejected by the
  non-regression gate. Unsafe parent-traversal `input_files` were skipped by
  the existing safety filter, which is correct behavior and should not be
  presented as a task-specific hidden failure.
- Official-eval operations also exposed two environment issues: the default
  HuggingFace cache under `C:\Users\Administrator\.cache` hit a permission
  error, so the successful retry used workspace-local `output\hf_cache`; the
  Docker API required elevated access. The successful official eval ran with
  `workers=1`, `branch_workers=1`, `docker_cpus=1`, `branch_retries=1`, and a
  bounded 1200-second timeout.

### 2026-05-20 Continuation Evidence Refresh

- A read-only Codex subagent independently rechecked the current official
  breakthrough queue after the `elfcat` run. It recommended `wfxr__csview` only
  as a local restore-axis target, not as an official-ready candidate: the strict
  official-ready ranker still returned zero rows under the runtime-smoke,
  local-holdout-gap, and existing-official baseline gates.
- The main thread verified that generic strategy-ablation commands default to
  `config/settings.yaml`, which uses an external GLM provider. For no-external
  subagent work, the safe path is the dedicated `file_bridge` harness or an
  explicit loopback local endpoint plus `--ack-local-llm-docker`; otherwise the
  command is outside the no-external evidence boundary.
- `scripts\audit_official_baseline_candidates.py --actionable-only` reported no
  unrecorded official aggregate upgrades after the `elfcat` baseline file was
  written. The strict official-ready candidate gate also remained empty, so the
  correct next action is local mechanism work rather than another official eval.
- `rbakbashev__elfcat.52f8cc7` remains the publishable official-standard
  subagent result from this batch: baseline record
  `baselines\programbench\rbakbashev__elfcat.52f8cc7.baseline.json` records
  model `codex-subagent-file-bridge-elfcat-holdout-probe1`, counted official
  aggregate `215/564`, score `38`, and submission SHA-256
  `d742b71da693358a7a8eabf3df16254107fd30c166b5d2d2cf10493c3f6f4c73`.
  A raw eval parser pass over the official JSON reported `288/646`, score `45`;
  public copy should use the counted ProgramBench baseline score for
  breakthrough claims and may mention the raw score only as secondary aggregate
  context.
- Kimi K2.6 was not used in this continuation. It should stay documented as the
  fallback only if ReBuilder's `file_bridge` or loopback-local LLM path cannot
  run an official-standard attempt; that was not the blocker here.
- Small tooling caveat: `audit_official_baseline_candidates.py` currently emits
  markdown only and does not accept `--format json`. This caused one harmless
  rejected audit invocation during the refresh and should not be treated as an
  experiment failure.

### 2026-05-20 No-External Planner Hardening

- A second read-only Codex subagent audited the official-standard command path
  without editing files, Docker, network, or LLM calls. It confirmed the main
  risk: planner-generated weak rerun, restore-ablation, and missing-holdout
  commands did not carry an explicit `--config`, so executing those commands
  could fall back to `config/settings.yaml`, whose default provider is external
  GLM. `--skip-official-eval` only disables official eval; it is not a
  no-external guarantee.
- Repair: `scripts\plan_official_breakthrough_targets.py` now accepts explicit
  local/no-external command-rendering knobs for weak rerun, restore ablation,
  and missing holdout: `--*-config` plus `--*-ack-local-llm-docker`. These are
  threaded into generated `next_command` values. `scripts\summarize_holdout_trends.py`
  now lets guarded weak rerun commands include `--ack-local-llm-docker`.
- Consistency repair: the local `output\file_bridge_manual` harnesses for
  `clog`, `htmlq`, and `gron` now use `--ack-local-llm-docker` instead of
  `--ack-external-llm-docker`. They were already pointed at file_bridge config,
  so this was an evidence-labeling and drift-prevention fix, not a claim that
  they previously called an external provider.
- Verification:
  - `.\.venv\Scripts\python.exe -m py_compile scripts\plan_official_breakthrough_targets.py scripts\summarize_holdout_trends.py tests\test_plan_official_breakthrough_targets.py tests\test_summarize_holdout_trends.py output\file_bridge_manual\run_clog_file_bridge.py output\file_bridge_manual\run_htmlq_file_bridge.py output\file_bridge_manual\run_gron_restore_patch.py`
    passed.
  - `python -m ruff check scripts\plan_official_breakthrough_targets.py scripts\summarize_holdout_trends.py tests\test_plan_official_breakthrough_targets.py tests\test_summarize_holdout_trends.py`
    passed.
  - `.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests\test_plan_official_breakthrough_targets.py tests\test_summarize_holdout_trends.py -q`
    passed as `47 passed` when run outside the sandbox.
  - A real planner JSON smoke over current `runs` rendered restore commands for
    `wfxr__csview.8ac4de0` and `psampaz__go-mod-outdated.bb79367`, and a weak
    rerun command for `ajeetdsouza__zoxide.67ca1bc`; those commands included
    `--config config\smoke_file_bridge.yaml` and `--ack-local-llm-docker`.
  - `scripts\audit_official_baseline_candidates.py --actionable-only` still
    returned no unrecorded aggregate upgrades, and strict official-ready ranking
    still returned `row_count: 0`.
- Difficulties and boundaries:
  - Kimi K2.6 was not used. The local ReBuilder `file_bridge`/loopback path was
    usable enough for command-chain hardening, so the fallback condition was not
    met.
  - In-sandbox pytest attempts repeatedly hit Windows `WinError 5` while
    creating or cleaning temp directories under `.codex-tmp`, workspace
    `output`, and `C:\tmp`; the focused pytest pass required an elevated
    sandbox-outside run. This is an environment verification blocker, not a
    product result.
  - The repo still has no new strict official-ready candidate after this fix.
    The change hardens the official-standard workflow against accidental
    external-LLM execution; it is not itself a new ProgramBench score
    breakthrough.

### 2026-05-20 Restore-Axis Batch Planner Follow-Up

- A follow-up read-only subagent audited the next no-external mechanism target
  and recommended `wfxr__csview.8ac4de0` over `psampaz__go-mod-outdated` and
  `ajeetdsouza__zoxide`: current `csview` is a `restore_historical_gate`
  regression with historical best holdout `0.9167`, latest no-external patch8
  holdout `0.5714`, `axis_delta_action=ablate_added_axis_domains:csv_table`,
  and missing `input_files` runtime-smoke coverage. This is a general
  axis-domain/generalization-gate issue, not a task-specific hidden-test claim.
- Repair: `scripts\plan_official_breakthrough_targets.py` now supports
  `--restore-ablation-command-kind batch` plus
  `--restore-ablation-show-axis-action`. With those flags, restore rows render
  `scripts\run_restore_axis_ablation_batch.py` commands instead of direct
  single-task strategy-ablation commands. The batch wrapper can surface
  axis-action metadata before execution while still forwarding the local
  `file_bridge` config and `--ack-local-llm-docker`.
- Verification:
  - `.\.venv\Scripts\python.exe -m py_compile scripts\plan_official_breakthrough_targets.py tests\test_plan_official_breakthrough_targets.py`
    passed.
  - `python -m ruff check scripts\plan_official_breakthrough_targets.py tests\test_plan_official_breakthrough_targets.py`
    passed.
  - `.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests\test_plan_official_breakthrough_targets.py -q`
    passed as `12 passed` when run outside the sandbox.
  - A real planner JSON smoke over current `runs` rendered restore-batch dry-run
    commands for `wfxr__csview.8ac4de0` and
    `psampaz__go-mod-outdated.bb79367` with
    `--config config\smoke_file_bridge.yaml`, `--ack-local-llm-docker`,
    `--show-axis-action`, `--format json`, and `--dry-run`.
  - A direct dry-run of
    `scripts\run_restore_axis_ablation_batch.py wfxr__csview.8ac4de0 ... --show-axis-action --format json`
    selected one row and reported
    `axis_delta_action=ablate_added_axis_domains:csv_table`, with a child
    strategy-ablation command that requires `args,input_files` runtime-smoke
    coverage and skips official eval.
  - The strict official-ready ranker still returned `row_count: 0`, and
    `scripts\audit_official_baseline_candidates.py --actionable-only` still
    reported no unrecorded aggregate upgrades.
- Difficulties and boundaries:
  - Kimi K2.6 was not used. The ReBuilder local `file_bridge` path remained
    available, so the fallback condition was not met.
  - In-sandbox pytest still hit Windows `WinError 5` on
    `C:\Users\Administrator\.codex-tmp\pytest-of-Administrator`; the focused
    pytest pass required a sandbox-outside run.
  - The generic restore-axis batch execute path was not started blindly:
    `config\smoke_file_bridge.yaml` is a file-bridge handoff that writes
    requests under `output\file_bridge_llm` and waits for a responder. Without
    a live responder process or task-specific harness, executing it would risk
    a long wait rather than a meaningful official-standard attempt.
  - This follow-up improves the official-standard no-external command path for
    the next restore experiment. It does not create a new official aggregate
    score, and no official eval was run in this step.

### 2026-05-20 Runtime-Smoke Input-Files Dimension Repair

- Follow-up evidence on `wfxr__csview.8ac4de0` showed a concrete mismatch:
  the latest no-external patch8 result had file-input probe coverage in
  implementation metadata, but the recorded runtime-smoke metadata still had
  `input_file_case_count=0` and dimensions limited to `args/default/stdin`.
  The subagent audit correctly treated this as a blocker for official-standard
  promotion, not as a hidden-test failure signal.
- Root cause: `core\codebase\runtime_smoke.py` selected only the first
  `max_contract_cases` contracts after sorting. Generic `smoke_contract` tags
  were ranked ahead of file-input contracts, so safe `input_files` cases could
  be starved when a task had many argument-only smoke contracts.
- Repair: `PythonRuntimeSmokeChecker._contract_priority` now prioritizes safe
  file-input contracts before error-mode probes, then env-var contracts,
  stdin-only contracts, generic smoke contracts, help/version probes, and the
  remaining cases. This is a general dimension-coverage repair; it does not
  mention or special-case `csview`.
- Test coverage: `tests\test_codebase_integrity.py` now includes
  `test_python_runtime_smoke_checker_prioritizes_input_files_with_limited_contract_budget`,
  which creates more argument-only smoke contracts than the case budget and
  verifies that the late-sorted file-input contract is still planned and
  executed. A follow-up regression,
  `test_python_runtime_smoke_checker_keeps_file_input_when_error_contracts_fill_budget`,
  covers the case where error contracts alone would otherwise fill the limited
  contract budget.
- Verification:
  - `.\.venv\Scripts\python.exe -m py_compile core\codebase\runtime_smoke.py tests\test_codebase_integrity.py`
    passed.
  - `python -m ruff check core\codebase\runtime_smoke.py tests\test_codebase_integrity.py`
    passed.
  - `.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests\test_codebase_integrity.py -q`
    passed as `19 passed` when run outside the sandbox.
  - The combined focused regression run
    `.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests\test_codebase_integrity.py tests\test_plan_official_breakthrough_targets.py -q`
    passed as `31 passed` when run outside the sandbox.
  - `scripts\audit_runtime_smoke_replay.py --task wfxr__csview.8ac4de0 --require-runtime-smoke-dimensions args,input_files,stdin --execute --format json`
    reported `row_count=12`: 1 historical `csview_stdinio` artifact
    `replay_passed` with `args/default/input_files/stdin`, while 11 artifacts
    remained `insufficient_contract_artifacts` because their evidence does not
    contain the required `stdin` dimension.
  - `scripts\audit_runtime_smoke_gate_replay.py --task wfxr__csview.8ac4de0 --require-runtime-smoke-dimensions args,input_files,stdin --execute-replay --format json`
    still reported `replay_failed_or_incomplete`; the strict gate-selected
    historical `csview_min50` row still lacks `stdin`, and its remaining
    blockers are `already_official` plus `runtime_smoke_not_passed`.
  - The strict official-ready ranker with
    `--require-runtime-smoke-dimensions args,input_files,stdin` still returned
    `row_count=0`, and `scripts\audit_official_baseline_candidates.py --actionable-only`
    printed only the table header, meaning there is no new unrecorded official
    aggregate upgrade from this step.
- Difficulties and boundaries:
  - In-sandbox runtime replay reached the expected planned dimensions but failed
    at execution with `runtime_smoke_executor_permission_denied`; the same
    command passed the eligible replay row outside the sandbox. This is an
    environment permission boundary, not a model-quality result.
  - One baseline-audit attempt used an unsupported `--runs` argument; the
    corrected command is
    `scripts\audit_official_baseline_candidates.py --official-eval-root runs\programbench_official_eval --baseline-root baselines\programbench --actionable-only`.
  - The patch8 no-external `file_bridge` artifacts still do not satisfy the
    full `args/input_files/stdin` strict gate because their available evidence
    lacks `stdin`. The runtime-smoke fix removes one source of starvation, but
    it does not manufacture missing contract evidence.
  - Kimi K2.6 was not used. No external LLM was called during this repair or
    replay verification.
  - No official eval was run in this step, no new strict official-ready row was
    produced, and this is not a ProgramBench aggregate breakthrough.

### 2026-05-20 Official-Generalization Gap Audit

- A follow-up audit made the local-green/official-flat failure mode explicit in
  tooling instead of leaving it as prose in run logs. The new
  `scripts\audit_official_generalization_gaps.py` reports candidates that have
  local holdout/runtime-smoke evidence, already embed an aggregate-only official
  summary, and still fail to outrank the recorded baseline.
- The audit is intentionally aggregate-only. It reports official score,
  counted passed tests, pass rate, fully/almost-resolved flags, local holdout
  rate, runtime-smoke dimensions, and the candidate `result.json` path. It does
  not print hidden failure details or baseline notes.
- A read-only subagent independently audited the sharpest current example,
  `alecthomas__chroma.8d04def`. It confirmed that the authoritative baseline
  remains counted `13/515`, score `3`, while the latest no-external
  `restore_patch2` candidate has official counted `0/515`, score `0`, with raw
  `0/531`, score `0`. The local ReBuilder evidence was still strong:
  holdout `31/31` and runtime smoke over args, stdin, input files, and default.
  The correct conclusion is a generalization gap, not a missing artifact,
  parser failure, or official breakthrough.
- Running the new audit over current `runs` with strict runtime-smoke dimensions
  returned eight blocked rows:
  - `chmln__sd.87d1ba5`: candidate score `80` / `651` counted vs baseline
    score `86` / `697`, delta `-6` score and `-46` counted;
  - `alecthomas__chroma.8d04def`: candidate score `0` / `0` counted vs
    baseline score `3` / `13`, delta `-3` score and `-13` counted;
  - `mgdm__htmlq.6e31bc8`: same rounded score `91` but one counted pass below
    baseline (`1329` vs `1330`);
  - `clog`, `gron`, `elfcat`, `zip-password-finder`, and `xsv`: equal to the
    recorded aggregate baselines, so they are refinements or confirmations, not
    new baseline upgrades.
- The common next action for these rows is
  `repair_local_generalization_before_more_official_eval`. Repeating the same
  package through official eval is not a valid improvement strategy when an
  aggregate official summary is already equal to or worse than baseline.
- Verification:
  - `.\.venv\Scripts\python.exe -m py_compile scripts\audit_official_generalization_gaps.py tests\test_audit_official_generalization_gaps.py`
    passed.
  - `python -m ruff check scripts\audit_official_generalization_gaps.py tests\test_audit_official_generalization_gaps.py`
    passed.
  - `.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests\test_audit_official_generalization_gaps.py -q`
    passed as `2 passed` when run outside the restrictive sandbox.
  - The related focused regression suite
    `.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests\test_audit_official_generalization_gaps.py tests\test_rank_programbench_candidates.py tests\test_plan_official_breakthrough_targets.py tests\test_audit_generalization_risk.py -q`
    passed as `87 passed` outside the restrictive sandbox.
  - Real `runs` smoke with
    `--require-runtime-smoke-dimensions args,input_files,stdin --latest-per-task`
    returned `row_count=8`, all blocked by `official_not_above_baseline`.
- Difficulties and boundaries:
  - The first non-elevated pytest attempt hit the known Windows ACL failure at
    `C:\Users\Administrator\.codex-tmp\pytest-of-Administrator` with
    `WinError 5`; the same focused tests passed outside that sandbox. This is a
    local verification environment issue, not a failing regression.
  - Kimi K2.6 was not used. The ReBuilder `file_bridge` and local audit path
    were sufficient for this step, so the external-LLM fallback condition was
    not met.
  - No new official eval was launched by this audit. It classifies existing
    aggregate official evidence and prevents overclaiming; it does not create a
    new ProgramBench score.
  - No new official aggregate breakthrough exists from this step. Local
    holdout, runtime smoke, and subagent reasoning remain weaker than aggregate
    official evidence that beats the recorded baseline.

### 2026-05-20 Planner Routing For Official-Generalization Gaps

- A read-only subagent then audited the planner/ranker chain and found one
  remaining semantic drift: `rank_programbench_candidates.py` correctly blocked
  embedded official summaries that were equal to or worse than baseline, but
  `plan_official_breakthrough_targets.py` still exported those rows as
  `ready_baseline_gate` with `next_action=audit_baseline_upgrade_candidate`.
  The attached `baseline_upgrade_gate` was already
  `official_not_above_baseline`, so the command path was safe but misleading:
  it encouraged another official-ready ranking pass that necessarily returned
  an empty table.
- Repair: planner JSON and markdown output now reinterpret those rows as
  `target_class=official_generalization_gap`,
  `next_action=repair_local_generalization_before_more_official_eval`, and
  `reason=official_not_above_baseline`. Their `next_command` now points to a
  task-scoped aggregate-only generalization-gap audit instead of
  `rank_programbench_candidates.py --official-eligible-only`.
- `scripts\audit_official_generalization_gaps.py` now supports repeated
  `--task` filters so planner-generated commands can focus on the exact
  blocked candidate, such as `alecthomas__chroma.8d04def`, without widening the
  audit scope or exposing hidden-test details.
- Real current-state smoke after the fix:
  - planner over current `runs` with strict runtime-smoke dimensions returned
    the former top ready rows as `official_generalization_gap`, including
    `chroma`, `zip-password-finder`, `elfcat`, `xsv`, and `clog`;
  - the first row's next command was
    `python scripts/audit_official_generalization_gaps.py ... --task alecthomas__chroma.8d04def ... --latest-per-task --format json`;
  - executing that command returned one aggregate-only `chroma` row: local
    holdout `31/31`, runtime smoke over args/stdin/input-files/default,
    candidate official score `0` / `0` counted, recorded baseline score `3` /
    `13` counted;
  - the strict official-ready ranker still returned `row_count=0`, so no new
    official-ready baseline upgrade exists.
- Verification:
  - `.\.venv\Scripts\python.exe -m py_compile scripts\plan_official_breakthrough_targets.py scripts\audit_official_generalization_gaps.py tests\test_plan_official_breakthrough_targets.py tests\test_audit_official_generalization_gaps.py`
    passed.
  - `python -m ruff check scripts\plan_official_breakthrough_targets.py scripts\audit_official_generalization_gaps.py tests\test_plan_official_breakthrough_targets.py tests\test_audit_official_generalization_gaps.py`
    passed.
  - `.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests\test_plan_official_breakthrough_targets.py tests\test_audit_official_generalization_gaps.py -q`
    passed as `17 passed` outside the restrictive sandbox.
- Difficulties and boundaries:
  - The first focused pytest run failed because the new test asserted a
    `next_command` while omitting `--include-next-command`; the test input was
    corrected and the suite then passed. This was test coverage drift, not a
    product regression.
  - Kimi K2.6 was not used. No external LLM, Docker, or official eval was
    invoked for this planner repair.
  - This change improves execution steering and anti-overclaim behavior. It
    does not improve any official aggregate score and is not a ProgramBench
    breakthrough.

### 2026-05-20 Restore-Axis Domain Ablation Plumbing

- A read-only subagent audited the sharpest restore-axis candidate,
  `wfxr__csview.8ac4de0`, using the official-standard evidence already on
  disk. The latest no-external `file_bridge` patch8 run was locally solved
  (`resolved_rate=1.0`) but had weak holdout evidence (`0.5714` over 14), while
  the historical stronger local candidate had holdout `0.9167` over 12. The
  restore audit classified the axis delta as
  `ablate_added_axis_domains:csv_table`.
- Repair: the adaptive-probe domain exclusion is now a real execution control
  instead of metadata. A repeatable `--adaptive-probe-exclude-domain` flag is
  plumbed through `main.py`, `MetaController`, `ProbeEngine`,
  `AdaptiveProbePlanner`, `run_official_closed_loop.py`,
  `run_official_strategy_ablation.py`, and
  `run_restore_axis_ablation_batch.py`.
- The restore-axis batch planner now supports `--apply-axis-action`. For
  `ablate_added_axis_domains:*`, it forwards the target domains to the closed
  loop command and drops the minimum smoke/adaptive axis floor to `0`, so the
  ablation is not rejected merely because the intentionally removed axis is
  missing.
- `plan_official_breakthrough_targets.py` can now emit restore-axis batch
  commands with `--restore-ablation-apply-axis-action`, preserving the same
  no-external, file-bridge, aggregate-only workflow while making the next
  command executable.
- Real current-state dry-run evidence for `wfxr__csview.8ac4de0`:
  - `applied_axis_exclude_domains=["csv_table"]`;
  - `effective_min_smoke_contract_axes=0`;
  - the generated child command includes
    `--adaptive-probe-exclude-domain csv_table`,
    `--skip-official-eval`, `--config config\smoke_file_bridge.yaml`, and the
    strict runtime-smoke dimensions;
  - this was a dry-run only, so it did not launch Docker, official eval, Kimi,
    or another external LLM.
- Verification:
  - `.\.venv\Scripts\python.exe -m py_compile ...` over the edited runtime,
    planner, runner, and focused test files passed.
  - `python -m ruff check ...` over the same edited files passed.
  - The focused regression suite passed as `178 passed`.
  - The strict official-ready ranker still returned `row_count=0`.
  - `scripts\audit_official_baseline_candidates.py --actionable-only` still
    printed only the table header.
- Difficulties and boundaries:
  - The first in-sandbox pytest attempt hit the known Windows ACL failure at
    `C:\Users\Administrator\.codex-tmp\pytest-of-Administrator` with
    `WinError 5`; rerunning the same focused suite outside that restrictive
    sandbox passed.
  - One real test failure surfaced during the first pytest run:
    `test_build_strategy_ablation_command_can_forward_local_llm_ack` used an
    older test `Namespace` without `max_local_holdout_gap`. The runner now
    reads that field with a backward-compatible default.
  - No official ProgramBench eval was run in this step. The repair makes the
    next no-external restore-axis experiment faithful to the audit diagnosis,
    but it is not itself an official aggregate breakthrough.
  - Kimi K2.6 was not used. The external-LLM fallback condition was not met
    because the internal ReBuilder/subagent path was sufficient to identify and
    wire the missing execution control.

### 2026-05-20 Csview Axis-Ablation Official Baseline Upgrade

- A real no-external `file_bridge` follow-up run executed the restored
  `wfxr__csview.8ac4de0` candidate with the `csv_table` adaptive-probe domain
  excluded, matching the restore-axis audit recommendation. A Codex subagent
  responded to four local bridge requests under
  `output\file_bridge_manual\requests_csview_axis_ablate_contractfix`; no Kimi
  K2.6 or external LLM API was used.
- Root cause of the previous gate failure: behavior-contract synthesis kept
  only the first limited slice of the corpus, so sparse dimensions such as
  safe `input_files` could be dropped before runtime smoke saw them. Runtime
  smoke also allowed error contracts to starve file-input contracts under the
  six-contract budget.
- Repair: `core\spec_synthesizer.py` now preserves representatives for sparse
  behavior dimensions when contract generation truncates a large corpus:
  safe input files, output files, safe env vars, stdin, and nonzero exit.
  `core\codebase\runtime_smoke.py` now keeps safe file-input contracts ahead
  of error-mode contracts in the limited smoke budget.
- Local ReBuilder evidence:
  `runs\file_bridge_no_external_csview_20260520_axis_ablate_contractfix\wfxr__csview.8ac4de0\generated\wfxr__csview.8ac4de0\wfxr__csview.8ac4de0\result.json`
  reports `resolved_rate=1.0`, holdout `12/12`, `file_bridge_harness_calls=4`,
  runtime smoke `passed`, and runtime dimensions `args/default/input_files/stdin`
  with `input_file_case_count=1`.
- Official ProgramBench aggregate evaluation completed on the packaged
  submission at
  `runs\file_bridge_no_external_csview_20260520_axis_ablate_contractfix_submission\axis_ablate_contractfix_eval\wfxr__csview.8ac4de0\submission.tar.gz`.
  The official result is a baseline upgrade: counted `291/335`, score `87`;
  raw `303/348`, score `87`; not fully resolved and not almost resolved. The
  previous recorded `csview` baseline was counted `190/335`, score `57`.
- The aggregate-only baseline registry was updated at
  `baselines\programbench\wfxr__csview.8ac4de0.baseline.json` with the new
  score-87 official summary. After recording it, the strict official-ready
  ranker correctly returned `row_count=0` because the candidate is no longer an
  unrecorded upgrade.
- Verification:
  - `.\.venv\Scripts\python.exe -m py_compile core\spec_synthesizer.py core\codebase\runtime_smoke.py tests\test_spec_synthesizer_parsing.py tests\test_codebase_integrity.py`
    passed.
  - `python -m ruff check core\spec_synthesizer.py core\codebase\runtime_smoke.py tests\test_spec_synthesizer_parsing.py tests\test_codebase_integrity.py`
    passed.
  - Focused regressions passed as `2 passed`; the related focused slice passed
    as `38 passed` outside the restrictive sandbox.
  - `scripts\rank_programbench_candidates.py --runs runs\file_bridge_no_external_csview_20260520_axis_ablate_contractfix --allow-existing-official --official-eligible-only --require-runtime-smoke-dimensions args,input_files,stdin --format json`
    returned one `eligible_baseline_upgrade` row before the baseline was
    recorded, and zero rows after recording the new baseline.
  - `scripts\audit_official_baseline_candidates.py --official-eval-root runs\file_bridge_no_external_csview_20260520_axis_ablate_contractfix_submission --baseline-root baselines\programbench --actionable-only`
    printed only the table header after the baseline update.
- Difficulties and boundaries:
  - The first axis-ablation local run passed holdout but failed the strict
    official-entry gate because runtime smoke still lacked `input_files`.
  - The first ProgramBench official eval attempt failed in the Windows console
    environment with GBK decoding/encoding errors and a ProgramBench
    `NoneType + str` TypeError. Re-running the same packaged submission with
    `PYTHONUTF8=1` and `PYTHONIOENCODING=utf-8` completed successfully.
  - Focused pytest needed to run outside the restrictive shell sandbox because
    the sandboxed pytest temp path hit the known Windows `WinError 5` ACL
    failure.
  - This is an official aggregate baseline upgrade, not a solved task. It must
    not be described as fully resolved or as proof that local holdout is
    equivalent to official hidden evaluation.

### 2026-05-20 Go-Mod Table Patch5 Official Baseline Upgrade

- A follow-up official-standard no-external run targeted
  `psampaz__go-mod-outdated.bb79367` through the ReBuilder `file_bridge`
  architecture. Two local Codex subagents were used for target selection and
  public-semantics repair design; the actual ReBuilder closed loop used local
  file-bridge responses only. Kimi K2.6, GLM, and other external LLM APIs were
  not used.
- Repair summary: `table_patch5` extends the prior go-mod table candidate with
  public Go CLI and module-list semantics rather than hidden eval feedback. It
  handles Go-style `--` flag termination, boolean flag forms, `style` value
  diagnostics, `json.Decoder`-style stream/truncation errors, defensive
  zero-value handling for module `Replace` and `Update` records, filtered
  `-ci` outdated-row exits, deterministic ASCII/Markdown table rendering, and
  display-width-aware alignment for wide Unicode module names.
- Gate hardening: the first strict run had perfect local holdout but only seven
  holdout cases, so the official-entry gate correctly stopped it with
  `holdout_cases=7 below min=10`. The `table_patch5` config then increased the
  internal holdout ratio to produce an 11-case holdout split. The passing
  ReBuilder run reported exploration `19/19`, holdout `11/11`, runtime smoke
  `passed`, and runtime dimensions `args/default/input_files/stdin`.
- Official ProgramBench aggregate evaluation completed at
  `runs\programbench_official_eval\submission_go_mod_outdated_table_patch5_20260520\psampaz__go-mod-outdated.bb79367\psampaz__go-mod-outdated.bb79367.eval.json`.
  The result is a real official aggregate baseline upgrade: counted `267/285`,
  score `94`; raw `316/342`, score `92`; `fully_resolved=false` and
  `almost_resolved=false`. The previous recorded go-mod baseline from
  `table_patch4` was counted `229/285`, score `80`, and the older pre-bridge
  baseline was score `15`.
- The aggregate-only baseline registry was updated at
  `baselines\programbench\psampaz__go-mod-outdated.bb79367.baseline.json` with
  model `codex-file-bridge-go-mod-table_patch5` and submission SHA-256
  `abc79e8e3140009a4a214bb5e13ff3fb00f7eb2d1aee0309e1b9dd733f6d8913`.
- Verification:
  - Focused TDD regressions for `table_patch5` first failed, then passed as
    `4 passed`:
    `.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp C:\tmp\rebuilder_pytest_go_mod_patch5_green3 tests\test_go_mod_file_bridge_harness.py`.
  - Syntax check passed:
    `.\.venv\Scripts\python.exe -m py_compile output\file_bridge_manual\run_go_mod_file_bridge.py tests\test_go_mod_file_bridge_harness.py`.
  - Lint check passed:
    `python -m ruff check output\file_bridge_manual\run_go_mod_file_bridge.py tests\test_go_mod_file_bridge_harness.py`.
  - Local official-entry run:
    `.\.venv\Scripts\python.exe output\file_bridge_manual\run_go_mod_file_bridge.py table_patch5 --force`
    -> exploration `19/19`, holdout `11/11`, runtime smoke passed.
  - Official eval run:
    `.\.venv\Scripts\python.exe output\file_bridge_manual\run_go_mod_file_bridge.py table_patch5 --official-eval --force`
    -> counted `267/285`, score `94`.
  - After the baseline update, the strict official-ready ranker returned
    `row_count=0` with required runtime-smoke dimensions
    `args,input_files,stdin` and `--max-local-holdout-gap 0.15`.
  - The generated config for this run contains only the `file_bridge` provider
    section; it does not include Kimi, GLM, or local OpenAI provider blocks.
- Difficulties and boundaries:
  - The cleanroom image was initially missing, so the first run failed before
    ReBuilder inference; rerunning with `--pull` prepared the image.
  - Pytest inside the restrictive Windows sandbox repeatedly hit temp-directory
    ACL failures (`WinError 5`), so focused tests were rerun with an explicit
    `C:\tmp` basetemp outside that restriction.
  - The repository `.venv` does not contain `ruff`, so the lint check used the
    available project-level `python -m ruff` command.
  - The first strict local gate stopped on insufficient holdout case count even
    though the rate was 100%; this is a useful anti-overfit guard and should be
    kept.
  - No hidden official failure details were used for the repair. Publish only
    aggregate official evidence, not detailed hidden test behavior.
  - This is an official aggregate baseline upgrade, not a solved task.

### 2026-05-20 Zip Password Finder Usage Patch2 Official Baseline Upgrade

- A follow-up no-external run targeted
  `agourlay__zip-password-finder.704700d` through the ReBuilder `file_bridge`
  architecture. The loop used local bridge responses inside ReBuilder for spec,
  architecture, implementation, local differential testing, packaging, and
  official aggregate evaluation. Kimi K2.6, GLM, and other external LLM APIs
  were not used.
- Repair summary: `usage_patch2` extends the earlier restore candidate with
  cleanroom-local CLI parser/validation precedence repairs. The patch validates
  unknown charset option letters before ZIP archive parsing, emits clap-style
  missing-value diagnostics with `<flag>` placeholders, validates explicit u64
  options before required-argument errors, and lets the harness pass
  `--pull` so missing cleanroom images can be prepared through the existing
  official cleanroom path.
- Local ReBuilder gate: focused TDD regressions first failed, then passed as
  `3 passed`. The full no-external local bridge run reached exploration
  `98/98` (`100%`), holdout `13/16` (`81.2%`), status `SUCCESS`, and runtime
  smoke `passed` with dimensions `args/default/input_files/stdin`.
- Official ProgramBench aggregate evaluation completed at
  `runs\programbench_official_eval\submission_zip_password_finder_usage_patch2_20260520\agourlay__zip-password-finder.704700d\agourlay__zip-password-finder.704700d.eval.json`.
  The result is a real official aggregate baseline upgrade over the previous
  score-36 record: counted `274/680`, score `40`; raw `366/792`, score `46`;
  `fully_resolved=false` and `almost_resolved=false`.
- The aggregate-only baseline registry was updated at
  `baselines\programbench\agourlay__zip-password-finder.704700d.baseline.json`
  with model `codex-file-bridge-zip-usage_patch2` and submission SHA-256
  `2dfa91d5a573f4da025988621e9bbbca78c564726940c87fe9291e6c11a9a8fe`.
- Verification:
  - Focused TDD regressions:
    `.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp tmp_pytest_zip_green3 tests\test_zip_file_bridge_harness.py`
    -> `3 passed`.
  - Local no-external bridge run:
    `.\.venv\Scripts\python.exe output\file_bridge_manual\run_zip_file_bridge.py usage_patch2`
    -> exploration `98/98`, holdout `13/16`, packaged submission.
  - Official eval run:
    `.\.venv\Scripts\python.exe output\file_bridge_manual\run_zip_file_bridge.py usage_patch2 --official-eval`
    -> counted `274/680`, score `40`; raw `366/792`, score `46`.
- Difficulties and boundaries:
  - The first `usage_patch2` run failed before ReBuilder inference because the
    zip cleanroom image was missing locally. The harness now passes `--pull`,
    using the existing official `task_cleanroom` preparation path rather than
    bypassing the cleanroom boundary.
  - Windows sandbox pytest repeatedly hit temp-directory ACL failures, so the
    focused tests were run with elevated workspace-local basetemps and then the
    generated temp directories needed cleanup.
  - The local gate still used only exploration failures and aggregate holdout.
    Official eval was used only for the final aggregate summary; no hidden
    official case details should be included in prompts, repairs, or release
    material.
  - This is an official aggregate baseline upgrade, not a solved task.

### 2026-05-20 File-Bridge Subagent Probe Closeout

- The remaining open subagent-backed `file_bridge` probe was closed out for
  `rbakbashev__elfcat.52f8cc7`. A subagent wrote
  `output\file_bridge_manual\requests_elfcat_holdout_probe1\response_1416c3e75fad429ea3310b5bea9ccc40.json`
  in the ReBuilder file-bridge response format. The outer response JSON parsed,
  the inner `content` parsed as a JSON list, it contained five adversarial ELF
  cases, the bytes payloads used JSON-safe base64 wrappers, and no unsafe file
  paths were present.
- The corresponding ReBuilder run now has a result artifact at
  `runs\missing_holdout_cleanroom_rerun\rbakbashev__elfcat.52f8cc7_probe1\rbakbashev__elfcat.52f8cc7\generated\rbakbashev__elfcat.52f8cc7\rbakbashev__elfcat.52f8cc7\result.json`.
  Its recorded LLM usage is 29 `file_bridge_subagent_calls`, with no external
  provider label.
- Local evidence from that result:
  - status: `failed`;
  - local resolved rate: `0.6428571428571429`;
  - holdout: `0.875` over 17 cases;
  - probes conducted: 68;
  - runtime smoke: `passed`, 8 cases, 6 contract cases, and dimensions
    `args/default/input_files/stdin`;
  - smoke/adaptive axis count: 13/13.
- Verification:
  - `scripts\rank_programbench_candidates.py --runs runs\missing_holdout_cleanroom_rerun --baseline-root baselines\programbench --official-eval-root runs\programbench_official_eval --allow-existing-official --require-runtime-smoke-dimensions args,input_files --format json --limit 20`
    returned one `elfcat` row with `official_gate=official_not_above_baseline`
    and `official_gate_blockers=["official_not_above_baseline"]`.
- Difficulties and boundaries:
  - One subagent's earlier audit was stale by the time it was collected: it
    reported no `result.json`, but the result artifact later appeared and was
    verified directly.
  - `scripts\rank_programbench_candidates.py` does not support a `--task`
    filter; scope it with `--runs` or filter output after the command.
  - This is positive evidence that a subagent can reason through ReBuilder's
    `file_bridge` architecture without Kimi K2.6 or another external LLM. It is
  not an official ProgramBench breakthrough because the run status is still
  `failed`, no new official eval was run here, and the ranking gate reports
  `official_not_above_baseline`.

### 2026-05-20 Subagent Official-Standard Continuation Audit

- After the `go-mod-outdated` score-94 upgrade, two read-only helper agents were
  asked to audit the next official-standard step without reading hidden
  case-level official failures. Both audits agreed that the next action should
  not be another immediate official eval: the strict official-ready ranker still
  returns `row_count=0` under `--allow-existing-official`,
  `--official-eligible-only`, `--latest-per-task`,
  `--require-runtime-smoke-dimensions args,input_files,stdin`, and
  `--max-local-holdout-gap 0.15`.
- The latest aggregate-only generalization-gap audit returns 10 blocked rows.
  The sharpest evidence is `chmln__sd.87d1ba5` at candidate score 80 vs recorded
  baseline 86, and `alecthomas__chroma.8d04def` at candidate score 0 vs recorded
  baseline 3 despite local exploration/holdout both being 100% for the latest
  no-external `file_bridge` candidate. `htmlq` is one counted pass below its
  score-91 baseline, while `go-mod-outdated` is now equal to the recorded
  score-94 baseline.
- Decision: do not use Kimi K2.6 as a fallback at this point. ReBuilder's
  `file_bridge` path has already proven that local subagent reasoning can be
  placed inside the architecture and evaluated with ProgramBench aggregate
  standards. The blocker is not lack of an LLM responder; it is that current
  candidates either regress, tie their baseline, miss runtime-smoke coverage, or
  show poor local-to-official predictiveness.
- Release boundary: present this as a gate discipline result, not a stall. The
  project has official aggregate upgrades (`elfcat`, `csview`, `go-mod`, `zip`
  usage_patch2) and same-score refinements (`clog`, `xsv`, `gron`), but the
  current queue has no clean official-ready candidate that should be submitted
  again without a new mechanism or stronger unseen local evidence.

### 2026-05-20 Generalization-Gap Gate Upgrade

- `scripts/audit_official_generalization_gaps.py` is now a safer automation
  gate, not only a report. JSON rows expose `official_eval_allowed=false`,
  `repeat_official_eval_recommended=false`,
  `evidence_boundary=aggregate_official_not_above_baseline`,
  `local_holdout_gap`, local/holdout-to-official pass-rate gaps, and optional
  task-scoped `next_command` values that rerun only the aggregate audit.
- The audit now accepts `--max-local-holdout-gap` to align this gap check with
  the existing anti-overfit ranker, and `--fail-on-gap` to exit non-zero after
  printing parseable JSON when any blocked row remains. This prevents an
  automation layer from treating "found 10 official-generalization gaps" as a
  green light for another official eval or an external LLM fallback.
- It also accepts `--sort-by diagnostic-priority` and emits
  `generalization_failure_mode` plus `diagnostic_priority`, so automation can
  rank local-green/official-collapse cases ahead of ordinary regressions. This
  is a repair triage signal only; it does not make a blocked candidate eligible
  for official submission.
- Real `runs` verification with strict runtime-smoke dimensions returned
  `total_row_count=10`: 3 `official_regressed`, 7 `official_equal_baseline`,
  and `would_fail=true`. The strict official-ready ranker still returned
  `row_count=0` under `--allow-existing-official`,
  `--official-eligible-only`, `--latest-per-task`,
  `--require-runtime-smoke-dimensions args,input_files,stdin`, and
  `--max-local-holdout-gap 0.15`.
- Follow-up hardening added counted `total_tests`, candidate raw aggregate,
  baseline raw aggregate when the baseline record points to a repo-local eval
  JSON, and raw score/passed deltas. These fields are still aggregate-only:
  they are built from `official_eval_summary` and `ProgramBenchEvalParser`, and
  tests assert hidden markers from candidate/baseline payloads are not emitted.
  Current `chroma` shows the intended diagnostic shape: local and holdout are
  both `1.0`, but counted official is `0/515`, raw official is `0/531`, and
  the recorded counted baseline is `13/515` score 3; the older baseline lacks a
  repo-local eval path, so `recorded_baseline_raw` is `null` rather than guessed
  from notes. With diagnostic sorting, `chroma` ranks first as
  `official_collapse_after_local_green` with priority `101.0`.
- Verification: focused tests for the gap audit pass as `8 passed` when run
  outside the restrictive shell sandbox; `py_compile` passed; `python -m ruff
  check scripts\audit_official_generalization_gaps.py
  tests\test_audit_official_generalization_gaps.py` passed. The same tests
  inside the normal sandbox still hit Windows temp-directory ACL failures, so
  this run required an elevated pytest invocation and cleanup of the generated
  temp directories.
- Remaining difficulty: raw baseline aggregate can only be populated when the
  baseline record contains a submission path whose sibling eval JSON exists
  locally. Older baselines without that artifact remain `null` by design; do
  not parse free-text notes as evidence.

### 2026-05-20 Chroma Generalization Probe Official Attempt

- A follow-up no-external `file_bridge` run targeted
  `alecthomas__chroma.8d04def` after the aggregate gap audit made it the
  sharpest local-green/official-collapse case. A read-only subagent first
  confirmed that the previous `restore_patch2` candidate should not be
  re-submitted directly: local holdout was green, but the embedded official
  aggregate was still score `0` against the recorded baseline score `3`.
- The audit script now reports local probe-domain sprawl from
  `implementation_metadata.probe_axis_coverage`. On the previous chroma
  candidate it detected five local probe domains
  (`csv_table`, `filesystem_tool`, `go_dependency_report`, `html_selector`,
  `json_transform`) and marked `probe_domain_sprawl=true`. This is an
  aggregate/local metadata diagnostic only; it does not inspect official hidden
  failures.
- Repair: `output\file_bridge_manual\run_chroma_file_bridge.py` gained a
  stricter `restore_patch2_generalization_probe` variant. It reuses the
  `restore_patch2` source, excludes the cross-task `csv_table`,
  `go_dependency_report`, and `json_transform` adaptive domains, injects one
  explicit probe iteration, and adds chroma-specific public CLI axes such as
  `--trace`, `--unbuffered`, lexer filename inference, formatter variants,
  missing style files, multi-file input, and HTML line/table/linkable output.
- Local ReBuilder gate evidence:
  - command:
    `.\.venv\Scripts\python.exe output\file_bridge_manual\run_chroma_file_bridge.py restore_patch2_generalization_probe --pull`;
  - result path:
    `runs\file_bridge_no_external_chroma_20260520_restore_patch2_generalization_probe\alecthomas__chroma.8d04def\generated\alecthomas__chroma.8d04def\alecthomas__chroma.8d04def\result.json`;
  - local status `partial`, resolved rate `95.7%`, exploration behavioral
    equivalence `67/70`, holdout `46/46`, probes `102`, and runtime smoke
    `passed` with dimensions `args/default/input_files/stdin`;
  - local probe coverage reported no uncovered CLI flags after the manual probe
    injection fix.
- Official-standard attempt: the harness now has an explicit
  `--run-official-eval` mode so official aggregate eval still runs under the
  same file-bridge responder. The attempted command was
  `.\.venv\Scripts\python.exe output\file_bridge_manual\run_chroma_file_bridge.py restore_patch2_generalization_probe --pull --run-official-eval --official-eval-timeout-seconds 3600`.
  It packaged the submission, launched ProgramBench official eval, then timed
  out after `3600` seconds without producing an `eval.json`.
- Failure artifact:
  `runs\file_bridge_no_external_chroma_20260520_restore_patch2_generalization_probe_submission\file_bridge_no_external_chroma_20260520_restore_patch2_generalization_probe_eval\official_eval_failure_report.json`
  records `reason=official_eval_failed_without_eval_json`, the 3600-second
  timeout, `stopped_eval_container_count=1`, `removed_compiled_image_count=1`,
  `submission_exists=true`, and `eval_json_exists=false`.
- Verification:
  - `.\.venv\Scripts\python.exe -m py_compile output\file_bridge_manual\run_chroma_file_bridge.py tests\test_chroma_file_bridge_harness.py`
    passed.
  - `python -m ruff check output\file_bridge_manual\run_chroma_file_bridge.py tests\test_chroma_file_bridge_harness.py`
    passed.
  - `.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp C:\tmp\rebuilder_pytest_chroma_harness_official_switch tests\test_chroma_file_bridge_harness.py`
    passed as `4 passed`.
- Difficulties and boundaries:
  - A direct `scripts\run_official_closed_loop.py` invocation hung because
    `file_bridge` needs a live harness process to answer request JSON files.
    That mistake left two waiting ReBuilder Python processes, which were
    identified by command line and stopped before continuing.
  - The first stricter local gate attempt had only `34` holdout cases and
    correctly refused official promotion. The actual cause was that the manual
    probe response was prepared but `--probe-iterations` was still `0`; the
    harness now uses one probe iteration and a higher holdout ratio for this
    variant.
  - The chroma official aggregate result is unavailable because ProgramBench
    timed out before writing `eval.json`. This step is therefore not an
    official aggregate breakthrough, not a solved task, and not evidence that
    local holdout predicts hidden official behavior.
  - Kimi K2.6, GLM, and other external LLM APIs were not used. The fallback
    condition was not met because the ReBuilder `file_bridge` path was
    available; the blocker was the official evaluator timeout, not lack of an
    LLM responder.

### 2026-05-20 Official Eval Failure Gate Repair

- Repair: `scripts\rank_programbench_candidates.py` now discovers adjacent
  aggregate-only `official_eval_failure_report.json` files and treats them as
  real official-eval attempts when no `*.eval.json` was produced. The exposed
  JSON fields are limited to `official_eval_failure_reason` and
  `official_eval_failure_report_path`; they do not include hidden official case
  details.
- Planner behavior: `scripts\plan_official_breakthrough_targets.py` now routes
  such rows to `target_class=official_eval_operational_failure`,
  `next_action=repair_official_eval_harness_before_more_official_eval`, and the
  recorded failure reason. The current `chroma` generalization-probe attempt is
  therefore blocked by `official_eval_failed_without_eval_json` instead of being
  misread as `missing_official_candidate_summary` or a baseline-ready candidate.
- Verification:
  - `.\.venv\Scripts\python.exe -m py_compile scripts\rank_programbench_candidates.py scripts\plan_official_breakthrough_targets.py tests\test_rank_programbench_candidates.py tests\test_plan_official_breakthrough_targets.py`
    passed.
  - `python -m ruff check scripts\rank_programbench_candidates.py scripts\plan_official_breakthrough_targets.py tests\test_rank_programbench_candidates.py tests\test_plan_official_breakthrough_targets.py`
    passed.
  - Elevated focused pytest was required because ordinary sandbox pytest still
    hits Windows basetemp ACL failures; the elevated run passed as `83 passed`.
  - Real planner JSON smoke now ranks
    `alecthomas__chroma.8d04def` first as
    `official_eval_operational_failure`, with blocker
    `official_eval_failed_without_eval_json` and the failure-report path under
    `runs\file_bridge_no_external_chroma_20260520_restore_patch2_generalization_probe_submission\...`.
- Boundary: no external Kimi/GLM provider was used, no additional official eval
  was launched in this repair step, and no official aggregate score improved.
  This is an anti-overclaim/operations-triage fix, not a ProgramBench
  breakthrough.

### 2026-05-20 Clog Patch6 Official Same-Score Negative Evidence

- Repair: `output\file_bridge_manual\run_clog_file_bridge.py` now has
  `from_latest_patch6`, which fixes the remaining visible cleanroom-local
  outfile padding mismatch from patch5. The patch is deliberately narrow: it
  only adjusts the empty-version, empty-existing-content, `--outfile` path that
  was exposed by local exploration evidence.
- Harness hardening: the same runner now exposes `--pull`, `--official-eval`,
  and `--force`, matching the newer no-external `file_bridge` runners. The
  default still stops after the local package gate; official ProgramBench eval
  only runs when explicitly requested.
- Local ReBuilder result: the no-external `file_bridge` run stayed inside the
  ReBuilder architecture, with five local bridge calls and no Kimi/GLM fallback.
  It reached exploration `106/106` and holdout `16/16`, then packaged
  successfully.
- Official aggregate result: ProgramBench official eval completed for
  `submission_clog_from_latest_patch6_20260520`, but the aggregate stayed equal
  to the recorded baseline: counted `260/575`, score `45`; raw `394/778`,
  score `51`. This is not an official score breakthrough, not a solved task,
  and not a baseline upgrade.
- Difficulties:
  - the cleanroom image was initially unavailable locally, and the manual
    `clog` runner did not yet expose `--pull`;
  - Docker Desktop access was blocked inside the normal sandbox, so the local
    gate and official eval needed elevated Docker access;
  - ordinary sandbox pytest still hit Windows basetemp ACL `WinError 5`; the
    focused test had to run elevated;
  - runtime smoke for this patch covered args/default/input_files but not
    stdin, so the strict official-ready ranker with required
    `args,input_files,stdin` still returned `row_count=0`;
  - no hidden official case details should be used to explain or tune this
    result; only aggregate official evidence is publishable.
- Verification:
  - `.\.venv\Scripts\python.exe -m py_compile output\file_bridge_manual\run_clog_file_bridge.py tests\test_clog_file_bridge_harness.py`
    passed.
  - `python -m ruff check output\file_bridge_manual\run_clog_file_bridge.py tests\test_clog_file_bridge_harness.py`
    passed.
  - Elevated focused pytest:
    `.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp C:\tmp\rebuilder_clog_patch6_pytest_20260520 tests\test_clog_file_bridge_harness.py`
    -> `1 passed`.
  - Strict official-ready ranker with
    `--require-runtime-smoke-dimensions args,input_files,stdin` and
    `--max-local-holdout-gap 0.15` still returned `row_count=0`.
  - Planner now classifies this `clog` candidate as
    `official_generalization_gap` with reason `official_not_above_baseline`.

### 2026-05-20 Elfcat Reference HTML Patch1 Official Upgrade

- Repair: `output\file_bridge_manual\run_elfcat_file_bridge.py` now has a
  `reference_html_patch1` variant for `rbakbashev__elfcat.52f8cc7`. It starts
  from the previous no-external generated implementation and injects a
  reference-like HTML renderer derived from visible cleanroom local evidence:
  static shell/CSS/JS shape, dynamic ELF64 header fields, file path handling,
  byte/ascii table output, and Rust-like malformed section-table panic text.
  The runner config uses only ReBuilder `file_bridge`; Kimi/GLM was not used.
- Harness coverage: `tests\test_elfcat_file_bridge_harness.py` covers the
  reference HTML shell for a dotfile ELF, path/endianness/AArch64 DYN metadata,
  and malformed section-string-table panic shape. It is local cleanroom
  evidence only and does not inspect official hidden cases.
- Local ReBuilder result: the no-external closed loop used 73 probes and
  reached exploration `97/119` (`81.5%`), holdout `15/18` (`83.3%`), runtime
  smoke status `passed`, and runtime smoke dimensions
  args/default/input_files/stdin. The package gate passed, but the local result
  still had `status=FAILED` and `almost_resolved=false`.
- Official aggregate result: ProgramBench official eval completed for
  `runs\programbench_official_eval\submission_elfcat_reference_html_patch1_20260520`.
  Counted result was `316/564`, score `56`; raw result was `390/646`, score
  `60`; `fully_resolved=false` and `almost_resolved=false`. This is a real
  official aggregate baseline upgrade over the previous elfcat score-38 record,
  but it is still not a solved task.
- Baseline record: `baselines\programbench\rbakbashev__elfcat.52f8cc7.baseline.json`
  then recorded model `codex-file-bridge-elfcat-reference_html_patch1`, counted
  `316/564`, score `56`, and submission SHA-256
  `6c6c56e9837d06dd5e52b8a0c936883a3c2e4504b40f6a8414876d5d0564dddb`.
  The current baseline was later upgraded by `reference_html_patch4` to score
  `66`.
- Difficulties:
  - strict ranking before official eval reported
    `missing_official_candidate_summary` because existing-baseline upgrades now
    require an embedded official aggregate summary before they can be treated as
    upgraded;
  - after the official eval refreshed the baseline to score 56, the same strict
    gate reports `official_not_above_baseline`, which means the candidate is now
    equal to the current baseline, not that the breakthrough failed;
  - ordinary sandbox pytest still hit Windows basetemp ACL `WinError 5`, so the
    focused harness pytest had to run elevated;
  - Docker/ProgramBench official eval required elevated Docker access;
  - remaining local failure clusters are still file-output HTML byte equality,
    malformed string-table/range panic shape, and one directory-input errno
    stderr difference. These are local cleanroom failure clusters, not official
    hidden case details.
- Verification:
  - `.\.venv\Scripts\python.exe -m py_compile output\file_bridge_manual\run_elfcat_file_bridge.py tests\test_elfcat_file_bridge_harness.py`
    passed.
  - `python -m ruff check output\file_bridge_manual\run_elfcat_file_bridge.py tests\test_elfcat_file_bridge_harness.py`
    passed.
  - Elevated focused pytest:
    `.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp C:\tmp\rebuilder_elfcat_patch1_pytest_20260520d tests\test_elfcat_file_bridge_harness.py`
    -> `3 passed`.
  - Local cleanroom reference HTML smoke matched four visible evidence outputs
    byte-for-byte before the ReBuilder gate run.
  - Official ProgramBench eval wrote
    `runs\programbench_official_eval\submission_elfcat_reference_html_patch1_20260520\rbakbashev__elfcat.52f8cc7\rbakbashev__elfcat.52f8cc7.eval.json`.

## 2026-05-21 XSV Restore Patch2 Local Negative Evidence

### Publishable Summary

The `burntsushi__xsv.f430466` follow-up stayed on the no-external ReBuilder
`file_bridge` path. `output\file_bridge_manual\run_xsv_file_bridge.py` now has
a `restore_patch2` variant that keeps the prior restore implementation and adds
two narrow local repairs:

- `frequency` tie ordering is now deterministic by descending count and lexical
  value order;
- empty `xsv index` arguments now return the locally observed invalid-argument
  diagnostic shape.

This produced a valid local ReBuilder run and package, but it did not improve
the current holdout evidence. The local result was exploration `83/102`
(`81.4%`), holdout `12/15` (`80.0%`), runtime smoke `passed`, with dimensions
`args/default/input_files/stdin`. The package was written under
`runs\file_bridge_no_external_xsv_20260521_restore_patch2_submission\file_bridge_no_external_xsv_20260521_restore_patch2_eval\burntsushi__xsv.f430466\submission.tar.gz`.

The official-ready strict gate remained empty:
`rank_programbench_candidates.py --allow-existing-official --official-eligible-only --latest-per-task --require-runtime-smoke-dimensions args,input_files,stdin --max-local-holdout-gap 0.15`
returned `row_count=0`. `audit_holdout_improvement.py` also reported
`improved=false`, with best previous holdout `0.8181818181818182` and current
holdout `0.8`. Because the local holdout signal did not improve, this package
was not submitted to ProgramBench official eval.

### Difficulties

- The repo `.venv` did not provide `ruff`, so lint was run with the available
  `python -m ruff`.
- Focused pytest hit the recurring Windows `C:\tmp` basetemp `WinError 5`
  under the ordinary sandbox and had to be rerun elevated.
- The local Docker image existed, but sandboxed Docker access could not see or
  use it reliably; the ReBuilder local run needed elevated Docker access.
- The result is a local mechanism repair and a negative official-candidate
  signal, not an official aggregate breakthrough.

### Verification

- `.\.venv\Scripts\python.exe -m py_compile output\file_bridge_manual\run_xsv_file_bridge.py tests\test_xsv_file_bridge_harness.py`
  passed.
- `python -m ruff check --no-cache output\file_bridge_manual\run_xsv_file_bridge.py tests\test_xsv_file_bridge_harness.py`
  passed.
- Elevated focused pytest:
  `.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp C:\tmp\rebuilder_xsv_patch2_pytest_20260521 tests\test_xsv_file_bridge_harness.py`
  -> `2 passed`.
- No ProgramBench official eval was run for `restore_patch2`.

## 2026-05-21 CHMLN Baseline Regex Patch1 Official Refinement

### Publishable Summary

The `chmln__sd.87d1ba5` follow-up also stayed on the no-external ReBuilder
`file_bridge` path. `output\file_bridge_manual\run_chmln_file_bridge.py`
restores the recorded 2026-05-18 score-86 official baseline submission from
`runs\programbench_official_eval_subagent_20260518\subagent_chmln_20260518\chmln__sd.87d1ba5\submission.tar.gz`
and applies a narrow local repair to Rust-style regex diagnostics for unclosed
groups. It preserves the existing look-around and parser diagnostic behavior
covered by the harness.

The first local run exposed a runner serialization issue rather than a semantic
sd bug: the baseline tarball source carried CRLF newlines, and Windows text
writing expanded the generated file into `0D 0D 0A` line endings. That inserted
blank lines into help output and produced four local stdout mismatches. The
runner now normalizes the baseline source to LF immediately after reading the
tarball.

After the LF fix, the no-external ReBuilder closed loop reached exploration
`40/40` (`100.0%`), holdout `12/12` (`100.0%`), status `SUCCESS`,
`almost_resolved=true`, and runtime smoke dimensions
`args/default/input_files/stdin`. Packaging succeeded at
`runs\file_bridge_no_external_chmln_20260521_baseline_regex_patch1_submission\file_bridge_no_external_chmln_20260521_baseline_regex_patch1_eval\chmln__sd.87d1ba5\submission.tar.gz`.

The same no-external package was then submitted to ProgramBench official eval.
Official aggregate completed with counted `699/810`, score `86`, raw
`752/869`, raw score `87`, `fully_resolved=false`, and
`almost_resolved=false`. This refreshes the recorded score-86 baseline from
`697/810` counted to `699/810` counted, but the rounded official score did not
increase and the task is not solved.

After the baseline update, the strict official-ready ranker still returned
`row_count=0`; the same candidate is now blocked by `official_not_above_baseline`
because it is the recorded baseline. This is therefore a same-score counted
refinement and release-evidence update, not an official score breakthrough.

### Difficulties

- The root cause of the initial `36/40` local result was newline expansion in
  the file_bridge runner, not the regex repair itself.
- Focused pytest again required elevated execution because ordinary sandboxed
  pytest could not create its `C:\tmp` basetemp.
- ReBuilder's local ProgramBench run and official ProgramBench eval required
  elevated Docker access.
- Ordinary `git status` is blocked by Windows dubious-ownership protection in
  this checkout; status checks should use a one-shot
  `git -c safe.directory=...` read instead of changing global git config.
- `audit_generalization_risk.py` in this checkout does not support a task-scoped
  `--task` argument, so task-specific generalization evidence should come from
  ranker/holdout audits unless that CLI is extended.
- The official aggregate improved counted tests within the same rounded score
  bucket only. Do not present this as a score breakthrough, solved task, or
  hidden-test-guided repair.

### Verification

- `.\.venv\Scripts\python.exe -m py_compile output\file_bridge_manual\run_chmln_file_bridge.py tests\test_chmln_file_bridge_harness.py`
  passed.
- `python -m ruff check --no-cache output\file_bridge_manual\run_chmln_file_bridge.py tests\test_chmln_file_bridge_harness.py`
  passed.
- Elevated focused pytest:
  `.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp C:\tmp\rebuilder_chmln_patch1_lf_pytest_20260521 tests\test_chmln_file_bridge_harness.py`
  -> `4 passed`.
- `Format-Hex` on generated `main.py` showed normal `0D 0A` sequences rather
  than the earlier `0D 0D 0A` expansion.
- Local ReBuilder `file_bridge` run:
  `.\.venv\Scripts\python.exe output\file_bridge_manual\run_chmln_file_bridge.py baseline_regex_patch1`
  -> exploration `40/40`, holdout `12/12`, package written.
- Official ProgramBench eval:
  `.\.venv\Scripts\python.exe output\file_bridge_manual\run_chmln_file_bridge.py baseline_regex_patch1 --official-eval`
  -> counted `699/810`, score `86`, raw `752/869`, raw score `87`.
- Aggregate summarizer:
  `.\.venv\Scripts\python.exe scripts\summarize_programbench_eval.py runs\programbench_official_eval\submission_chmln_baseline_regex_patch1_20260521\chmln__sd.87d1ba5\chmln__sd.87d1ba5.eval.json --instance-id chmln__sd.87d1ba5`
  reported the same counted/raw aggregate and `fully_resolved=false`.
- Strict official-ready ranker after the baseline update still returned
  `row_count=0`; the same candidate is now an `official_not_above_baseline`
  baseline row, not a repeat-eval target.

## 2026-05-21 Planner Local-Generalization Routing Repair

### Publishable Summary

The target planner now separates official aggregate gaps from local
generalization gaps before any further official-eval attempt. In the previous
planner output, a candidate such as `burntsushi__xsv.f430466` could still be
shown as `ready_baseline_gate` even when the strict baseline gate listed
aggregate blockers like `local_holdout_gap_too_high`. That made the dry-run
queue too easy to misread as an official-ready queue.

`scripts\plan_official_breakthrough_targets.py` now routes those rows to
`target_class=local_generalization_gap`,
`next_action=repair_local_generalization_before_official_eval`, and emits a
task-scoped `scripts/audit_generalization_risk.py --task ...` next command.
`scripts\audit_generalization_risk.py` now accepts repeatable `--task` filters,
so a single candidate can be checked without scanning or publishing the whole
run history.

The real `xsv restore_patch2` smoke now reports
`target_class=local_generalization_gap`, reason
`local_holdout_gap_too_high`, with blockers
`missing_official_candidate_summary` and `local_holdout_gap_too_high`.
The task-scoped risk audit reports local `0.9706`, holdout `0.8000`, gap
`0.1706`, `risk_level=high`, and `block_official_eval=true`.

This is a framework-quality fix, not an official aggregate breakthrough. It
keeps no-external ReBuilder/subagent evaluation aligned with the official
standard by preventing local-overfit or weak-holdout candidates from being
treated as ready for another official submission.

### Difficulties

- The first patch attempt failed because one test file had drifted from the
  expected context; the fix was reapplied in smaller chunks.
- `.venv` does not provide `ruff`, so linting used the project-level
  `python -m ruff` module.
- Ordinary sandboxed pytest still hit Windows
  `C:\Users\Administrator\.codex-tmp\pytest-of-Administrator` ACL errors;
  focused pytest had to be rerun elevated.
- The no-external path remains valid. No Kimi/GLM fallback, Docker official
  eval, or external LLM call was made in this planner repair pass.

### Verification

- `.\.venv\Scripts\python.exe -m py_compile scripts\plan_official_breakthrough_targets.py scripts\audit_generalization_risk.py tests\test_plan_official_breakthrough_targets.py tests\test_audit_generalization_risk.py`
  passed.
- `python -m ruff check --no-cache scripts\plan_official_breakthrough_targets.py scripts\audit_generalization_risk.py tests\test_plan_official_breakthrough_targets.py tests\test_audit_generalization_risk.py`
  passed.
- Elevated focused pytest:
  `.\.venv\Scripts\python.exe -m pytest tests\test_plan_official_breakthrough_targets.py tests\test_audit_generalization_risk.py -q`
  -> `23 passed`.
- Real planner smoke with strict runtime dimensions and local/holdout gap gate:
  `row_count=13`; `burntsushi__xsv.f430466` is now
  `local_generalization_gap`, not `ready_baseline_gate`.
- Real task-scoped risk audit:
  `scripts\audit_generalization_risk.py --task burntsushi__xsv.f430466`
  -> `row_count=1`, `risk_reason=local_holdout_gap_too_high`,
  `block_official_eval=true`.

### Safe External Narrative

Useful public phrasing:

> We hardened ReBuilder's cleanroom loop after observing that file-based
> adversarial tests from a local subagent could be serialized in a JSON-safe
> bytes format but were not decoded on the way back into differential testing.
> The fix lets local no-external-LLM responders participate in the same
> ReBuilder validation pipeline without dropping file-input cases.

> We also used the same `file_bridge` path to run a local subagent inside the
> ReBuilder loop for `elfcat`, then evaluated the resulting package with the
> official ProgramBench evaluator. The aggregate score improved from the
> historical score-17 record to score 38, while remaining far from a solved task.

> A later `elfcat` reference-HTML follow-up stayed on the no-external
> ReBuilder `file_bridge` path and improved the official aggregate baseline
> again, from score 38 to score 56. It is still not solved, but it is a clean
> aggregate upgrade with publishable local repair and difficulty records.

> A later bounded-rendering `elfcat` follow-up stayed on the same no-external
> path and improved the counted official aggregate baseline again, from score
> 56 to score 66. The task remains unsolved, but the improvement is backed by
> an official aggregate eval JSON and a reproducible local gate.

> A later `csview` restore-axis follow-up used a local subagent through
> ReBuilder's `file_bridge` provider, preserved sparse file-input contracts in
> runtime smoke, and produced an official aggregate baseline upgrade from score
> 57 to score 87. The result is not solved, but it is a clean aggregate
> improvement without an external LLM fallback.

> A later `go-mod-outdated` follow-up used local subagent review and
> ReBuilder's no-external `file_bridge` loop to harden public Go CLI, JSON
> stream, module update, and table-rendering semantics. The official aggregate
> baseline improved from the prior score 80 record to score 94, while still not
> reaching a solved-task state.

> A later `zip-password-finder` follow-up used the same no-external
> `file_bridge` path to repair public CLI parser and validation precedence. The
> official aggregate baseline improved from score 36 to score 40, while still
> not reaching a solved-task state.

> A later `xsv` follow-up repaired two local restore behaviors through the same
> no-external `file_bridge` path, but holdout evidence did not improve, so it
> was kept as local negative evidence rather than submitted to official eval.

> A later `chmln/sd` follow-up repaired a local Rust-regex diagnostic mismatch
> and a Windows newline serialization bug in the bridge runner, reaching local
> exploration and holdout 100%. ProgramBench official eval then refreshed the
> score-86 aggregate baseline from counted `697/810` to `699/810`, but the
> rounded official score stayed 86, so this is a same-score counted refinement
> rather than an official score breakthrough.

Avoid claiming:

- that this fix solved a ProgramBench task;
- that local holdout or replay results are equivalent to official hidden tests;
- that external Kimi K2.6 was used in this run;
- that the `elfcat` result is fully resolved or close to solved; the current
  aggregate baseline is score 66, upgraded from the earlier score-38 and
  score-56 records,
  but it remains neither `fully_resolved` nor `almost_resolved`;
- that the earlier `clog` restore-axis retry produced an official score; it
  stopped at holdout `14/18` and official eval was skipped;
- that the later `clog` patch5 run was an official score breakthrough; it
  completed official eval and improved counted tests to `260/575`, but the
  rounded official score stayed `45`;
- that the later `clog` patch6 run improved the official score; it fixed a
  local outfile mismatch and reached local/holdout 100%, but official aggregate
  remained counted `260/575`, score `45`;
- that `zip-password-finder` usage_patch1 improved the official baseline; it
  matched the existing score-36 aggregate baseline. Only usage_patch2 upgraded
  the aggregate score to 40, and it is still not solved;
- that the `xsv` follow-up improved the rounded official score; it only
  improved counted passed tests within the same score-44 aggregate bucket;
- that `xsv restore_patch2` was officially evaluated; it was stopped at local
  evidence because holdout did not improve over the previous best;
- that `chmln baseline_regex_patch1` produced a new rounded official score;
  it completed official eval and improved counted tests to `699/810`, but the
  ProgramBench info score stayed `86`;
- that the earlier `csview` patch8 restore attempt entered official eval; it
  stopped at local holdout `8/14` and missing input-files runtime-smoke
  coverage. The later axis-ablation contractfix run is a separate official
  aggregate baseline upgrade to score 87, not a solved task;
- that `go-mod-outdated` table_patch5 fully solved the task; it is an official
  aggregate upgrade to score 94, not `fully_resolved` or `almost_resolved`;
- any hidden test failure details or non-aggregate official evidence.

## 2026-05-21 Chroma Patch3 And Htmlq Patch4 Official-Standard Follow-Up

### Publishable Summary

This pass continued the no-external-LLM `file_bridge` route inside the
ReBuilder architecture, with a read-only subagent first auditing the official
candidate boundary. The subagent confirmed that the strict official-ready
ranker still returned `row_count=0`, and recommended `chroma` as the top
no-external repair target because its latest local/holdout evidence was strong
while the blocker was official-eval operations, not a visible local failure.

Two narrow public-behavior repairs were made:

- `htmlq` gained a `patch4` bridge variant that fixes whitespace around
  explicit CSS combinators (`>`, `+`, `~`), adds common structural pseudo-class
  support such as `:empty`, `:only-child`, `:first-of-type`,
  `:last-of-type`, `:nth-of-type`, and splits selector groups only on
  top-level commas. The harness config was also reduced to the active
  `file_bridge` provider so Kimi/GLM/local OpenAI stanzas are not present in
  the no-external path.
- `chroma` gained a `restore_patch3_generalization_probe` variant. It keeps
  the previous restore source, removes the non-active local OpenAI stanza from
  the generated config, preserves missing XML style-file diagnostics, and
  handles public HTML line-table/linkable-line/highlight flags without treating
  `--style github` as an input file.

The `chroma` patch3 no-external ReBuilder run improved local exploration from
`67/70` to `68/70`, kept holdout at `46/46` (`100%`), passed runtime smoke with
`args`, `stdin`, `input_files`, and `default`, and produced a submission tarball.
A bounded ProgramBench official aggregate attempt was then run with
`--official-eval-timeout-seconds 600`. It timed out after `Fetching ... files:
3it`, produced no `*.eval.json`, wrote an aggregate-only failure report, stopped
one matching eval container, and removed one matching compiled image. Therefore
this is not an official aggregate breakthrough and no baseline should be
updated.

### Evidence

- Local `chroma` patch3 result:
  `runs\file_bridge_no_external_chroma_20260521_restore_patch3_generalization_probe\alecthomas__chroma.8d04def\generated\alecthomas__chroma.8d04def\alecthomas__chroma.8d04def\result.json`
  with exploration `68/70`, holdout `46/46`, and runtime-smoke dimensions
  `args/stdin/input_files/default`.
- Official bounded attempt failure report:
  `runs\file_bridge_no_external_chroma_20260521_restore_patch3_generalization_probe_submission\file_bridge_no_external_chroma_20260521_restore_patch3_generalization_probe_eval\official_eval_failure_report.json`
  with reason `official_eval_failed_without_eval_json`, timeout `600`, no eval
  JSON, one stopped eval container, and one removed
  `programbench-compiled/alecthomas__chroma.8d04def:*` image.
- Strict official-ready ranker after the attempt still returned
  `row_count=0`.
- Planner still ranks `alecthomas__chroma.8d04def` first, but as
  `target_class=official_eval_operational_failure`, next action
  `repair_official_eval_harness_before_more_official_eval`.
- `audit_official_eval_gate.py` on the patch3 result reports
  `eligible=false`, reason `official_eval_failed_without_eval_json`.
- Docker verification after cleanup showed no running ProgramBench/chroma eval
  container and no remaining `programbench-compiled/alecthomas__chroma.8d04def`
  image.

### Difficulties

- The normal sandbox could not see or use the required ProgramBench cleanroom
  Docker image for `htmlq` or `chroma`; the official-standard `chroma` local
  loop needed elevated Docker access and `--pull`.
- The official `chroma` evaluator repeated the known operational failure mode:
  it stalled after fetching three files and did not write an aggregate eval
  JSON within the 600-second bound.
- `.venv` does not provide `ruff`; lint verification used project/global
  `python -m ruff`.
- Initial pytest with `tmp_path` hit the known Windows
  `C:\Users\Administrator\.codex-tmp\pytest-of-Administrator` ACL issue. The
  focused harness tests were rewritten to avoid `tmp_path` and then passed
  without needing to claim broad pytest health.

### Verification

- `.\.venv\Scripts\python.exe -m py_compile output\file_bridge_manual\run_chroma_file_bridge.py output\file_bridge_manual\run_htmlq_file_bridge.py output\file_bridge_manual\htmlq_patch4.py tests\test_chroma_file_bridge_harness.py tests\test_htmlq_file_bridge_harness.py`
  passed.
- `.\.venv\Scripts\python.exe -B -m pytest -p no:cacheprovider tests\test_chroma_file_bridge_harness.py tests\test_htmlq_file_bridge_harness.py -q`
  -> `10 passed`.
- `python -m ruff check --no-cache output\file_bridge_manual\run_chroma_file_bridge.py output\file_bridge_manual\run_htmlq_file_bridge.py tests\test_chroma_file_bridge_harness.py tests\test_htmlq_file_bridge_harness.py`
  passed.

### Safe External Narrative

Useful public phrasing:

> We continued the no-external ReBuilder `file_bridge` evaluation path with a
> local subagent-style responder and a bounded official-standard ProgramBench
> attempt. The `chroma` candidate improved local exploration while preserving
> 100% holdout, but ProgramBench official eval timed out without an aggregate
> JSON, so the result is recorded as an official-eval operations blocker rather
> than a benchmark breakthrough.

Avoid claiming:

- that `chroma restore_patch3_generalization_probe` has an official aggregate
  score;
- that the local `68/70` exploration and `46/46` holdout result predicts hidden
  official behavior;
- that external Kimi K2.6, GLM, or another external LLM was used;
- that this pass updated a ProgramBench baseline or solved a task.

## 2026-05-21 Zip Patch3 And Xsv Patch4 Official-Standard Follow-Up

### Publishable Summary

This pass continued the official-standard no-external route inside the
ReBuilder architecture. A read-only subagent first audited the `zip` and `xsv`
candidate boundary. The actual inference/evaluation path stayed on
`file_bridge`; Kimi K2.6, GLM, local OpenAI, and other external providers were
not used because the ReBuilder-internal route was available.

Two repair lines were attempted:

- `zip-password-finder` gained `usage_patch3`. The generated config now contains
  only the active `file_bridge` provider, and the harness adds an invalid
  file-number probe before the missing-input-file scenario. The local
  official-standard loop reached exploration `99/99` and holdout `13/16`, with
  runtime-smoke dimensions `args`, `input_files`, and `stdin`.
- `xsv` gained `restore_patch3` and `restore_patch4`. Patch3 tested
  first-seen frequency tie ordering and moved local exploration to `100/102`
  but exposed normal `stats` float-output drift. Patch4 repaired normal
  `stats` with sequential summation and Welford population statistics, while
  preserving prior `stats --everything` behavior.

Neither candidate was submitted to official aggregate evaluation in this pass.
Both remained blocked by local official-ready gates:

- `zip usage_patch3` was marked high risk by the generalization audit because
  the local holdout gap remained `0.1875`;
- `xsv restore_patch4` was marked high risk because the local holdout gap
  remained about `0.1804`, and the strict official-ready ranker still returned
  `row_count=0`.

This is therefore recorded as a disciplined gate-stop and repair log, not as an
official ProgramBench breakthrough.

### Evidence

- `zip usage_patch3` result:
  `runs\file_bridge_no_external_zip_20260521_usage_patch3\agourlay__zip-password-finder.704700d\generated\agourlay__zip-password-finder.704700d\agourlay__zip-password-finder.704700d\result.json`
  with exploration `99/99`, holdout `13/16`, provider `file_bridge`, and
  runtime-smoke dimensions `args/input_files/stdin`.
- `zip usage_patch3` submission package:
  `runs\file_bridge_no_external_zip_20260521_usage_patch3_submission\file_bridge_no_external_zip_20260521_usage_patch3_eval\agourlay__zip-password-finder.704700d\submission.tar.gz`.
- `zip` generalization audit:
  `risk_level=high`, `risk_reason=local_holdout_gap_too_high`,
  `block_official_eval=true`, latest local resolved rate `1.0`, latest holdout
  gap `0.1875`.
- `xsv restore_patch3` result improved local exploration to `100/102` and kept
  holdout at `12/15`, but still failed the normal `stats` case because float
  formatting/statistics did not match the reference exactly.
- `xsv restore_patch4` result:
  `runs\file_bridge_no_external_xsv_20260521_restore_patch4\burntsushi__xsv.f430466\generated\burntsushi__xsv.f430466\burntsushi__xsv.f430466\result.json`
  with exploration `100/102`, holdout `12/15`, provider `file_bridge`, and
  runtime-smoke dimensions `args/stdin/input_files/default`.
- `xsv restore_patch4` submission package:
  `runs\file_bridge_no_external_xsv_20260521_restore_patch4_submission\file_bridge_no_external_xsv_20260521_restore_patch4_eval\burntsushi__xsv.f430466\submission.tar.gz`.
- `xsv restore_patch4` remaining failure report:
  `runs\file_bridge_no_external_xsv_20260521_restore_patch4\burntsushi__xsv.f430466\reports\burntsushi__xsv.f430466.exploration.failures.json`,
  now reduced to two `frequency_analysis` ordering failures.
- The `xsv frequency` tie-order evidence is inconsistent across local
  reference records. Patch3 expected `size,M,1` before `size,L,1` for one
  adaptive record, while patch4 expected `size,L,1` before `size,M,1` for the
  same public stdin shape. This makes a single hard-coded equal-count ordering
  unsafe without broader evidence.
- Strict official-ready ranker after `xsv restore_patch4` still returned
  `row_count=0`.
- `audit_official_eval_gate.py` on the `xsv restore_patch4` result reported
  `eligible=false`, reason `missing_official_candidate_summary`, while runtime
  smoke itself had passed with the required dimensions.

### Difficulties

- ProgramBench cleanroom loops required elevated Docker access; the normal
  sandbox could not run the complete no-external task loop.
- Focused pytest runs hit the known Windows ACL issue under
  `C:\Users\Administrator\.codex-tmp\pytest-of-Administrator`; verification
  used elevated pytest with `--basetemp C:\tmp\...`.
- The repo `.venv` still did not provide `ruff`; lint verification used
  project/global `python -m ruff`.
- Ordinary `git status` hit Git's dubious-ownership guard for this checkout;
  status inspection used a one-shot `safe.directory` override.
- `audit_official_eval_gate.py` does not accept `--result`, `--format`, or
  `--max-local-holdout-gap`; the correct invocation uses the result JSON path
  as the positional argument.
- No hidden official failure details were available or used. All decisions here
  are based on local official-standard results, aggregate baseline records, and
  gate outputs.

### Verification

- `.\.venv\Scripts\python.exe -m py_compile output\file_bridge_manual\run_zip_file_bridge.py tests\test_zip_file_bridge_harness.py`
  passed.
- `python -m ruff check --no-cache output\file_bridge_manual\run_zip_file_bridge.py tests\test_zip_file_bridge_harness.py`
  passed.
- `.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp C:\tmp\rebuilder_zip_patch3_pytest_20260521 tests\test_zip_file_bridge_harness.py`
  -> `4 passed`.
- `.\.venv\Scripts\python.exe output\file_bridge_manual\run_zip_file_bridge.py usage_patch3`
  completed with local exploration `99/99` and holdout `13/16`.
- `.\.venv\Scripts\python.exe -m py_compile output\file_bridge_manual\run_xsv_file_bridge.py tests\test_xsv_file_bridge_harness.py`
  passed.
- `python -m ruff check --no-cache output\file_bridge_manual\run_xsv_file_bridge.py tests\test_xsv_file_bridge_harness.py`
  passed.
- `.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp C:\tmp\rebuilder_xsv_patch4_pytest_20260521 tests\test_xsv_file_bridge_harness.py`
  -> `8 passed`.
- `.\.venv\Scripts\python.exe output\file_bridge_manual\run_xsv_file_bridge.py restore_patch4`
  completed with local exploration `100/102` and holdout `12/15`.

### Safe External Narrative

Useful public phrasing:

> We placed a ReBuilder-internal `file_bridge` responder on the
> official-standard ProgramBench path and used a read-only subagent to audit the
> candidate boundary. `zip-password-finder` reached a clean local exploration
> result but still failed the generalization gate, while `xsv` repaired its
> normal `stats` behavior and exposed unstable equal-count `frequency` ordering.
> Both candidates were stopped before official aggregate submission because the
> official-ready gates did not clear.

Avoid claiming:

- that `zip usage_patch3` or `xsv restore_patch4` has a new official aggregate
  score;
- that either task is solved;
- that Kimi K2.6, GLM, local OpenAI, or another external LLM was used;
- that local exploration/holdout results predict hidden official behavior;
- that the observed `xsv frequency` tie ordering is a stable public contract.

## 2026-05-23 No-External Subagent Boundary, xsv Patch6, And Zip Domain Filter

### Summary

- Requirement captured: official-set testing may need reasoning, but subagents
  must be placed inside ReBuilder's no-external path, preferably through
  `file_bridge`; do not call external LLM services for official-test work.
- Planner repair: `local_generalization_gap` next commands now default to
  `--config config/smoke_file_bridge.yaml` and `--ack-local-llm-docker` even
  when the operator does not pass `--rerun-config`.
- xsv `restore_patch6` repaired one local stdin frequency-tie behavior in the
  ignored manual file_bridge harness, then ran a no-external local closed loop.
  It reached exploration `102/102` and holdout `12/15`, matching patch5's
  holdout and remaining below the strict local-gap gate.
- A read-only helper audit recommended testing whether `zip-password-finder`
  was being harmed by cross-domain adaptive probes. The new
  `usage_patch4_domain_filter` path excludes non-archive adaptive domains from
  the zip harness. The resulting no-external local closed loop contained only
  `archive_compression` probe axes, but regressed to exploration `92/92` and
  holdout `10/13`, so the harness correctly skipped official eval.
- The strict official-ready ranker still returned `row_count=0`; no official
  eval was run for xsv patch6 or zip usage_patch4, and this is not an official
  breakthrough.
- `chroma` gained explicit official-eval resource controls in the manual
  no-external `file_bridge` harness: official-eval timeout, Docker command
  timeout, worker counts, Docker CPU limit, branch retry count, and force mode.
  A bounded official retry for `restore_patch3_generalization_probe` kept the
  ReBuilder `file_bridge` path active, repackaged the same no-external
  candidate, and then timed out after 2400 seconds without an official eval
  JSON. The fresh aggregate-only failure report was written at
  `runs\file_bridge_no_external_chroma_20260521_restore_patch3_generalization_probe_submission\file_bridge_no_external_chroma_20260521_restore_patch3_generalization_probe_eval\official_eval_failure_report.json`
  with `timeout_seconds=2400`, `eval_json.exists=false`, one stopped
  ProgramBench eval container, and one removed compiled `chroma` image. This is
  still an official-eval operations blocker, not an official aggregate
  improvement.
- `xsv` gained a narrow `restore_patch7` repair for the public
  `frequency -n/--no-headers` behavior: the first row is counted as data and
  fields are labeled with 1-based column numbers. The change was proposed by a
  read-only helper audit and implemented only in the no-external
  `file_bridge` manual harness. Its local no-official run improved holdout from
  patch6's `12/15` to `13/15`, but the official run's fresh local split landed
  at `12/15`; it still passed the package gate and produced an official
  aggregate baseline upgrade. The official aggregate result for
  `submission_xsv_restore_patch7_20260522` was counted `590/1186`, score `50`
  (raw `671/1317`, score `51`), improving the recorded counted baseline from
  score `44` to score `50`. This is an official baseline upgrade, not a solved
  task.

### Verification

- `.\.venv\Scripts\python.exe -m py_compile scripts\plan_official_breakthrough_targets.py tests\test_plan_official_breakthrough_targets.py tests\test_xsv_file_bridge_harness.py output\file_bridge_manual\run_xsv_file_bridge.py`
  passed.
- `python -m ruff check --no-cache scripts\plan_official_breakthrough_targets.py tests\test_plan_official_breakthrough_targets.py tests\test_xsv_file_bridge_harness.py output\file_bridge_manual\run_xsv_file_bridge.py`
  passed.
- `.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp C:\tmp\rebuilder_planner_tests_20260523 tests\test_plan_official_breakthrough_targets.py`
  -> `18 passed`.
- `.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp C:\tmp\rebuilder_xsv_tests_20260523 tests\test_xsv_file_bridge_harness.py`
  -> `9 passed`.
- `.\.venv\Scripts\python.exe output\file_bridge_manual\run_xsv_file_bridge.py restore_patch6 --pull`
  completed through the ReBuilder `file_bridge` provider with local exploration
  `102/102` and holdout `12/15`.
- `.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp C:\tmp\rebuilder_zip_harness_full_20260523 tests\test_zip_file_bridge_harness.py`
  -> `6 passed`.
- `.\.venv\Scripts\python.exe -m py_compile output\file_bridge_manual\run_zip_file_bridge.py tests\test_zip_file_bridge_harness.py`
  passed.
- `python -m ruff check --no-cache output\file_bridge_manual\run_zip_file_bridge.py tests\test_zip_file_bridge_harness.py`
  passed.
- `.\.venv\Scripts\python.exe output\file_bridge_manual\run_zip_file_bridge.py usage_patch4_domain_filter`
  completed through the ReBuilder `file_bridge` provider with local exploration
  `92/92`, holdout `10/13`, and only `archive_compression` probe axes. It
  skipped official eval because holdout was below `0.8`.
- `.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp C:\tmp\rebuilder_chroma_harness_full_20260523 tests\test_chroma_file_bridge_harness.py`
  -> `8 passed`.
- `.\.venv\Scripts\python.exe -m py_compile output\file_bridge_manual\run_chroma_file_bridge.py tests\test_chroma_file_bridge_harness.py`
  passed.
- `python -m ruff check --no-cache output\file_bridge_manual\run_chroma_file_bridge.py tests\test_chroma_file_bridge_harness.py`
  passed.
- `.\.venv\Scripts\python.exe output\file_bridge_manual\run_chroma_file_bridge.py restore_patch3_generalization_probe --run-official-eval --official-eval-timeout-seconds 2400 --docker-command-timeout-seconds 300 --workers 1 --branch-workers 1 --docker-cpus 2 --branch-retries 0 --force --pull`
  completed local packaging through the ReBuilder `file_bridge` provider with
  local exploration `68/70`, holdout `46/46`, then timed out during ProgramBench
  official eval without producing
  `alecthomas__chroma.8d04def.eval.json`; cleanup stopped one matching
  ProgramBench container and removed one matching compiled image.
- `.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp C:\tmp\rebuilder_xsv_patch7_green tests\test_xsv_file_bridge_harness.py::test_restore_patch7_frequency_no_headers_counts_first_row_as_data`
  first failed before implementation with `ValueError: unknown variant:
  restore_patch7`, then passed after the patch.
- `.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp C:\tmp\rebuilder_xsv_patch7_tests tests\test_xsv_file_bridge_harness.py`
  -> `10 passed`.
- `.\.venv\Scripts\python.exe -m py_compile output\file_bridge_manual\run_xsv_file_bridge.py tests\test_xsv_file_bridge_harness.py`
  passed.
- `python -m ruff check --no-cache output\file_bridge_manual\run_xsv_file_bridge.py tests\test_xsv_file_bridge_harness.py`
  passed.
- `.\.venv\Scripts\python.exe output\file_bridge_manual\run_xsv_file_bridge.py restore_patch7 --pull`
  completed through the ReBuilder `file_bridge` provider with local exploration
  `101/102`, holdout `13/15`, package gate passed, and no official eval.
- `.\.venv\Scripts\python.exe output\file_bridge_manual\run_xsv_file_bridge.py restore_patch7 --pull --official-eval`
  completed through the same no-external `file_bridge` provider; the official
  aggregate eval wrote counted `590/1186`, score `50`, raw `671/1317`, score
  `51`, and updated
  `baselines\programbench\burntsushi__xsv.f430466.baseline.json`.
- `.\.venv\Scripts\python.exe scripts\rank_programbench_candidates.py --runs runs --official-eval-root runs\programbench_official_eval --baseline-root baselines\programbench --official-eligible-only --allow-existing-official --latest-per-task --require-runtime-smoke-dimensions args,input_files,stdin --max-local-holdout-gap 0.15 --format json`
  returned `row_count=0`.

### Safe External Narrative

Useful public phrasing:

> We tightened ReBuilder's planner so local generalization-gap follow-ups stay
> on the no-external `file_bridge` route by default. A new xsv patch was tested
> locally through that path, but it only matched the previous holdout result and
> did not clear the strict official-ready gate. We also removed non-archive
> adaptive probe domains from the zip harness; that produced cleaner local probe
> coverage but a worse holdout aggregate. A bounded chroma official retry kept
> the same no-external bridge boundary and improved operational evidence, but
> ProgramBench timed out without an official eval JSON. A subsequent xsv
> `frequency -n` public-behavior repair did produce an official aggregate
> baseline upgrade, moving counted score from 44 to 50, while still remaining
> far from a solved task.

Avoid claiming:

- that xsv `restore_patch6` has a new official score;
- that zip `usage_patch4_domain_filter` has a new official score;
- that chroma `restore_patch3_generalization_probe` has a new official score;
- that xsv is solved or almost solved in official aggregate terms;
- that external LLMs were used for this official-test path;
- that hidden official case details informed the repair.
