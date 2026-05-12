"""Cleanroom file I/O probe planning."""

from __future__ import annotations

import re

from core.data_models import CLISurface, FlagSpec, TestCase


class FileIOProbePlanner:
    """Plan simple documented file input/output probes."""

    SAMPLE_INPUT = b"alpha\nbeta\n"
    EMPTY_INPUT = b""
    BINARY_INPUT = b"\x00\x01\x02\xff"

    def plan(self, documentation: str, cli_surface: CLISurface) -> list[TestCase]:
        text = documentation or ""
        input_flags = self._input_flags(cli_surface, text)
        output_flags = self._output_flags(cli_surface, text)
        output_directory_flags = self._output_directory_flags(cli_surface, text)
        probes: list[TestCase] = []

        if input_flags and output_flags:
            probes.append(
                TestCase(
                    name="file_io_input_output_flags",
                    args=[input_flags[0], "input.txt", output_flags[0], "out.txt"],
                    input_files={"input.txt": self.SAMPLE_INPUT},
                    description="Probe documented file input and output flags",
                )
            )
        elif input_flags and output_directory_flags:
            probes.append(
                TestCase(
                    name="file_io_input_output_directory_flags",
                    args=[input_flags[0], "input.txt", output_directory_flags[0], "outdir"],
                    input_files={"input.txt": self.SAMPLE_INPUT},
                    description="Probe documented file input and directory side-effect output flags",
                )
            )
        elif input_flags:
            probes.append(
                TestCase(
                    name="file_io_input_flag",
                    args=[input_flags[0], "input.txt"],
                    input_files={"input.txt": self.SAMPLE_INPUT},
                    description="Probe documented file input flag",
                )
            )
        elif output_flags:
            probes.append(
                TestCase(
                    name="file_io_stdin_output_flag",
                    args=[output_flags[0], "out.txt"],
                    stdin=self.SAMPLE_INPUT.decode("utf-8"),
                    description="Probe documented file output flag using stdin",
                )
            )

        if output_directory_flags and not input_flags:
            probes.append(
                TestCase(
                    name="file_io_stdin_output_directory_flag",
                    args=[output_directory_flags[0], "outdir"],
                    stdin=self.SAMPLE_INPUT.decode("utf-8"),
                    description="Probe documented output directory or side-effect directory flag using stdin",
                )
            )

        if self._mentions_positional_input(text) and not input_flags:
            probes.extend(self._positional_input_probes())

        return self._dedupe(probes)

    def _positional_input_probes(self) -> list[TestCase]:
        return [
            TestCase(
                name="file_io_positional_input",
                args=["input.txt"],
                input_files={"input.txt": self.SAMPLE_INPUT},
                description="Probe documented positional input file",
            ),
            TestCase(
                name="file_io_positional_input_missing",
                args=["missing.txt"],
                description="Probe documented positional input file when the file is missing",
            ),
            TestCase(
                name="file_io_positional_input_empty",
                args=["empty.txt"],
                input_files={"empty.txt": self.EMPTY_INPUT},
                description="Probe documented positional input file with empty content",
            ),
            TestCase(
                name="file_io_positional_input_binary",
                args=["input.bin"],
                input_files={"input.bin": self.BINARY_INPUT},
                description="Probe documented positional input file with binary content",
            ),
        ]

    def _input_flags(self, cli_surface: CLISurface, documentation: str) -> list[str]:
        flags = [
            flag.name
            for flag in cli_surface.flags
            if self._looks_like_input_flag(flag)
        ]
        flags.extend(self._documented_flags(documentation, purpose="input"))
        return self._ordered_unique(flags)

    def _output_flags(self, cli_surface: CLISurface, documentation: str) -> list[str]:
        flags = [
            flag.name
            for flag in cli_surface.flags
            if self._looks_like_output_flag(flag)
        ]
        flags.extend(self._documented_flags(documentation, purpose="output"))
        return self._ordered_unique(flags)

    def _looks_like_input_flag(self, flag: FlagSpec) -> bool:
        haystack = f"{flag.name} {flag.type_hint} {flag.description}".lower()
        if self._looks_like_output_flag(flag):
            return False
        return (
            flag.name in {"--input", "--in", "--file"}
            or "input file" in haystack
            or "read" in haystack and "file" in haystack
            or flag.type_hint in {"file", "path"} and "input" in haystack
        )

    def _looks_like_output_flag(self, flag: FlagSpec) -> bool:
        haystack = f"{flag.name} {flag.type_hint} {flag.description}".lower()
        if self._looks_like_output_directory_flag(flag):
            return False
        return (
            flag.name in {"--output", "--out", "--dest", "--destination"}
            or "output file" in haystack
            or "write" in haystack and "file" in haystack
            or "destination" in haystack
        )

    def _output_directory_flags(self, cli_surface: CLISurface, documentation: str) -> list[str]:
        flags = [
            flag.name
            for flag in cli_surface.flags
            if self._looks_like_output_directory_flag(flag)
        ]
        flags.extend(self._documented_flags(documentation, purpose="output_directory"))
        return self._ordered_unique(flags)

    def _looks_like_output_directory_flag(self, flag: FlagSpec) -> bool:
        haystack = f"{flag.name} {flag.type_hint} {flag.description}".lower()
        return (
            flag.name in {"--output-dir", "--out-dir", "--output-directory"}
            or any(term in haystack for term in ["output directory", "output dir", "write files to"])
            or any(term in haystack for term in ["cache dir", "config dir", "state dir"])
            or (
                any(term in flag.name.lower() for term in ["dir", "directory", "folder"])
                and any(term in haystack for term in ["output", "cache", "config", "state"])
            )
        )

    def _documented_flags(self, documentation: str, purpose: str) -> list[str]:
        found: list[str] = []
        text = documentation or ""
        for match in re.finditer(r"--[A-Za-z][A-Za-z0-9_-]*", text):
            flag = match.group(0)
            window = text[max(0, match.start() - 40) : match.end() + 80].lower()
            if purpose == "input" and self._documented_flag_is_input(flag, window):
                found.append(flag)
            if purpose == "output" and self._documented_flag_is_output(flag, window):
                found.append(flag)
            if purpose == "output_directory" and self._documented_flag_is_output_directory(flag, window):
                found.append(flag)
        return found

    def _documented_flag_is_input(self, flag: str, window: str) -> bool:
        name = flag.lower()
        if any(term in name for term in ["output", "out", "dest"]):
            return False
        return (
            any(term in name for term in ["input", "in", "file", "path"])
            or "input file" in window
            or "read" in window and "file" in window
        )

    def _documented_flag_is_output(self, flag: str, window: str) -> bool:
        name = flag.lower()
        if self._documented_flag_is_output_directory(flag, window):
            return False
        return (
            any(term in name for term in ["output", "out", "dest"])
            or "output file" in window
            or "write" in window and "file" in window
            or "save" in window and "file" in window
        )

    def _documented_flag_is_output_directory(self, flag: str, window: str) -> bool:
        name = flag.lower()
        return (
            any(term in name for term in ["output-dir", "out-dir", "directory", "folder"])
            or "output directory" in window
            or "output dir" in window
            or "write files to" in window
            or "cache dir" in window
            or "config dir" in window
            or "state dir" in window
        )

    def _mentions_positional_input(self, documentation: str) -> bool:
        text = documentation or ""
        lowered = text.lower()
        if not any(term in lowered for term in ["input file", "read the", "reads "]):
            return False
        return bool(
            re.search(r"\b[A-Z_]*FILE\b", text)
            or re.search(r"<(?:input|file|path)[^>]*>", text, flags=re.IGNORECASE)
        )

    def _ordered_unique(self, values: list[str]) -> list[str]:
        seen: set[str] = set()
        unique: list[str] = []
        for value in values:
            if value not in seen:
                seen.add(value)
                unique.append(value)
        return unique

    def _dedupe(self, probes: list[TestCase]) -> list[TestCase]:
        seen: set[tuple[str, ...]] = set()
        unique: list[TestCase] = []
        for probe in probes:
            key = tuple(probe.args)
            if key not in seen:
                seen.add(key)
                unique.append(probe)
        return unique
