
"""Tests for the FRIDAY CLI."""

import unittest
from unittest.mock import patch

from friday.cli import main
from friday.config import AppConfig, OllamaConfig
from friday.ollama_client import OllamaError


class CliTests(unittest.TestCase):
    @patch("friday.cli.OllamaClient")
    @patch("friday.cli.load_config")
    def test_cli_uses_loaded_configuration(
        self,
        mock_load_config,
        mock_client_class,
    ) -> None:
        mock_load_config.return_value = AppConfig(
            ollama=OllamaConfig(
                base_url="http://localhost:11434",
                model="test-model",
                timeout=30.0,
                system_prompt="Test assistant prompt",
                max_history_turns=5,
            )
        )

        with (
            patch("builtins.input", side_effect=["Hello", "/exit"]),
            patch("builtins.print") as mock_print,
        ):
            main()

        mock_client_class.assert_called_once_with(
            base_url="http://localhost:11434",
            model="test-model",
            timeout=30.0,
            system_prompt="Test assistant prompt",
            max_history_turns=5,
        )

        mock_client_class.return_value.chat.assert_called_once_with("Hello")

        mock_print.assert_any_call(
            "Local AI assistant — model: test-model"
        )

    @patch("friday.cli.load_config", side_effect=ValueError("Invalid settings"))
    def test_cli_handles_configuration_error(self, _mock_load_config) -> None:
        with patch("builtins.print") as mock_print:
            main()

        mock_print.assert_any_call(
            "FRIDAY: Could not load configuration: Invalid settings"
        )

    @patch("friday.cli.OllamaClient")
    @patch("friday.cli.load_config", return_value=AppConfig())
    def test_cli_handles_ollama_error(
        self,
        _mock_load_config,
        mock_client_class,
    ) -> None:
        mock_client_class.return_value.chat.side_effect = OllamaError(
            "Ollama is unavailable."
        )

        with (
            patch("builtins.input", side_effect=["Hello", "/exit"]),
            patch("builtins.print") as mock_print,
        ):
            main()

        mock_print.assert_any_call("FRIDAY: Ollama is unavailable.")


if __name__ == "__main__":
    unittest.main()
