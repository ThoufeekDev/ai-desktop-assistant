"""Regression tests for JARVIS's wake-word detection."""

import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import sounddevice as sd

from jarvis.wake_word import WakeWordDetector


class WakeWordDetectorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.jarvis_model_path = (
            Path(__file__).resolve().parents[1]
            / "models"
            / "wakewords"
            / "jarvis.onnx"
        )

    def test_missing_model_file_raises_filenotfound(self) -> None:
        with self.assertRaises(FileNotFoundError):
            WakeWordDetector(model_path="/nonexistent/model.onnx")

    def test_threshold_validation(self) -> None:
        # Threshold must be finite and 0.0 < threshold <= 1.0
        with self.assertRaises(ValueError):
            WakeWordDetector(threshold=0.0)
        with self.assertRaises(ValueError):
            WakeWordDetector(threshold=1.5)
        with self.assertRaises(ValueError):
            WakeWordDetector(threshold=float("nan"))
        with self.assertRaises(ValueError):
            WakeWordDetector(threshold=float("inf"))
        with self.assertRaises(ValueError):
            WakeWordDetector(threshold=True)

    def test_sample_rate_validation(self) -> None:
        # openWakeWord requires 16000 Hz
        with self.assertRaises(ValueError):
            WakeWordDetector(sample_rate=44100)
        with self.assertRaises(ValueError):
            WakeWordDetector(sample_rate=0)
        with self.assertRaises(ValueError):
            WakeWordDetector(sample_rate=True)

    def test_chunk_size_validation(self) -> None:
        # Chunk size must be positive multiple of 1280
        with self.assertRaises(ValueError):
            WakeWordDetector(chunk_size=1000)
        with self.assertRaises(ValueError):
            WakeWordDetector(chunk_size=0)
        with self.assertRaises(ValueError):
            WakeWordDetector(chunk_size=-1280)
        with self.assertRaises(ValueError):
            WakeWordDetector(chunk_size=True)

    @patch("jarvis.wake_word.Model")
    def test_model_loading_and_key_identification(self, mock_model_class) -> None:
        mock_instance = MagicMock()
        mock_instance.models = {"jarvis": MagicMock()}
        mock_model_class.return_value = mock_instance

        detector = WakeWordDetector(
            model_path=self.jarvis_model_path,
            threshold=0.5,
        )

        mock_model_class.assert_called_once_with(
            wakeword_model_paths=[str(self.jarvis_model_path)]
        )
        self.assertEqual(detector.model_key, "jarvis")
        self.assertEqual(detector.threshold, 0.5)

    @patch("jarvis.wake_word.Model")
    @patch("jarvis.wake_word.sd.InputStream")
    def test_wake_word_detected_stream_handoff(
        self, mock_input_stream, mock_model_class
    ) -> None:
        mock_model = MagicMock()
        mock_model.models = {"jarvis": MagicMock()}
        # 1st prediction below threshold, 2nd prediction above threshold
        mock_model.predict.side_effect = [
            {"jarvis": 0.12},
            {"jarvis": 0.85},
        ]
        mock_model_class.return_value = mock_model

        mock_stream = MagicMock()
        dummy_audio = np.zeros(1280, dtype=np.int16)
        mock_stream.read.return_value = (dummy_audio, False)
        mock_input_stream.return_value = mock_stream

        detector = WakeWordDetector(
            model_path=self.jarvis_model_path,
            threshold=0.5,
        )

        handoff = detector.wait_until_detected(return_stream=True)
        self.assertIsNotNone(handoff)
        stream, post_wake = handoff
        self.assertEqual(stream, mock_stream)
        self.assertIsInstance(post_wake, np.ndarray)
        # Verify stream was not closed during handoff
        mock_stream.close.assert_not_called()

    @patch("jarvis.wake_word.Model")
    @patch("jarvis.wake_word.sd.InputStream")
    def test_wake_word_detected_legacy_no_return_stream(
        self, mock_input_stream, mock_model_class
    ) -> None:
        mock_model = MagicMock()
        mock_model.models = {"jarvis": MagicMock()}
        mock_model.predict.return_value = {"jarvis": 0.90}
        mock_model_class.return_value = mock_model

        mock_stream = MagicMock()
        dummy_audio = np.zeros(1280, dtype=np.int16)
        mock_stream.read.return_value = (dummy_audio, False)
        mock_input_stream.return_value = mock_stream

        detector = WakeWordDetector(
            model_path=self.jarvis_model_path,
            threshold=0.5,
        )

        res = detector.wait_until_detected(return_stream=False)
        self.assertIsNone(res)
        # Stream owned by detector should be closed when return_stream is False
        mock_stream.close.assert_called_once()

    @patch("jarvis.wake_word.Model")
    @patch("jarvis.wake_word.sd.InputStream")
    def test_stream_init_failure_raises_runtime_error(
        self, mock_input_stream, mock_model_class
    ) -> None:
        mock_model = MagicMock()
        mock_model.models = {"jarvis": MagicMock()}
        mock_model_class.return_value = mock_model
        mock_input_stream.side_effect = sd.PortAudioError("Device unavailable")

        detector = WakeWordDetector(model_path=self.jarvis_model_path)
        with self.assertRaisesRegex(RuntimeError, "Could not open microphone"):
            detector.wait_until_detected()

    @patch("jarvis.wake_word.Model")
    @patch("jarvis.wake_word.sd.InputStream")
    def test_stream_read_error_raises_runtime_error(
        self, mock_input_stream, mock_model_class
    ) -> None:
        mock_model = MagicMock()
        mock_model.models = {"jarvis": MagicMock()}
        mock_model_class.return_value = mock_model

        mock_stream = MagicMock()
        mock_stream.read.side_effect = sd.PortAudioError("Stream read error")
        mock_input_stream.return_value = mock_stream

        detector = WakeWordDetector(model_path=self.jarvis_model_path)
        with self.assertRaisesRegex(RuntimeError, "Microphone read error"):
            detector.wait_until_detected()

    @patch("jarvis.wake_word.Model")
    @patch("jarvis.wake_word.sd.InputStream")
    def test_keyboard_interrupt_cleans_up_stream(
        self, mock_input_stream, mock_model_class
    ) -> None:
        mock_model = MagicMock()
        mock_model.models = {"jarvis": MagicMock()}
        mock_model_class.return_value = mock_model

        mock_stream = MagicMock()
        mock_stream.closed = False
        mock_stream.read.side_effect = KeyboardInterrupt()
        mock_input_stream.return_value = mock_stream

        detector = WakeWordDetector(model_path=self.jarvis_model_path)
        with self.assertRaises(KeyboardInterrupt):
            detector.wait_until_detected()

        mock_stream.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
