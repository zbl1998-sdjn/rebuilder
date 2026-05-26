# Changelog

All notable official-baseline changes to ReBuilder are recorded here.
Scores are ProgramBench aggregate "info score" (counted pass-rate × 100),
`fully_resolved=false` for all — aggregate baseline upgrades, not solved tasks.

## [0.6.0] - 2026-05-26

Five no-external-LLM, cleanroom-compliant official ProgramBench breakthroughs
this session, all confirmed by clean official Docker evals (`error_code=None`,
all branches ran) and recorded in `baselines/programbench/`. Full unit suite
`946 passed`.

### Official baseline upgrades
- **agourlay__zip-password-finder**: 40 → **98** (counted 667/680; raw 778/792).
  Pure-stdlib WinZip AES PBKDF2 password verification (eval container lacks
  pyzipper) + reference output/exit/error contracts. Near-solved.
- **clog-tool__clog-cli**: 45 → **75** (counted 432/575; raw 567/778).
  Config-dependent degenerate-reference contract (no `.clog.toml` →
  `fatal I/O error`) + help/missing-file/SemVer fixes.
- **ajeetdsouza__zoxide**: 37 → **67** (counted 357/531; raw 396/577).
  Byte-exact `init <shell>` static assets for 9 shells + general flag
  substitution + general db algorithms (add/query/remove/import).
- **burntsushi__xsv**: 50 → **70** (counted 832/1186; raw 953/1317).
  General-algorithm reimplementation of many subcommands (stats/flatten/fmt/
  split/cat/headers) + `split --size 0` infinite-loop fix.
- **alecthomas__chroma**: 3 → **13** (counted 65/515; raw 73/531). Secured a
  previously-uncommitted verified file_bridge syntax-highlighter patch; further
  gains are anti-overfit-capped (would require per-style/lexer reference data).

### Method & tooling
- In-framework subagent (no external LLM) drives black-box differential probing
  vs the `:task_cleanroom` reference, then general-algorithm reconstruction.
- Official-eval ops playbook: clean orphan `programbench-*` containers,
  `PYTHONUTF8=1` (avoid GBK ✅ crash), `--branch-workers 12`, hang-hunt the
  candidate before eval (a single hang stalls a whole branch).
- Framework: syntax_highlighter strategy domain + adaptive probes;
  official-eval operational-failure classification (results_read_failed /
  invalid_aggregate / failed_without_eval_json).

### Notes
- Mean recorded official baseline across the 13 tracked tasks rose to ~75.6;
  12/13 are now ≥62. Only `chroma` (13) remains low (anti-overfit ceiling).
