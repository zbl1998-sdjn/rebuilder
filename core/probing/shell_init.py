"""Cleanroom shell initialization probe planning."""

from __future__ import annotations

import re

from core.data_models import TestCase


class ShellInitProbePlanner:
    """Plan documented `init <shell>` probes that capture full shell glue output."""

    SHELL_ORDER = ("bash", "zsh", "fish", "powershell")

    def plan(self, documentation: str) -> list[TestCase]:
        text = documentation or ""
        if "init" not in text.lower():
            return []

        probes: list[TestCase] = []
        for shell in self.SHELL_ORDER:
            if self._mentions_init_shell(text, shell):
                probes.append(
                    TestCase(
                        name=f"shell_init_{shell}",
                        args=["init", shell],
                        description=(
                            f"Capture the full documented `{shell}` shell "
                            "initialization script emitted on stdout"
                        ),
                    )
                )
        return probes

    def _mentions_init_shell(self, text: str, shell: str) -> bool:
        pattern = rf"\binit\s+{re.escape(shell)}\b"
        return re.search(pattern, text, flags=re.IGNORECASE) is not None
