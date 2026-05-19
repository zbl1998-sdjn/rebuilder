import json
import math

import pytest

from core.experiments.registry import (
    AggregateFeedback,
    ExperimentRegistry,
    ExperimentRun,
    StrategyVariant,
    validate_aggregate_only,
)


def make_run(run_id: str = "run-1", score: float = 0.5, holdout_cases: int = 1) -> ExperimentRun:
    return ExperimentRun(
        run_id=run_id,
        instance_id="owner__repo.abcdef0",
        variant=StrategyVariant(variant_id="baseline", strategy="repair_loop"),
        official=AggregateFeedback(
            score=score,
            passed_tests=5,
            total_tests=10,
            pass_rate=0.5,
            fully_resolved=False,
            almost_resolved=False,
            error_code=None,
            warning_count=1,
        ),
        holdout_cases=holdout_cases,
    )


def test_validate_aggregate_only_accepts_official_aggregate_fields():
    validate_aggregate_only(
        {
            "official": {
                "score": 0.75,
                "passed_tests": 3,
                "total_tests": 4,
                "pass_rate": 0.75,
                "fully_resolved": False,
                "almost_resolved": False,
                "error_code": None,
                "warning_count": 0,
            },
            "variant": {"variant_id": "safe", "strategy": "aggregate_only", "params": {"temperature": 0.2}},
        }
    )


@pytest.mark.parametrize("param_name", ["input", "output", "case_id", "message", "logs", "error_details", "test_case", "cases"])
def test_strategy_variant_rejects_hidden_detail_param_names(param_name):
    with pytest.raises(ValueError, match=param_name):
        StrategyVariant(variant_id="leaky", strategy="repair_loop", params={param_name: "hidden detail"})


@pytest.mark.parametrize("param_value", [{"nested": True}, ["case-1"], ("case-1",)])
def test_strategy_variant_rejects_nested_or_sequence_params(param_value):
    with pytest.raises(ValueError, match="scalar"):
        StrategyVariant(variant_id="leaky", strategy="repair_loop", params={"temperature": param_value})


@pytest.mark.parametrize(
    ("param_name", "param_value", "message"),
    [
        ("probe_budget", -1, "probe_budget must be non-negative"),
        ("min_samples", -1, "min_samples must be non-negative"),
        ("max_repair_attempts", -1, "max_repair_attempts must be non-negative"),
        ("temperature", -0.1, "temperature must be non-negative"),
        ("min_coverage", 1.1, "min_coverage must be a finite rate between 0 and 1"),
        ("top_p", 1.1, "top_p must be a finite rate between 0 and 1"),
    ],
)
def test_strategy_variant_rejects_invalid_numeric_params(param_name, param_value, message):
    with pytest.raises(ValueError, match=message):
        StrategyVariant(variant_id="safe", strategy="repair_loop", params={param_name: param_value})


@pytest.mark.parametrize(
    "forbidden_key",
    ["test_results", "stdout", "stderr", "args", "branch", "name", "expected", "actual", "diff"],
)
def test_validate_aggregate_only_rejects_forbidden_keys_recursively(forbidden_key):
    with pytest.raises(ValueError, match=forbidden_key):
        validate_aggregate_only({"outer": [{"nested": {forbidden_key: "hidden detail"}}]})


def test_aggregate_feedback_rejects_non_aggregate_official_fields():
    with pytest.raises(ValueError, match="Extra inputs"):
        AggregateFeedback.model_validate({"score": 0.5, "test_results": []})


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("score", math.nan),
        ("score", math.inf),
        ("score", -0.1),
        ("score", 1.1),
        ("pass_rate", math.nan),
        ("pass_rate", math.inf),
        ("pass_rate", -0.1),
        ("pass_rate", 1.1),
    ],
)
def test_aggregate_feedback_rejects_non_finite_or_out_of_range_rates(field, value):
    payload = {
        "score": 0.5,
        "passed_tests": 5,
        "total_tests": 10,
        "pass_rate": 0.5,
    }
    payload[field] = value

    with pytest.raises(ValueError, match=field):
        AggregateFeedback.model_validate(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("passed_tests", -1),
        ("total_tests", -1),
        ("warning_count", -1),
    ],
)
def test_aggregate_feedback_rejects_negative_counts(field, value):
    payload = {
        "score": 0.5,
        "passed_tests": 5,
        "total_tests": 10,
        "pass_rate": 0.5,
    }
    payload[field] = value

    with pytest.raises(ValueError, match=field):
        AggregateFeedback.model_validate(payload)


def test_aggregate_feedback_rejects_passed_tests_above_total_tests():
    with pytest.raises(ValueError, match="passed_tests cannot exceed total_tests"):
        AggregateFeedback.model_validate(
            {
                "score": 1.0,
                "passed_tests": 11,
                "total_tests": 10,
                "pass_rate": 1.0,
            }
        )


def test_experiment_run_rejects_negative_holdout_cases():
    with pytest.raises(ValueError, match="holdout_cases must be non-negative"):
        make_run(holdout_cases=-1)


def test_registry_appends_and_loads_jsonl_rows(tmp_path):
    path = tmp_path / "experiments.jsonl"
    registry = ExperimentRegistry(path)
    registry.append(make_run(run_id="run-1", score=0.25))
    registry.append(make_run(run_id="run-2", score=0.75))

    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["official"]["score"] == 0.25

    rows = registry.load()
    assert [row.run_id for row in rows] == ["run-1", "run-2"]
    assert rows[1].official.score == 0.75
    assert "test_results" not in path.read_text(encoding="utf-8")


def test_registry_load_rejects_hidden_detail_rows(tmp_path):
    path = tmp_path / "experiments.jsonl"
    path.write_text(json.dumps({"run_id": "bad", "nested": {"stdout": "hidden"}}) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="invalid aggregate registry row 1"):
        ExperimentRegistry(path).load()


def test_registry_load_rejects_negative_holdout_cases(tmp_path):
    path = tmp_path / "experiments.jsonl"
    payload = make_run().model_dump(mode="json")
    payload["holdout_cases"] = -1
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="invalid aggregate registry row 1"):
        ExperimentRegistry(path).load()


def test_registry_load_rejects_non_finite_official_score(tmp_path):
    path = tmp_path / "experiments.jsonl"
    payload = make_run().model_dump(mode="json")
    payload["official"]["score"] = math.nan
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="invalid aggregate registry row 1"):
        ExperimentRegistry(path).load()


def test_registry_load_ignores_invalid_jsonl_rows(tmp_path):
    path = tmp_path / "experiments.jsonl"
    good = make_run(run_id="good").model_dump(mode="json")
    path.write_text("{\n" + json.dumps(good) + "\n", encoding="utf-8")

    rows = ExperimentRegistry(path).load()

    assert [row.run_id for row in rows] == ["good"]


def test_registry_load_ignores_non_object_rows(tmp_path):
    path = tmp_path / "experiments.jsonl"
    good = make_run(run_id="good").model_dump(mode="json")
    path.write_text(json.dumps(["not", "a", "row"]) + "\n" + json.dumps(good) + "\n", encoding="utf-8")

    rows = ExperimentRegistry(path).load()

    assert [row.run_id for row in rows] == ["good"]


def test_registry_load_rejects_hidden_detail_strategy_params(tmp_path):
    path = tmp_path / "experiments.jsonl"
    payload = make_run().model_dump(mode="json")
    payload["variant"]["params"] = {"case_id": "hidden-case-1"}
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="invalid aggregate registry row 1"):
        ExperimentRegistry(path).load()
