"""Stateful cleanroom probe planning and execution."""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from core.data_models import BehaviorSample, TestCase
from utils.executable import SandboxExecutor


@dataclass(frozen=True)
class StatefulProbeStep:
    test_case: TestCase


@dataclass(frozen=True)
class StatefulProbePlan:
    name: str
    steps: list[StatefulProbeStep]


class StatefulProbePlanner:
    """Plan cleanroom-safe multi-run probes from documented CLI behavior."""

    def plan(self, documentation: str) -> list[StatefulProbePlan]:
        text = documentation.lower()
        if not all(command in text for command in ["add", "query", "remove"]):
            return []
        if "_zo_data_dir" not in text:
            return []

        env = {"_ZO_DATA_DIR": ".rebuilder-state/zoxide"}
        return [
            StatefulProbePlan(
                name="stateful_add_query_remove",
                steps=[
                    StatefulProbeStep(
                        TestCase(
                            name="stateful_add_alpha",
                            args=["add", "alpha"],
                            input_files={"alpha/.keep": ""},
                            env_vars=env,
                            description="Add an existing directory into a shared state directory",
                        )
                    ),
                    StatefulProbeStep(
                        TestCase(
                            name="stateful_query_alpha_after_add",
                            args=["query", "alpha"],
                            env_vars=env,
                            description="Query a directory after it was added in the same state directory",
                        )
                    ),
                    StatefulProbeStep(
                        TestCase(
                            name="stateful_remove_alpha",
                            args=["remove", "alpha"],
                            env_vars=env,
                            description="Remove a directory from the same state directory",
                        )
                    ),
                    StatefulProbeStep(
                        TestCase(
                            name="stateful_query_alpha_after_remove",
                            args=["query", "alpha"],
                            env_vars=env,
                            description="Query a directory after removal in the same state directory",
                        )
                    ),
                ],
            )
        ]


class StatefulProbeRunner:
    """Run a stateful probe plan in one shared working directory."""

    def __init__(
        self,
        executable,
        backend=None,
        timeout: float = 10.0,
        work_root: Path | None = None,
    ):
        self.executor = SandboxExecutor(executable, timeout=timeout, backend=backend)
        self.work_root = work_root

    async def run_plan(self, plan: StatefulProbePlan) -> list[BehaviorSample]:
        if self.work_root is not None:
            workdir = self.work_root / plan.name
            if workdir.exists():
                shutil.rmtree(workdir)
            workdir.mkdir(parents=True)
            return await self._run_steps(plan, workdir)

        with tempfile.TemporaryDirectory() as tmpdir:
            return await self._run_steps(plan, Path(tmpdir))

    async def _run_steps(
        self,
        plan: StatefulProbePlan,
        workdir: Path,
    ) -> list[BehaviorSample]:
        samples: list[BehaviorSample] = []
        for index, step in enumerate(plan.steps):
            result = await self.executor.run_in_workdir(step.test_case, workdir)
            tags = [
                "stateful",
                f"stateful_plan:{plan.name}",
                f"stateful_step:{index}",
            ]
            if result.exit_code != 0:
                tags.append("error_mode")
            samples.append(
                BehaviorSample(
                    test_case=step.test_case,
                    observed_result=result,
                    tags=tags,
                )
            )
        return samples
