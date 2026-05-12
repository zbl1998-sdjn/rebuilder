"""
Meta Controller: Orchestrate the full ReBuilder pipeline.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import List, Optional

import httpx
from rich.console import Console
from rich.progress import Progress, TextColumn

from core.data_models import (
    BehaviorSample,
    Codebase,
    DiffReport,
    ProgramSpec,
    ArchitectureBlueprint,
    TaskResult,
)
from core.probe_engine import ProbeEngine
from core.probing.corpus import CorpusSplitter
from core.spec_synthesizer import SpecSynthesizer
from core.architect_agent import ArchitectAgent
from core.implementer_agent import ImplementerAgent
from core.differential_tester import DifferentialTester
from core.evidence import EvidenceStore
from core.evaluation import FailureReportWriter
from core.repair.clustering import FailureClusterer
from core.repair_loop import RepairLoop
from core.session import RunSession
from llm_clients.base import BaseLLMClient


console = Console()


def progress_columns(description: str):
    """Return ASCII-safe progress columns for Windows consoles."""
    return [TextColumn("[progress.description]{task.description}")]


class MetaController:
    """Orchestrates the full probe-specify-architect-implement-validate-repair loop."""
    
    def __init__(
        self,
        llm_client: BaseLLMClient,
        max_repair_iterations: int = 10,
        min_probe_coverage: float = 0.0,
        output_root: Path | str = "./output",
        probe_iterations: int = 30,
        probe_timeout: float = 10.0,
        internal_holdout_ratio: float = 0.0,
        holdout_seed: str = "rebuilder",
        preferred_languages: List[str] | None = None,
        architect_complexity_threshold: int = 3,
        max_architecture_modules: int | None = None,
        run_session: RunSession | None = None,
        evidence_store: EvidenceStore | None = None,
        reference_executor_backend=None,
        replacement_executor_backend=None,
        enable_static_output_assets: bool = True,
    ):
        self.llm = llm_client
        self.max_repair_iterations = max_repair_iterations
        self.min_probe_coverage = min_probe_coverage
        self.output_root = Path(output_root)
        self.probe_iterations = probe_iterations
        self.probe_timeout = probe_timeout
        self.internal_holdout_ratio = internal_holdout_ratio
        self.holdout_seed = holdout_seed
        self.preferred_languages = preferred_languages or []
        self.architect_complexity_threshold = architect_complexity_threshold
        self.max_architecture_modules = max_architecture_modules
        self.run_session = run_session
        self.evidence_store = evidence_store or (
            EvidenceStore(run_session.evidence_path) if run_session else None
        )
        self.reference_executor_backend = reference_executor_backend
        self.replacement_executor_backend = replacement_executor_backend
        self.enable_static_output_assets = enable_static_output_assets
        self.probe_engine: Optional[ProbeEngine] = None
        self.spec: Optional[ProgramSpec] = None
        self.blueprint: Optional[ArchitectureBlueprint] = None
        self.codebase: Optional[Codebase] = None
        self.logs: List[str] = []
    
    def log(self, message: str):
        self.logs.append(message)
        console.log(f"[ReBuilder] {message}")
    
    async def run(self, task_id: str, executable: Path, documentation: str) -> TaskResult:
        """Execute the full ReBuilder pipeline on a ProgramBench task."""
        self.llm.reset_usage_tracking()
        self.log(f"Starting task {task_id}")
        self.log(f"Target executable: {executable}")
        
        # Phase 1: Probe
        with Progress(
            *progress_columns("Probing black-box executable..."),
            console=console,
        ) as progress:
            probe_task = progress.add_task("Probing black-box executable...", total=None)
            self.probe_engine = ProbeEngine(
                executable=executable,
                documentation=documentation,
                llm_client=self.llm,
                max_iterations=self.probe_iterations,
                timeout=self.probe_timeout,
                evidence_store=self.evidence_store,
                executor_backend=self.reference_executor_backend,
            )
            self.llm.set_usage_phase("probe")
            corpus = await self.probe_engine.probe()
            progress.update(probe_task, completed=True)
        
        self.log(f"Probe complete: {len(corpus)} behavior samples collected")
        corpus_split = CorpusSplitter(
            holdout_ratio=self.internal_holdout_ratio,
            seed=self.holdout_seed,
        ).split(corpus)
        exploration_corpus = corpus_split.exploration
        holdout_corpus = corpus_split.holdout
        if holdout_corpus:
            self.log(
                f"Internal split: {len(exploration_corpus)} exploration, "
                f"{len(holdout_corpus)} holdout"
            )
        
        # Phase 2: Synthesize Specification
        with Progress(
            *progress_columns("Synthesizing specification..."),
            console=console,
        ) as progress:
            spec_task = progress.add_task("Synthesizing specification...", total=None)
            synthesizer = SpecSynthesizer(self.llm)
            self.llm.set_usage_phase("spec_synthesis")
            self.spec = await synthesizer.synthesize(
                corpus=exploration_corpus,
                documentation=documentation,
                cli_surface=self.probe_engine.cli_surface,
            )
            progress.update(spec_task, completed=True)
        
        self.log(f"Specification synthesized: {self.spec.summary[:100]}...")
        
        # Phase 3: Architecture Design
        with Progress(
            *progress_columns("Designing architecture..."),
            console=console,
        ) as progress:
            arch_task = progress.add_task("Designing architecture...", total=None)
            architect = ArchitectAgent(
                self.llm,
                complexity_threshold=self.architect_complexity_threshold,
                preferred_languages=self.preferred_languages,
                max_modules=self.max_architecture_modules,
            )
            self.llm.set_usage_phase("architecture")
            self.blueprint = await architect.design(self.spec)
            progress.update(arch_task, completed=True)
        
        self.log(f"Architecture designed: {self.blueprint.language}, {len(self.blueprint.modules)} modules")
        
        # Phase 4: Implementation
        output_dir = self._output_dir_for_task(task_id)
        self._prepare_output_dir(output_dir)
        
        with Progress(
            *progress_columns("Implementing codebase..."),
            console=console,
        ) as progress:
            impl_task = progress.add_task("Implementing codebase...", total=None)
            implementer = ImplementerAgent(
                self.llm,
                enable_static_output_assets=self.enable_static_output_assets,
            )
            self.llm.set_usage_phase("implementation")
            self.codebase = await implementer.implement(self.spec, self.blueprint, output_dir)
            progress.update(impl_task, completed=True)
        
        self.log(f"Implementation complete: {len(self.codebase.files)} files")
        
        # Phase 5: Differential Validation & Repair Loop
        if not self.codebase.executable_path or not self.codebase.executable_path.exists():
            # For Python, we need to handle execution differently
            self.codebase.executable_path = self._resolve_executable(self.codebase)
        
        if self.codebase.executable_path:
            tester = DifferentialTester(
                original=executable,
                replacement=self.codebase.executable_path,
                llm_client=self.llm,
                original_backend=self.reference_executor_backend,
                replacement_backend=self.replacement_executor_backend,
            )
            
            best_reports: List[DiffReport] = []
            resolved_rate = 0.0
            accepted_codebase = self.codebase.model_copy(deep=True)
            accepted_reports: List[DiffReport] = []
            accepted_rate = -1.0
            repair_iterations_used = 0
            validation_passes = self.max_repair_iterations + 1
            
            for validation_pass in range(validation_passes):
                self.log(f"Validation pass {validation_pass + 1}/{validation_passes}")
                
                reports = await tester.run_full_suite(exploration_corpus)
                best_reports = reports
                
                passed = sum(1 for r in reports if r.is_equivalent)
                total = len(reports)
                resolved_rate = passed / total if total > 0 else 0.0
                self.log(f"Behavioral equivalence: {passed}/{total} ({resolved_rate:.1%})")

                if validation_pass > 0 and resolved_rate < accepted_rate:
                    self.log(
                        "Repair rejected: behavioral equivalence decreased "
                        f"from {accepted_rate:.1%} to {resolved_rate:.1%}"
                    )
                    self._restore_codebase_files(accepted_codebase, self.codebase)
                    self.codebase = accepted_codebase.model_copy(deep=True)
                    self.codebase.executable_path = self._resolve_executable(self.codebase)
                    best_reports = accepted_reports
                    resolved_rate = accepted_rate
                    break

                accepted_codebase = self.codebase.model_copy(deep=True)
                accepted_reports = reports
                accepted_rate = resolved_rate
                
                if resolved_rate >= 0.99:
                    self.log("Behavioral equivalence achieved!")
                    break

                if repair_iterations_used >= self.max_repair_iterations:
                    break
                
                cluster = FailureClusterer().repair_target(reports)
                if cluster is None:
                    break
                
                repair = RepairLoop(self.llm)
                self.log(
                    f"Repair target cluster: {cluster.kind.value} "
                    f"({len(cluster.reports)} failures)"
                )
                try:
                    self.llm.set_usage_phase("repair")
                    strategy = await repair.diagnose_cluster(cluster, self.spec, self.codebase)
                    self.log(f"Repair strategy: {strategy.strategy_type} -> {strategy.description[:80]}...")
                    self.llm.set_usage_phase("repair")
                    self.codebase = await repair.apply_repair(strategy, self.codebase, self.spec)
                except httpx.HTTPError as exc:
                    self.log(
                        "WARNING: Skipping repair iteration after LLM transport failure: "
                        f"{type(exc).__name__}"
                    )
                    break
                repair_iterations_used += 1
                # Re-resolve executable after repair
                self.codebase.executable_path = self._resolve_executable(self.codebase)
                if self.codebase.executable_path:
                    tester = DifferentialTester(
                        original=executable,
                        replacement=self.codebase.executable_path,
                        llm_client=self.llm,
                        original_backend=self.reference_executor_backend,
                        replacement_backend=self.replacement_executor_backend,
                    )
            
            almost_resolved = resolved_rate >= 0.95
            status = "success" if resolved_rate >= 0.99 else ("partial" if almost_resolved else "failed")
            self._write_exploration_failure_report(task_id, best_reports)
            holdout_resolved_rate = await self._evaluate_holdout(
                executable=executable,
                replacement=self.codebase.executable_path,
                holdout_corpus=holdout_corpus,
            )
            
            return TaskResult(
                task_id=task_id,
                status=status,
                codebase=self.codebase,
                final_diff_report=best_reports[0] if best_reports else None,
                resolved_rate=resolved_rate,
                almost_resolved=almost_resolved,
                iterations_used=repair_iterations_used,
                probes_conducted=len(corpus),
                exploration_cases=len(exploration_corpus),
                holdout_cases=len(holdout_corpus),
                holdout_resolved_rate=holdout_resolved_rate,
                implementation_metadata=self._implementation_metadata(),
                logs=self.logs,
            )
        else:
            self.log("ERROR: Could not resolve replacement executable path")
            return TaskResult(
                task_id=task_id,
                status="failed",
                codebase=self.codebase,
                resolved_rate=0.0,
                almost_resolved=False,
                iterations_used=0,
                probes_conducted=len(corpus),
                exploration_cases=len(exploration_corpus),
                holdout_cases=len(holdout_corpus),
                implementation_metadata=self._implementation_metadata(),
                logs=self.logs,
            )
    
    def _resolve_executable(self, codebase: Codebase) -> Optional[Path]:
        """Determine how to run the replacement codebase."""
        if codebase.executable_path and codebase.executable_path.exists():
            return codebase.executable_path

        if codebase.language.lower() == "python":
            # Find the entry point
            entry_candidates = ["main.py", "app.py", "cli.py", "__main__.py"]
            for candidate in entry_candidates:
                if candidate in codebase.files:
                    return codebase.root_path / candidate
        
        # For compiled languages, check for build artifacts
        # This is simplified; real implementation would run the build script
        return codebase.executable_path

    def _implementation_metadata(self) -> dict:
        llm_usage = self.llm.usage_summary()
        if not self.codebase:
            return {
                "static_output_assets_enabled": self.enable_static_output_assets,
                "llm_usage": llm_usage,
            }
        return {
            "static_output_assets_enabled": self.enable_static_output_assets,
            "llm_usage": llm_usage,
            **self.codebase.generation_metadata,
        }

    def _output_dir_for_task(self, task_id: str) -> Path:
        return self.output_root / task_id

    def _prepare_output_dir(self, output_dir: Path) -> None:
        """Create a clean per-task generated directory before implementation."""
        output_root = self.output_root.resolve()
        target = output_dir.resolve()
        target.relative_to(output_root)
        target.mkdir(parents=True, exist_ok=True)
        for child in target.iterdir():
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()

    def _write_exploration_failure_report(
        self,
        task_id: str,
        reports: List[DiffReport],
    ) -> None:
        """Write detailed diagnostics only for exploration failures."""
        if not self.run_session or not reports:
            return
        if all(report.is_equivalent for report in reports):
            return
        paths = FailureReportWriter().write(
            reports=reports,
            output_dir=self.run_session.reports_path,
            task_id=task_id,
            scope="exploration",
        )
        self.log(f"Exploration failure report: {paths.json_path}")

    def _restore_codebase_files(
        self,
        accepted: Codebase,
        current: Codebase | None,
    ) -> None:
        """Restore an accepted generated codebase inside its output directory."""
        if current is not None:
            for relative in set(current.files) - set(accepted.files):
                target = self._safe_codebase_path(accepted.root_path, relative)
                if target.exists() and target.is_file():
                    target.unlink()
                    self._remove_empty_generated_dirs(target.parent, accepted.root_path)

        for relative, content in accepted.files.items():
            target = self._safe_codebase_path(accepted.root_path, relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")

    def _safe_codebase_path(self, root_path: Path, relative_path: str) -> Path:
        root = root_path.resolve()
        target = (root / relative_path).resolve()
        target.relative_to(root)
        return target

    def _remove_empty_generated_dirs(self, directory: Path, root_path: Path) -> None:
        root = root_path.resolve()
        current = directory.resolve()
        while current != root and root in current.parents:
            try:
                current.rmdir()
            except OSError:
                return
            current = current.parent

    async def _evaluate_holdout(
        self,
        executable,
        replacement: Path | None,
        holdout_corpus: List[BehaviorSample],
    ) -> float | None:
        """Evaluate held-out cleanroom observations without exposing detailed failures."""
        if not holdout_corpus or replacement is None:
            return None
        tester = DifferentialTester(
            original=executable,
            replacement=replacement,
            llm_client=None,
            original_backend=self.reference_executor_backend,
            replacement_backend=self.replacement_executor_backend,
        )
        reports = await tester.run_full_suite(holdout_corpus)
        passed = sum(1 for report in reports if report.is_equivalent)
        total = len(reports)
        rate = passed / total if total else 0.0
        self.log(f"Holdout behavioral equivalence: {passed}/{total} ({rate:.1%})")
        return rate
