
"""Compact, reusable tool execution result chip."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QHBoxLayout

from jarvis.gui.theme import tokens


class ToolChip(QFrame):
    """Display a tool name, target, risk level, and execution status."""

    def __init__(
        self,
        tool_name: str,
        target: str,
        risk: str,
        status: str,
        parent=None,
    ) -> None:
        super().__init__(parent)

        self.setObjectName("ToolChip")
        self.setStyleSheet(
            f"""
            QFrame#ToolChip {{
                background-color: {tokens.SURFACE_RAISED};
                border: 1px solid {tokens.BORDER};
                border-radius: 10px;
            }}
            """
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)

        self.tool_label = QLabel(tool_name)
        self.tool_label.setStyleSheet(
            f"color: {tokens.ACCENT}; font-family: "
            f"'{tokens.FONT_MONO}'; font-weight: 600; "
            "background: transparent; border: none;"
        )

        self.target_label = QLabel(target)
        self.target_label.setProperty("muted", True)
        self.target_label.setStyleSheet(
            "background: transparent; border: none;"
        )

        self.risk_label = QLabel(risk.upper())
        self.risk_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.risk_label.setStyleSheet(
            f"color: {tokens.WARNING}; font-size: 11px; "
            "background: transparent; border: none;"
        )

        self.status_label = QLabel()
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet(
            "font-size: 11px; font-weight: 600; "
            "background: transparent; border: none;"
        )

        layout.addWidget(self.tool_label)
        layout.addWidget(self.target_label, 1)
        layout.addWidget(self.risk_label)
        layout.addWidget(self.status_label)

        self.set_status(status)

    def set_status(self, status: str) -> None:
        """Update the status text and its semantic color."""
        normalized = status.strip().lower()
        self.status_label.setText(normalized.upper())

        if normalized in {"done", "success", "completed"}:
            color = tokens.SUCCESS
        elif normalized in {"pending", "running"}:
            color = tokens.WARNING
        elif normalized in {"failed", "denied", "blocked", "error"}:
            color = tokens.DANGER
        else:
            color = tokens.MUTED

        self.status_label.setStyleSheet(
            f"color: {color}; font-size: 11px; font-weight: 600; "
            "background: transparent; border: none;"
        )
