"""Compact JARVIS popup connected to the real local chat worker."""

import sys

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from jarvis.text_to_speech import TextToSpeech
from jarvis.speech_to_text import SpeechToText
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QScrollArea,
)

from jarvis.config import load_config
from jarvis.gui.chat_worker import ChatWorker
from jarvis.gui.voice_worker import VoiceWorker
from jarvis.gui.wake_word_worker import WakeWordWorker
from jarvis.gui.components.message_view import MessageView
from jarvis.gui.components.orb import Orb, OrbState
from jarvis.gui.theme import tokens
from jarvis.gui.theme.loader import apply_theme
from jarvis.ollama_client import OllamaClient
from jarvis.assistant_engine import AssistantEngine

class SpeechWorker(QThread):
    """Play JARVIS speech and detect user interruptions."""

    failed = Signal(str)
    interrupted = Signal(str)
    spoken = Signal()

    def __init__(
        self,
        speaker: TextToSpeech,
        text: str,
        speech_to_text: SpeechToText | None = None,
    ) -> None:
        super().__init__()
        self.speaker = speaker
        self.text = text
        self.speech_to_text = speech_to_text

    def run(self) -> None:
        try:
            interruption = self.speaker.speak(
                self.text,
                speech_to_text=self.speech_to_text,
            )

            if interruption:
                self.interrupted.emit(interruption)
            else:
                self.spoken.emit()

        except Exception as exc:
            self.failed.emit(str(exc))
            
            
class PopupWindow(QWidget):
    """Small, keyboard-friendly JARVIS popup."""


    def __init__(self) -> None:
        super().__init__()

        self.setObjectName("JarvisPopup")
        self.setWindowTitle("JARVIS")
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowMinimizeButtonHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.setFixedSize(tokens.POPUP_WIDTH, tokens.POPUP_HEIGHT)

        self._chat_thread: QThread | None = None
        self._chat_worker: ChatWorker | None = None
        self._last_error = ""
        self._assistant_engine: AssistantEngine | None = None
        self._speech_thread: SpeechWorker | None = None
        self._pending_system_action: str | None = None
        self._voice_thread: QThread | None = None
        self._voice_worker: VoiceWorker | None = None

        # Continuous wake-word listener.
        self._wake_word_thread: QThread | None = None
        self._wake_word_worker: WakeWordWorker | None = None
        self._close_when_idle = False

        try:
            self._speaker: TextToSpeech | None = TextToSpeech(speed=0.75)
            print("[JARVIS] Piper voice initialized.", flush=True)
        except (RuntimeError, FileNotFoundError, OSError) as exc:
            self._speaker = None
            print(f"[JARVIS] Voice unavailable: {exc}", flush=True)

        try:
            ollama = load_config().ollama
            self._ollama_client: OllamaClient | None = OllamaClient(
                base_url=ollama.base_url,
                model=ollama.model,
                timeout=ollama.timeout,
                system_prompt=ollama.system_prompt,
                max_history_turns=ollama.max_history_turns,
            )
            self._assistant_engine = AssistantEngine(
                client=self._ollama_client,
            )
                        

        except Exception as exc:
            self._ollama_client = None
            self._last_error = str(exc)

        self._build_ui()

        self.messages.add_message(
            "assistant",
            "Hello. I'm JARVIS. How can I help?",
        )

        if self._ollama_client is None or self._assistant_engine is None:
            self._set_status("CONFIG ERROR")
            self.messages.add_message(
                "assistant",
                f"Couldn't initialize local chat: {self._last_error}",
            )
        else:
            QTimer.singleShot(
                500,
                self._start_wake_word_listening,
            )



    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(8)

        header = QHBoxLayout()

        self.orb = Orb()
        self.orb.setMinimumSize(0, 0)
        self.orb.setFixedSize(54, 54)

        self.state_label = QLabel("IDLE")
        self.state_label.setProperty("mono", True)
        self.state_label.setStyleSheet(
            f"color: {tokens.ACCENT}; font-family: "
            f"'{tokens.FONT_MONO}'; font-weight: 600;"
        )

        self.minimize_button = QPushButton("—")
        self.minimize_button.setAccessibleName("Minimize JARVIS")
        self.minimize_button.setFixedWidth(32)
        self.minimize_button.clicked.connect(self.showMinimized)

        header.addWidget(self.orb)
        header.addWidget(self.state_label)
        header.addStretch()
        header.addWidget(self.minimize_button)

        self.last_request = QLabel("Ready for your request")
        self.last_request.setProperty("muted", True)
        self.last_request.setStyleSheet(
            f"color: {tokens.MUTED}; font-family: "
            f"'{tokens.FONT_MONO}'; font-size: 11px;"
        )
        self.last_request.setWordWrap(True)

        # Scrollable conversation area.
        self.messages = MessageView()
        self.messages.setMinimumHeight(0)
        self.messages.setMaximumHeight(16777215)

        self.message_scroll = QScrollArea()
        self.message_scroll.setWidgetResizable(True)
        self.message_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.message_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.message_scroll.setWidget(self.messages)
        # Animate the assistant's reply and keep the latest text visible.
        self._reply_text = ""
        self._typed_chars = 0

        self._typing_timer = QTimer(self)
        self._typing_timer.setInterval(15)
        self._typing_timer.timeout.connect(self._reveal_next_chunk)        
        self.message_scroll.setMinimumHeight(100)

        input_row = QHBoxLayout()

        self.input = QLineEdit()
        self.input.setPlaceholderText("Ask JARVIS...")
        self.input.setAccessibleName("Message to JARVIS")
        self.input.returnPressed.connect(self._send_message)

        self.send_button = QPushButton("Send")
        self.send_button.setAccessibleName("Send message")
        self.send_button.setMinimumHeight(44)
        self.send_button.clicked.connect(self._send_message)
        self.mic_button = QPushButton("🎙")
        self.mic_button.setAccessibleName("Start voice input")
        self.mic_button.setMinimumHeight(44)
        self.mic_button.setToolTip("Speak to JARVIS")
        self.mic_button.clicked.connect(self._start_voice_listening)        
        self.stop_button = QPushButton("Stop")
        self.stop_button.setAccessibleName("Stop JARVIS speech")
        self.stop_button.setMinimumHeight(44)
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self._stop_speaking)        

        input_row.addWidget(self.input, 1)
        input_row.addWidget(self.mic_button)
        input_row.addWidget(self.send_button)
        input_row.addWidget(self.stop_button)

        footer = QLabel("Enter to send • Esc to close")
        footer.setAlignment(Qt.AlignmentFlag.AlignRight)
        footer.setStyleSheet(f"color: {tokens.MUTED}; font-size: 11px;")

        root.addLayout(header)
        root.addWidget(self.last_request)
        root.addWidget(self.message_scroll, 1)
        root.addLayout(input_row)
        root.addWidget(footer)


    def _set_state(self, state: OrbState) -> None:
        self.state_label.setText(state.value)
        self.orb.set_state(state)

    def _set_status(self, text: str) -> None:
        self.state_label.setText(text)

    def _scroll_to_bottom(self) -> None:
        """Keep the newest conversation content visible."""
        QTimer.singleShot(
            0,
            lambda: self.message_scroll.verticalScrollBar().setValue(
                self.message_scroll.verticalScrollBar().maximum()
            ),
        )

    def _reveal_next_chunk(self) -> None:
        """Reveal the assistant's response progressively."""
        if self._typed_chars >= len(self._reply_text):
            self._typing_timer.stop()
            self._set_state(OrbState.IDLE)
            self._scroll_to_bottom()
            return

        self._typed_chars = min(
            self._typed_chars + 2,
            len(self._reply_text),
        )
        self._thinking_label.setText(
            self._reply_text[:self._typed_chars]
        )
        self._scroll_to_bottom()


    def _send_message(self) -> None:
        message = self.input.text().strip()

        if not message or self._chat_thread is not None:
            return

        if self._ollama_client is None or self._assistant_engine is None:
            self.messages.add_message(
                "assistant",
                f"Local chat is unavailable: {self._last_error}",
            )
            return

        self.input.clear()
        self.input.setEnabled(False)
        self.send_button.setEnabled(False)

        self.last_request.setText(message)
        self.messages.add_message("user", message)
        self._thinking_label = self.messages.add_message(
            "assistant", "Thinking…"
        )
        self._set_state(OrbState.THINKING)
        self._scroll_to_bottom()

        thread = QThread(self)
        worker = ChatWorker(self._assistant_engine, message)
        worker.moveToThread(thread)


        thread.started.connect(
            lambda: print("[JARVIS DEBUG] Chat thread started", flush=True)
        )
        thread.started.connect(worker.run)

        worker.succeeded.connect(
            lambda reply: print(
                f"[JARVIS DEBUG] Success signal: {reply!r}", flush=True
            )
        )
        worker.succeeded.connect(self._on_chat_success)
        worker.system_action_requested.connect(
            self._on_system_action_requested
        )
            
        worker.failed.connect(
            lambda error: print(
                f"[JARVIS DEBUG] Failure signal: {error!r}", flush=True
            )
        )
        worker.failed.connect(self._on_chat_failure)

        worker.finished.connect(
            lambda: print(
                "[JARVIS DEBUG] Worker finished signal", flush=True
            )
        )
        worker.finished.connect(thread.quit)

        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(self._on_chat_thread_finished)


        self._chat_thread = thread
        self._chat_worker = worker
        thread.start()

    def _on_chat_success(self, reply: str) -> None:
        self._reply_text = reply
        self._typed_chars = 0

        self._thinking_label.setText("")
        self._set_state(OrbState.SPEAKING)
        self._scroll_to_bottom()

        self._typing_timer.start()

        # A pending power action uses one non-interruptible announcement.
        if self._pending_system_action is not None:
            self._speak_reply(reply, allow_interruption=False)
        else:
            self._speak_reply(reply)
    def _speak_reply(
        self,
        text: str,
        allow_interruption: bool = True,
    ) -> None:
        """Speak the assistant response in a background thread."""
        if self._speaker is None or not text.strip():
            if self._pending_system_action is not None:
                self._pending_system_action = None
                self.messages.add_message(
                    "assistant",
                    "System action cancelled: voice announcement is unavailable.",
                )

            if self._wake_word_worker is not None:
                self._wake_word_worker.resume_listening()
            return

        if self._speech_thread is not None:
            return

        speech_to_text = None

        if allow_interruption and self._wake_word_worker is not None:
            speech_to_text = self._wake_word_worker.speech_to_text

        worker = SpeechWorker(
            self._speaker,
            text,
            speech_to_text=speech_to_text,
        )
        worker.interrupted.connect(self._on_speech_interrupted)
        worker.spoken.connect(self._on_speech_completed)
        worker.failed.connect(self._on_speech_failed)
        worker.finished.connect(self._on_speech_finished)
        

        self._speech_thread = worker
        self.stop_button.setEnabled(True)
        worker.start()
    def _on_system_action_requested(
        self,
        announcement: str,
        action: str,
    ) -> None:
        """Remember a power action until its announcement has been spoken."""

        if action not in {"shutdown_system", "reboot_system"}:
            return

        self._pending_system_action = action

    def _on_speech_completed(self) -> None:
        """Execute a pending system action after successful playback."""

        action = self._pending_system_action

        if action is None:
            return

        self._pending_system_action = None

        if self._assistant_engine is None:
            self.messages.add_message(
                "assistant",
                "System action cancelled: assistant engine is unavailable.",
            )
            return

        try:
            result = self._assistant_engine.execute_system_action(action)
        except Exception as exc:
            result = f"System action failed: {exc}"

        print(f"[JARVIS] {result}", flush=True)
        self.messages.add_message("assistant", result)

    def _on_speech_failed(self, error: str) -> None:
        """Cancel a pending system action if speech playback fails."""

        if self._pending_system_action is not None:
            self._pending_system_action = None
            self.messages.add_message(
                "assistant",
                "System action cancelled because the announcement "
                "could not be played.",
            )

        print(f"[JARVIS] Speech error: {error}", flush=True)        
    def _on_speech_interrupted(self, transcript: str) -> None:
        """Process speech captured while JARVIS was talking."""
        if self._pending_system_action is not None:
            self._pending_system_action = None
            self.messages.add_message(
                "assistant",
                "System action cancelled because the announcement was interrupted.",
            )

        if not transcript.strip():
            return

        print(
            f"[JARVIS] Speech interrupted: {transcript}",
            flush=True,
        )

        self.input.setText(transcript)
        self._send_message()        
    def _stop_speaking(self) -> None:
        """Stop playback and cancel any pending power action."""
        if self._pending_system_action is not None:
            self._pending_system_action = None
            self.messages.add_message(
                "assistant",
                "System action cancelled because speech was stopped.",
            )

        if self._speaker is not None:
            self._speaker.stop()

        self.stop_button.setEnabled(False)
        self._set_state(OrbState.IDLE)

    def _on_speech_finished(self) -> None:
        """Clean up speech playback and resume wake-word detection."""
        worker = self._speech_thread
        self._speech_thread = None

        if worker is not None:
            worker.deleteLater()

        self.stop_button.setEnabled(False)

        if not self._typing_timer.isActive():
            self._set_state(OrbState.IDLE)

        # Resume only when no new chat request is being processed.
        if (
            self._wake_word_worker is not None
            and self._chat_thread is None
        ):
            self._wake_word_worker.resume_listening()

        self._finish_close_if_idle()
    

    def _on_chat_failure(self, error: str) -> None:
        self._thinking_label.setText(f"JARVIS error: {error}")
        self._set_state(OrbState.IDLE)

        if self._wake_word_worker is not None:
            self._wake_word_worker.resume_listening()

    def _on_chat_thread_finished(self) -> None:
        thread = self._chat_thread
        self._chat_thread = None
        self._chat_worker = None

        self.input.setEnabled(True)
        self.send_button.setEnabled(True)
        self.input.setFocus()

        if thread is not None:
            thread.deleteLater()

        self._finish_close_if_idle()      
            

    def _start_wake_word_listening(self) -> None:
        """Start continuous Hey JARVIS detection in the background."""
        if self._wake_word_thread is not None:
            return

        if (
            self._chat_thread is not None
            or self._voice_thread is not None
            or self._speech_thread is not None
        ):
            return

        thread = QThread(self)
        worker = WakeWordWorker(speaker=self._speaker)
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.status_changed.connect(self._on_wake_word_status)
        worker.transcript_ready.connect(self._on_wake_word_transcript)
        worker.error_occurred.connect(self._on_wake_word_error)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(self._on_wake_word_thread_finished)

        self._wake_word_thread = thread
        self._wake_word_worker = worker

        self._set_state(OrbState.LISTENING)
        self.last_request.setText("Starting wake-word detection...")

        thread.start()

    def _on_wake_word_status(self, state: str, detail: str) -> None:
        """Display wake-word listener status."""
        try:
            orb_state = OrbState(state)
        except ValueError:
            orb_state = OrbState.IDLE

        self._set_state(orb_state)
        self.last_request.setText(detail)

    def _on_wake_word_transcript(self, transcript: str) -> None:
        """Send a wake-word command to the existing chat system."""
        if not transcript.strip():
            return

        self.input.setText(transcript)
        self._send_message()

    def _on_wake_word_error(self, error: str) -> None:
        """Display wake-word detection errors."""
        self.messages.add_message(
            "assistant",
            f"Wake-word error: {error}",
        )
        self._set_state(OrbState.IDLE)

    def _finish_close_if_idle(self) -> None:
        """Close the popup after all background workers have stopped."""
        if not self._close_when_idle:
            return

        if (
            self._wake_word_thread is None
            and self._chat_thread is None
            and self._voice_thread is None
            and self._speech_thread is None
        ):
            self.close()


    def _on_wake_word_thread_finished(self) -> None:
        """Clean up the continuous wake-word worker."""
        thread = self._wake_word_thread

        self._wake_word_thread = None
        self._wake_word_worker = None

        if thread is not None:
            thread.deleteLater()

        self._finish_close_if_idle()

            

    def _start_voice_listening(self) -> None:
        """Start microphone recording in a background thread."""

        # Continuous wake-word detection already owns the microphone.
        if self._wake_word_thread is not None:
            self.last_request.setText(
                'Wake-word mode is active. Say "Hey JARVIS".'
            )
            return

        if self._voice_thread is not None:
            return

        if self._chat_thread is not None:
            self._set_status("CHAT BUSY")
            return

        if self._speech_thread is not None:
            self._set_status("SPEAKING")
            return

        thread = QThread(self)
        worker = VoiceWorker()
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.status_changed.connect(self._on_voice_status)
        worker.transcript_ready.connect(self._on_voice_transcript)
        worker.error_occurred.connect(self._on_voice_error)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(self._on_voice_thread_finished)

        self._voice_thread = thread
        self._voice_worker = worker

        self.mic_button.setEnabled(False)
        self._set_state(OrbState.LISTENING)
        self.last_request.setText("Starting microphone...")

        thread.start()
     

    def _on_voice_status(self, state: str, detail: str) -> None:
        """Update the popup when microphone status changes."""
        try:
            orb_state = OrbState(state)
        except ValueError:
            orb_state = OrbState.IDLE

        self._set_state(orb_state)
        self.last_request.setText(detail)

    def _on_voice_transcript(self, transcript: str) -> None:
        """Send recognized speech to JARVIS."""
        if not transcript.strip():
            self.last_request.setText("No speech detected. Try again.")
            return

        self.input.setText(transcript)
        self._send_message()

    def _on_voice_error(self, error: str) -> None:
        """Display microphone or speech-recognition errors."""
        self.last_request.setText("Voice input failed.")
        self.messages.add_message("assistant", f"Voice error: {error}")
        self._set_state(OrbState.IDLE)

    def _on_voice_thread_finished(self) -> None:
        """Clean up the completed microphone worker."""
        thread = self._voice_thread

        self._voice_thread = None
        self._voice_worker = None

        self.mic_button.setEnabled(True)

        if thread is not None:
            thread.deleteLater()

        if self._chat_thread is None:
            self._set_state(OrbState.IDLE)            

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            return

        super().keyPressEvent(event)



    def closeEvent(self, event) -> None:
        """Wait for all background workers before closing."""

        workers_active = (
            self._wake_word_thread is not None
            or self._chat_thread is not None
            or self._voice_thread is not None
            or self._speech_thread is not None
        )

        if workers_active:
            self._close_when_idle = True

            if self._wake_word_worker is not None:
                self._wake_word_worker.request_stop()

            event.ignore()
            self._set_status("STOPPING JARVIS...")
            return

        super().closeEvent(event)




def main() -> int:
    app = QApplication(sys.argv)
    apply_theme(app)

    window = PopupWindow()
    window.show()
    window.input.setFocus()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())