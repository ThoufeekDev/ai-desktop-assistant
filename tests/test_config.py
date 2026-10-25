
"""Tests for FRIDAY configuration loading."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from friday.config import (
    AppConfig,
    OllamaConfig,
    default_config_path,
    load_config,
)


class ConfigTests(unittest.TestCase):
    def test_missing_file_uses_defaults(self) -> None:
        config = load_config(Path("/nonexistent/friday/config.toml"))

        self.assertEqual(config, AppConfig())

    def test_custom_ollama_settings(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.toml"
            config_path.write_text(
                """
[ollama]
base_url = "http://localhost:11434/"
model = "qwen2.5:3b-instruct"
timeout = 60
""",
                encoding="utf-8",
            )

            config = load_config(config_path)

        self.assertEqual(
            config.ollama,
            OllamaConfig(
                base_url="http://localhost:11434",
                model="qwen2.5:3b-instruct",
                timeout=60.0,
            ),
        )

    def test_invalid_base_url_is_rejected(self) -> None:
        self.assert_invalid_config('base_url = "   "')

    def test_invalid_model_is_rejected(self) -> None:
        self.assert_invalid_config('model = ""')

    def test_invalid_timeout_is_rejected(self) -> None:
        self.assert_invalid_config("timeout = 0")

    def test_boolean_timeout_is_rejected(self) -> None:
        self.assert_invalid_config("timeout = true")

    def test_ollama_section_must_be_a_table(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.toml"
            config_path.write_text(
                'ollama = "invalid"',
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, r"\[ollama\]"):
                load_config(config_path)

    def test_xdg_config_home_is_respected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict(os.environ, {"XDG_CONFIG_HOME": temp_dir}):
                self.assertEqual(
                    default_config_path(),
                    Path(temp_dir) / "friday" / "config.toml",
                )

    def test_default_system_prompt_and_history_limit(self) -> None:
        config = load_config(Path("/nonexistent/friday/config.toml"))

        self.assertIn("FRIDAY", config.ollama.system_prompt)
        self.assertEqual(config.ollama.max_history_turns, 10)

    def test_custom_system_prompt_and_history_limit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.toml"
            config_path.write_text(
                '[ollama]\n'
                'system_prompt = "You are a concise coding assistant."\n'
                'max_history_turns = 5\n',
                encoding="utf-8",
            )

            config = load_config(config_path)

        self.assertEqual(
            config.ollama.system_prompt,
            "You are a concise coding assistant.",
        )
        self.assertEqual(config.ollama.max_history_turns, 5)

    def test_invalid_history_limit_is_rejected(self) -> None:
        self.assert_invalid_config("max_history_turns = 0")

    def assert_invalid_config(self, setting: str) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.toml"
            config_path.write_text(
                f"[ollama]\n{setting}\n",
                encoding="utf-8",
            )

            with self.assertRaises(ValueError):
                load_config(config_path)


if __name__ == "__main__":
    unittest.main()
