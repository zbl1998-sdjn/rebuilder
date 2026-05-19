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


def test_failure_clusterer_orders_reports_within_cluster_deterministically():
    beta = report(
        test_case=TestCase(name="stdout_beta", args=["--beta"]),
        stdout_match=False,
        stderr_match=True,
        exit_code_match=True,
        file_outputs_match=True,
    )
    alpha = report(
        test_case=TestCase(name="stdout_alpha", args=["--alpha"]),
        stdout_match=False,
        stderr_match=True,
        exit_code_match=True,
        file_outputs_match=True,
    )

    cluster = FailureClusterer().repair_target([beta, alpha])

    assert cluster is not None
    assert [item.test_case.name for item in cluster.reports] == ["stdout_alpha", "stdout_beta"]


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


def test_failure_clusterer_prioritizes_network_special_address_multiple_cluster():
    special_address_reports = [
        report(
            test_case=TestCase(
                name=f"adaptive_network_ping_special_address_{index}",
                args=["-c", "1", host],
                description="adaptive_axis:network_ping.special_address_error stdout stats, stderr network error, and exit 2",
            ),
            original_result=TestResult(stdout="PING host\n--- host ping statistics ---\n0 packets transmitted => 0 received (100% loss)\n", stderr="write: network is unreachable\n", exit_code=2),
            replacement_result=TestResult(stdout="PING host\nseq=0\n", stderr="", exit_code=0),
            stdout_match=False,
            stderr_match=False,
            exit_code_match=False,
            file_outputs_match=True,
        )
        for index, host in enumerate(["224.0.0.1", "255.255.255.255", "ff02::1", "169.254.1.1"])
    ]
    stdout_reports = [
        report(
            test_case=TestCase(name=f"stdout_art_{index}", args=["-c", "1", "localhost"]),
            stdout_match=False,
            stderr_match=True,
            exit_code_match=True,
            file_outputs_match=True,
        )
        for index in range(11)
    ]

    cluster = FailureClusterer().repair_target(special_address_reports + stdout_reports)

    assert cluster is not None
    assert cluster.kind == FailureKind.MULTIPLE
    assert [item.test_case.name for item in cluster.reports] == [
        "adaptive_network_ping_special_address_0",
        "adaptive_network_ping_special_address_1",
        "adaptive_network_ping_special_address_2",
        "adaptive_network_ping_special_address_3",
    ]


def test_failure_clusterer_can_exclude_regressed_target():
    clusterer = FailureClusterer()
    stderr_report = report(
        test_case=TestCase(name="stderr"),
        stdout_match=True,
        stderr_match=False,
        exit_code_match=True,
        file_outputs_match=True,
    )
    stdout_report = report(
        test_case=TestCase(name="stdout"),
        stdout_match=False,
        stderr_match=True,
        exit_code_match=True,
        file_outputs_match=True,
    )
    first = clusterer.repair_target([stderr_report, stdout_report])

    assert first is not None
    second = clusterer.repair_target(
        [stderr_report, stdout_report],
        excluded_keys={clusterer.target_key(first)},
    )

    assert second is not None
    assert second.kind != first.kind


def test_failure_clusterer_target_key_distinguishes_same_name_different_args():
    clusterer = FailureClusterer()
    first = clusterer.repair_target(
        [
            report(
                test_case=TestCase(name="probe", args=["--mode", "json"]),
                stdout_match=False,
                stderr_match=True,
                exit_code_match=True,
                file_outputs_match=True,
            )
        ]
    )
    second = clusterer.repair_target(
        [
            report(
                test_case=TestCase(name="probe", args=["--mode", "csv"]),
                stdout_match=False,
                stderr_match=True,
                exit_code_match=True,
                file_outputs_match=True,
            )
        ]
    )

    assert first is not None
    assert second is not None
    assert clusterer.target_key(first) != clusterer.target_key(second)


def test_failure_clusterer_target_key_distinguishes_same_name_args_different_stdin():
    clusterer = FailureClusterer()
    first = clusterer.repair_target(
        [
            report(
                test_case=TestCase(name="probe", args=["--mode", "json"], stdin='{"format":"compact"}\n'),
                stdout_match=False,
                stderr_match=True,
                exit_code_match=True,
                file_outputs_match=True,
            )
        ]
    )
    second = clusterer.repair_target(
        [
            report(
                test_case=TestCase(name="probe", args=["--mode", "json"], stdin='{"format":"pretty"}\n'),
                stdout_match=False,
                stderr_match=True,
                exit_code_match=True,
                file_outputs_match=True,
            )
        ]
    )

    assert first is not None
    assert second is not None
    assert clusterer.target_key(first) != clusterer.target_key(second)


def test_failure_clusterer_target_key_omits_raw_input_payload_values():
    clusterer = FailureClusterer()
    cluster = clusterer.repair_target(
        [
            report(
                test_case=TestCase(
                    name="probe",
                    args=["--mode", "json"],
                    stdin="secret-token\n",
                    env_vars={"API_TOKEN": "secret-token"},
                ),
                stdout_match=False,
                stderr_match=True,
                exit_code_match=True,
                file_outputs_match=True,
            )
        ]
    )

    assert cluster is not None
    key_text = repr(clusterer.target_key(cluster))
    assert "secret-token" not in key_text
    assert "API_TOKEN" not in key_text


def test_failure_clusterer_target_key_omits_raw_args_values():
    clusterer = FailureClusterer()
    cluster = clusterer.repair_target(
        [
            report(
                test_case=TestCase(
                    name="probe",
                    args=["--token", "secret-token"],
                ),
                stdout_match=False,
                stderr_match=True,
                exit_code_match=True,
                file_outputs_match=True,
            )
        ]
    )

    assert cluster is not None
    key_text = repr(clusterer.target_key(cluster))
    assert "secret-token" not in key_text
    assert "--token" not in key_text


def test_failure_clusterer_target_key_hashes_description_without_raw_values():
    clusterer = FailureClusterer()
    first = clusterer.repair_target(
        [
            report(
                test_case=TestCase(
                    name="probe",
                    description="adaptive case for secret-token",
                ),
                stdout_match=False,
                stderr_match=True,
                exit_code_match=True,
                file_outputs_match=True,
            )
        ]
    )
    second = clusterer.repair_target(
        [
            report(
                test_case=TestCase(
                    name="probe",
                    description="adaptive case for other-token",
                ),
                stdout_match=False,
                stderr_match=True,
                exit_code_match=True,
                file_outputs_match=True,
            )
        ]
    )

    assert first is not None
    assert second is not None
    assert clusterer.target_key(first) != clusterer.target_key(second)
    key_text = repr(clusterer.target_key(first))
    assert "secret-token" not in key_text
    assert "adaptive case" not in key_text
