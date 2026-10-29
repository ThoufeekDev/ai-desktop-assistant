
"""Confirmation UI for actions that require user approval."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from jarvis.gui.theme import tokens


class ConfirmBar(QFrame):
    """Display a pending action and emit the user's decision."""

    allowed = Signal()
    denied = Signal()

    def __init__(
        self,
        action_description: str,
        parent=None,
    ) -> None:
        super().__init__(parent)

        self.setObjectName("ConfirmBar")
        self.setStyleSheet(
            f"""
            QFrame#ConfirmBar {{
                background-color: {tokens.SURFACE_RAISED};
                border: 1px solid {tokens.WARNING};
                border-radius: 12px;
            }}
            """
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(10)

        self.heading_label = QLabel("CONFIRM ACTION")
        self.heading_label.setStyleSheet(
            f"color: {tokens.WARNING}; font-weight: 600; "
            "background: transparent; border: none;"
        )

        self.description_label = QLabel(action_description)
        self.description_label.setWordWrap(True)
        self.description_label.setStyleSheet(
            f"color: {tokens.TEXT}; background: transparent; border: none;"
        )

        buttons = QHBoxLayout()
        buttons.setSpacing(8)

        self.allow_button = QPushButton("Allow")
        self.allow_button.setAccessibleName("Allow action")
        self.allow_button.setMinimumHeight(44)
        self.allow_button.setStyleSheet(
            f"background-color: {tokens.ACCENT}; "
            f"color: {tokens.ACCENT_TEXT}; "
            f"border: 1px solid {tokens.ACCENT}; "
            "border-radius: 8px; font-weight: 600;"
        )
        self.allow_button.clicked.connect(self.allowed.emit)

        self.deny_button = QPushButton("Deny")
        self.deny_button.setAccessibleName("Deny action")
        self.deny_button.setMinimumHeight(44)
        self.deny_button.setStyleSheet(
            f"background-color: {tokens.DANGER}; "
            f"color: {tokens.DANGER_TEXT}; "
            f"border: 1px solid {tokens.DANGER}; "
            "border-radius: 8px; font-weight: 600;"
        )
        self.deny_button.clicked.connect(self.denied.emit)

        buttons.addWidget(self.allow_button)
        buttons.addWidget(self.deny_button)

        layout.addWidget(self.heading_label)
        layout.addWidget(self.description_label)
        layout.addLayout(buttons)
