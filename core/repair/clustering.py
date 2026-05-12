"""Cluster differential failures by observable mismatch type."""

from __future__ import annotations

from enum import Enum
from typing import Dict, List

from pydantic import BaseModel, Field

from core.data_models import DiffReport


class FailureKind(str, Enum):
    STDOUT = "stdout"
    STDERR = "stderr"
    EXIT_CODE = "exit_code"
    FILE_OUTPUT = "file_output"
    MULTIPLE = "multiple"


class FailureCluster(BaseModel):
    kind: FailureKind
    reports: List[DiffReport] = Field(default_factory=list)


ClusterKey = tuple[FailureKind, tuple[str, ...]]


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
        return [
            FailureCluster(kind=kind, reports=items)
            for kind, items in sorted(
                grouped.items(),
                key=lambda pair: (pair[0].value, [report.test_case.name for report in pair[1]]),
            )
        ]

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
            tuple(sorted(report.test_case.name for report in cluster.reports)),
        )

    def _repair_score(self, cluster: FailureCluster) -> float:
        return len(cluster.reports) * self._REPAIR_COHERENCE_WEIGHT[cluster.kind]

    def _kind_for(self, report: DiffReport) -> FailureKind:
        mismatches = [
            FailureKind.STDOUT if not report.stdout_match else None,
            FailureKind.STDERR if not report.stderr_match else None,
            FailureKind.EXIT_CODE if not report.exit_code_match else None,
            FailureKind.FILE_OUTPUT if not report.file_outputs_match else None,
        ]
        concrete = [kind for kind in mismatches if kind is not None]
        return concrete[0] if len(concrete) == 1 else FailureKind.MULTIPLE
