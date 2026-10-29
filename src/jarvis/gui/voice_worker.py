
"""Background speech-recognition worker for the JARVIS GUI."""

import threading
import traceback

from PySide6.QtCore import QObject, Signal, Slot

from jarvis.speech_to_text import SpeechToText


class VoiceWorker(QObject):
    """Capture and transcribe one utterance outside the GUI thread."""

    status_changed = Signal(str, str)
    transcript_ready = Signal(str)
    error_occurred = Signal(str)
    finished = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._stop_event = threading.Event()
        self._speech: SpeechToText | None = None

    def request_stop(self) -> None:
        """Request cancellation without touching the microphone from the GUI thread."""
        self._stop_event.set()

    @Slot()
    def run(self) -> None:
        """Listen for one utterance and emit the recognized text."""
        try:
            self.status_changed.emit(
                "LISTENING",
                "Loading speech recognition and opening the microphone...",
            )

            if self._stop_event.is_set():
                return

            self._speech = SpeechToText()

            if self._stop_event.is_set():
                return

            self.status_changed.emit(
                "LISTENING",
                "Microphone active. Speak clearly, then pause.",
            )

            # listen_once owns and closes its microphone stream.
            # Cancellation is checked before recording and after it returns.
            transcript = self._speech.listen_once(
                stop_event=self._stop_event
            )

            if self._stop_event.is_set():
                self.status_changed.emit(
                    "IDLE",
                    "Listening stopped.",
                )
                return

            self.transcript_ready.emit(transcript)
            self.status_changed.emit(
                "IDLE",
                "Recording finished. You can listen again.",
            )

        except Exception as exc:
            self.error_occurred.emit(
                f"{exc}\n\n{traceback.format_exc()}"
            )
            self.status_changed.emit(
                "IDLE",
                "Voice processing failed. Check the error message.",
            )

        finally:
            if self._speech is not None:
                try:
                    self._speech.close()
                except Exception:
                    pass

            self.finished.emit()
