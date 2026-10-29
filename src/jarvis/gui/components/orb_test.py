"""Visual test for the JARVIS Orb component."""

import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

from jarvis.gui.components.orb import Orb, OrbState
from jarvis.gui.theme.loader import apply_theme


def main() -> int:
    app = QApplication(sys.argv)
    apply_theme(app)

    window = QWidget()
    window.setWindowTitle("JARVIS — Orb Test")
    window.resize(360, 360)

    layout = QVBoxLayout(window)
    layout.setContentsMargins(24, 16, 24, 20)
    layout.setSpacing(8)

    orb = Orb()
    orb.setFixedSize(220, 220)

    status = QLabel("IDLE")
    status.setAlignment(
        __import__("PySide6.QtCore", fromlist=["Qt"]).Qt.AlignmentFlag.AlignCenter
    )
    status.setProperty("mono", True)

    layout.addWidget(orb, alignment=__import__(
        "PySide6.QtCore", fromlist=["Qt"]
    ).Qt.AlignmentFlag.AlignCenter)
    layout.addWidget(status)

    states = [
        OrbState.IDLE,
        OrbState.LISTENING,
        OrbState.THINKING,
        OrbState.SPEAKING,
    ]
    index = 0

    def next_state() -> None:
        nonlocal index
        index = (index + 1) % len(states)
        orb.set_state(states[index])
        status.setText(states[index].value)

    timer = QTimer(window)
    timer.timeout.connect(next_state)
    timer.start(2000)

    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
