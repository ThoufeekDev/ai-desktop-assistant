
"""Tests for the JARVIS CLI."""

import unittest
from unittest.mock import MagicMock, patch

from jarvis.cli import main
from jarvis.config import AppConfig, OllamaConfig
from jarvis.ollama_client import OllamaError


class CliTests(unittest.TestCase):
    @patch("jarvis.cli.TextToSpeech")
    @patch("jarvis.cli.OllamaClient")
    @patch("jarvis.cli.load_config")
    def test_cli_uses_loaded_configuration(
        self,
        mock_load_config,
        mock_client_class,
        mock_text_to_speech,
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
        mock_client_class.return_value.chat.return_value = "Hello from FRIDAY"

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
        mock_client_class.return_value.chat.assert_called_once_with(
            "Hello",
            memories=[],
        )
        mock_print.assert_any_call(
            "Local AI assistant — model: test-model"
        )
        mock_text_to_speech.return_value.speak.assert_called_once_with(
            "Hello from FRIDAY"
        )

    @patch("jarvis.cli.load_config", side_effect=ValueError("Invalid settings"))
    def test_cli_handles_configuration_error(self, _mock_load_config) -> None:
        with patch("builtins.print") as mock_print:
            main()

        mock_print.assert_any_call(
            "JARVIS: Could not load configuration: Invalid settings"
        )

    @patch("jarvis.cli.TextToSpeech")
    @patch("jarvis.cli.OllamaClient")
    @patch("jarvis.cli.load_config", return_value=AppConfig())
    def test_cli_handles_ollama_error(
        self,
        _mock_load_config,
        mock_client_class,
        _mock_text_to_speech,
    ) -> None:
        mock_client_class.return_value.chat.side_effect = OllamaError(
            "Ollama is unavailable."
        )

        with (
            patch("builtins.input", side_effect=["Hello", "/exit"]),
            patch("builtins.print") as mock_print,
        ):
            main()

        mock_print.assert_any_call(
            "\nJARVIS: Ollama is unavailable.\n"
        )


    @patch("jarvis.cli.SpeechToText")
    @patch("jarvis.wake_word.WakeWordDetector")
    @patch("jarvis.cli.TextToSpeech")
    @patch("jarvis.cli.OllamaClient")
    @patch("jarvis.cli.load_config", return_value=AppConfig())
    def test_cli_wake_word_mode_handoff(
        self,
        _mock_load_config,
        mock_client_class,
        mock_text_to_speech,
        mock_wake_detector_class,
        mock_stt_class,
    ) -> None:
        mock_client = MagicMock()
        mock_client.chat.return_value = "It is 12:00 PM."
        mock_client_class.return_value = mock_client
        mock_text_to_speech.return_value.speak.return_value = None

        mock_stream = MagicMock()
        mock_stream.closed = False
        dummy_post_wake = MagicMock()

        mock_wake_detector = MagicMock()
        mock_wake_detector.wait_until_detected.return_value = (
            mock_stream,
            dummy_post_wake,
        )
        mock_wake_detector_class.return_value = mock_wake_detector

        mock_stt = MagicMock()
        # First utterance: user request; Second utterance: exit wake mode
        mock_stt.listen_once.side_effect = [
            "what time is it",
            "stop listening",
        ]
        mock_stt_class.return_value = mock_stt

        with patch("builtins.input", side_effect=["/wake", "/exit"]):
            main()

        # Verify listen_once received the handed-off stream and initial audio
        mock_stt.listen_once.assert_any_call(
            stream=mock_stream, initial_audio=dummy_post_wake
        )
        # Verify stream was closed in finally
        mock_stream.close.assert_called()
        mock_client.chat.assert_called_with("what time is it", memories=[])
        mock_text_to_speech.return_value.speak.assert_called_with(
            "It is 12:00 PM.", speech_to_text=mock_stt
        )

    @patch("jarvis.wake_word.WakeWordDetector")
    @patch("jarvis.cli.TextToSpeech")
    @patch("jarvis.cli.OllamaClient")
    @patch("jarvis.cli.load_config", return_value=AppConfig())
    def test_cli_wake_word_mode_keyboard_interrupt(
        self,
        _mock_load_config,
        _mock_client_class,
        _mock_text_to_speech,
        mock_wake_detector_class,
    ) -> None:
        mock_wake_detector = MagicMock()
        mock_wake_detector.wait_until_detected.side_effect = KeyboardInterrupt()
        mock_wake_detector_class.return_value = mock_wake_detector

        with (
            patch("builtins.input", side_effect=["/wake", "/exit"]),
            patch("builtins.print") as mock_print,
        ):
            main()

        mock_print.assert_any_call(
            "\nJARVIS: Wake-word mode stopped. Back to text mode.\n"
        )


if __name__ == "__main__":
    unittest.main()
