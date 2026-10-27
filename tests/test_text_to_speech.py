"""Regression tests for JARVIS's TextToSpeech pipeline."""

import subprocess
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from jarvis.text_to_speech import TextToSpeech


class TextToSpeechTests(unittest.TestCase):
    def setUp(self) -> None:
        self.voice_path = (
            Path.home()
            / ".local/share/friday/voices"
            / "en_GB-vctk-medium.onnx"
        )

    def test_speed_validation(self) -> None:
        with self.assertRaises(ValueError):
            TextToSpeech(speed=0)
        with self.assertRaises(ValueError):
            TextToSpeech(speed=-1.0)

    def test_missing_voice_raises_filenotfound(self) -> None:
        with self.assertRaises(FileNotFoundError):
            TextToSpeech(voice_path=Path("/nonexistent/voice.onnx"))

    @patch("jarvis.text_to_speech.shutil.which", return_value=None)
    def test_missing_player_raises_runtime_error(self, _mock_which) -> None:
        with self.assertRaisesRegex(RuntimeError, "No audio player found"):
            TextToSpeech(voice_path=self.voice_path)

    @patch("jarvis.text_to_speech.PiperVoice.load")
    @patch("jarvis.text_to_speech.shutil.which", return_value="/usr/bin/pw-play")
    def test_empty_text_returns_none(self, _mock_which, _mock_load) -> None:
        tts = TextToSpeech(voice_path=self.voice_path)
        self.assertIsNone(tts.speak(""))
        self.assertIsNone(tts.speak("   "))

    def _setup_mock_voice(self, mock_load):
        def fake_synth(text, wav_file, syn_config=None):
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(22050)
            wav_file.writeframes(b"\x00" * 100)

        mock_voice = MagicMock()
        mock_voice.synthesize_wav.side_effect = fake_synth
        mock_load.return_value = mock_voice
        return mock_voice

    @patch("jarvis.text_to_speech.PiperVoice.load")
    @patch("jarvis.text_to_speech.subprocess.Popen")
    @patch("jarvis.text_to_speech.shutil.which", return_value="/usr/bin/pw-play")
    def test_speak_successful_playback_cleans_temp_file(
        self, _mock_which, mock_popen, mock_load
    ) -> None:
        self._setup_mock_voice(mock_load)
        mock_proc = MagicMock()
        mock_proc.pid = 12345
        mock_proc.poll.return_value = 0
        mock_proc.returncode = 0
        mock_popen.return_value = mock_proc

        tts = TextToSpeech(voice_path=self.voice_path)
        res = tts.speak("Hello there")

        self.assertIsNone(res)
        mock_popen.assert_called_once()
        # Verify pw-play command structure
        cmd = mock_popen.call_args[0][0]
        self.assertEqual(cmd[0], "/usr/bin/pw-play")
        self.assertEqual(cmd[1], "--")
        wav_arg = Path(cmd[2])
        # The temporary file and directory should have been deleted
        self.assertFalse(wav_arg.exists())
        self.assertFalse(wav_arg.parent.exists())

    @patch("jarvis.text_to_speech.PiperVoice.load")
    @patch("jarvis.text_to_speech.subprocess.Popen")
    @patch("jarvis.text_to_speech.shutil.which", return_value="/usr/bin/pw-play")
    def test_speak_with_barge_in_interruption(
        self, _mock_which, mock_popen, mock_load
    ) -> None:
        self._setup_mock_voice(mock_load)
        mock_proc = MagicMock()
        mock_proc.pid = 12345
        mock_proc.poll.return_value = None
        mock_proc.returncode = -15
        mock_popen.return_value = mock_proc

        tts = TextToSpeech(voice_path=self.voice_path)

        mock_stt = MagicMock()

        # When barge-in is detected, stop() is called, which marks cancellation
        def mock_listen(is_playing, stop_playback):
            stop_playback()
            mock_proc.poll.return_value = 0
            return "stop listening"

        mock_stt.listen_for_barge_in.side_effect = mock_listen

        interruption = tts.speak("Long speaking text", speech_to_text=mock_stt)
        self.assertEqual(interruption, "stop listening")
        mock_proc.terminate.assert_called()

    @patch("jarvis.text_to_speech.PiperVoice.load")
    @patch("jarvis.text_to_speech.subprocess.Popen")
    @patch("jarvis.text_to_speech.shutil.which", return_value="/usr/bin/pw-play")
    def test_speak_exception_in_barge_in_terminates_process(
        self, _mock_which, mock_popen, mock_load
    ) -> None:
        self._setup_mock_voice(mock_load)
        mock_proc = MagicMock()
        mock_proc.pid = 12345
        mock_proc.poll.return_value = None  # Process is still running
        mock_popen.return_value = mock_proc

        tts = TextToSpeech(voice_path=self.voice_path)

        mock_stt = MagicMock()
        mock_stt.listen_for_barge_in.side_effect = KeyboardInterrupt("Interrupted")

        with self.assertRaises(KeyboardInterrupt):
            tts.speak("Some text", speech_to_text=mock_stt)

        # Process MUST be terminated so it does not keep playing in the background
        mock_proc.terminate.assert_called()
        self.assertIsNone(tts._playback_process)

    @patch("jarvis.text_to_speech.PiperVoice.load")
    @patch("jarvis.text_to_speech.subprocess.Popen")
    @patch("jarvis.text_to_speech.shutil.which", return_value="/usr/bin/pw-play")
    def test_speak_player_exit_failure_raises_runtime_error(
        self, _mock_which, mock_popen, mock_load
    ) -> None:
        self._setup_mock_voice(mock_load)
        mock_proc = MagicMock()
        mock_proc.pid = 12345
        mock_proc.poll.return_value = 1
        mock_proc.returncode = 1
        mock_popen.return_value = mock_proc

        tts = TextToSpeech(voice_path=self.voice_path)
        with self.assertRaisesRegex(RuntimeError, "Audio playback failed with exit code 1"):
            tts.speak("Fail please")

    @patch("jarvis.text_to_speech.PiperVoice.load")
    @patch("jarvis.text_to_speech.subprocess.Popen")
    @patch("jarvis.text_to_speech.shutil.which", return_value="/usr/bin/pw-play")
    def test_stop_bounded_wait(self, _mock_which, mock_popen, mock_load) -> None:
        mock_proc = MagicMock()
        mock_proc.pid = 12345
        mock_proc.poll.return_value = None
        mock_proc.wait.side_effect = [subprocess.TimeoutExpired(cmd="pw-play", timeout=2.0), None]
        mock_popen.return_value = mock_proc

        tts = TextToSpeech(voice_path=self.voice_path)
        tts._playback_process = mock_proc

        tts.stop()

        mock_proc.terminate.assert_called_once()
        mock_proc.kill.assert_called_once()
        # Verify bounded wait was called with timeout after kill
        mock_proc.wait.assert_called_with(timeout=1.0)


if __name__ == "__main__":
    unittest.main()
