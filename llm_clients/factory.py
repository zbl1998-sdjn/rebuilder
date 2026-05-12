"""
Factory for creating LLM clients based on configuration.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Any

import yaml

from .base import BaseLLMClient
from .glm_client import GLMClient
from .kimi_client import KimiClient


def load_config(config_path: str = "config/settings.yaml") -> Dict[str, Any]:
    """Load YAML config, resolving environment variables."""
    config_file = Path(config_path)
    dotenv_values = _load_dotenv_values(config_file)
    with open(config_file, "r", encoding="utf-8") as f:
        raw = f.read()
    
    # Simple env var substitution: ${VAR_NAME} -> value
    import re
    def replace_env(match):
        var_name = match.group(1)
        return os.environ.get(var_name, dotenv_values.get(var_name, match.group(0)))
    
    raw = re.sub(r"\$\{([^}]+)\}", replace_env, raw)
    return yaml.safe_load(raw)


def _load_dotenv_values(config_path: Path) -> Dict[str, str]:
    """Load simple KEY=VALUE pairs from a project-local .env file."""
    candidates = [
        Path.cwd() / ".env",
        config_path.resolve().parent.parent / ".env",
    ]
    values: Dict[str, str] = {}
    for path in candidates:
        if not path.exists():
            continue
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def create_llm_client(config: Dict[str, Any] | str | None = None) -> BaseLLMClient:
    """Create an LLM client from config or auto-detect."""
    if config is None:
        config = load_config()
    elif isinstance(config, str):
        config = load_config(config)
    
    llm_cfg = config["llm"]
    provider = llm_cfg["provider"]
    
    if provider == "glm":
        cfg = llm_cfg["glm"]
        return GLMClient(
            api_key=cfg["api_key"],
            base_url=cfg["base_url"],
            model=cfg["model"],
            temperature=cfg.get("temperature", 0.3),
            max_tokens=cfg.get("max_tokens", 8192),
            timeout=cfg.get("timeout", 120),
            thinking=cfg.get("thinking"),
            max_retries=cfg.get("max_retries", 2),
            retry_delay=cfg.get("retry_delay", 1.0),
        )
    elif provider == "kimi":
        cfg = llm_cfg["kimi"]
        return KimiClient(
            api_key=cfg["api_key"],
            base_url=cfg["base_url"],
            model=cfg["model"],
            temperature=cfg.get("temperature", 0.3),
            max_tokens=cfg.get("max_tokens", 8192),
            timeout=cfg.get("timeout", 120),
        )
    else:
        raise ValueError(f"Unknown LLM provider: {provider}")
