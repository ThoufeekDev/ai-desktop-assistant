
"""Continuous wake-word and speech-recognition worker for the JARVIS GUI."""

import threading
import traceback
from pathlib import Path

import sounddevice as sd
from PySide6.QtCore import QObject, Signal, Slot

from jarvis.config import load_config
from jarvis.speech_to_text import SpeechToText
from jarvis.text_to_speech import TextToSpeech
from jarvis.wake_word import WakeWordDetector


class WakeWordWorker(QObject):
    """Wait continuously for Hey JARVIS and capture spoken commands."""

    status_changed = Signal(str, str)
    transcript_ready = Signal(str)
    error_occurred = Signal(str)
    finished = Signal()

    def __init__(self, speaker: TextToSpeech | None = None) -> None:
        super().__init__()
        self._speaker = speaker
        self._stop_event = threading.Event()

        # The worker pauses here while JARVIS processes and speaks.
        self._resume_event = threading.Event()
        self._resume_event.set()

        self._speech: SpeechToText | None = None

    @property
    def speech_to_text(self) -> SpeechToText | None:
        """Expose the recogniser for speech interruption detection."""
        return self._speech

    def request_stop(self) -> None:
        """Request cancellation and release any paused worker."""
        self._stop_event.set()
        self._resume_event.set()

    def resume_listening(self) -> None:
        """Resume wake-word detection after JARVIS finishes responding."""
        self._resume_event.set()

    @Slot()
    def run(self) -> None:
        """Continuously detect the wake word and recognize commands."""
        stream: sd.InputStream | None = None

        try:
            self.status_changed.emit(
                "LISTENING",
                "Loading wake-word detection and speech recognition...",
            )

            if self._stop_event.is_set():
                return

            config = load_config()
            wake_config = config.wake_word

            model_path = Path(wake_config.model_path)

            if not model_path.is_absolute():
                model_path = (
                    Path(__file__).resolve().parents[3] / model_path
                )

            detector = WakeWordDetector(
                model_path=model_path,
                threshold=wake_config.threshold,
                sample_rate=wake_config.sample_rate,
                chunk_size=wake_config.chunk_size,
            )

            self._speech = SpeechToText()

            while not self._stop_event.is_set():
                self.status_changed.emit(
                    "LISTENING",
                    'Standing by. Say "Hey JARVIS".',
                )

                handoff = detector.wait_until_detected(
                    stop_event=self._stop_event,
                )

                if self._stop_event.is_set() or handoff is None:
                    break

                stream, initial_audio = handoff

                self.status_changed.emit(
                    "SPEAKING",
                    "Hey JARVIS detected. Yes, I'm listening...",
                )

                print(
                    "JARVIS: Yes, I'm listening.",
                    flush=True,
                )

                try:
                    interruption = None

                    if self._speaker is not None:
                        interruption = self._speaker.speak(
                            "Yes, I'm listening.",
                            speech_to_text=self._speech,
                        )

                    if interruption:
                        transcript = interruption
                    else:
                        transcript = self._speech.listen_once(
                            stream=stream,
                            initial_audio=initial_audio,
                            stop_event=self._stop_event,
                        )
                finally:
                    if stream is not None and not stream.closed:
                        stream.close()
                    stream = None

                if self._stop_event.is_set():
                    break

                if not transcript.strip():
                    self.status_changed.emit(
                        "LISTENING",
                        'No speech detected. Say "Hey JARVIS" again.',
                    )
                    continue

                # Pause wake-word detection while the GUI handles the reply.
                self._resume_event.clear()

                self.status_changed.emit(
                    "IDLE",
                    "Command captured. Waiting for JARVIS to respond...",
                )
                self.transcript_ready.emit(transcript)

                while (
                    not self._stop_event.is_set()
                    and not self._resume_event.wait(timeout=0.1)
                ):
                    pass

        except Exception as exc:
            self.error_occurred.emit(
                f"{exc}\n\n{traceback.format_exc()}"
            )

        finally:
            if stream is not None and not stream.closed:
                stream.close()

            if self._speech is not None:
                try:
                    self._speech.close()
                except Exception:
                    pass

            self.status_changed.emit(
                "IDLE",
                "Wake-word listening stopped.",
            )
            self.finished.emit()
