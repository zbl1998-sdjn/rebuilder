"""Data models for ProgramBench cleanroom compliance checks."""

from __future__ import annotations

from enum import Enum
from typing import List

from pydantic import BaseModel, Field


class ComplianceSeverity(str, Enum):
    """Severity for a cleanroom compliance finding."""

    ERROR = "error"
    WARNING = "warning"


class ComplianceRule(BaseModel):
    """A pattern-based cleanroom rule."""

    rule_id: str
    description: str
    pattern: str
    severity: ComplianceSeverity = ComplianceSeverity.ERROR


class ComplianceFinding(BaseModel):
    """A concrete violation found in a generated artifact."""

    rule_id: str
    severity: ComplianceSeverity
    path: str
    line_number: int
    line: str
    description: str


class ComplianceReport(BaseModel):
    """Aggregated cleanroom compliance result."""

    findings: List[ComplianceFinding] = Field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not any(f.severity == ComplianceSeverity.ERROR for f in self.findings)
