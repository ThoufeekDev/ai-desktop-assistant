"""Main JARVIS manager window with a real local-AI chat page."""

import sys

from PySide6.QtCore import Qt, QThread, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)


from jarvis.assistant_engine import AssistantEngine
from jarvis.gui.chat_worker import ChatWorker
from jarvis.gui.components.message_view import MessageView
from jarvis.gui.components.orb import OrbState
from jarvis.gui.voice_worker import VoiceWorker
from jarvis.gui.wake_word_worker import WakeWordWorker
from jarvis.gui.manager.memory_page import MemoryPage
from jarvis.gui.manager.tools_page import ToolsPage
from jarvis.gui.manager.settings_page import SettingsPage
from jarvis.gui.manager.voice_page import VoicePage
from jarvis.gui.manager.storage_page import StoragePage
from jarvis.gui.theme import tokens
from jarvis.gui.theme.loader import apply_theme
from jarvis.ollama_client import OllamaClient
from jarvis.system_metrics import (
    get_cpu_usage,
    get_disk_usage,
    get_memory_usage,
    get_swap_usage,
    get_system_info,
)




PAGES = [
    ("Dashboard", "Overview of JARVIS status and activity."),
    ("Chat", "Conversation with your local AI assistant."),
    ("Voice", "Voice assistant controls and audio status."),
    ("Memory", "Review and manage approved memories."),
    ("Storage", "Mounted filesystems and disk capacity."),
    ("Tools", "Available tools and permission status."),
    ("Automation", "Planned and scheduled workflows."),
    ("Settings", "Appearance and assistant preferences."),
]



class ManagerWindow(QWidget):
    """Full-size JARVIS manager with sidebar navigation."""

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("JarvisManager")
        self.setWindowTitle("JARVIS — Manager")
        self.resize(tokens.MANAGER_WIDTH, tokens.MANAGER_HEIGHT)
        self.setMinimumSize(960, 640)

        self._ollama_client: OllamaClient | None = None
        self._assistant_engine: AssistantEngine | None = None
        self._chat_thread: QThread | None = None
        self._chat_worker: ChatWorker | None = None
        self._last_error = ""
        self._voice_thread: QThread | None = None
        self._voice_worker: VoiceWorker | None = None
        self._wake_word_thread: QThread | None = None
        self._wake_word_worker: WakeWordWorker | None = None
        self._close_when_idle = False

        try:
            from jarvis.config import load_config

            ollama = load_config().ollama
            self._ollama_client = OllamaClient(
                base_url=ollama.base_url,
                model=ollama.model,
                timeout=ollama.timeout,
                system_prompt=ollama.system_prompt,
                max_history_turns=ollama.max_history_turns,
            )
            self._assistant_engine = AssistantEngine(
                client=self._ollama_client,
            )
            self._last_error = ""
        except Exception as exc:
            self._last_error = str(exc)

        self._build_ui()

        # Dashboard system metrics refresh
        self._previous_cpu_sample = None

        self._metrics_timer = QTimer(self)
        self._metrics_timer.setInterval(2000)
        self._metrics_timer.timeout.connect(
            self._refresh_system_metrics
        )
        self._metrics_timer.start()

        # Populate the metrics immediately.
        self._refresh_system_metrics()

        if self._ollama_client is None:
            self.status_label.setText("● CONFIGURATION ERROR")
            self.status_label.setToolTip(self._last_error)
        else:
            self.status_label.setText(
                f"● LOCAL MODEL • {self._ollama_client.model}"
            )
            self.status_label.setToolTip(
                "Configured local Ollama model. Connection is checked "
                "when you send a message."
            )

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        sidebar = QFrame()
        sidebar.setObjectName("ManagerSidebar")
        sidebar.setFixedWidth(240)
        sidebar.setStyleSheet(
            f"QFrame#ManagerSidebar {{"
            f"background-color: {tokens.SURFACE};"
            f"border-right: 1px solid {tokens.BORDER};"
            f"}}"
        )

        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(18, 24, 18, 18)
        side_layout.setSpacing(8)

        brand = QLabel("JARVIS")
        brand.setStyleSheet(
            f"color: {tokens.ACCENT}; font-family: "
            f"'{tokens.FONT_MONO}'; font-size: 20px; font-weight: 700;"
        )

        subtitle = QLabel("PERSONAL AI")
        subtitle.setStyleSheet(
            f"color: {tokens.MUTED}; font-size: 10px; letter-spacing: 2px;"
        )

        side_layout.addWidget(brand)
        side_layout.addWidget(subtitle)
        side_layout.addSpacing(18)

        self.navigation = QListWidget()
        self.navigation.setObjectName("ManagerNavigation")
        self.navigation.setAccessibleName("Manager page navigation")
        self.navigation.setSpacing(5)
        self.navigation.setFrameShape(QFrame.Shape.NoFrame)
        self.navigation.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.navigation.setStyleSheet(
            f"""
            QListWidget#ManagerNavigation {{
                background-color: transparent;
                border: none;
                outline: none;
                color: {tokens.MUTED};
                font-size: 13px;
                padding: 4px 0;
            }}

            QListWidget#ManagerNavigation::item {{
                min-height: 40px;
                padding: 0 12px;
                border-radius: 8px;
                border: 1px solid transparent;
            }}

            QListWidget#ManagerNavigation::item:hover {{
                background-color: {tokens.SURFACE_RAISED};
                color: {tokens.TEXT};
            }}

            QListWidget#ManagerNavigation::item:selected {{
                background-color: {tokens.SURFACE_RAISED};
                color: {tokens.ACCENT};
                border: 1px solid {tokens.BORDER};
                font-weight: 600;
            }}
            """
        )

        page_icons = {
            "Dashboard": "◈",
            "Chat": "◉",
            "Voice": "♫",
            "Memory": "◎",
            "Storage": "▤",
            "Tools": "⚒",
            "Automation": "⟳",
            "Settings": "⚙",
        }

        for name, _description in PAGES:
            icon = page_icons.get(name, "•")
            item = QListWidgetItem(f"{icon}    {name}")
            item.setTextAlignment(
                Qt.AlignmentFlag.AlignVCenter
                | Qt.AlignmentFlag.AlignLeft
            )
            self.navigation.addItem(item)
            item.setTextAlignment(
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
            )
            self.navigation.addItem(item)

        side_layout.addWidget(self.navigation, 1)

        version = QLabel("LOCAL • DEVELOPMENT")
        version.setStyleSheet(
            f"color: {tokens.MUTED}; font-family: "
            f"'{tokens.FONT_MONO}'; font-size: 10px;"
        )
        side_layout.addWidget(version)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(28, 24, 28, 24)
        content_layout.setSpacing(20)

        header = QHBoxLayout()

        self.page_title = QLabel("Dashboard")
        self.page_title.setStyleSheet(
            f"color: {tokens.TEXT}; font-size: 24px; font-weight: 700;"
        )

        self.status_label = QLabel("● STARTING")
        self.status_label.setStyleSheet(
            f"color: {tokens.WARNING}; font-family: "
            f"'{tokens.FONT_MONO}'; font-size: 11px;"
        )

        header.addWidget(self.page_title)
        header.addStretch()
        header.addWidget(self.status_label)

        self.pages = QStackedWidget()

        for name, description in PAGES:
            page = QWidget()
            page_layout = QVBoxLayout(page)
            page_layout.setContentsMargins(0, 12, 0, 0)
            page_layout.setSpacing(16)


            if name == "Dashboard":
                self._build_dashboard_page(page, page_layout)
            elif name == "Chat":
                self._build_chat_page(page, page_layout)

            elif name == "Voice":
                self.voice_page = VoicePage()
                self.voice_page.start_requested.connect(
                    self._start_voice_listening
                )
                self.voice_page.stop_requested.connect(
                    self._stop_voice_listening
                )
                page_layout.addWidget(self.voice_page, 1)

            elif name == "Memory":
                self.memory_page = MemoryPage()
                page_layout.addWidget(self.memory_page, 1)
            elif name == "Storage":
                self.storage_page = StoragePage()
                page_layout.addWidget(self.storage_page, 1)
            elif name == "Tools":

                self.tools_page = ToolsPage()
                page_layout.addWidget(self.tools_page, 1)
            elif name == "Settings":
                self.settings_page = SettingsPage()
                self.settings_page.settings_saved.connect(
                    self._reload_ollama_client
                )
                page_layout.addWidget(self.settings_page, 1)
            else:
                heading = QLabel(name)
                heading.setStyleSheet(
                    f"color: {tokens.ACCENT}; font-size: 18px; "
                    "font-weight: 600;"
                )

                details = QLabel(description)
                details.setWordWrap(True)
                details.setStyleSheet(
                    f"color: {tokens.MUTED}; font-size: 13px;"
                )

                card = QFrame()
                card.setObjectName("ManagerCard")
                card.setStyleSheet(
                    f"QFrame#ManagerCard {{"
                    f"background-color: {tokens.SURFACE_RAISED};"
                    f"border: 1px solid {tokens.BORDER};"
                    f"border-radius: 14px;"
                    f"}}"
                )

                card_layout = QVBoxLayout(card)
                card_layout.setContentsMargins(20, 20, 20, 20)
                card_layout.setSpacing(10)
                card_layout.addWidget(heading)
                card_layout.addWidget(details)

                if name == "Dashboard":
                    self.dashboard_status = QLabel(
                        "Assistant: Local model configured\n"
                        "AI engine: Checked when you send a message\n"
                        "Voice: Not connected to this page yet\n"
                        "Desktop tools: Not connected to this page yet"
                    )
                    self.dashboard_status.setWordWrap(True)
                    self.dashboard_status.setStyleSheet(
                        f"color: {tokens.TEXT};"
                    )
                    card_layout.addWidget(self.dashboard_status)

                page_layout.addWidget(card)
                page_layout.addStretch()

            self.pages.addWidget(page)

        content_layout.addLayout(header)
        content_layout.addWidget(self.pages, 1)

        root.addWidget(sidebar)
        root.addWidget(content, 1)

        self.navigation.setCurrentRow(0)
        self.navigation.currentRowChanged.connect(self._change_page)

    def _build_chat_page(
        self,
        page: QWidget,
        page_layout: QVBoxLayout,
    ) -> None:
        intro = QLabel(
            "Chat with your local model. Messages are processed on this "
            "computer through Ollama."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet(f"color: {tokens.MUTED};")
        page_layout.addWidget(intro)

        self.chat_scroll = QScrollArea()
        self.chat_scroll.setWidgetResizable(True)
        self.chat_scroll.setFrameShape(QFrame.Shape.NoFrame)

        self.messages = MessageView()
        self.chat_scroll.setWidget(self.messages)
        page_layout.addWidget(self.chat_scroll, 1)

        input_row = QHBoxLayout()

        self.chat_input = QLineEdit()
        self.chat_input.setPlaceholderText("Ask JARVIS something...")
        self.chat_input.setAccessibleName("Message to JARVIS")
        self.chat_input.returnPressed.connect(self._send_message)

        self.send_button = QPushButton("Send")
        self.send_button.setProperty("primary", True)
        self.send_button.setMinimumHeight(42)
        self.send_button.clicked.connect(self._send_message)

        self.clear_button = QPushButton("Clear conversation")
        self.clear_button.setMinimumHeight(42)
        self.clear_button.clicked.connect(self._clear_conversation)

        input_row.addWidget(self.chat_input, 1)
        input_row.addWidget(self.send_button)
        page_layout.addLayout(input_row)
        page_layout.addWidget(self.clear_button, alignment=Qt.AlignmentFlag.AlignRight)

        self.messages.add_message(
            "assistant",
            "Hello. I'm JARVIS. Your local chat is ready when you are.",
        )

    def _start_voice_listening(self) -> None:
        """Start microphone recording in a background thread."""
        if self._voice_thread is not None:
            return

        thread = QThread(self)
        worker = VoiceWorker()
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.status_changed.connect(self._on_voice_status)
        worker.transcript_ready.connect(
            self.voice_page.set_transcript
        )
        worker.error_occurred.connect(self._on_voice_error)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(self._on_voice_thread_finished)

        self._voice_thread = thread
        self._voice_worker = worker

        self.voice_page.set_listening_controls(True)
        self.voice_page.set_status(
            OrbState.LISTENING,
            "Starting microphone and speech recognition...",
        )

        thread.start()

    def _stop_voice_listening(self) -> None:
        """Request that microphone recording stop."""
        if self._voice_worker is None:
            return

        self.voice_page.set_status(
            OrbState.LISTENING,
            "Stopping microphone recording...",
        )
        self._voice_worker.request_stop()

    def _on_voice_status(self, state: str, detail: str) -> None:
        """Update the voice orb and status text."""
        try:
            orb_state = OrbState(state)
        except ValueError:
            orb_state = OrbState.IDLE

        self.voice_page.set_status(orb_state, detail)

    def _on_voice_thread_finished(self) -> None:
        """Clean up the completed voice worker thread."""
        thread = self._voice_thread

        self._voice_thread = None
        self._voice_worker = None

        self.voice_page.set_listening_controls(False)
        self.voice_page.set_status(
            OrbState.IDLE,
            "Microphone inactive. Start listening when you're ready.",
        )

        if thread is not None:
            thread.deleteLater()

    def _on_voice_error(self, error: str) -> None:
        """Display a voice-processing error."""
        message = error.splitlines()[0] if error else "Unknown voice error"
        self.voice_page.set_status(
            OrbState.IDLE,
            f"Voice error: {message}",
        )
        self.voice_page.set_transcript(f"Voice error: {message}")

    def _send_message(self) -> None:
        message = self.chat_input.text().strip()
        if not message or self._chat_thread is not None:
            return

        if self._ollama_client is None:
            self.messages.add_message(
                "assistant",
                f"JARVIS configuration error: {self._last_error}",
            )
            return

        self.chat_input.clear()
        self.messages.add_message("user", message)
        self.messages.add_message("assistant", "Thinking…")
        self.dashboard_orb.set_state(OrbState.THINKING)
        self._scroll_to_bottom()

        self.chat_input.setEnabled(False)
        self.send_button.setEnabled(False)
        self.clear_button.setEnabled(False)
        self.status_label.setText("● THINKING")

        thread = QThread(self)
        if self._assistant_engine is None:
            self.messages.add_message(
                "assistant",
                "JARVIS assistant engine is not initialized.",
            )
            self.dashboard_orb.set_state(OrbState.IDLE)
            self.chat_input.setEnabled(True)
            self.send_button.setEnabled(True)
            self.clear_button.setEnabled(True)
            return

        worker = ChatWorker(self._assistant_engine, message)
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.succeeded.connect(self._on_chat_success)
        worker.failed.connect(self._on_chat_failure)
        worker.finished.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(self._on_chat_thread_finished)

        self._chat_thread = thread
        self._chat_worker = worker
        thread.start()


    def _replace_thinking_message(self, text: str) -> None:
        # Replace only the latest placeholder; keep earlier conversation intact.
        layout = self.messages.layout()
        for index in range(layout.count() - 1, -1, -1):
            widget = layout.itemAt(index).widget()
            if isinstance(widget, QLabel) and widget.text() == "Thinking…":
                widget.setText(text)
                return

        self.messages.add_message("assistant", text)

        self.dashboard_orb.set_state(OrbState.IDLE)

    def _on_chat_success(self, reply: str) -> None:
        self.dashboard_orb.set_state(OrbState.IDLE)
        self._replace_thinking_message(reply)
        self.status_label.setText("● CONNECTED")
        self.dashboard_status.setText(
            "Assistant: Ready\n"
            f"AI engine: {self._ollama_client.model}\n"
            "Voice: Available on the Voice page\n"
            "Desktop tools: Available on the Tools page"
        )
        self._scroll_to_bottom()

    def _on_chat_failure(self, error: str) -> None:
        self.dashboard_orb.set_state(OrbState.IDLE)
        self._replace_thinking_message(f"JARVIS error: {error}")
        self.status_label.setText("● OFFLINE / ERROR")
        self._scroll_to_bottom()

    def _on_chat_thread_finished(self) -> None:
        thread = self._chat_thread
        self._chat_thread = None
        self._chat_worker = None

        self.chat_input.setEnabled(True)
        self.send_button.setEnabled(True)
        self.clear_button.setEnabled(True)

        if thread is not None:
            thread.deleteLater()

        self.chat_input.setFocus()

    def _scroll_to_bottom(self) -> None:
        QTimer.singleShot(
            0,
            lambda: self.chat_scroll.verticalScrollBar().setValue(
                self.chat_scroll.verticalScrollBar().maximum()
            ),
        )

    def _clear_conversation(self) -> None:
        if self._chat_thread is not None:
            return

        if self._ollama_client is not None:
            self._ollama_client.reset_conversation()

        self.messages.clear_messages()
        self.messages.add_message(
            "assistant",
            "Conversation cleared. What would you like to discuss?",
        )
        self.status_label.setText("● READY")
        self._scroll_to_bottom()

    def _reload_ollama_client(self) -> None:
        """Apply saved Ollama settings when no request is running."""
        if self._chat_thread is not None:
            self.status_label.setText(
                "● SETTINGS SAVED • APPLY AFTER CURRENT CHAT"
            )
            return

        try:
            from jarvis.config import load_config

            ollama = load_config().ollama
            self._ollama_client = OllamaClient(
                base_url=ollama.base_url,
                model=ollama.model,
                timeout=ollama.timeout,
                system_prompt=ollama.system_prompt,
                max_history_turns=ollama.max_history_turns,
            )
            if self._assistant_engine is None:
                self._assistant_engine = AssistantEngine(
                    client=self._ollama_client,
                )
            else:
                self._assistant_engine.client = self._ollama_client
            self._last_error = ""
            self.status_label.setText(
                f"● LOCAL MODEL • {self._ollama_client.model}"
            )
            self.status_label.setToolTip(
                "Updated from the saved local Ollama configuration."
            )
            self.dashboard_status.setText(
                "Assistant: Ready\n"
                f"AI engine: {self._ollama_client.model}\n"
                "Voice: Available on the Voice page\n"
                "Desktop tools: Available on the Tools page"
            )
        except Exception as exc:
            self._last_error = str(exc)
            self.status_label.setText("● CONFIGURATION ERROR")
            self.status_label.setToolTip(self._last_error)

    def _change_page(self, index: int) -> None:
        if not 0 <= index < len(PAGES):
            return

        self.page_title.setText(PAGES[index][0])
        self.pages.setCurrentIndex(index)





    def _build_dashboard_page(
        self,
        page: QWidget,
        page_layout: QVBoxLayout,
    ) -> None:
        """Build a dashboard with separate, reusable visual cards."""
        page_layout.setSpacing(16)

        card_style = (
            f"background-color: {tokens.SURFACE_RAISED};"
            f"border: 1px solid {tokens.BORDER};"
            "border-radius: 14px;"
        )

        label_style = (
            f"color: {tokens.ACCENT};"
            f"font-family: '{tokens.FONT_MONO}';"
            "font-size: 11px;"
            "font-weight: 700;"
            "background-color: transparent;"
            "border: none;"
        )

        def make_card(object_name: str) -> tuple[QFrame, QVBoxLayout]:
            card = QFrame()
            card.setObjectName(object_name)
            card.setStyleSheet(
                f"QFrame#{object_name} {{{card_style}}}"
            )

            layout = QVBoxLayout(card)
            layout.setContentsMargins(16, 14, 16, 14)
            layout.setSpacing(10)
            return card, layout

        def make_heading(text: str) -> QLabel:
            label = QLabel(text)
            label.setStyleSheet(label_style)
            return label

        # Dashboard heading
        heading = QLabel("NEURAL INTERFACE")
        heading.setStyleSheet(
            f"color: {tokens.TEXT}; font-size: 22px; font-weight: 700;"
        )

        description = QLabel(
            "Your local AI command center. Ready when you are."
        )
        description.setWordWrap(True)
        description.setStyleSheet(
            f"color: {tokens.MUTED}; font-size: 12px;"
        )

        page_layout.addWidget(heading)
        page_layout.addWidget(description)

        # Four independent system metric cards
        metrics_grid = QGridLayout()
        metrics_grid.setSpacing(12)

        metric_definitions = (
            ("CPU USAGE", "dashboard_cpu", "Measuring…"),
            ("MEMORY", "dashboard_ram", "Reading…"),
            ("DISK STORAGE", "dashboard_disk", "Reading…"),
            ("SWAP MEMORY", "dashboard_swap", "Reading…"),
        )

        for index, (title, attribute, initial_value) in enumerate(
            metric_definitions
        ):
            card, layout = make_card(f"DashboardMetric{index}")

            layout.addWidget(make_heading(title))

            value_label = QLabel(initial_value)
            value_label.setWordWrap(True)
            value_label.setMinimumHeight(36)
            value_label.setStyleSheet(
                f"color: {tokens.TEXT};"
                "font-size: 17px;"
                "font-weight: 600;"
                "background-color: transparent;"
                "border: none;"
            )

            layout.addWidget(value_label)
            setattr(self, attribute, value_label)

            metrics_grid.addWidget(card, index // 2, index % 2)

        page_layout.addLayout(metrics_grid)

        # Main row: neural interface and independent status/actions cards
        main_row = QHBoxLayout()
        main_row.setSpacing(14)

        # Neural interface card
        neural_card, neural_layout = make_card(
            "DashboardNeuralCard"
        )
        neural_layout.setContentsMargins(18, 18, 18, 18)

        neural_title = QLabel("J.A.R.V.I.S.")
        neural_title.setStyleSheet(
            f"color: {tokens.TEXT}; font-size: 20px; font-weight: 700;"
            "background-color: transparent; border: none;"
        )

        neural_layout.addWidget(neural_title)
        neural_layout.addWidget(make_heading("PERSONAL AI SYSTEM"))

        from jarvis.gui.components.orb import Orb

        self.dashboard_orb = Orb()
        self.dashboard_orb.setMinimumSize(180, 180)
        self.dashboard_orb.setMaximumSize(280, 280)
        self.dashboard_orb.set_state(OrbState.IDLE)
        self.dashboard_orb.setToolTip(
            "JARVIS visual interface. Voice-state integration "
            "will be connected separately."
        )

        neural_layout.addWidget(
            self.dashboard_orb,
            1,
            Qt.AlignmentFlag.AlignCenter,
        )

        welcome = QLabel("How can I help you today?")
        welcome.setAlignment(Qt.AlignmentFlag.AlignCenter)
        welcome.setWordWrap(True)
        welcome.setStyleSheet(
            f"color: {tokens.TEXT}; font-size: 15px; font-weight: 600;"
            "background-color: transparent; border: none;"
        )

        neural_hint = QLabel(
            "Start a conversation or open the Voice page."
        )
        neural_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        neural_hint.setWordWrap(True)
        neural_hint.setStyleSheet(
            f"color: {tokens.MUTED}; font-size: 11px;"
            "background-color: transparent; border: none;"
        )

        neural_layout.addWidget(welcome)
        neural_layout.addWidget(neural_hint)

        # Right column contains separate status and action cards
        right_column = QVBoxLayout()
        right_column.setSpacing(14)

        status_card, status_layout = make_card(
            "DashboardStatusCard"
        )
        status_layout.addWidget(make_heading("SYSTEM STATUS"))

        self.dashboard_status = QLabel()
        self.dashboard_status.setWordWrap(True)
        self.dashboard_status.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.dashboard_status.setStyleSheet(
            f"color: {tokens.TEXT}; font-size: 12px;"
            "background-color: transparent; border: none;"
        )

        if self._ollama_client is not None:
            self.dashboard_status.setText(
                "Assistant: Configured\n"
                f"AI model: {self._ollama_client.model}\n"
                "AI connection: Not yet verified\n"
                "Voice: Manage on the Voice page\n"
                "Tools: Inspect on the Tools page"
            )
        else:
            self.dashboard_status.setText(
                "Assistant: Configuration needs attention\n"
                f"Details: {self._last_error}"
            )

        status_layout.addWidget(self.dashboard_status)
        status_layout.addStretch()

        actions_card, actions_layout = make_card(
            "DashboardActionsCard"
        )
        actions_layout.addWidget(make_heading("QUICK ACTIONS"))

        for target, caption in (
            ("Chat", "Open Chat"),
            ("Voice", "Open Voice"),
            ("Tools", "Open Tools"),
            ("Settings", "Open Settings"),
        ):
            button = QPushButton(caption)
            button.setMinimumHeight(38)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setToolTip(f"Navigate to the {target} page")

            button.clicked.connect(
                lambda _checked=False, name=target:
                self.navigation.setCurrentRow(
                    next(
                        i
                        for i, (page_name, _description) in enumerate(PAGES)
                        if page_name == name
                    )
                )
            )

            actions_layout.addWidget(button)

        right_column.addWidget(status_card, 1)
        right_column.addWidget(actions_card)

        main_row.addWidget(neural_card, 3)
        main_row.addLayout(right_column, 2)

        page_layout.addLayout(main_row, 1)

        # Independent system information card
        info_card, info_layout = make_card(
            "DashboardInfoCard"
        )
        info_layout.addWidget(make_heading("SYSTEM INFORMATION"))

        self.dashboard_system_info = QLabel(
            "Loading system information…"
        )
        self.dashboard_system_info.setWordWrap(True)
        self.dashboard_system_info.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.dashboard_system_info.setStyleSheet(
            f"color: {tokens.TEXT}; font-size: 12px;"
            "background-color: transparent; border: none;"
        )

        info_layout.addWidget(self.dashboard_system_info)
        page_layout.addWidget(info_card)

        system_info = get_system_info()
        self.dashboard_system_info.setText(
            f"Distribution: {system_info.get('distribution', 'Unknown')}\n"
            f"Kernel: {system_info.get('kernel', 'Unknown')}\n"
            f"Architecture: {system_info.get('architecture', 'Unknown')}\n"
            f"Logical CPU cores: {system_info.get('logical_cpus', 'Unknown')}\n"
            f"Hostname: {system_info.get('hostname', 'Unknown')}\n"
            f"System uptime: {system_info.get('uptime', 'Unknown')}"
        )





    def _refresh_system_metrics(self) -> None:
        """Refresh the dashboard's CPU, memory, disk, and swap readings."""
        try:
            cpu_usage, self._previous_cpu_sample = get_cpu_usage(
                self._previous_cpu_sample
            )

            if cpu_usage is None:
                self.dashboard_cpu.setText("Measuring…")
            else:
                self.dashboard_cpu.setText(f"{cpu_usage:.1f}%")

            used, total, percentage = get_memory_usage()
            self.dashboard_ram.setText(
                f"{percentage:.1f}%\n"
                f"{used:,} / {total:,} MiB"
            )

            disk_used, disk_total, disk_free, disk_percent = (
                get_disk_usage()
            )
            self.dashboard_disk.setText(
                f"{disk_percent:.1f}%\n"
                f"{disk_free} GiB available"
            )

            swap_used, swap_total, swap_percent = get_swap_usage()
            self.dashboard_swap.setText(
                f"{swap_percent:.1f}%\n"
                f"{swap_used:,} / {swap_total:,} MiB"
            )

        except (OSError, ValueError, RuntimeError) as exc:
            self.dashboard_cpu.setText("Unavailable")
            self.dashboard_ram.setText("Unavailable")
            self.dashboard_disk.setText("Unavailable")
            self.dashboard_swap.setText("Unavailable")



def main() -> int:
    app = QApplication(sys.argv)
    apply_theme(app)

    window = ManagerWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())