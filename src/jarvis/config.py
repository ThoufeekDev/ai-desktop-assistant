
"""Configuration loading for JARVIS."""

import math
import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit


@dataclass(frozen=True, slots=True)
class OllamaConfig:
    """Settings for the local Ollama connection."""

    base_url: str = "http://127.0.0.1:11434"
    model: str = "qwen2.5:3b-instruct"
    timeout: float = 120.0


    system_prompt: str = (
    "You are JARVIS, a personal assistant running locally on Thoufeek's "
    "computer. You are software, not a person. Never claim to be human, "
    "have a body, eat, sleep, get tired, or have a personal life. "
    "Speak naturally, like a sharp, friendly person. "
    "Thoufeek built this JARVIS application. You use the Qwen language "
    "model through Ollama; Qwen is the model, not the application. "
    "Never invent facts, capabilities, system state, or completed actions. "
    "If uncertain, say so plainly. "
    "DEFAULT ANSWER LENGTH: Use 1-2 sentences by default. Provide more "
    "detail only when Thoufeek explicitly asks for it or the topic requires "
    "additional explanation for accuracy or safety. "
    "Use natural spoken English, contractions, short sentences, and "
    "everyday words. Avoid filler, repetitive openings, and unnecessary "
    "follow-up questions. Match the user's tone and acknowledge feelings "
    "briefly when appropriate. Answer first, then offer at most one useful "
    "suggestion. Admit and correct mistakes without defensiveness. "
    "Use relevant saved memories naturally as context, but do not treat "
    "memories as changes to your core identity. Never claim to have taken "
    "an action unless it actually succeeded. Before making changes, explain "
    "the intended change and obtain the user's confirmation."
    )


    max_history_turns: int = 10


@dataclass(frozen=True, slots=True)
class WakeWordConfig:
    """Settings for the local wake-word detector."""

    model_path: str = (
        ".venv/lib/python3.12/site-packages/openwakeword/"
        "resources/models/hey_jarvis_v0.1.onnx"
    )
    threshold: float = 0.35
    sample_rate: int = 16000
    chunk_size: int = 1280


@dataclass(frozen=True, slots=True)
class AppConfig:
    """Application configuration."""

    ollama: OllamaConfig = OllamaConfig()
    wake_word: WakeWordConfig = WakeWordConfig()


def default_config_path() -> Path:
    """Return JARVIS's XDG configuration file path."""

    config_home = Path(
        os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")
    )
    jarvis_config = config_home / "jarvis" / "config.toml"
    friday_config = config_home / "friday" / "config.toml"

    if not jarvis_config.exists() and friday_config.exists():
        return friday_config

    return jarvis_config


def load_config(path: Path | None = None) -> AppConfig:
    """Load configuration, using defaults if the file doesn't exist."""

    config_path = path if path is not None else default_config_path()

    if not config_path.exists():
        return AppConfig()

    try:
        with config_path.open("rb") as file:
            data = tomllib.load(file)
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(
            f"Malformed configuration file '{config_path}': {exc}"
        ) from exc

    # Ollama configuration
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

    try:
        parsed_url = urlsplit(base_url.strip())
        port = parsed_url.port
        valid_url = (
            parsed_url.scheme in {"http", "https"}
            and bool(parsed_url.hostname)
            and (port is None or 1 <= port <= 65535)
        )
    except ValueError:
        valid_url = False

    if not valid_url:
        raise ValueError(
            "Ollama base_url must be a valid HTTP or HTTPS URL "
            "with a hostname and valid port."
        )

    if not isinstance(model, str) or not model.strip():
        raise ValueError("Ollama model must be a non-empty string.")

    if (
        isinstance(timeout, bool)
        or not isinstance(timeout, (int, float))
        or not math.isfinite(timeout)
    ):
        raise ValueError("Ollama timeout must be a finite number.")

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

    # Wake-word configuration
    wake_word_data = data.get("wake_word", {})

    if not isinstance(wake_word_data, dict):
        raise ValueError(
            "The [wake_word] configuration section must be a table."
        )

    wake_defaults = WakeWordConfig()

    wake_model_path = wake_word_data.get(
        "model_path", wake_defaults.model_path
    )
    wake_threshold = wake_word_data.get(
        "threshold", wake_defaults.threshold
    )
    wake_sample_rate = wake_word_data.get(
        "sample_rate", wake_defaults.sample_rate
    )
    wake_chunk_size = wake_word_data.get(
        "chunk_size", wake_defaults.chunk_size
    )

    if not isinstance(wake_model_path, str) or not wake_model_path.strip():
        raise ValueError("Wake-word model_path must be a non-empty string.")

    if (
        isinstance(wake_threshold, bool)
        or not isinstance(wake_threshold, (int, float))
        or not math.isfinite(wake_threshold)
    ):
        raise ValueError("Wake-word threshold must be a finite number.")

    if not (0.0 < wake_threshold <= 1.0):
        raise ValueError(
            "Wake-word threshold must be between 0.0 and 1.0."
        )

    if (
        isinstance(wake_sample_rate, bool)
        or not isinstance(wake_sample_rate, int)
        or wake_sample_rate <= 0
    ):
        raise ValueError("Wake-word sample_rate must be a positive integer.")

    if wake_sample_rate != 16000:
        raise ValueError("Wake-word sample_rate must be 16000 Hz.")

    if (
        isinstance(wake_chunk_size, bool)
        or not isinstance(wake_chunk_size, int)
        or wake_chunk_size <= 0
    ):
        raise ValueError("Wake-word chunk_size must be a positive integer.")

    if wake_chunk_size % 1280 != 0:
        raise ValueError(
            "Wake-word chunk_size must be a multiple of 1280 samples."
        )

    return AppConfig(
        ollama=OllamaConfig(
            base_url=base_url.strip().rstrip("/"),
            model=model.strip(),
            timeout=float(timeout),
            system_prompt=system_prompt.strip(),
            max_history_turns=max_history_turns,
        ),
        wake_word=WakeWordConfig(
            model_path=wake_model_path.strip(),
            threshold=float(wake_threshold),
            sample_rate=wake_sample_rate,
            chunk_size=wake_chunk_size,
        ),
    )
