from scripts.record_programbench_baseline import parse_args


def test_record_baseline_parse_args():
    args = parse_args(
        [
            "owner__repo.abcdef0",
            "--local-result",
            "runs/task/result.json",
            "--official-eval",
            "runs/task.eval.json",
            "--submission",
            "runs/task/submission.tar.gz",
            "--output",
            "baselines/programbench",
            "--model",
            "glm-5.1",
            "--config",
            "config/smoke_glm.yaml",
            "--notes",
            "baseline",
        ]
    )

    assert args.instance_id == "owner__repo.abcdef0"
    assert args.model == "glm-5.1"
    assert args.config == "config/smoke_glm.yaml"
