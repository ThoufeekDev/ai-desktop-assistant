"""Load the shared JARVIS Qt theme from centralized design tokens."""

from pathlib import Path

from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

from jarvis.gui.theme import tokens


_THEME_FILE = Path(__file__).with_name("jarvis.qss")


def _load_stylesheet() -> str:
    """Expand token placeholders in the shared QSS file."""
    stylesheet = _THEME_FILE.read_text(encoding="utf-8")

    replacements = {
        "{{BACKGROUND}}": tokens.BACKGROUND,
        "{{SURFACE}}": tokens.SURFACE,
        "{{SURFACE_RAISED}}": tokens.SURFACE_RAISED,
        "{{BORDER}}": tokens.BORDER,
        "{{TEXT}}": tokens.TEXT,
        "{{MUTED}}": tokens.MUTED,
        "{{ACCENT}}": tokens.ACCENT,
        "{{ACCENT_TEXT}}": tokens.ACCENT_TEXT,
        "{{ACCENT_SOFT}}": tokens.ACCENT_SOFT,
        "{{SUCCESS}}": tokens.SUCCESS,
        "{{WARNING}}": tokens.WARNING,
        "{{DANGER}}": tokens.DANGER,
        "{{DANGER_TEXT}}": tokens.DANGER_TEXT,
        "{{FONT_UI}}": tokens.FONT_UI,
        "{{FONT_MONO}}": tokens.FONT_MONO,
        "{{FONT_FALLBACK_UI}}": tokens.FONT_FALLBACK_UI,
        "{{FONT_FALLBACK_MONO}}": tokens.FONT_FALLBACK_MONO,
    }

    for placeholder, value in replacements.items():
        stylesheet = stylesheet.replace(placeholder, value)

    return stylesheet


def apply_theme(app: QApplication) -> None:
    """Apply the shared stylesheet and default UI font."""
    app.setStyleSheet(_load_stylesheet())

    available_fonts = set(QFontDatabase.families())

    ui_font = (
        tokens.FONT_UI
        if tokens.FONT_UI in available_fonts
        else tokens.FONT_FALLBACK_UI
    )
    app.setFont(QFont(ui_font, 10))
