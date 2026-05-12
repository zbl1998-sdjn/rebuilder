import pytest

from core.data_models import CLISurface, FlagSpec, TestResult
from core.probe_engine import ProbeEngine
from core.probing.file_io import FileIOProbePlanner
from tests.test_probe_engine import MockLLMClient


def test_file_io_planner_uses_documented_input_and_output_flags():
    docs = "Usage: tool --input FILE --output FILE\nReads input and writes output."
    cli_surface = CLISurface(
        flags=[
            FlagSpec(name="--input", type_hint="file", description="Input file"),
            FlagSpec(name="--output", type_hint="file", description="Output file"),
        ]
    )

    probes = FileIOProbePlanner().plan(docs, cli_surface)

    assert probes[0].name == "file_io_input_output_flags"
    assert probes[0].args == ["--input", "input.txt", "--output", "out.txt"]
    assert probes[0].input_files == {"input.txt": b"alpha\nbeta\n"}


def test_file_io_planner_adds_positional_input_probe_from_docs():
    docs = "Usage: wordcount FILE\nRead the input file and print statistics."

    probes = FileIOProbePlanner().plan(docs, CLISurface())

    assert [probe.name for probe in probes] == [
        "file_io_positional_input",
        "file_io_positional_input_missing",
        "file_io_positional_input_empty",
        "file_io_positional_input_binary",
    ]
    assert probes[0].args == ["input.txt"]
    assert probes[0].input_files == {"input.txt": b"alpha\nbeta\n"}
    assert probes[1].args == ["missing.txt"]
    assert probes[1].input_files == {}
    assert probes[2].args == ["empty.txt"]
    assert probes[2].input_files == {"empty.txt": b""}
    assert probes[3].args == ["input.bin"]
    assert probes[3].input_files == {"input.bin": b"\x00\x01\x02\xff"}


def test_file_io_planner_does_not_treat_output_flag_as_input_from_docs():
    docs = "Usage: tool --output FILE\nWrite stdin to an output file."

    probes = FileIOProbePlanner().plan(docs, CLISurface())

    assert [probe.name for probe in probes] == ["file_io_stdin_output_flag"]
    assert probes[0].args == ["--output", "out.txt"]


def test_file_io_planner_adds_output_directory_probe():
    docs = "Usage: tool --input FILE --output-dir DIR\nWrites generated files to the output directory."
    cli_surface = CLISurface(
        flags=[
            FlagSpec(name="--input", type_hint="file", description="Input file"),
            FlagSpec(name="--output-dir", type_hint="path", description="Output directory"),
        ]
    )

    probes = FileIOProbePlanner().plan(docs, cli_surface)

    assert [probe.name for probe in probes] == ["file_io_input_output_directory_flags"]
    assert probes[0].args == ["--input", "input.txt", "--output-dir", "outdir"]


class FileIOBackend:
    def __init__(self):
        self.calls = []

    async def run(self, executable, test_case):
        self.calls.append(test_case)
        if "outdir" in test_case.args:
            return TestResult(
                stdout="",
                exit_code=0,
                output_files={"outdir/result.txt": b"alpha\nbeta\n"},
            )
        if "out.txt" in test_case.args:
            return TestResult(
                stdout="",
                exit_code=0,
                output_files={"out.txt": b"alpha\nbeta\n"},
            )
        return TestResult(stdout="2\n", exit_code=0)


@pytest.mark.asyncio
async def test_probe_engine_records_file_io_side_effect_samples():
    backend = FileIOBackend()
    engine = ProbeEngine(
        executable="reference",
        documentation="Usage: tool --input FILE --output FILE",
        llm_client=MockLLMClient(),
        max_iterations=0,
        executor_backend=backend,
    )
    engine.cli_surface.flags = [
        FlagSpec(name="--input", type_hint="file", description="Input file"),
        FlagSpec(name="--output", type_hint="file", description="Output file"),
    ]

    await engine._probe_file_io_side_effects()

    samples = [sample for sample in engine.corpus if "file_io" in sample.tags]
    assert len(samples) >= 1
    assert samples[0].observed_result.output_files == {"out.txt": b"alpha\nbeta\n"}
    assert "side_effect" in samples[0].tags


@pytest.mark.asyncio
async def test_probe_engine_records_directory_side_effect_samples():
    backend = FileIOBackend()
    engine = ProbeEngine(
        executable="reference",
        documentation="Usage: tool --output-dir DIR",
        llm_client=MockLLMClient(),
        max_iterations=0,
        executor_backend=backend,
    )
    engine.cli_surface.flags = [
        FlagSpec(name="--output-dir", type_hint="path", description="Output directory"),
    ]

    await engine._probe_file_io_side_effects()

    samples = [sample for sample in engine.corpus if "file_io" in sample.tags]
    assert len(samples) >= 1
    assert samples[0].observed_result.output_files == {"outdir/result.txt": b"alpha\nbeta\n"}
    assert "file_output" in samples[0].tags
