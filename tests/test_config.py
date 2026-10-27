
"""Tests for JARVIS configuration loading."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jarvis.config import (
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
                    Path(temp_dir) / "jarvis" / "config.toml",
                )

    def test_default_system_prompt_and_history_limit(self) -> None:
        config = load_config(Path("/nonexistent/friday/config.toml"))

        self.assertIn("JARVIS", config.ollama.system_prompt)
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


    def test_base_url_without_scheme_is_rejected(self) -> None:
        self.assert_invalid_config('base_url = "localhost:11434"')

    def test_base_url_without_hostname_is_rejected(self) -> None:
        self.assert_invalid_config('base_url = "http://"')

    def test_base_url_with_invalid_port_is_rejected(self) -> None:
        self.assert_invalid_config('base_url = "http://localhost:invalid"')

    def test_https_base_url_is_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.toml"
            config_path.write_text(
                '[ollama]\nbase_url = "https://localhost:11434/"\n',
                encoding="utf-8",
            )

            config = load_config(config_path)

        self.assertEqual(
            config.ollama.base_url,
            "https://localhost:11434",
        )



    def test_malformed_toml_raises_value_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.toml"
            config_path.write_text("[ollama\nunclosed_bracket = true", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Malformed configuration file"):
                load_config(config_path)

    def test_non_finite_timeout_is_rejected(self) -> None:
        self.assert_invalid_config("timeout = inf")
        self.assert_invalid_config("timeout = -inf")
        self.assert_invalid_config("timeout = nan")

    def test_wrong_timeout_types_rejected(self) -> None:
        self.assert_invalid_config('timeout = "fast"')
        self.assert_invalid_config("timeout = true")

    def test_wake_word_threshold_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.toml"

            # 0.0 threshold rejected
            config_path.write_text("[wake_word]\nthreshold = 0.0\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Wake-word threshold"):
                load_config(config_path)

            # > 1.0 threshold rejected
            config_path.write_text("[wake_word]\nthreshold = 1.5\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Wake-word threshold"):
                load_config(config_path)

            # nan/inf threshold rejected
            config_path.write_text("[wake_word]\nthreshold = nan\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Wake-word threshold"):
                load_config(config_path)

            config_path.write_text("[wake_word]\nthreshold = inf\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Wake-word threshold"):
                load_config(config_path)

            # boolean threshold rejected
            config_path.write_text("[wake_word]\nthreshold = true\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Wake-word threshold"):
                load_config(config_path)

            # Valid custom threshold
            config_path.write_text("[wake_word]\nthreshold = 0.65\n", encoding="utf-8")
            cfg = load_config(config_path)
            self.assertEqual(cfg.wake_word.threshold, 0.65)

    def test_wake_word_audio_parameters_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.toml"

            # Non-16000 sample_rate rejected
            config_path.write_text("[wake_word]\nsample_rate = 44100\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "16000 Hz"):
                load_config(config_path)

            # Boolean sample_rate rejected
            config_path.write_text("[wake_word]\nsample_rate = true\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                load_config(config_path)

            # Chunk size not multiple of 1280 rejected
            config_path.write_text("[wake_word]\nchunk_size = 1000\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "multiple of 1280"):
                load_config(config_path)

            # Valid audio parameters
            config_path.write_text(
                "[wake_word]\nsample_rate = 16000\nchunk_size = 2560\n",
                encoding="utf-8",
            )
            cfg = load_config(config_path)
            self.assertEqual(cfg.wake_word.sample_rate, 16000)
            self.assertEqual(cfg.wake_word.chunk_size, 2560)


if __name__ == "__main__":
    unittest.main()
