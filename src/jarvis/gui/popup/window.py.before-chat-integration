"""Compact JARVIS popup UI using the fake backend."""

import sys
from collections import deque

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from jarvis.gui.components.confirm_bar import ConfirmBar
from jarvis.gui.components.message_view import MessageView
from jarvis.gui.components.orb import Orb, OrbState
from jarvis.gui.components.tool_chip import ToolChip
from jarvis.gui.fake_backend.events import (
    AssistantText,
    ConfirmationRequested,
    MicrophoneLevel,
    StateChanged,
    ToolResult,
    UserMessage,
)
from jarvis.gui.fake_backend.scenario import demo_scenario
from jarvis.gui.theme import tokens
from jarvis.gui.theme.loader import apply_theme


class PopupWindow(QWidget):
    """Small, keyboard-friendly JARVIS popup."""

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("JarvisPopup")
        self.setWindowTitle("JARVIS")
        self.setFixedSize(tokens.POPUP_WIDTH, tokens.POPUP_HEIGHT)

        self._events = deque()
        self._waiting_for_confirmation = False
        self._assistant_label = None
        self._tool_pending = False
        self._tool_target = "kitty"
        self._confirmation_request_id = None

        self._scenario_timer = QTimer(self)
        self._scenario_timer.setSingleShot(True)
        self._scenario_timer.timeout.connect(self._process_next_event)

        self._build_ui()
        self._show_demo()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(8)

        header = QHBoxLayout()

        self.orb = Orb()
        self.orb.setFixedSize(54, 54)

        self.state_label = QLabel("IDLE")
        self.state_label.setProperty("mono", True)
        self.state_label.setStyleSheet(
            f"color: {tokens.ACCENT}; font-family: "
            f"'{tokens.FONT_MONO}'; font-weight: 600;"
        )

        header.addWidget(self.orb)
        header.addWidget(self.state_label)
        header.addStretch()

        self.last_request = QLabel("Ready for your request")
        self.last_request.setProperty("muted", True)
        self.last_request.setStyleSheet(
            f"color: {tokens.MUTED}; font-family: "
            f"'{tokens.FONT_MONO}'; font-size: 11px;"
        )

        self.messages = MessageView()
        self.messages.setMinimumHeight(70)
        self.messages.setMaximumHeight(100)

        self.tool_chip = ToolChip(
            "open_app", "kitty", "confirm-before-run", "idle"
        )

        self.run_demo_button = QPushButton("Run demo scenario")
        self.run_demo_button.setAccessibleName("Run fake backend scenario")
        self.run_demo_button.clicked.connect(self._start_demo_scenario)

        self.confirm_bar = ConfirmBar("Waiting for a simulated action request.")
        self.confirm_bar.setVisible(False)
        self.confirm_bar.allowed.connect(self._demo_allow)
        self.confirm_bar.denied.connect(self._demo_deny)

        input_row = QHBoxLayout()

        self.mic_button = QPushButton("Mic")
        self.mic_button.setAccessibleName("Toggle push to talk")
        self.mic_button.setMinimumSize(44, 44)
        self.mic_button.setCheckable(True)
        self.mic_button.toggled.connect(self._toggle_mic_ui)

        self.input = QLineEdit()
        self.input.setPlaceholderText("Ask JARVIS...")
        self.input.setAccessibleName("Message to JARVIS")
        self.input.returnPressed.connect(self._send_message)

        self.send_button = QPushButton("Send")
        self.send_button.setAccessibleName("Send message")
        self.send_button.setMinimumHeight(44)
        self.send_button.clicked.connect(self._send_message)

        input_row.addWidget(self.mic_button)
        input_row.addWidget(self.input, 1)
        input_row.addWidget(self.send_button)

        footer = QLabel("Esc to close")
        footer.setAlignment(Qt.AlignmentFlag.AlignRight)
        footer.setStyleSheet(f"color: {tokens.MUTED}; font-size: 11px;")

        root.addLayout(header)
        root.addWidget(self.last_request)
        root.addWidget(self.messages, 1)
        root.addWidget(self.tool_chip)
        root.addWidget(self.run_demo_button)
        root.addWidget(self.confirm_bar)
        root.addLayout(input_row)
        root.addWidget(footer)

    def _show_demo(self) -> None:
        self.messages.add_message(
            "assistant",
            "Hello. I'm JARVIS. How can I help?",
        )

    def _set_state(self, state: str) -> None:
        self.state_label.setText(state)
        self.orb.set_state(OrbState(state))

    def _start_demo_scenario(self) -> None:
        if self._scenario_timer.isActive() or self._waiting_for_confirmation:
            return

        self._events = deque(demo_scenario())
        self._assistant_label = None
        self._tool_pending = False
        self._confirmation_request_id = None
        self.run_demo_button.setEnabled(False)
        self.run_demo_button.setText("Demo running…")
        self._process_next_event()

    def _process_next_event(self) -> None:
        if not self._events or self._waiting_for_confirmation:
            if not self._waiting_for_confirmation:
                self.run_demo_button.setEnabled(True)
                self.run_demo_button.setText("Run demo scenario")
                self._set_state("IDLE")
            return

        event = self._events.popleft()

        if isinstance(event, StateChanged):
            self._set_state(event.state)

        elif isinstance(event, MicrophoneLevel):
            # UI demo only: no microphone is accessed.
            self.last_request.setText(
                f"Demo microphone level: {event.level:.2f}"
            )

        elif isinstance(event, UserMessage):
            self.last_request.setText(event.text)
            self.messages.add_message("user", event.text)

        elif isinstance(event, AssistantText):
            if self._assistant_label is None:
                self._assistant_label = self.messages.add_message(
                    "assistant", event.text
                )
            else:
                self._assistant_label.setText(event.text)

            if event.complete:
                self._assistant_label = None

        elif isinstance(event, ToolResult):
            self._tool_pending = event.status == "pending"
            self._tool_target = event.target
            self.tool_chip.tool_label.setText(event.tool_name)
            self.tool_chip.target_label.setText(event.target)
            self.tool_chip.risk_label.setText(event.risk.upper())
            self.tool_chip.status_label.setText(event.status.upper())

        elif isinstance(event, ConfirmationRequested):
            self._confirmation_request_id = event.request_id
            self._waiting_for_confirmation = True
            self.confirm_bar.heading_label.setText("CONFIRM ACTION")
            self.confirm_bar.description_label.setText(event.description)
            self.setMinimumWidth(tokens.POPUP_WIDTH)
            self.setMaximumWidth(tokens.POPUP_WIDTH)
            self.setMinimumHeight(440)
            self.setMaximumHeight(600)
            self.run_demo_button.setVisible(False)
            self.confirm_bar.setVisible(True)
            self.adjustSize()
            return

        self._scenario_timer.start(500)

    def _finish_demo_confirmation(self, allowed: bool) -> None:
        if not self._waiting_for_confirmation:
            return

        self._waiting_for_confirmation = False
        self.confirm_bar.setVisible(False)
        self.run_demo_button.setVisible(True)
        self.setMinimumSize(tokens.POPUP_WIDTH, tokens.POPUP_HEIGHT)
        self.setMaximumSize(tokens.POPUP_WIDTH, tokens.POPUP_HEIGHT)
        self.resize(tokens.POPUP_WIDTH, tokens.POPUP_HEIGHT)

        if allowed:
            # Simulated success only; no tool is executed.
            self.tool_chip.status_label.setText("DEMO ALLOWED")
            self.messages.add_message(
                "assistant",
                "Demo: approval received. No desktop action was executed.",
            )
        else:
            self.tool_chip.status_label.setText("DENIED")
            self.messages.add_message(
                "assistant",
                "Demo: action denied. Nothing was executed.",
            )

        self._tool_pending = False
        self._scenario_timer.start(300)

    def _demo_allow(self) -> None:
        self._finish_demo_confirmation(True)

    def _demo_deny(self) -> None:
        self._finish_demo_confirmation(False)

    def _toggle_mic_ui(self, enabled: bool) -> None:
        """Simulate microphone state without capturing audio."""
        if enabled:
            self._set_state("LISTENING")
            self.mic_button.setText("Stop")
        else:
            self._set_state("IDLE")
            self.mic_button.setText("Mic")

    def _send_message(self) -> None:
        text = self.input.text().strip()
        if not text:
            return

        self.last_request.setText(text)
        self.messages.add_message("user", text)
        self.input.clear()

        self._set_state("THINKING")
        self.messages.add_message(
            "assistant",
            f"Demo mode received: {text}",
        )
        self._set_state("IDLE")

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            return
        super().keyPressEvent(event)


def main() -> int:
    app = QApplication(sys.argv)
    apply_theme(app)

    window = PopupWindow()
    window.show()
    window.input.setFocus()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
