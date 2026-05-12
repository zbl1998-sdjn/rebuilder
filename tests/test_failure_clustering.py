from core.data_models import DiffReport, TestCase, TestResult
from core.repair.clustering import FailureClusterer, FailureKind


def report(**kwargs):
    defaults = dict(
        test_case=TestCase(name="case"),
        original_result=TestResult(stdout="a", stderr="", exit_code=0),
        replacement_result=TestResult(stdout="b", stderr="", exit_code=0),
        stdout_match=False,
        stderr_match=True,
        exit_code_match=True,
        file_outputs_match=True,
    )
    defaults.update(kwargs)
    return DiffReport(**defaults)


def test_failure_clusterer_groups_by_observable_mismatch_kind():
    reports = [
        report(stdout_match=False, stderr_match=True, exit_code_match=True, file_outputs_match=True),
        report(stdout_match=True, stderr_match=False, exit_code_match=True, file_outputs_match=True),
        report(stdout_match=True, stderr_match=True, exit_code_match=False, file_outputs_match=True),
        report(stdout_match=True, stderr_match=True, exit_code_match=True, file_outputs_match=False),
    ]

    clusters = FailureClusterer().cluster(reports)
    kinds = {cluster.kind for cluster in clusters}

    assert kinds == {
        FailureKind.STDOUT,
        FailureKind.STDERR,
        FailureKind.EXIT_CODE,
        FailureKind.FILE_OUTPUT,
    }


def test_failure_clusterer_ignores_equivalent_reports():
    clusters = FailureClusterer().cluster(
        [
            report(
                stdout_match=True,
                stderr_match=True,
                exit_code_match=True,
                file_outputs_match=True,
            )
        ]
    )

    assert clusters == []


def test_failure_clusterer_selects_largest_cluster_for_repair():
    stdout_a = report(
        test_case=TestCase(name="stdout_a"),
        stdout_match=False,
        stderr_match=True,
        exit_code_match=True,
        file_outputs_match=True,
    )
    stdout_b = report(
        test_case=TestCase(name="stdout_b"),
        stdout_match=False,
        stderr_match=True,
        exit_code_match=True,
        file_outputs_match=True,
    )
    exit_code = report(
        test_case=TestCase(name="exit"),
        stdout_match=True,
        stderr_match=True,
        exit_code_match=False,
        file_outputs_match=True,
    )

    cluster = FailureClusterer().largest_cluster([exit_code, stdout_a, stdout_b])

    assert cluster is not None
    assert cluster.kind == FailureKind.STDOUT
    assert [item.test_case.name for item in cluster.reports] == ["stdout_a", "stdout_b"]


def test_failure_clusterer_prefers_coherent_repair_target_over_broad_multiple():
    multiple_reports = [
        report(
            test_case=TestCase(name=f"multiple_{index}"),
            stdout_match=False,
            stderr_match=False,
            exit_code_match=True,
            file_outputs_match=True,
        )
        for index in range(4)
    ]
    stdout_reports = [
        report(
            test_case=TestCase(name=f"stdout_{index}"),
            stdout_match=False,
            stderr_match=True,
            exit_code_match=True,
            file_outputs_match=True,
        )
        for index in range(2)
    ]

    cluster = FailureClusterer().repair_target(multiple_reports + stdout_reports)

    assert cluster is not None
    assert cluster.kind == FailureKind.STDOUT
    assert [item.test_case.name for item in cluster.reports] == ["stdout_0", "stdout_1"]


def test_failure_clusterer_still_targets_multiple_when_it_dominates():
    multiple_reports = [
        report(
            test_case=TestCase(name=f"multiple_{index}"),
            stdout_match=False,
            stderr_match=False,
            exit_code_match=True,
            file_outputs_match=True,
        )
        for index in range(8)
    ]
    stdout_report = report(
        test_case=TestCase(name="stdout"),
        stdout_match=False,
        stderr_match=True,
        exit_code_match=True,
        file_outputs_match=True,
    )

    cluster = FailureClusterer().repair_target(multiple_reports + [stdout_report])

    assert cluster is not None
    assert cluster.kind == FailureKind.MULTIPLE
