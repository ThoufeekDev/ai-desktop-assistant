
"""Voice controls and status display for the JARVIS manager."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from jarvis.gui.components.orb import Orb, OrbState
from jarvis.gui.theme import tokens


class VoicePage(QWidget):
    """Display voice status and expose safe listening controls."""

    start_requested = Signal()
    stop_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._listening = False
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 12, 20, 20)
        root.setSpacing(18)

        intro = QLabel(
            "Talk to JARVIS using your microphone. "
            "Audio processing will run locally."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet(f"color: {tokens.MUTED};")
        root.addWidget(intro)

        card = QFrame()
        card.setObjectName("VoiceCard")
        card.setStyleSheet(
            f"QFrame#VoiceCard {{"
            f"background-color: {tokens.SURFACE_RAISED};"
            f"border: 1px solid {tokens.BORDER};"
            f"border-radius: 16px;"
            f"}}"
        )

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(24, 22, 24, 22)
        card_layout.setSpacing(12)

        self.orb = Orb()
        self.orb.set_state(OrbState.IDLE)
        card_layout.addWidget(
            self.orb,
            alignment=Qt.AlignmentFlag.AlignHCenter,
        )

        self.state_label = QLabel("VOICE STANDBY")
        self.state_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.state_label.setStyleSheet(
            f"color: {tokens.ACCENT};"
            f"font-family: '{tokens.FONT_MONO}';"
            "font-size: 12px;"
            "font-weight: 700;"
        )
        card_layout.addWidget(self.state_label)

        self.detail_label = QLabel(
            "Microphone is inactive. Start listening when you're ready."
        )
        self.detail_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.detail_label.setWordWrap(True)
        self.detail_label.setStyleSheet(f"color: {tokens.MUTED};")
        card_layout.addWidget(self.detail_label)

        root.addWidget(card)

        transcript_heading = QLabel("LAST TRANSCRIPTION")
        transcript_heading.setStyleSheet(
            f"color: {tokens.MUTED};"
            f"font-family: '{tokens.FONT_MONO}';"
            "font-size: 10px;"
            "font-weight: 700;"
        )
        root.addWidget(transcript_heading)

        self.transcript_label = QLabel(
            "Your recognized speech will appear here."
        )
        self.transcript_label.setWordWrap(True)
        self.transcript_label.setMinimumHeight(54)
        self.transcript_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.transcript_label.setStyleSheet(
            f"color: {tokens.TEXT};"
            f"background-color: {tokens.SURFACE};"
            f"border: 1px solid {tokens.BORDER};"
            "border-radius: 10px;"
            "padding: 12px;"
        )
        root.addWidget(self.transcript_label)

        controls = QHBoxLayout()
        controls.setSpacing(12)

        self.start_button = QPushButton("Start Listening")
        self.start_button.setProperty("primary", True)
        self.start_button.setMinimumHeight(44)
        self.start_button.clicked.connect(self.start_requested.emit)

        self.stop_button = QPushButton("Stop Listening")
        self.stop_button.setMinimumHeight(44)
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.stop_requested.emit)

        controls.addWidget(self.start_button)
        controls.addWidget(self.stop_button)
        root.addLayout(controls)
        root.addStretch()

    def set_status(self, state: OrbState, detail: str) -> None:
        """Update the displayed voice state."""
        self.orb.set_state(state)
        self.state_label.setText(f"VOICE {state.value}")
        self.detail_label.setText(detail)

    def set_listening_controls(self, active: bool) -> None:
        """Enable or disable controls based on worker state."""
        self._listening = active
        self.start_button.setEnabled(not active)
        self.stop_button.setEnabled(active)

    def set_transcript(self, text: str) -> None:
        """Display the latest recognized utterance."""
        self.transcript_label.setText(
            text.strip() or "No speech was recognized."
        )
