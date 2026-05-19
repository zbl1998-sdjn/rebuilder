"""Cluster differential failures by observable mismatch type."""

from __future__ import annotations

import hashlib
from enum import Enum
from typing import Dict, List

from pydantic import BaseModel, Field

from core.data_models import DiffReport
from core.evidence.models import test_case_fingerprint


class FailureKind(str, Enum):
    STDOUT = "stdout"
    STDERR = "stderr"
    EXIT_CODE = "exit_code"
    FILE_OUTPUT = "file_output"
    MULTIPLE = "multiple"


class FailureCluster(BaseModel):
    kind: FailureKind
    reports: List[DiffReport] = Field(default_factory=list)


ReportSortKey = tuple[str, tuple[str, ...], str, str]
ReportTargetKey = tuple[str, str, str]
ClusterKey = tuple[FailureKind, tuple[ReportTargetKey, ...]]


class FailureClusterer:
    """Group failures so repair can target related mismatches together."""

    _REPAIR_COHERENCE_WEIGHT = {
        FailureKind.STDOUT: 1.0,
        FailureKind.STDERR: 1.0,
        FailureKind.EXIT_CODE: 1.0,
        FailureKind.FILE_OUTPUT: 1.0,
        FailureKind.MULTIPLE: 0.35,
    }

    def cluster(self, reports: List[DiffReport]) -> List[FailureCluster]:
        grouped: Dict[FailureKind, List[DiffReport]] = {}
        for report in reports:
            if report.is_equivalent:
                continue
            kind = self._kind_for(report)
            grouped.setdefault(kind, []).append(report)
        clusters = [
            FailureCluster(kind=kind, reports=sorted(items, key=self._report_sort_key))
            for kind, items in grouped.items()
        ]
        return sorted(
            clusters,
            key=lambda cluster: (
                cluster.kind.value,
                [self._report_sort_key(report) for report in cluster.reports],
            ),
        )

    def largest_cluster(self, reports: List[DiffReport]) -> FailureCluster | None:
        """Return the largest repair target cluster using deterministic tie-breaks."""
        clusters = self.cluster(reports)
        if not clusters:
            return None
        return sorted(
            clusters,
            key=lambda cluster: (-len(cluster.reports), cluster.kind.value),
        )[0]

    def repair_target(
        self,
        reports: List[DiffReport],
        excluded_keys: set[ClusterKey] | None = None,
    ) -> FailureCluster | None:
        """Return the most actionable repair target using count and coherence."""
        excluded = excluded_keys or set()
        clusters = [
            cluster
            for cluster in self.cluster(reports)
            if self.target_key(cluster) not in excluded
        ]
        if not clusters:
            return None
        return sorted(
            clusters,
            key=lambda cluster: (
                -self._repair_score(cluster),
                -len(cluster.reports),
                cluster.kind.value,
            ),
        )[0]

    def target_key(self, cluster: FailureCluster) -> ClusterKey:
        """Return a stable key for excluding already-regressed repair targets."""
        return (
            cluster.kind,
            tuple(self._report_target_key(report) for report in sorted(cluster.reports, key=self._report_sort_key)),
        )

    def _repair_score(self, cluster: FailureCluster) -> float:
        weight = self._REPAIR_COHERENCE_WEIGHT[cluster.kind]
        if cluster.kind == FailureKind.MULTIPLE and self._is_network_special_address_cluster(cluster):
            weight = 3.0
        return len(cluster.reports) * weight

    def _report_sort_key(self, report: DiffReport) -> ReportSortKey:
        test_case = report.test_case
        return (
            test_case.name,
            tuple(test_case.args),
            test_case_fingerprint(test_case),
            test_case.description,
        )

    def _report_target_key(self, report: DiffReport) -> ReportTargetKey:
        test_case = report.test_case
        return (
            test_case.name,
            test_case_fingerprint(test_case),
            self._description_fingerprint(test_case.description),
        )

    def _description_fingerprint(self, description: str) -> str:
        return hashlib.sha256(description.encode("utf-8")).hexdigest()

    def _kind_for(self, report: DiffReport) -> FailureKind:
        mismatches = [
            FailureKind.STDOUT if not report.stdout_match else None,
            FailureKind.STDERR if not report.stderr_match else None,
            FailureKind.EXIT_CODE if not report.exit_code_match else None,
            FailureKind.FILE_OUTPUT if not report.file_outputs_match else None,
        ]
        concrete = [kind for kind in mismatches if kind is not None]
        return concrete[0] if len(concrete) == 1 else FailureKind.MULTIPLE

    def _is_network_special_address_cluster(self, cluster: FailureCluster) -> bool:
        return any(self._is_network_special_address_report(report) for report in cluster.reports)

    def _is_network_special_address_report(self, report: DiffReport) -> bool:
        test_case = report.test_case
        text = " ".join(
            [
                test_case.name,
                test_case.description,
                " ".join(test_case.args),
                report.original_result.stdout,
                report.original_result.stderr,
                report.replacement_result.stderr,
            ]
        ).lower()
        return (
            "network_ping.special_address" in text
            or "special_address" in text
            or "0 packets transmitted" in text
            or any(host in text for host in ("224.0.0.1", "255.255.255.255", "169.254.", "ff02", "fe80"))
            or any(
                phrase in text
                for phrase in (
                    "network is unreachable",
                    "no route to host",
                    "cannot assign requested address",
                    "permission denied",
                )
            )
        )
