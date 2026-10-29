"""Desktop tools page using JARVIS's existing LinuxControl methods."""

from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from jarvis.gui.theme import tokens
from jarvis.linux_control import LinuxControl


class ToolsPage(QWidget):
    """Display Niri desktop state and provide a guarded app launcher."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.control = LinuxControl()

        root = QVBoxLayout(self)
        root.setSpacing(16)

        intro = QLabel(
            "Inspect your Niri desktop and launch installed applications. "
            "Launching an application changes your desktop and requires "
            "confirmation."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet(f"color: {tokens.MUTED};")
        root.addWidget(intro)

        status_card = QFrame()
        status_card.setObjectName("ManagerCard")
        status_layout = QVBoxLayout(status_card)
        status_layout.setContentsMargins(20, 18, 20, 18)
        status_layout.setSpacing(10)

        title = QLabel("Desktop status")
        title.setStyleSheet(
            f"color: {tokens.ACCENT}; font-size: 18px; font-weight: 600;"
        )
        status_layout.addWidget(title)

        self.workspace_label = QLabel("Workspace: not checked")
        self.monitor_label = QLabel("Monitor: not checked")
        self.workspace_label.setStyleSheet(f"color: {tokens.TEXT};")
        self.monitor_label.setStyleSheet(f"color: {tokens.TEXT};")
        status_layout.addWidget(self.workspace_label)
        status_layout.addWidget(self.monitor_label)

        refresh_status = QPushButton("Refresh desktop status")
        refresh_status.clicked.connect(self.refresh_status)
        status_layout.addWidget(refresh_status)
        root.addWidget(status_card)

        windows_card = QFrame()
        windows_card.setObjectName("ManagerCard")
        windows_layout = QVBoxLayout(windows_card)
        windows_layout.setContentsMargins(20, 18, 20, 18)
        windows_layout.setSpacing(10)

        windows_title_row = QHBoxLayout()
        windows_title = QLabel("Open windows")
        windows_title.setStyleSheet(
            f"color: {tokens.ACCENT}; font-size: 18px; font-weight: 600;"
        )

        refresh_windows = QPushButton("Refresh")
        refresh_windows.clicked.connect(self.refresh_windows)
        windows_title_row.addWidget(windows_title)
        windows_title_row.addStretch()
        windows_title_row.addWidget(refresh_windows)
        windows_layout.addLayout(windows_title_row)

        self.window_list = QListWidget()
        self.window_list.setAccessibleName("Open desktop windows")
        windows_layout.addWidget(self.window_list, 1)
        root.addWidget(windows_card, 1)

        launcher_card = QFrame()
        launcher_card.setObjectName("ManagerCard")
        launcher_layout = QVBoxLayout(launcher_card)
        launcher_layout.setContentsMargins(20, 18, 20, 18)
        launcher_layout.setSpacing(10)

        launcher_title = QLabel("Application launcher")
        launcher_title.setStyleSheet(
            f"color: {tokens.ACCENT}; font-size: 18px; font-weight: 600;"
        )
        launcher_layout.addWidget(launcher_title)

        launch_button = QPushButton("Choose application to open")
        launch_button.setProperty("primary", True)
        launch_button.clicked.connect(self.launch_application)
        launcher_layout.addWidget(launch_button)
        root.addWidget(launcher_card)

        self.result_label = QLabel("")
        self.result_label.setWordWrap(True)
        self.result_label.setStyleSheet(f"color: {tokens.MUTED};")
        root.addWidget(self.result_label)

        self.refresh_status()
        self.refresh_windows()

    def refresh_status(self) -> None:
        """Refresh the focused workspace and output information."""
        try:
            workspace = self.control.get_current_workspace()
            if workspace is None:
                self.workspace_label.setText(
                    "Workspace: unavailable (Niri did not report one)"
                )
                self.monitor_label.setText("Monitor: unavailable")
                return

            index = workspace.get("idx", "unknown")
            name = workspace.get("name")
            output = workspace.get("output", "unknown")

            workspace_text = f"Workspace: {index}"
            if name:
                workspace_text += f" — {name}"

            self.workspace_label.setText(workspace_text)
            self.monitor_label.setText(f"Monitor: {output}")
        except Exception as exc:
            self.workspace_label.setText("Workspace: error")
            self.monitor_label.setText(f"Could not read desktop status: {exc}")

    def refresh_windows(self) -> None:
        """Refresh the read-only list of Niri windows."""
        self.window_list.clear()

        try:
            windows = self.control.list_windows()
            for window in windows:
                title = window.get("title") or "(untitled window)"
                app_id = window.get("app_id") or "unknown application"
                window_id = window.get("id", "?")
                self.window_list.addItem(
                    f"{title}\n{app_id} • Window ID {window_id}"
                )

            if not windows:
                self.window_list.addItem(
                    "No windows reported, or Niri information is unavailable."
                )
        except Exception as exc:
            self.window_list.addItem(f"Could not read windows: {exc}")

    def launch_application(self) -> None:
        """Ask for an application and confirm before launching it."""
        app_name, accepted = QInputDialog.getText(
            self,
            "Open application",
            "Enter the installed application name:",
        )
        app_name = app_name.strip()

        if not accepted or not app_name:
            return

        answer = QMessageBox.question(
            self,
            "Confirm launch",
            f"Allow JARVIS to open '{app_name}' on the current desktop?",
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            self.result_label.setText("Launch cancelled. Nothing was opened.")
            return

        try:
            result = self.control.open_app(app_name, destination="cursor")
            self.result_label.setText(result)
            self.refresh_windows()
        except Exception as exc:
            self.result_label.setText(f"Could not launch application: {exc}")
