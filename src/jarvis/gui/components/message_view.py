"""Shared conversation message view for JARVIS interfaces."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from jarvis.gui.theme import tokens


class MessageView(QWidget):
    """Display a compact sequence of user and assistant messages."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(12)
        self._layout.setAlignment(Qt.AlignmentFlag.AlignTop)

    def add_message(self, role: str, text: str) -> QLabel:
        """Append a user or assistant message and return its label."""
        normalized_role = role.strip().casefold()

        if normalized_role not in {"user", "assistant"}:
            raise ValueError("role must be 'user' or 'assistant'")

        label = QLabel(text)
        label.setWordWrap(True)
        label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        label.setProperty("messageRole", normalized_role)

        if normalized_role == "user":
            label.setStyleSheet(
                f"color: {tokens.MUTED}; "
                f"background-color: {tokens.SURFACE}; "
                f"border: 1px solid {tokens.BORDER}; "
                "border-radius: 10px; padding: 10px;"
            )
        else:
            label.setStyleSheet(
                f"color: {tokens.TEXT}; "
                f"background-color: {tokens.SURFACE_RAISED}; "
                f"border: 1px solid {tokens.BORDER}; "
                "border-radius: 10px; padding: 12px;"
            )

        self._layout.addWidget(label)
        return label

    def clear_messages(self) -> None:
        """Remove all displayed messages."""
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
