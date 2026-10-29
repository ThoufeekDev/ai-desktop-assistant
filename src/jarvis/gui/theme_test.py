"""Temporary visual test for the shared JARVIS theme."""

import sys

from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from jarvis.gui.theme.loader import apply_theme
from jarvis.gui.theme import tokens


def main() -> int:
    app = QApplication(sys.argv)
    apply_theme(app)

    window = QWidget()
    window.setWindowTitle("JARVIS — Theme Test")
    window.resize(tokens.POPUP_WIDTH, tokens.POPUP_HEIGHT)

    layout = QVBoxLayout(window)
    layout.setContentsMargins(24, 24, 24, 24)
    layout.setSpacing(12)

    title = QLabel("JARVIS")
    title.setStyleSheet(
        f"color: {tokens.ACCENT}; font-size: 28px; font-weight: 600;"
    )

    subtitle = QLabel("LOCAL AI DESKTOP ASSISTANT")
    subtitle.setProperty("muted", True)
    subtitle.setProperty("mono", True)

    button = QLabel("Shared theme loaded")
    button.setStyleSheet(
        f"background-color: {tokens.SURFACE_RAISED};"
        f"border: 1px solid {tokens.BORDER};"
        "border-radius: 10px;"
        "padding: 14px;"
    )

    layout.addWidget(title)
    layout.addWidget(subtitle)
    layout.addStretch()
    layout.addWidget(button)

    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
