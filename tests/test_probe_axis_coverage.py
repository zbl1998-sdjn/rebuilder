from core.data_models import BehaviorSample, TestCase, TestResult
from core.probing.axis_coverage import summarize_probe_axis_coverage


def test_summarize_probe_axis_coverage_uses_tags_and_descriptions_without_outputs():
    samples = [
        BehaviorSample(
            test_case=TestCase(name="csv", description="adaptive_axis:csv_table.quoted_fields"),
            observed_result=TestResult(stdout="do not include", stderr="secret-ish"),
            tags=["smoke_contract:csv_table.quoted_fields"],
        ),
        BehaviorSample(
            test_case=TestCase(
                name="json",
                description=(
                    "smoke_contract:json_transform.invalid_json "
                    "adaptive_axis:json_transform.invalid_json"
                ),
            ),
            observed_result=TestResult(stdout="also omitted"),
            tags=[],
        ),
    ]

    coverage = summarize_probe_axis_coverage(samples)

    assert coverage == {
        "smoke_contract_axis_count": 2,
        "adaptive_axis_count": 2,
        "smoke_contract_domains": ["csv_table", "json_transform"],
        "adaptive_domains": ["csv_table", "json_transform"],
        "smoke_contract_axes": [
            "csv_table.quoted_fields",
            "json_transform.invalid_json",
        ],
        "adaptive_axes": [
            "csv_table.quoted_fields",
            "json_transform.invalid_json",
        ],
    }
    assert "do not include" not in repr(coverage)
    assert "secret-ish" not in repr(coverage)
