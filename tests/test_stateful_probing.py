import pytest

from core.data_models import TestCase, TestResult
from core.probing.stateful import StatefulProbePlanner, StatefulProbeRunner


def test_stateful_probe_planner_adds_zoxide_add_query_remove_plan():
    plans = StatefulProbePlanner().plan(
        documentation=(
            "Commands: add query remove\n"
            "Environment variables: _ZO_DATA_DIR Path for zoxide data files\n"
        )
    )

    assert len(plans) == 1
    plan = plans[0]
    assert plan.name == "stateful_add_query_remove"
    assert [step.test_case.args[0] for step in plan.steps] == ["add", "query", "remove", "query"]
    assert all(
        step.test_case.env_vars["_ZO_DATA_DIR"] == ".rebuilder-state/zoxide"
        for step in plan.steps
    )
    assert plan.steps[0].test_case.input_files == {"alpha/.keep": b""}


class SharedWorkdirBackend:
    def __init__(self):
        self.workdirs = []

    async def run_in_workdir(self, executable, test_case, workdir):
        self.workdirs.append(workdir)
        state_file = workdir / ".rebuilder-state" / "state.txt"
        if test_case.args[:1] == ["add"]:
            state_file.parent.mkdir(parents=True, exist_ok=True)
            state_file.write_text(test_case.args[1], encoding="utf-8")
            return TestResult(exit_code=0, output_files={"state.txt": b"set"})
        if test_case.args[:1] == ["query"]:
            value = state_file.read_text(encoding="utf-8") if state_file.exists() else ""
            return TestResult(stdout=value + "\n" if value else "", exit_code=0 if value else 1)
        return TestResult(exit_code=0)


@pytest.mark.asyncio
async def test_stateful_probe_runner_reuses_workdir_and_tags_samples(tmp_path):
    backend = SharedWorkdirBackend()
    plan = StatefulProbePlanner().plan(
        "Commands: add query remove\n_ZO_DATA_DIR Path for zoxide data files"
    )[0]

    samples = await StatefulProbeRunner(
        executable="reference",
        backend=backend,
        work_root=tmp_path,
    ).run_plan(plan)

    assert len(samples) == 4
    assert len(set(backend.workdirs)) == 1
    assert samples[1].observed_result.stdout == "alpha\n"
    assert all("stateful" in sample.tags for sample in samples)
    assert all("stateful_plan:stateful_add_query_remove" in sample.tags for sample in samples)
    assert samples[1].tags[-1] == "stateful_step:1"
