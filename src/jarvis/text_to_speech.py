
"""Local text-to-speech for JARVIS using Piper."""

import shutil
import subprocess
import tempfile
import threading
import wave
from pathlib import Path
from typing import TYPE_CHECKING

from piper import PiperVoice, SynthesisConfig

if TYPE_CHECKING:
    from jarvis.speech_to_text import SpeechToText


class TextToSpeech:
    """Speak locally using Piper, with optional interruptible playback."""

    def __init__(
        self,
        voice_path: Path | None = None,
        speed: float = 0.75,
    ) -> None:
        if speed <= 0:
            raise ValueError("Speech speed must be positive.")

        self.speed = speed
        if voice_path is not None:
            self.voice_path = voice_path
        else:
            jarvis_voice = (
                Path.home()
                / ".local/share/jarvis/voices"
                / "en_GB-vctk-medium.onnx"
            )
            friday_voice = (
                Path.home()
                / ".local/share/friday/voices"
                / "en_GB-vctk-medium.onnx"
            )
            self.voice_path = (
                jarvis_voice if jarvis_voice.is_file() else friday_voice
            )
        self.speaker_id = 73  # p264

        if not self.voice_path.is_file():
            raise FileNotFoundError(
                f"Piper voice model not found: {self.voice_path}"
            )

        self._player = shutil.which("pw-play") or shutil.which("aplay")

        if self._player is None:
            raise RuntimeError(
                "No audio player found. Install PipeWire tools with "
                "'sudo pacman -S pipewire-audio' or install alsa-utils."
            )

        self._voice = PiperVoice.load(str(self.voice_path))
        self._process_lock = threading.Lock()
        self._playback_process: subprocess.Popen[bytes] | None = None
        self._cancelled_pids: set[int] = set()

    @property
    def is_speaking(self) -> bool:
        """Return whether the audio player is currently running."""
        with self._process_lock:
            process = self._playback_process
            return process is not None and process.poll() is None

    def stop(self) -> None:
        """Stop the current audio playback, if any."""
        with self._process_lock:
            process = self._playback_process

            if process is None or process.poll() is not None:
                return

            self._cancelled_pids.add(process.pid)

            try:
                print(f"JARVIS DEBUG: stopping player PID {process.pid}")
                process.terminate()
            except OSError as exc:
                print(f"JARVIS DEBUG: terminate failed: {exc}")

        try:
            process.wait(timeout=2.0)
            print(f"JARVIS DEBUG: player exit code {process.poll()}")            
        except (subprocess.TimeoutExpired, OSError):
            try:
                process.kill()
                process.wait(timeout=1.0)
            except OSError:
                pass

    def speak(
        self,
        text: str,
        speech_to_text: "SpeechToText | None" = None,
    ) -> str | None:
        """Speak text and optionally listen for an interruption.

        Returns the transcribed interruption, or None when there was
        no interruption.
        """
        text = text.strip()

        if not text:
            return None

        config = SynthesisConfig(
            speaker_id=self.speaker_id,
            length_scale=1.0 / self.speed,
        )

        temp_dir = tempfile.mkdtemp(prefix="jarvis_tts_")
        wav_path = Path(temp_dir) / "output.wav"
        process: subprocess.Popen[bytes] | None = None
        was_cancelled = False
        interruption: str | None = None

        try:
            with wave.open(str(wav_path), "wb") as wav_file:
                self._voice.synthesize_wav(
                    text,
                    wav_file,
                    syn_config=config,
                )

            command = [self._player, str(wav_path)]
            if self._player.endswith("pw-play"):
                command = [self._player, "--", str(wav_path)]

            try:
                process = subprocess.Popen(
                    command,
                    stdin=subprocess.DEVNULL,
                )
            except OSError as exc:
                raise RuntimeError(
                    f"Could not start audio playback with {self._player}: {exc}"
                ) from exc

            with self._process_lock:
                self._playback_process = process

            try:
                if speech_to_text is not None:
                    interruption = speech_to_text.listen_for_barge_in(
                        is_playing=lambda: self.is_speaking,
                        stop_playback=self.stop,
                    )
                else:
                    process.wait(timeout=max(30.0, len(text) * 0.5))

                if process.poll() is None:
                    try:
                        process.wait(timeout=max(30.0, len(text) * 0.5))
                    except subprocess.TimeoutExpired as exc:
                        self.stop()
                        raise RuntimeError(
                            "Piper speech playback timed out."
                        ) from exc

            finally:
                with self._process_lock:
                    if process is not None:
                        was_cancelled = process.pid in self._cancelled_pids
                        self._cancelled_pids.discard(process.pid)
                        if self._playback_process is process:
                            self._playback_process = None

                # Ensure process never leaks even if an unhandled exception occurred
                if process is not None and process.poll() is None:
                    try:
                        process.terminate()
                        process.wait(timeout=1.0)
                    except (subprocess.TimeoutExpired, OSError):
                        try:
                            process.kill()
                            process.wait(timeout=1.0)
                        except OSError:
                            pass

            if was_cancelled:
                return interruption

            if process.returncode != 0:
                raise RuntimeError(
                    f"Audio playback failed with exit code {process.returncode}."
                )

            return interruption

        finally:
            try:
                if wav_path.is_file():
                    wav_path.unlink(missing_ok=True)
                Path(temp_dir).rmdir()
            except OSError:
                pass
