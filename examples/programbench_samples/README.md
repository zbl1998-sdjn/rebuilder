# ProgramBench Sample Metadata

This directory stores metadata for official ProgramBench task images from the DockerHub `programbench` namespace.

The metadata is safe to use during ReBuilder development because it lists task image names only. It does not include hidden evaluation tests, original source code, or binary-analysis output.

Fetch a small sample:

```bash
python scripts/fetch_programbench_samples.py --limit 5 --output examples/programbench_samples/samples.json
```

Use the `task_cleanroom` image for reconstruction experiments. Do not use official hidden evaluation results as repair feedback.

Prepare one workspace:

```bash
python scripts/prepare_programbench_task.py ajeetdsouza__zoxide.67ca1bc --runs runs --pull
```

Then run ReBuilder against the prepared `workspace/` directory.
