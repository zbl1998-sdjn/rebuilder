import os

from llm_clients.factory import load_config


def test_load_config_resolves_values_from_project_dotenv(tmp_path, monkeypatch):
    monkeypatch.delenv("GLM_API_KEY", raising=False)
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (tmp_path / ".env").write_text("GLM_API_KEY=from_dotenv\n", encoding="utf-8")
    config_path = config_dir / "settings.yaml"
    config_path.write_text(
        "llm:\n"
        "  provider: glm\n"
        "  glm:\n"
        "    api_key: \"${GLM_API_KEY}\"\n"
        "    base_url: \"https://api.z.ai/api/coding/paas/v4\"\n"
        "    model: \"glm-5.1\"\n",
        encoding="utf-8",
    )

    config = load_config(str(config_path))

    assert config["llm"]["glm"]["api_key"] == "from_dotenv"


def test_glm_config_uses_coding_plan_endpoint():
    config = load_config("config/settings.yaml")

    assert config["llm"]["glm"]["base_url"] == "https://api.z.ai/api/coding/paas/v4"


def test_glm_config_disables_thinking_for_structured_pipeline_calls():
    config = load_config("config/settings.yaml")

    assert config["llm"]["glm"]["thinking"] == {"type": "disabled"}


def test_glm_config_uses_resilient_request_settings():
    config = load_config("config/settings.yaml")

    assert config["llm"]["glm"]["timeout"] >= 300
    assert config["llm"]["glm"]["max_retries"] >= 5
    assert config["llm"]["glm"]["retry_delay"] >= 2


def test_default_architect_config_constrains_to_python():
    config = load_config("config/settings.yaml")

    assert config["architect"]["preferred_languages"] == ["python"]


def test_default_architect_config_prefers_single_file_python():
    config = load_config("config/settings.yaml")

    assert config["architect"]["max_modules"] == 1
