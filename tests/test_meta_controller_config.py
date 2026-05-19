import httpx

from core.meta_controller import MetaController
from core.data_models import (
    ArchitectureBlueprint,
    BehaviorSample,
    Codebase,
    DiffReport,
    ProgramSpec,
    RepairStrategy,
    TestCase,
    TestResult,
)
from core.repair.clustering import FailureKind
from core.session import RunSession
from tests.test_probe_engine import MockLLMClient
import pytest


def test_meta_controller_uses_configured_output_root(tmp_path):
    controller = MetaController(
        llm_client=MockLLMClient(),
        output_root=tmp_path / "runs",
    )

    assert controller._output_dir_for_task("sample") == tmp_path / "runs" / "sample"


def test_meta_controller_derives_evidence_store_from_run_session(tmp_path):
    session = RunSession.create(
        root_path=tmp_path / "runs",
        task_id="sample",
        source="programbench_cleanroom",
    )

    controller = MetaController(
        llm_client=MockLLMClient(),
        output_root=session.generated_path,
        run_session=session,
    )

    assert controller.evidence_store is not None
    assert controller.evidence_store.root_path == session.evidence_path
    assert controller._output_dir_for_task("sample") == session.generated_path / "sample"


def test_meta_controller_prepares_clean_output_dir_under_output_root(tmp_path):
    output_root = tmp_path / "generated"
    output_dir = output_root / "sample"
    stale_dir = output_dir / "stale"
    stale_dir.mkdir(parents=True)
    (stale_dir / "old.py").write_text("print('old')\n", encoding="utf-8")
    (output_dir / "result.json").write_text("{}", encoding="utf-8")

    controller = MetaController(
        llm_client=MockLLMClient(),
        output_root=output_root,
    )

    controller._prepare_output_dir(output_dir)

    assert output_dir.exists()
    assert list(output_dir.iterdir()) == []


def test_meta_controller_does_not_use_package_init_as_python_entrypoint(tmp_path):
    package_dir = tmp_path / "zoxide"
    package_dir.mkdir()
    init_path = package_dir / "__init__.py"
    init_path.write_text("", encoding="utf-8")
    codebase = Codebase(
        root_path=tmp_path,
        language="python",
        files={"zoxide/__init__.py": ""},
    )
    controller = MetaController(
        llm_client=MockLLMClient(),
        output_root=tmp_path,
    )

    assert controller._resolve_executable(codebase) is None


@pytest.mark.asyncio
async def test_meta_controller_revalidates_after_last_allowed_repair(monkeypatch, tmp_path):
    import core.meta_controller as meta_module

    test_case = TestCase(name="help", args=["--help"])
    sample = BehaviorSample(
        test_case=test_case,
        observed_result=TestResult(stdout="ok", exit_code=0),
    )
    failed_report = DiffReport(
        test_case=test_case,
        original_result=TestResult(stdout="ok", exit_code=0),
        replacement_result=TestResult(stdout="bad", exit_code=0),
        stdout_match=False,
        stderr_match=True,
        exit_code_match=True,
        file_outputs_match=True,
    )
    passed_report = DiffReport(
        test_case=test_case,
        original_result=TestResult(stdout="ok", exit_code=0),
        replacement_result=TestResult(stdout="ok", exit_code=0),
        stdout_match=True,
        stderr_match=True,
        exit_code_match=True,
        file_outputs_match=True,
    )

    class FakeProbeEngine:
        cli_surface = None

        def __init__(self, *args, **kwargs):
            pass

        async def probe(self):
            return [sample]

    class FakeSpecSynthesizer:
        def __init__(self, *args, **kwargs):
            pass

        async def synthesize(self, *args, **kwargs):
            return ProgramSpec(summary="spec")

    class FakeArchitectAgent:
        def __init__(self, *args, **kwargs):
            pass

        async def design(self, *args, **kwargs):
            return ArchitectureBlueprint(language="python", entry_point="main.py")

    class FakeImplementerAgent:
        def __init__(self, *args, **kwargs):
            pass

        async def implement(self, spec, blueprint, output_dir):
            output_dir.mkdir(parents=True, exist_ok=True)
            path = output_dir / "main.py"
            path.write_text("print('bad')\n", encoding="utf-8")
            return Codebase(
                root_path=output_dir,
                language="python",
                files={"main.py": "print('bad')\n"},
                executable_path=path,
            )

    class FakeDifferentialTester:
        calls = 0

        def __init__(self, *args, **kwargs):
            pass

        async def run_full_suite(self, corpus):
            FakeDifferentialTester.calls += 1
            return [failed_report] if FakeDifferentialTester.calls == 1 else [passed_report]

    class FakeRepairLoop:
        def __init__(self, *args, **kwargs):
            pass

        async def diagnose_cluster(self, *args, **kwargs):
            return RepairStrategy(strategy_type="fix_output_format", description="fix")

        async def apply_repair(self, strategy, codebase, spec):
            codebase.files["main.py"] = "print('ok')\n"
            return codebase

    monkeypatch.setattr(meta_module, "ProbeEngine", FakeProbeEngine)
    monkeypatch.setattr(meta_module, "SpecSynthesizer", FakeSpecSynthesizer)
    monkeypatch.setattr(meta_module, "ArchitectAgent", FakeArchitectAgent)
    monkeypatch.setattr(meta_module, "ImplementerAgent", FakeImplementerAgent)
    monkeypatch.setattr(meta_module, "DifferentialTester", FakeDifferentialTester)
    monkeypatch.setattr(meta_module, "RepairLoop", FakeRepairLoop)

    controller = MetaController(
        llm_client=MockLLMClient(),
        output_root=tmp_path,
        max_repair_iterations=1,
    )

    result = await controller.run("sample", tmp_path / "reference.py", "docs")

    assert FakeDifferentialTester.calls == 2
    assert result.resolved_rate == 1.0
    assert result.status == "success"
    assert result.iterations_used == 1


@pytest.mark.asyncio
async def test_meta_controller_uses_exploration_for_repair_and_reports_holdout(
    monkeypatch,
    tmp_path,
):
    import core.meta_controller as meta_module

    samples = [
        BehaviorSample(
            test_case=TestCase(name=f"case_{index}"),
            observed_result=TestResult(stdout=str(index)),
        )
        for index in range(4)
    ]

    class FakeProbeEngine:
        cli_surface = None

        def __init__(self, *args, **kwargs):
            pass

        async def probe(self):
            return samples

    class FakeSpecSynthesizer:
        corpus_size = None

        def __init__(self, *args, **kwargs):
            pass

        async def synthesize(self, corpus, *args, **kwargs):
            FakeSpecSynthesizer.corpus_size = len(corpus)
            return ProgramSpec(summary="spec")

    class FakeArchitectAgent:
        def __init__(self, *args, **kwargs):
            pass

        async def design(self, *args, **kwargs):
            return ArchitectureBlueprint(language="python", entry_point="main.py")

    class FakeImplementerAgent:
        def __init__(self, *args, **kwargs):
            pass

        async def implement(self, spec, blueprint, output_dir):
            output_dir.mkdir(parents=True, exist_ok=True)
            path = output_dir / "main.py"
            path.write_text("print('ok')\n", encoding="utf-8")
            return Codebase(
                root_path=output_dir,
                language="python",
                files={"main.py": "print('ok')\n"},
                executable_path=path,
            )

    class FakeDifferentialTester:
        suite_sizes = []

        def __init__(self, *args, **kwargs):
            pass

        async def run_full_suite(self, corpus):
            FakeDifferentialTester.suite_sizes.append(len(corpus))
            return [
                DiffReport(
                    test_case=sample.test_case,
                    original_result=sample.observed_result,
                    replacement_result=sample.observed_result,
                    stdout_match=True,
                    stderr_match=True,
                    exit_code_match=True,
                    file_outputs_match=True,
                )
                for sample in corpus
            ]

    monkeypatch.setattr(meta_module, "ProbeEngine", FakeProbeEngine)
    monkeypatch.setattr(meta_module, "SpecSynthesizer", FakeSpecSynthesizer)
    monkeypatch.setattr(meta_module, "ArchitectAgent", FakeArchitectAgent)
    monkeypatch.setattr(meta_module, "ImplementerAgent", FakeImplementerAgent)
    monkeypatch.setattr(meta_module, "DifferentialTester", FakeDifferentialTester)

    controller = MetaController(
        llm_client=MockLLMClient(),
        output_root=tmp_path,
        max_repair_iterations=0,
        internal_holdout_ratio=0.5,
        holdout_seed="fixed",
    )

    result = await controller.run("sample", tmp_path / "reference.py", "docs")

    assert FakeSpecSynthesizer.corpus_size == 2
    assert FakeDifferentialTester.suite_sizes == [2, 2]
    assert result.exploration_cases == 2
    assert result.holdout_cases == 2
    assert result.holdout_resolved_rate == 1.0


@pytest.mark.asyncio
async def test_meta_controller_returns_implementation_metadata(monkeypatch, tmp_path):
    import core.meta_controller as meta_module

    sample = BehaviorSample(
        test_case=TestCase(
            name="case",
            description="smoke_contract:csv_table.quoted_fields adaptive_axis:csv_table.quoted_fields",
        ),
        observed_result=TestResult(stdout="ok", exit_code=0),
        tags=["adaptive_profile", "profile_domain:csv_table"],
    )

    class FakeProbeEngine:
        cli_surface = None

        def __init__(self, *args, **kwargs):
            pass

        async def probe(self):
            return [sample]

    class FakeSpecSynthesizer:
        def __init__(self, *args, **kwargs):
            pass

        async def synthesize(self, *args, **kwargs):
            return ProgramSpec(summary="spec")

    class FakeArchitectAgent:
        def __init__(self, *args, **kwargs):
            pass

        async def design(self, *args, **kwargs):
            return ArchitectureBlueprint(language="python", entry_point="main.py")

    class FakeImplementerAgent:
        def __init__(self, *args, **kwargs):
            self.enable_static_output_assets = kwargs.get("enable_static_output_assets")

        async def implement(self, spec, blueprint, output_dir):
            output_dir.mkdir(parents=True, exist_ok=True)
            path = output_dir / "main.py"
            path.write_text("print('ok')\n", encoding="utf-8")
            return Codebase(
                root_path=output_dir,
                language="python",
                files={"main.py": "print('ok')\n"},
                executable_path=path,
                generation_metadata={
                    "static_output_assets_enabled": self.enable_static_output_assets,
                    "contract_asset_status": "disabled",
                },
            )

    class FakeDifferentialTester:
        def __init__(self, *args, **kwargs):
            pass

        async def run_full_suite(self, corpus):
            return [
                DiffReport(
                    test_case=sample.test_case,
                    original_result=sample.observed_result,
                    replacement_result=sample.observed_result,
                    stdout_match=True,
                    stderr_match=True,
                    exit_code_match=True,
                    file_outputs_match=True,
                )
                for sample in corpus
            ]

    monkeypatch.setattr(meta_module, "ProbeEngine", FakeProbeEngine)
    monkeypatch.setattr(meta_module, "SpecSynthesizer", FakeSpecSynthesizer)
    monkeypatch.setattr(meta_module, "ArchitectAgent", FakeArchitectAgent)
    monkeypatch.setattr(meta_module, "ImplementerAgent", FakeImplementerAgent)
    monkeypatch.setattr(meta_module, "DifferentialTester", FakeDifferentialTester)

    controller = MetaController(
        llm_client=MockLLMClient(),
        output_root=tmp_path,
        max_repair_iterations=0,
        enable_static_output_assets=False,
    )

    result = await controller.run("sample", tmp_path / "reference.py", "docs")

    assert result.implementation_metadata["static_output_assets_enabled"] is False
    assert result.implementation_metadata["contract_asset_status"] == "disabled"
    assert result.implementation_metadata["probe_axis_coverage"] == {
        "smoke_contract_axis_count": 1,
        "adaptive_axis_count": 1,
        "smoke_contract_domains": ["csv_table"],
        "adaptive_domains": ["csv_table"],
        "smoke_contract_axes": ["csv_table.quoted_fields"],
        "adaptive_axes": ["csv_table.quoted_fields"],
    }


@pytest.mark.asyncio
async def test_meta_controller_writes_exploration_failure_report_only(
    monkeypatch,
    tmp_path,
):
    import core.meta_controller as meta_module

    samples = [
        BehaviorSample(
            test_case=TestCase(name=f"case_{index}"),
            observed_result=TestResult(stdout=f"expected {index}", exit_code=0),
        )
        for index in range(4)
    ]

    class FakeProbeEngine:
        cli_surface = None

        def __init__(self, *args, **kwargs):
            pass

        async def probe(self):
            return samples

    class FakeSpecSynthesizer:
        def __init__(self, *args, **kwargs):
            pass

        async def synthesize(self, *args, **kwargs):
            return ProgramSpec(summary="spec")

    class FakeArchitectAgent:
        def __init__(self, *args, **kwargs):
            pass

        async def design(self, *args, **kwargs):
            return ArchitectureBlueprint(language="python", entry_point="main.py")

    class FakeImplementerAgent:
        def __init__(self, *args, **kwargs):
            pass

        async def implement(self, spec, blueprint, output_dir):
            output_dir.mkdir(parents=True, exist_ok=True)
            path = output_dir / "main.py"
            path.write_text("print('bad')\n", encoding="utf-8")
            return Codebase(
                root_path=output_dir,
                language="python",
                files={"main.py": "print('bad')\n"},
                executable_path=path,
            )

    class FakeDifferentialTester:
        calls = 0

        def __init__(self, *args, **kwargs):
            pass

        async def run_full_suite(self, corpus):
            FakeDifferentialTester.calls += 1
            if FakeDifferentialTester.calls == 1:
                return [
                    DiffReport(
                        test_case=sample.test_case,
                        original_result=sample.observed_result,
                        replacement_result=TestResult(stdout="wrong", exit_code=0),
                        stdout_match=False,
                        stderr_match=True,
                        exit_code_match=True,
                        file_outputs_match=True,
                    )
                    for sample in corpus
                ]
            return [
                DiffReport(
                    test_case=sample.test_case,
                    original_result=sample.observed_result,
                    replacement_result=sample.observed_result,
                    stdout_match=True,
                    stderr_match=True,
                    exit_code_match=True,
                    file_outputs_match=True,
                )
                for sample in corpus
            ]

    monkeypatch.setattr(meta_module, "ProbeEngine", FakeProbeEngine)
    monkeypatch.setattr(meta_module, "SpecSynthesizer", FakeSpecSynthesizer)
    monkeypatch.setattr(meta_module, "ArchitectAgent", FakeArchitectAgent)
    monkeypatch.setattr(meta_module, "ImplementerAgent", FakeImplementerAgent)
    monkeypatch.setattr(meta_module, "DifferentialTester", FakeDifferentialTester)

    session = RunSession.create(tmp_path / "runs", "sample", "programbench_cleanroom")
    controller = MetaController(
        llm_client=MockLLMClient(),
        output_root=session.generated_path,
        max_repair_iterations=0,
        internal_holdout_ratio=0.5,
        holdout_seed="fixed",
        run_session=session,
    )

    await controller.run("sample", tmp_path / "reference.py", "docs")

    assert (session.reports_path / "sample.exploration.failures.json").exists()
    assert not (session.reports_path / "sample.holdout.failures.json").exists()


@pytest.mark.asyncio
async def test_meta_controller_repairs_largest_failure_cluster(monkeypatch, tmp_path):
    import core.meta_controller as meta_module

    samples = [
        BehaviorSample(
            test_case=TestCase(name=name),
            observed_result=TestResult(stdout=name, exit_code=0),
        )
        for name in ["exit_only", "stdout_a", "stdout_b"]
    ]

    class FakeProbeEngine:
        cli_surface = None

        def __init__(self, *args, **kwargs):
            pass

        async def probe(self):
            return samples

    class FakeSpecSynthesizer:
        def __init__(self, *args, **kwargs):
            pass

        async def synthesize(self, *args, **kwargs):
            return ProgramSpec(summary="spec")

    class FakeArchitectAgent:
        def __init__(self, *args, **kwargs):
            pass

        async def design(self, *args, **kwargs):
            return ArchitectureBlueprint(language="python", entry_point="main.py")

    class FakeImplementerAgent:
        def __init__(self, *args, **kwargs):
            pass

        async def implement(self, spec, blueprint, output_dir):
            output_dir.mkdir(parents=True, exist_ok=True)
            path = output_dir / "main.py"
            path.write_text("print('bad')\n", encoding="utf-8")
            return Codebase(
                root_path=output_dir,
                language="python",
                files={"main.py": "print('bad')\n"},
                executable_path=path,
            )

    class FakeDifferentialTester:
        def __init__(self, *args, **kwargs):
            pass

        async def run_full_suite(self, corpus):
            reports = []
            for sample in corpus:
                is_exit = sample.test_case.name == "exit_only"
                reports.append(
                    DiffReport(
                        test_case=sample.test_case,
                        original_result=sample.observed_result,
                        replacement_result=TestResult(stdout="wrong", exit_code=2 if is_exit else 0),
                        stdout_match=is_exit,
                        stderr_match=True,
                        exit_code_match=not is_exit,
                        file_outputs_match=True,
                    )
                )
            return reports

    class FakeRepairLoop:
        seen_cluster = None

        def __init__(self, *args, **kwargs):
            pass

        async def diagnose_cluster(self, cluster, spec, codebase):
            FakeRepairLoop.seen_cluster = cluster
            return RepairStrategy(strategy_type="fix_output_format", description="fix")

        async def apply_repair(self, strategy, codebase, spec):
            return codebase

    monkeypatch.setattr(meta_module, "ProbeEngine", FakeProbeEngine)
    monkeypatch.setattr(meta_module, "SpecSynthesizer", FakeSpecSynthesizer)
    monkeypatch.setattr(meta_module, "ArchitectAgent", FakeArchitectAgent)
    monkeypatch.setattr(meta_module, "ImplementerAgent", FakeImplementerAgent)
    monkeypatch.setattr(meta_module, "DifferentialTester", FakeDifferentialTester)
    monkeypatch.setattr(meta_module, "RepairLoop", FakeRepairLoop)

    controller = MetaController(
        llm_client=MockLLMClient(),
        output_root=tmp_path,
        max_repair_iterations=1,
    )

    await controller.run("sample", tmp_path / "reference.py", "docs")

    assert FakeRepairLoop.seen_cluster is not None
    assert FakeRepairLoop.seen_cluster.kind == FailureKind.STDOUT
    assert [report.test_case.name for report in FakeRepairLoop.seen_cluster.reports] == [
        "stdout_a",
        "stdout_b",
    ]


@pytest.mark.asyncio
async def test_meta_controller_repairs_coherent_cluster_before_broad_multiple(
    monkeypatch,
    tmp_path,
):
    import core.meta_controller as meta_module

    samples = [
        BehaviorSample(
            test_case=TestCase(name=f"case_{index}"),
            observed_result=TestResult(stdout=f"expected {index}", stderr="", exit_code=0),
        )
        for index in range(6)
    ]

    class FakeProbeEngine:
        cli_surface = None

        def __init__(self, *args, **kwargs):
            pass

        async def probe(self):
            return samples

    class FakeSpecSynthesizer:
        def __init__(self, *args, **kwargs):
            pass

        async def synthesize(self, *args, **kwargs):
            return ProgramSpec(summary="spec")

    class FakeArchitectAgent:
        def __init__(self, *args, **kwargs):
            pass

        async def design(self, *args, **kwargs):
            return ArchitectureBlueprint(language="python", entry_point="main.py")

    class FakeImplementerAgent:
        def __init__(self, *args, **kwargs):
            pass

        async def implement(self, spec, blueprint, output_dir):
            output_dir.mkdir(parents=True, exist_ok=True)
            path = output_dir / "main.py"
            path.write_text("print('bad')\n", encoding="utf-8")
            return Codebase(
                root_path=output_dir,
                language="python",
                files={"main.py": "print('bad')\n"},
                executable_path=path,
            )

    class FakeDifferentialTester:
        def __init__(self, *args, **kwargs):
            pass

        async def run_full_suite(self, corpus):
            reports = []
            for index, sample in enumerate(corpus):
                multiple = index < 4
                reports.append(
                    DiffReport(
                        test_case=sample.test_case,
                        original_result=sample.observed_result,
                        replacement_result=TestResult(stdout="wrong", stderr="wrong", exit_code=0),
                        stdout_match=False,
                        stderr_match=not multiple,
                        exit_code_match=True,
                        file_outputs_match=True,
                    )
                )
            return reports

    class FakeRepairLoop:
        seen_cluster = None

        def __init__(self, *args, **kwargs):
            pass

        async def diagnose_cluster(self, cluster, spec, codebase):
            FakeRepairLoop.seen_cluster = cluster
            return RepairStrategy(strategy_type="fix_output_format", description="fix")

        async def apply_repair(self, strategy, codebase, spec):
            return codebase

    monkeypatch.setattr(meta_module, "ProbeEngine", FakeProbeEngine)
    monkeypatch.setattr(meta_module, "SpecSynthesizer", FakeSpecSynthesizer)
    monkeypatch.setattr(meta_module, "ArchitectAgent", FakeArchitectAgent)
    monkeypatch.setattr(meta_module, "ImplementerAgent", FakeImplementerAgent)
    monkeypatch.setattr(meta_module, "DifferentialTester", FakeDifferentialTester)
    monkeypatch.setattr(meta_module, "RepairLoop", FakeRepairLoop)

    controller = MetaController(
        llm_client=MockLLMClient(),
        output_root=tmp_path,
        max_repair_iterations=1,
    )

    await controller.run("sample", tmp_path / "reference.py", "docs")

    assert FakeRepairLoop.seen_cluster is not None
    assert FakeRepairLoop.seen_cluster.kind == FailureKind.STDOUT
    assert [report.test_case.name for report in FakeRepairLoop.seen_cluster.reports] == [
        "case_4",
        "case_5",
    ]


@pytest.mark.asyncio
async def test_meta_controller_rejects_regressive_repair(monkeypatch, tmp_path):
    import core.meta_controller as meta_module

    samples = [
        BehaviorSample(
            test_case=TestCase(name="kept_pass"),
            observed_result=TestResult(stdout="ok", exit_code=0),
        ),
        BehaviorSample(
            test_case=TestCase(name="known_fail"),
            observed_result=TestResult(stdout="expected", exit_code=0),
        ),
    ]
    initial_reports = [
        DiffReport(
            test_case=samples[0].test_case,
            original_result=samples[0].observed_result,
            replacement_result=samples[0].observed_result,
            stdout_match=True,
            stderr_match=True,
            exit_code_match=True,
            file_outputs_match=True,
        ),
        DiffReport(
            test_case=samples[1].test_case,
            original_result=samples[1].observed_result,
            replacement_result=TestResult(stdout="wrong", exit_code=0),
            stdout_match=False,
            stderr_match=True,
            exit_code_match=True,
            file_outputs_match=True,
        ),
    ]
    regressed_reports = [
        DiffReport(
            test_case=sample.test_case,
            original_result=sample.observed_result,
            replacement_result=TestResult(stdout="worse", exit_code=0),
            stdout_match=False,
            stderr_match=True,
            exit_code_match=True,
            file_outputs_match=True,
        )
        for sample in samples
    ]

    class FakeProbeEngine:
        cli_surface = None

        def __init__(self, *args, **kwargs):
            pass

        async def probe(self):
            return samples

    class FakeSpecSynthesizer:
        def __init__(self, *args, **kwargs):
            pass

        async def synthesize(self, *args, **kwargs):
            return ProgramSpec(summary="spec")

    class FakeArchitectAgent:
        def __init__(self, *args, **kwargs):
            pass

        async def design(self, *args, **kwargs):
            return ArchitectureBlueprint(language="python", entry_point="main.py")

    class FakeImplementerAgent:
        def __init__(self, *args, **kwargs):
            pass

        async def implement(self, spec, blueprint, output_dir):
            output_dir.mkdir(parents=True, exist_ok=True)
            path = output_dir / "main.py"
            path.write_text("print('initial')\n", encoding="utf-8")
            return Codebase(
                root_path=output_dir,
                language="python",
                files={"main.py": "print('initial')\n"},
                executable_path=path,
            )

    class FakeDifferentialTester:
        calls = 0

        def __init__(self, *args, **kwargs):
            pass

        async def run_full_suite(self, corpus):
            FakeDifferentialTester.calls += 1
            if FakeDifferentialTester.calls == 1:
                return initial_reports
            return regressed_reports

    class FakeRepairLoop:
        def __init__(self, *args, **kwargs):
            pass

        async def diagnose_cluster(self, cluster, spec, codebase):
            return RepairStrategy(strategy_type="fix_output_format", description="fix")

        async def apply_repair(self, strategy, codebase, spec):
            (codebase.root_path / "main.py").write_text("print('worse')\n", encoding="utf-8")
            (codebase.root_path / "extra.py").write_text("print('extra')\n", encoding="utf-8")
            codebase.files["main.py"] = "print('worse')\n"
            codebase.files["extra.py"] = "print('extra')\n"
            return codebase

    monkeypatch.setattr(meta_module, "ProbeEngine", FakeProbeEngine)
    monkeypatch.setattr(meta_module, "SpecSynthesizer", FakeSpecSynthesizer)
    monkeypatch.setattr(meta_module, "ArchitectAgent", FakeArchitectAgent)
    monkeypatch.setattr(meta_module, "ImplementerAgent", FakeImplementerAgent)
    monkeypatch.setattr(meta_module, "DifferentialTester", FakeDifferentialTester)
    monkeypatch.setattr(meta_module, "RepairLoop", FakeRepairLoop)

    controller = MetaController(
        llm_client=MockLLMClient(),
        output_root=tmp_path,
        max_repair_iterations=1,
    )

    result = await controller.run("sample", tmp_path / "reference.py", "docs")

    assert FakeDifferentialTester.calls == 2
    assert result.resolved_rate == 0.5
    assert result.iterations_used == 1
    assert result.codebase.files == {"main.py": "print('initial')\n"}
    assert (tmp_path / "sample" / "main.py").read_text(encoding="utf-8") == "print('initial')\n"
    assert not (tmp_path / "sample" / "extra.py").exists()
    assert any("Repair rejected" in log for log in result.logs)
    decisions = result.implementation_metadata["repair_decisions"]
    assert len(decisions) == 1
    decision = decisions[0]
    assert decision["cluster_kind"] == "stdout"
    assert decision["cluster_size"] == 1
    assert decision["pre_exploration_rate"] == 0.5
    assert decision["post_exploration_rate"] == 0.0
    assert decision["status"] == "rejected"
    assert decision["reject_reason"] == "exploration_regressed"
    assert decision["holdout_evaluated"] is False
    assert "reports" not in decision
    assert "original_stdout" not in decision
    assert "replacement_stdout" not in decision


@pytest.mark.asyncio
async def test_meta_controller_rejects_syntax_broken_repair_before_acceptance(monkeypatch, tmp_path):
    import core.meta_controller as meta_module

    samples = [
        BehaviorSample(
            test_case=TestCase(name="kept_pass"),
            observed_result=TestResult(stdout="ok", exit_code=0),
        ),
        BehaviorSample(
            test_case=TestCase(name="known_fail"),
            observed_result=TestResult(stdout="expected", exit_code=0),
        ),
    ]
    initial_reports = [
        DiffReport(
            test_case=samples[0].test_case,
            original_result=samples[0].observed_result,
            replacement_result=samples[0].observed_result,
            stdout_match=True,
            stderr_match=True,
            exit_code_match=True,
            file_outputs_match=True,
        ),
        DiffReport(
            test_case=samples[1].test_case,
            original_result=samples[1].observed_result,
            replacement_result=TestResult(stdout="wrong", exit_code=0),
            stdout_match=False,
            stderr_match=True,
            exit_code_match=True,
            file_outputs_match=True,
        ),
    ]

    class FakeProbeEngine:
        cli_surface = None

        def __init__(self, *args, **kwargs):
            pass

        async def probe(self):
            return samples

    class FakeSpecSynthesizer:
        def __init__(self, *args, **kwargs):
            pass

        async def synthesize(self, *args, **kwargs):
            return ProgramSpec(summary="spec")

    class FakeArchitectAgent:
        def __init__(self, *args, **kwargs):
            pass

        async def design(self, *args, **kwargs):
            return ArchitectureBlueprint(language="python", entry_point="main.py")

    class FakeImplementerAgent:
        def __init__(self, *args, **kwargs):
            pass

        async def implement(self, spec, blueprint, output_dir):
            output_dir.mkdir(parents=True, exist_ok=True)
            path = output_dir / "main.py"
            path.write_text("print('initial')\n", encoding="utf-8")
            return Codebase(
                root_path=output_dir,
                language="python",
                files={"main.py": "print('initial')\n"},
                executable_path=path,
            )

    class FakeDifferentialTester:
        calls = 0

        def __init__(self, *args, **kwargs):
            pass

        async def run_full_suite(self, corpus):
            FakeDifferentialTester.calls += 1
            return initial_reports

    class FakeRepairLoop:
        def __init__(self, *args, **kwargs):
            pass

        async def diagnose_cluster(self, cluster, spec, codebase):
            return RepairStrategy(strategy_type="fix_algorithm", description="broken repair")

        async def apply_repair(self, strategy, codebase, spec):
            (codebase.root_path / "main.py").write_text("def broken(:\n", encoding="utf-8")
            codebase.files["main.py"] = "def broken(:\n"
            return codebase

    monkeypatch.setattr(meta_module, "ProbeEngine", FakeProbeEngine)
    monkeypatch.setattr(meta_module, "SpecSynthesizer", FakeSpecSynthesizer)
    monkeypatch.setattr(meta_module, "ArchitectAgent", FakeArchitectAgent)
    monkeypatch.setattr(meta_module, "ImplementerAgent", FakeImplementerAgent)
    monkeypatch.setattr(meta_module, "DifferentialTester", FakeDifferentialTester)
    monkeypatch.setattr(meta_module, "RepairLoop", FakeRepairLoop)

    controller = MetaController(
        llm_client=MockLLMClient(),
        output_root=tmp_path,
        max_repair_iterations=1,
    )

    result = await controller.run("sample", tmp_path / "reference.py", "docs")

    assert FakeDifferentialTester.calls == 2
    assert result.resolved_rate == 0.5
    assert result.iterations_used == 1
    assert result.codebase.files == {"main.py": "print('initial')\n"}
    assert (tmp_path / "sample" / "main.py").read_text(encoding="utf-8") == "print('initial')\n"
    decisions = result.implementation_metadata["repair_decisions"]
    assert len(decisions) == 1
    decision = decisions[0]
    assert decision["status"] == "rejected"
    assert decision["reject_reason"] == "repair_integrity_failed"
    assert decision["post_exploration_rate"] is None
    assert "syntax error" in decision["integrity_issues"][0]
    assert any("Repair rejected: generated candidate failed integrity check" in log for log in result.logs)


@pytest.mark.asyncio
async def test_meta_controller_tries_next_cluster_after_regressive_repair(monkeypatch, tmp_path):
    import core.meta_controller as meta_module

    samples = [
        BehaviorSample(test_case=TestCase(name="pass"), observed_result=TestResult(stdout="ok", exit_code=0)),
        BehaviorSample(test_case=TestCase(name="stdout_fail"), observed_result=TestResult(stdout="expected", exit_code=0)),
        BehaviorSample(test_case=TestCase(name="stderr_fail"), observed_result=TestResult(stderr="expected", exit_code=0)),
    ]

    initial_reports = [
        DiffReport(
            test_case=samples[0].test_case,
            original_result=samples[0].observed_result,
            replacement_result=samples[0].observed_result,
            stdout_match=True,
            stderr_match=True,
            exit_code_match=True,
            file_outputs_match=True,
        ),
        DiffReport(
            test_case=samples[1].test_case,
            original_result=samples[1].observed_result,
            replacement_result=TestResult(stdout="wrong", exit_code=0),
            stdout_match=False,
            stderr_match=True,
            exit_code_match=True,
            file_outputs_match=True,
        ),
        DiffReport(
            test_case=samples[2].test_case,
            original_result=samples[2].observed_result,
            replacement_result=TestResult(stderr="wrong", exit_code=0),
            stdout_match=True,
            stderr_match=False,
            exit_code_match=True,
            file_outputs_match=True,
        ),
    ]
    regressed_reports = [
        DiffReport(
            test_case=sample.test_case,
            original_result=sample.observed_result,
            replacement_result=TestResult(stdout="worse", stderr="worse", exit_code=1),
            stdout_match=False,
            stderr_match=False,
            exit_code_match=False,
            file_outputs_match=True,
        )
        for sample in samples
    ]
    improved_reports = [
        DiffReport(
            test_case=sample.test_case,
            original_result=sample.observed_result,
            replacement_result=sample.observed_result,
            stdout_match=True,
            stderr_match=True,
            exit_code_match=True,
            file_outputs_match=True,
        )
        for sample in samples
    ]

    class FakeProbeEngine:
        cli_surface = None

        def __init__(self, *args, **kwargs):
            pass

        async def probe(self):
            return samples

    class FakeSpecSynthesizer:
        def __init__(self, *args, **kwargs):
            pass

        async def synthesize(self, *args, **kwargs):
            return ProgramSpec(summary="spec")

    class FakeArchitectAgent:
        def __init__(self, *args, **kwargs):
            pass

        async def design(self, *args, **kwargs):
            return ArchitectureBlueprint(language="python", entry_point="main.py")

    class FakeImplementerAgent:
        def __init__(self, *args, **kwargs):
            pass

        async def implement(self, spec, blueprint, output_dir):
            output_dir.mkdir(parents=True, exist_ok=True)
            path = output_dir / "main.py"
            path.write_text("print('initial')\n", encoding="utf-8")
            return Codebase(
                root_path=output_dir,
                language="python",
                files={"main.py": "print('initial')\n"},
                executable_path=path,
            )

    class FakeDifferentialTester:
        calls = 0

        def __init__(self, *args, **kwargs):
            pass

        async def run_full_suite(self, corpus):
            FakeDifferentialTester.calls += 1
            if FakeDifferentialTester.calls == 1:
                return initial_reports
            if FakeDifferentialTester.calls == 2:
                return regressed_reports
            return improved_reports

    class FakeRepairLoop:
        seen_kinds = []

        def __init__(self, *args, **kwargs):
            pass

        async def diagnose_cluster(self, cluster, spec, codebase):
            FakeRepairLoop.seen_kinds.append(cluster.kind)
            return RepairStrategy(strategy_type="fix_output_format", description="fix")

        async def apply_repair(self, strategy, codebase, spec):
            codebase.files["main.py"] = "print('changed')\n"
            (codebase.root_path / "main.py").write_text("print('changed')\n", encoding="utf-8")
            return codebase

    monkeypatch.setattr(meta_module, "ProbeEngine", FakeProbeEngine)
    monkeypatch.setattr(meta_module, "SpecSynthesizer", FakeSpecSynthesizer)
    monkeypatch.setattr(meta_module, "ArchitectAgent", FakeArchitectAgent)
    monkeypatch.setattr(meta_module, "ImplementerAgent", FakeImplementerAgent)
    monkeypatch.setattr(meta_module, "DifferentialTester", FakeDifferentialTester)
    monkeypatch.setattr(meta_module, "RepairLoop", FakeRepairLoop)

    controller = MetaController(
        llm_client=MockLLMClient(),
        output_root=tmp_path,
        max_repair_iterations=2,
        internal_holdout_ratio=0.0,
    )

    result = await controller.run("sample", tmp_path / "reference.py", "docs")

    assert result.resolved_rate == 1.0
    assert result.iterations_used == 2
    assert FakeDifferentialTester.calls == 3
    assert len(FakeRepairLoop.seen_kinds) == 2
    assert FakeRepairLoop.seen_kinds[0] != FakeRepairLoop.seen_kinds[1]
    assert any("Repair rejected" in log for log in result.logs)
    decisions = result.implementation_metadata["repair_decisions"]
    assert [decision["status"] for decision in decisions] == ["rejected", "accepted"]
    assert decisions[0]["reject_reason"] == "exploration_regressed"
    assert decisions[1]["reject_reason"] is None
    assert decisions[1]["pre_exploration_rate"] == pytest.approx(1 / 3)
    assert decisions[1]["post_exploration_rate"] == 1.0
    assert all(decision["holdout_evaluated"] is False for decision in decisions)


@pytest.mark.asyncio
async def test_meta_controller_skips_repair_on_llm_transport_failure(monkeypatch, tmp_path):
    import core.meta_controller as meta_module

    test_case = TestCase(name="help", args=["--help"])
    sample = BehaviorSample(
        test_case=test_case,
        observed_result=TestResult(stdout="ok", exit_code=0),
    )
    failed_report = DiffReport(
        test_case=test_case,
        original_result=TestResult(stdout="ok", exit_code=0),
        replacement_result=TestResult(stdout="bad", exit_code=0),
        stdout_match=False,
        stderr_match=True,
        exit_code_match=True,
        file_outputs_match=True,
    )

    class FakeProbeEngine:
        cli_surface = None

        def __init__(self, *args, **kwargs):
            pass

        async def probe(self):
            return [sample]

    class FakeSpecSynthesizer:
        def __init__(self, *args, **kwargs):
            pass

        async def synthesize(self, *args, **kwargs):
            return ProgramSpec(summary="spec")

    class FakeArchitectAgent:
        def __init__(self, *args, **kwargs):
            pass

        async def design(self, *args, **kwargs):
            return ArchitectureBlueprint(language="python", entry_point="main.py")

    class FakeImplementerAgent:
        def __init__(self, *args, **kwargs):
            pass

        async def implement(self, spec, blueprint, output_dir):
            output_dir.mkdir(parents=True, exist_ok=True)
            path = output_dir / "main.py"
            path.write_text("print('bad')\n", encoding="utf-8")
            return Codebase(
                root_path=output_dir,
                language="python",
                files={"main.py": "print('bad')\n"},
                executable_path=path,
            )

    class FakeDifferentialTester:
        def __init__(self, *args, **kwargs):
            pass

        async def run_full_suite(self, corpus):
            return [failed_report]

    class FakeRepairLoop:
        def __init__(self, *args, **kwargs):
            pass

        async def diagnose_cluster(self, cluster, spec, codebase):
            raise httpx.ConnectError("temporary")

    monkeypatch.setattr(meta_module, "ProbeEngine", FakeProbeEngine)
    monkeypatch.setattr(meta_module, "SpecSynthesizer", FakeSpecSynthesizer)
    monkeypatch.setattr(meta_module, "ArchitectAgent", FakeArchitectAgent)
    monkeypatch.setattr(meta_module, "ImplementerAgent", FakeImplementerAgent)
    monkeypatch.setattr(meta_module, "DifferentialTester", FakeDifferentialTester)
    monkeypatch.setattr(meta_module, "RepairLoop", FakeRepairLoop)

    result = await MetaController(
        llm_client=MockLLMClient(),
        output_root=tmp_path,
        max_repair_iterations=1,
    ).run("sample", tmp_path / "reference.py", "docs")

    assert result.resolved_rate == 0.0
    assert result.iterations_used == 0
    assert any("Skipping repair iteration after LLM transport failure" in log for log in result.logs)
