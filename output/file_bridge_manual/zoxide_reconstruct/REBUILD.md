# zoxide reconstruction (no-external-LLM)

Multi-file submission source that took official zoxide 37 -> 67
(counted 357/531; raw 396/577). The original score-37 base had a 1-line
`init` stub; this reconstruction embeds byte-exact default `init <shell>`
outputs for 9 shells (the allowed static-asset exception), applies
`--cmd/--hook/--no-cmd` via general template substitution, and fixes the db
algorithms (add dir-validation, +4.0 frecency, query ranking, `--list`,
`--score` rjust(6), remove, import).

Rebuild the submission:
```
python -c "import tarfile,io,time,os; \
d='output/file_bridge_manual/zoxide_reconstruct'; \
out='runs/.../submission.tar.gz'; \
tf=tarfile.open(out,'w:gz'); \
[tf.addfile(tarfile.TarInfo(f) ... ) for f in ['main.py','db.py','init_templates.py','rebuilder_contracts.py','compile.sh']]; tf.close()"
```
Then run the ProgramBench official eval on that submission dir with
PYTHONUTF8=1 and branch-workers=12 (see the official-eval ops memory).
