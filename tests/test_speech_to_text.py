"""Regression tests for JARVIS's speech-to-text pipeline."""

import unittest
from unittest.mock import MagicMock, patch

import numpy as np
import sounddevice as sd

from jarvis.speech_to_text import SpeechToText


class SpeechToTextTests(unittest.TestCase):
    def test_sample_rate_validation(self) -> None:
        with self.assertRaises(ValueError):
            SpeechToText(sample_rate=44100)

    @patch("jarvis.speech_to_text.WhisperModel")
    def test_transcribe_strips_leading_wake_word(self, mock_whisper_class) -> None:
        mock_model = MagicMock()
        mock_segment1 = MagicMock()
        mock_segment1.text = "Jarvis, what time is it?"
        mock_model.transcribe.return_value = ([mock_segment1], None)
        mock_whisper_class.return_value = mock_model

        stt = SpeechToText()
        stt._model = mock_model

        dummy_audio = np.ones(16000, dtype=np.float32) * 0.1
        transcript = stt._transcribe(dummy_audio)
        self.assertEqual(transcript, "what time is it?")

    @patch("jarvis.speech_to_text.WhisperModel")
    def test_transcribe_preserves_request_without_wake_word(
        self, mock_whisper_class
    ) -> None:
        mock_model = MagicMock()
        mock_segment = MagicMock()
        mock_segment.text = "What is the capital of France?"
        mock_model.transcribe.return_value = ([mock_segment], None)
        mock_whisper_class.return_value = mock_model

        stt = SpeechToText()
        stt._model = mock_model

        dummy_audio = np.ones(16000, dtype=np.float32) * 0.1
        transcript = stt._transcribe(dummy_audio)
        self.assertEqual(transcript, "What is the capital of France?")

    @patch("jarvis.speech_to_text.WhisperModel")
    def test_transcribe_empty_audio_returns_empty_string(
        self, mock_whisper_class
    ) -> None:
        stt = SpeechToText()
        res = stt._transcribe(np.empty(0, dtype=np.float32))
        self.assertEqual(res, "")

    @patch.object(SpeechToText, "_transcribe")
    @patch.object(SpeechToText, "_suppress_noise")
    def test_listen_once_with_stream_handoff(
        self, mock_suppress, mock_transcribe
    ) -> None:
        mock_suppress.side_effect = lambda a: a
        mock_transcribe.return_value = "hello world"

        stt = SpeechToText()
        # Mock active stream
        mock_stream = MagicMock()
        mock_stream.closed = False
        mock_stream.active = True
        mock_stream.blocksize = 1280

        # Simulate speech blocks (amplitude ~0.1) followed by silence blocks (~0.0)
        speech_chunk = (np.ones(1280, dtype=np.int16) * 3000)
        silence_chunk = np.zeros(1280, dtype=np.int16)

        # 4 speech chunks (~320 ms) then 16 silence chunks (~1280 ms > 1.2s silence threshold)
        chunks = [speech_chunk] * 4 + [silence_chunk] * 16
        mock_stream.read.side_effect = [(c, False) for c in chunks]

        # Initial post-wake audio
        initial_audio = np.ones(1280, dtype=np.float32) * 0.1

        result = stt.listen_once(stream=mock_stream, initial_audio=initial_audio)
        self.assertEqual(result, "hello world")
        mock_transcribe.assert_called_once()
        # Verify noise suppression was performed once on the complete utterance
        mock_suppress.assert_called_once()

    @patch("jarvis.speech_to_text.sd.InputStream")
    def test_listen_once_timeout_when_silent(self, mock_input_stream) -> None:
        stt = SpeechToText()
        stt.speech_timeout = 0.1  # Fast timeout for test

        mock_stream = MagicMock()
        mock_stream.read.return_value = (np.zeros(1280, dtype=np.int16), False)
        mock_input_stream.return_value = mock_stream

        result = stt.listen_once()
        self.assertEqual(result, "")

    @patch.object(SpeechToText, "_transcribe")
    @patch.object(SpeechToText, "_suppress_noise")
    @patch("jarvis.speech_to_text.sd.InputStream")
    def test_listen_for_barge_in_prevents_false_interruption_from_speaker(
        self, mock_input_stream, mock_suppress, mock_transcribe
    ) -> None:
        stt = SpeechToText()

        mock_stream = MagicMock()
        # Steady speaker sound bleed (~0.04 RMS)
        speaker_audio = (np.ones(480, dtype=np.int16) * 1300)
        mock_stream.read.return_value = (speaker_audio, False)
        mock_input_stream.return_value.__enter__.return_value = mock_stream

        stop_called = False
        def mock_stop():
            nonlocal stop_called
            stop_called = True

        # Simulate 10 iterations of playback, then playback ends
        playback_counter = 10
        def is_playing():
            nonlocal playback_counter
            playback_counter -= 1
            return playback_counter > 0

        interruption = stt.listen_for_barge_in(
            is_playing=is_playing,
            stop_playback=mock_stop,
        )

        # Should NOT trigger stop_playback on speaker bleed alone
        self.assertFalse(stop_called)
        self.assertIsNone(interruption)

    @patch.object(SpeechToText, "_transcribe")
    @patch.object(SpeechToText, "_suppress_noise")
    @patch("jarvis.speech_to_text.sd.InputStream")
    def test_listen_for_barge_in_detects_loud_user_speech(
        self, mock_input_stream, mock_suppress, mock_transcribe
    ) -> None:
        mock_suppress.side_effect = lambda a: a
        mock_transcribe.return_value = "stop"

        stt = SpeechToText()
        stt.barge_in_grace_seconds = 0.0

        mock_stream = MagicMock()
        # Low speaker sound first, then loud user interruption (>0.15 RMS), then silence
        soft_speaker = (np.ones(480, dtype=np.int16) * 600)   # ~0.018
        loud_user = (np.ones(480, dtype=np.int16) * 8000)     # ~0.24
        silence = np.zeros(480, dtype=np.int16)

        # 20 soft frames, 10 loud user frames, then 45 silence frames (>1.2s)
        frames = [soft_speaker] * 20 + [loud_user] * 10 + [silence] * 45
        mock_stream.read.side_effect = [(f, False) for f in frames]
        mock_input_stream.return_value.__enter__.return_value = mock_stream

        stop_called = False
        def mock_stop():
            nonlocal stop_called
            stop_called = True

        is_playing_flag = True
        def is_playing():
            return is_playing_flag

        interruption = stt.listen_for_barge_in(
            is_playing=is_playing,
            stop_playback=mock_stop,
        )

        self.assertTrue(stop_called)
        self.assertEqual(interruption, "stop")


if __name__ == "__main__":
    unittest.main()
