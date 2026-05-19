from llm_clients.factory import create_llm_client, load_config
from llm_clients.file_bridge_client import FileBridgeClient
from llm_clients.local_openai_client import LocalOpenAIClient


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


def test_default_config_includes_loopback_local_openai_provider():
    config = load_config("config/settings.yaml")

    assert config["llm"]["local_openai"]["base_url"].startswith("http://127.0.0.1:")
    assert config["llm"]["local_openai"]["api_key"] == ""


def test_default_config_includes_file_bridge_provider():
    config = load_config("config/settings.yaml")

    assert config["llm"]["file_bridge"]["request_dir"] == "output/file_bridge_llm"
    assert config["llm"]["file_bridge"]["api_key"] == ""


def test_local_openai_smoke_config_uses_local_provider():
    config = load_config("config/smoke_local_openai.yaml")

    assert config["llm"]["provider"] == "local_openai"
    assert config["llm"]["local_openai"]["base_url"].startswith("http://127.0.0.1:")


def test_file_bridge_smoke_config_uses_file_bridge_provider():
    config = load_config("config/smoke_file_bridge.yaml")

    assert config["llm"]["provider"] == "file_bridge"
    assert config["llm"]["file_bridge"]["request_dir"] == "output/file_bridge_llm"


def test_factory_creates_local_openai_client_for_loopback_endpoint():
    client = create_llm_client(
        {
            "llm": {
                "provider": "local_openai",
                "local_openai": {
                    "api_key": "",
                    "base_url": "http://127.0.0.1:11434/v1",
                    "model": "local-model",
                    "temperature": 0.1,
                    "max_tokens": 256,
                    "timeout": 10,
                },
            }
        }
    )

    assert isinstance(client, LocalOpenAIClient)


def test_factory_creates_file_bridge_client():
    client = create_llm_client(
        {
            "llm": {
                "provider": "file_bridge",
                "file_bridge": {
                    "api_key": "",
                    "request_dir": "output/file_bridge_llm",
                    "model": "codex-file-bridge",
                    "poll_interval": 0.1,
                    "timeout": 30,
                },
            }
        }
    )

    assert isinstance(client, FileBridgeClient)


def test_default_architect_config_constrains_to_python():
    config = load_config("config/settings.yaml")

    assert config["architect"]["preferred_languages"] == ["python"]


def test_default_architect_config_prefers_single_file_python():
    config = load_config("config/settings.yaml")

    assert config["architect"]["max_modules"] == 1
