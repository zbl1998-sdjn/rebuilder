from types import SimpleNamespace

from main import build_controller, discover_run_session, resolve_provider_api_key, resolve_task_id
from core.execution import WSLExecutorBackend
from core.session import RunSession
from tests.test_probe_engine import MockLLMClient


def args(max_repairs=None, output=None, static_output_assets="config", probe_iterations=None):
    return SimpleNamespace(
        max_repairs=max_repairs,
        probe_iterations=probe_iterations,
        output=output,
        replacement_executor=None,
        static_output_assets=static_output_assets,
    )


def test_build_controller_uses_yaml_config_when_cli_does_not_override(tmp_path):
    config = {
        "probe": {"max_probe_iterations": 12, "timeout_per_run": 3},
        "architect": {
            "preferred_languages": ["python"],
            "complexity_threshold": 4,
            "max_modules": 2,
        },
        "controller": {
            "max_repair_iterations": 7,
            "min_probe_coverage": 0.5,
            "internal_holdout_ratio": 0.25,
            "holdout_seed": "fixed",
        },
    }
    controller = build_controller(MockLLMClient(), config, args(output=str(tmp_path / "out")))

    assert controller.max_repair_iterations == 7
    assert controller.min_probe_coverage == 0.5
    assert controller.probe_iterations == 12
    assert controller.probe_timeout == 3
    assert controller.output_root == tmp_path / "out"
    assert controller.internal_holdout_ratio == 0.25
    assert controller.holdout_seed == "fixed"
    assert controller.preferred_languages == ["python"]
    assert controller.architect_complexity_threshold == 4
    assert controller.max_architecture_modules == 2


def test_build_controller_lets_cli_override_repair_iterations(tmp_path):
    config = {
        "probe": {"max_probe_iterations": 12, "timeout_per_run": 3},
        "controller": {"max_repair_iterations": 7, "min_probe_coverage": 0.5},
    }
    controller = build_controller(MockLLMClient(), config, args(max_repairs=2, output=str(tmp_path / "out")))

    assert controller.max_repair_iterations == 2


def test_build_controller_lets_cli_override_probe_iterations(tmp_path):
    config = {
        "probe": {"max_probe_iterations": 12, "timeout_per_run": 3},
        "controller": {"max_repair_iterations": 7, "min_probe_coverage": 0.5},
    }
    controller = build_controller(MockLLMClient(), config, args(probe_iterations=60, output=str(tmp_path / "out")))

    assert controller.probe_iterations == 60


def test_build_controller_uses_session_generated_path_when_output_not_set(tmp_path):
    config = {"probe": {}, "controller": {}}
    session = RunSession.create(
        root_path=tmp_path / "runs",
        task_id="sample",
        source="programbench_cleanroom",
    )

    controller = build_controller(MockLLMClient(), config, args(), run_session=session)

    assert controller.output_root == session.generated_path
    assert controller.evidence_store is not None
    assert controller.evidence_store.root_path == session.evidence_path


def test_build_controller_configures_wsl_replacement_backend(tmp_path):
    config = {
        "probe": {},
        "controller": {},
        "execution": {"replacement_backend": "wsl"},
    }

    controller = build_controller(MockLLMClient(), config, args(output=str(tmp_path / "out")))

    assert isinstance(controller.replacement_executor_backend, WSLExecutorBackend)


def test_build_controller_configures_static_output_asset_toggle(tmp_path):
    config = {
        "probe": {},
        "controller": {},
        "implementation": {"static_output_assets": False},
    }

    controller = build_controller(MockLLMClient(), config, args(output=str(tmp_path / "out")))

    assert controller.enable_static_output_assets is False


def test_build_controller_cli_overrides_static_output_asset_toggle(tmp_path):
    config = {
        "probe": {},
        "controller": {},
        "implementation": {"static_output_assets": True},
    }

    controller = build_controller(
        MockLLMClient(),
        config,
        args(output=str(tmp_path / "out"), static_output_assets="disabled"),
    )

    assert controller.enable_static_output_assets is False


def test_discover_run_session_from_workspace_path(tmp_path):
    session = RunSession.create(
        root_path=tmp_path / "runs",
        task_id="sample",
        source="programbench_cleanroom",
    )

    loaded = discover_run_session(session.workspace_path)

    assert loaded is not None
    assert loaded.task_id == "sample"


def test_resolve_provider_api_key_accepts_config_value_when_env_missing(monkeypatch):
    monkeypatch.delenv("GLM_API_KEY", raising=False)
    config = {"llm": {"provider": "glm", "glm": {"api_key": "from-config"}}}

    env_var, api_key = resolve_provider_api_key(config)

    assert env_var == "GLM_API_KEY"
    assert api_key == "from-config"


def test_resolve_task_id_prefers_run_session_id(tmp_path):
    session = RunSession.create(tmp_path / "runs", "owner__repo.abcdef0", "programbench_cleanroom")

    assert resolve_task_id(session.workspace_path, session) == "owner__repo.abcdef0"
