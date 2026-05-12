# ProgramBench Cleanroom Compliance

ReBuilder treats ProgramBench compliance as a top-level architecture constraint, not a documentation note.

## Boundary

ReBuilder may learn from:

- Documentation bundled in the task workspace.
- Normal user-interface execution of the reference executable: CLI arguments, stdin, stdout, stderr, exit codes, and file-system side effects.
- Artifacts bundled in the task workspace.

ReBuilder must not learn from:

- Original project source code, forks, mirrors, package registries, source tarballs, or local dependency caches.
- Decompilation, disassembly, tracing, or instrumentation of the provided reference executable.
- Official hidden evaluation tests or their failure details during reconstruction.

## Final Submission

The generated solution must be a genuine reimplementation. It must not:

- Copy the provided reference executable.
- Wrap, invoke, or shell out to the provided reference executable at runtime.
- Install and shim the original project or an equivalent prebuilt tool.
- Re-link prebuilt object files instead of compiling original source written by the agent.

## Design Consequence

Every inferred behavior should be traceable to one or more evidence records. If a behavior cannot be traced to bundled documentation or normal reference execution, it must remain an unknown hypothesis rather than a confirmed requirement.

## Static Output Assets

ReBuilder may materialize a narrow class of observed outputs as generated
support assets only when all of these are true:

- The behavior is a documented, deterministic, long static output.
- The observed input has no stdin, no file side effects, no stderr, and exit
  code `0`.
- The current implementation policy recognizes the exact input as
  `init <shell>` for a documented default shell.
- The asset is generated from exploration evidence only; holdout and official
  hidden evaluation details must never populate such assets.

Static output assets must not be used for behavioral commands such as
`query`, `add`, `remove`, `import`, file transformations, or any command whose
output depends on state, filesystem contents, environment, timestamps, or
hidden evaluation feedback. These behaviors must be implemented as logic and
judged through exploration/holdout/official aggregate metrics.

Reports that use static output assets should keep them distinguishable from
normal generated logic so ablation runs can compare asset-enabled and
asset-disabled performance.
