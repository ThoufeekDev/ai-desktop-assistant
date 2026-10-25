
"""Configuration loading for FRIDAY."""

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class OllamaConfig:
    """Settings for the local Ollama connection."""

    base_url: str = "http://127.0.0.1:11434"
    model: str = "qwen2.5:3b-instruct"
    timeout: float = 120.0
    system_prompt: str = (
        "You are FRIDAY, a helpful local AI assistant running on Linux. "
        "Be accurate, practical, concise, and transparent about uncertainty. "
        "Never claim to have performed an action you have not performed."
    )
    max_history_turns: int = 10


@dataclass(frozen=True, slots=True)
class AppConfig:
    """Application configuration."""

    ollama: OllamaConfig = OllamaConfig()


def default_config_path() -> Path:
    """Return FRIDAY's XDG configuration file path."""
    config_home = Path(
        os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")
    )
    return config_home / "friday" / "config.toml"


def load_config(path: Path | None = None) -> AppConfig:
    """Load configuration, using defaults if the file doesn't exist."""
    config_path = path if path is not None else default_config_path()

    if not config_path.exists():
        return AppConfig()

    with config_path.open("rb") as file:
        data = tomllib.load(file)

    ollama_data = data.get("ollama", {})

    if not isinstance(ollama_data, dict):
        raise ValueError("The [ollama] configuration section must be a table.")

    defaults = OllamaConfig()

    base_url = ollama_data.get("base_url", defaults.base_url)
    model = ollama_data.get("model", defaults.model)
    timeout = ollama_data.get("timeout", defaults.timeout)
    system_prompt = ollama_data.get(
        "system_prompt", defaults.system_prompt
    )
    max_history_turns = ollama_data.get(
        "max_history_turns", defaults.max_history_turns
    )

    if not isinstance(base_url, str) or not base_url.strip():
        raise ValueError("Ollama base_url must be a non-empty string.")

    if not isinstance(model, str) or not model.strip():
        raise ValueError("Ollama model must be a non-empty string.")

    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
        raise ValueError("Ollama timeout must be a number.")

    if timeout <= 0:
        raise ValueError("Ollama timeout must be greater than zero.")

    if not isinstance(system_prompt, str) or not system_prompt.strip():
        raise ValueError("Ollama system_prompt must be a non-empty string.")

    if (
        isinstance(max_history_turns, bool)
        or not isinstance(max_history_turns, int)
    ):
        raise ValueError("Ollama max_history_turns must be an integer.")

    if max_history_turns < 1:
        raise ValueError("Ollama max_history_turns must be at least 1.")

    return AppConfig(
        ollama=OllamaConfig(
            base_url=base_url.rstrip("/"),
            model=model.strip(),
            timeout=float(timeout),
            system_prompt=system_prompt.strip(),
            max_history_turns=max_history_turns,
        )
    )
