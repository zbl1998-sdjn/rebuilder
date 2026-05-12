"""Pattern-based scanner for ProgramBench cleanroom compliance."""

from __future__ import annotations

import re
from typing import Dict, Iterable, List

from .models import ComplianceFinding, ComplianceReport, ComplianceRule


DEFAULT_RULES: List[ComplianceRule] = [
    ComplianceRule(
        rule_id="binary_wrapping.copy_reference_binary",
        description="Generated artifacts must not copy or chmod the provided reference executable.",
        pattern=r"\b(cp|copy|chmod)\b[^\n]*(\./)?executable\b|shutil\.copy[^\n]*executable",
    ),
    ComplianceRule(
        rule_id="binary_wrapping.exec_reference_binary",
        description="Generated code must not execute the provided reference executable at runtime.",
        pattern=r"(subprocess\.\w+|exec|Command::new|process\.exec|os\.system)[^\n]*(\./)?executable\b",
    ),
    ComplianceRule(
        rule_id="source_lookup.git_clone",
        description="Reconstruction must not clone source repositories.",
        pattern=r"\bgit\s+clone\b",
    ),
    ComplianceRule(
        rule_id="source_lookup.package_source",
        description="Reconstruction must not obtain original project source from package managers.",
        pattern=r"\b(apt-get\s+source|cargo\s+install|go\s+get|npm\s+install|pip\s+install)\b",
    ),
    ComplianceRule(
        rule_id="binary_analysis.disassembler",
        description="The reference executable must not be inspected with binary-analysis tools.",
        pattern=r"\b(objdump|ghidra|strace|ltrace|radare2|r2\s+-|gdb)\b",
    ),
]


class ComplianceScanner:
    """Scan generated source files and scripts for cleanroom boundary violations."""

    def __init__(self, rules: Iterable[ComplianceRule] | None = None):
        self.rules = list(rules or DEFAULT_RULES)
        self._compiled = [
            (rule, re.compile(rule.pattern, flags=re.IGNORECASE)) for rule in self.rules
        ]

    def scan_files(self, files: Dict[str, str]) -> ComplianceReport:
        """Scan a mapping of relative path to file content."""
        findings: List[ComplianceFinding] = []

        for path, content in sorted(files.items()):
            for line_number, line in enumerate(content.splitlines(), start=1):
                for rule, pattern in self._compiled:
                    if pattern.search(line):
                        findings.append(
                            ComplianceFinding(
                                rule_id=rule.rule_id,
                                severity=rule.severity,
                                path=path,
                                line_number=line_number,
                                line=line.strip(),
                                description=rule.description,
                            )
                        )

        return ComplianceReport(findings=findings)
