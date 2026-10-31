"""Settings page for JARVIS's local Ollama configuration."""

import math
import tomllib
from pathlib import Path
from urllib.parse import urlsplit

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from jarvis.config import default_config_path, load_config
from jarvis.gui.theme import tokens


class SettingsPage(QWidget):
    """Edit and save local Ollama settings without losing other settings."""

    settings_saved = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.config_path = default_config_path()

        root = QVBoxLayout(self)
        root.setSpacing(14)

        intro = QLabel(
            "Configure JARVIS's local AI engine. These settings are saved "
            "to your existing configuration file; wake-word settings "
            "are preserved."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet(f"color: {tokens.MUTED};")
        root.addWidget(intro)

        form = QFormLayout()
        form.setSpacing(12)

        self.base_url = QLineEdit()
        self.base_url.setPlaceholderText("http://127.0.0.1:11434")
        self.base_url.setAccessibleName("Ollama server URL")
        form.addRow("Ollama URL", self.base_url)

        self.model = QLineEdit()
        self.model.setPlaceholderText("qwen2.5:3b-instruct")
        self.model.setAccessibleName("Ollama model")
        form.addRow("Model", self.model)

        self.timeout = QDoubleSpinBox()
        self.timeout.setRange(1.0, 3600.0)
        self.timeout.setDecimals(1)
        self.timeout.setSuffix(" seconds")
        form.addRow("Request timeout", self.timeout)

        self.history_turns = QSpinBox()
        self.history_turns.setRange(1, 100)
        form.addRow("Conversation history turns", self.history_turns)

        root.addLayout(form)

        prompt_label = QLabel("System prompt")
        prompt_label.setStyleSheet(
            f"color: {tokens.TEXT}; font-weight: 600;"
        )
        root.addWidget(prompt_label)

        self.system_prompt = QPlainTextEdit()
        self.system_prompt.setPlaceholderText(
            "Describe how JARVIS should behave..."
        )
        self.system_prompt.setMinimumHeight(160)
        self.system_prompt.setAccessibleName("JARVIS system prompt")
        root.addWidget(self.system_prompt, 1)

        actions = QHBoxLayout()

        self.status = QLabel("")
        self.status.setWordWrap(True)
        self.status.setStyleSheet(f"color: {tokens.MUTED};")

        self.reload_button = QPushButton("Reload saved")
        self.reload_button.clicked.connect(self.reload_settings)

        self.save_button = QPushButton("Save settings")
        self.save_button.setProperty("primary", True)
        self.save_button.clicked.connect(self.save_settings)

        actions.addWidget(self.status, 1)
        actions.addWidget(self.reload_button)
        actions.addWidget(self.save_button)
        root.addLayout(actions)

        self.reload_settings()

    def reload_settings(self) -> None:
        """Load saved settings into the controls."""
        try:
            config = load_config(self.config_path)
            self.base_url.setText(config.ollama.base_url)
            self.model.setText(config.ollama.model)
            self.timeout.setValue(config.ollama.timeout)
            self.history_turns.setValue(config.ollama.max_history_turns)
            self.system_prompt.setPlainText(config.ollama.system_prompt)
            self.status.setText(f"Loaded {self.config_path}")
        except Exception as exc:
            self.status.setText(f"Could not load settings: {exc}")
            QMessageBox.warning(self, "Settings could not be loaded", str(exc))

    def save_settings(self) -> None:
        """Validate Ollama settings and preserve all other TOML sections."""
        base_url = self.base_url.text().strip().rstrip("/")
        model = self.model.text().strip()
        prompt = self.system_prompt.toPlainText().strip()
        timeout = self.timeout.value()
        history_turns = self.history_turns.value()

        if not base_url or not model or not prompt:
            QMessageBox.warning(
                self,
                "Missing settings",
                "Ollama URL, model, and system prompt cannot be empty.",
            )
            return

        try:
            parsed = urlsplit(base_url)
            port = parsed.port
            valid_url = (
                parsed.scheme in {"http", "https"}
                and bool(parsed.hostname)
                and (port is None or 1 <= port <= 65535)
            )
        except ValueError:
            valid_url = False

        if not valid_url:
            QMessageBox.warning(
                self,
                "Invalid URL",
                "Enter a valid HTTP or HTTPS Ollama URL, such as "
                "http://127.0.0.1:11434.",
            )
            return

        if not math.isfinite(timeout) or timeout <= 0:
            QMessageBox.warning(
                self, "Invalid timeout", "Timeout must be greater than zero."
            )
            return

        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)

            # Parse the existing file first, so malformed TOML is never
            # silently replaced and unrelated sections can be preserved.
            if self.config_path.exists():
                with self.config_path.open("rb") as file:
                    existing = tomllib.load(file)
            else:
                existing = {}

            if not isinstance(existing, dict):
                raise ValueError("The configuration root must be a TOML table.")

            wake_word = existing.get("wake_word", {})
            if not isinstance(wake_word, dict):
                raise ValueError(
                    "The existing [wake_word] section is not a TOML table."
                )

            # Retain all existing top-level settings and wake-word values.
            # The fields edited here are the only fields we replace.
            lines = [
                "# JARVIS configuration",
                "",
                "[ollama]",
                f"base_url = {self._toml_string(base_url)}",
                f"model = {self._toml_string(model)}",
                f"timeout = {timeout!r}",
                f"system_prompt = {self._toml_string(prompt)}",
                f"max_history_turns = {history_turns}",
                "",
            ]

            # Keep the existing wake-word section verbatim where possible.
            # Instead of serializing a partial section, retain the original
            # file and replace only its [ollama] block.
            original = (
                self.config_path.read_text(encoding="utf-8")
                if self.config_path.exists()
                else ""
            )
            updated = self._replace_ollama_section(original, "\n".join(lines))

            # Validate the complete proposed file before writing it.
            import tempfile

            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                suffix=".toml",
                dir=self.config_path.parent,
                delete=False,
            ) as temporary:
                temporary.write(updated)
                temporary_path = Path(temporary.name)

            try:
                load_config(temporary_path)
            except Exception as exc:
                raise RuntimeError(
                    f"{exc}\nTemporary configuration retained at: "
                    f"{temporary_path}"
                ) from exc
            else:
                temporary_path.unlink(missing_ok=True)

            # Atomic replacement avoids leaving a partially written config.
            temporary_path = self.config_path.with_suffix(
                self.config_path.suffix + ".tmp"
            )
            temporary_path.write_text(updated, encoding="utf-8")
            temporary_path.replace(self.config_path)

            self.status.setText(f"Saved settings to {self.config_path}")
            self.settings_saved.emit()
            QMessageBox.information(
                self,
                "Settings saved",
                "Ollama settings were saved. They will take effect when "
                "JARVIS creates or refreshes its AI client.",
            )
        except Exception as exc:
            self.status.setText(f"Save failed: {exc}")
            QMessageBox.critical(self, "Could not save settings", str(exc))

    @staticmethod
    def _toml_string(value: str) -> str:
        """Encode a Python string as a valid TOML basic string."""
        import json

        return json.dumps(value, ensure_ascii=False)

    @staticmethod
    def _replace_ollama_section(original: str, replacement: str) -> str:
        """Replace only [ollama], preserving all other TOML sections."""
        import re

        pattern = re.compile(
            r"(?m)^\[ollama\]\s*$.*?(?=^\[[^\]]+\]\s*$|\Z)",
            re.DOTALL,
        )
        if pattern.search(original):
            result = pattern.sub(lambda match: replacement.rstrip() + "\n\n", original, count=1)
            return result.rstrip() + "\n"

        separator = "\n" if original and not original.endswith("\n") else ""
        return original + separator + replacement.rstrip() + "\n"
