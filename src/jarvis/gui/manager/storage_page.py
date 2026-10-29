
"""Storage page showing mounted filesystem capacity."""

from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

from jarvis.gui.theme import tokens
from jarvis.system_metrics import get_mounted_storage


class StoragePage(QWidget):
    """Display capacity and usage for mounted filesystems."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        root = QVBoxLayout(self)
        root.setSpacing(16)

        intro = QLabel(
            "View disk capacity, used space, and available space for "
            "mounted filesystems. These readings do not modify your disks."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet(f"color: {tokens.MUTED};")
        root.addWidget(intro)

        header = QHBoxLayout()

        title = QLabel("Mounted storage")
        title.setStyleSheet(
            f"color: {tokens.ACCENT}; font-size: 18px; font-weight: 600;"
        )

        refresh_button = QPushButton("Refresh")
        refresh_button.clicked.connect(self.refresh_storage)

        header.addWidget(title)
        header.addStretch()
        header.addWidget(refresh_button)
        root.addLayout(header)

        self.storage_layout = QVBoxLayout()
        self.storage_layout.setSpacing(12)
        root.addLayout(self.storage_layout, 1)

        self.result_label = QLabel("")
        self.result_label.setWordWrap(True)
        self.result_label.setStyleSheet(f"color: {tokens.MUTED};")
        root.addWidget(self.result_label)

        self.refresh_storage()

    def refresh_storage(self) -> None:
        """Refresh mounted filesystem capacity information."""
        while self.storage_layout.count():
            item = self.storage_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        try:
            filesystems = get_mounted_storage()
        except (OSError, ValueError, RuntimeError) as exc:
            self.result_label.setText(
                f"Could not read mounted storage: {exc}"
            )
            return

        if not filesystems:
            self.result_label.setText(
                "No supported mounted filesystems were found."
            )
            return

        self.result_label.setText(
            f"Found {len(filesystems)} mounted filesystem(s)."
        )

        for filesystem in filesystems:
            card = QFrame()
            card.setObjectName("ManagerCard")

            layout = QVBoxLayout(card)
            layout.setContentsMargins(20, 16, 20, 16)
            layout.setSpacing(10)

            mountpoint = filesystem["mountpoint"]
            device = filesystem["device"]
            used = filesystem["used_gib"]
            total = filesystem["total_gib"]
            free = filesystem["free_gib"]
            percent = filesystem["percent"]
            filesystem_type = filesystem["filesystem"]

            heading = QLabel(mountpoint)
            heading.setStyleSheet(
                f"color: {tokens.ACCENT}; font-size: 18px; "
                "font-weight: 600;"
            )

            details = QLabel(
                f"Device: {device}\n"
                f"Filesystem: {filesystem_type}\n"
                f"Used: {used:.1f} GiB of {total:.1f} GiB\n"
                f"Available: {free:.1f} GiB"
            )
            details.setWordWrap(True)
            details.setTextInteractionFlags(
                details.textInteractionFlags()
                | details.textInteractionFlags().TextSelectableByMouse
            )
            details.setStyleSheet(f"color: {tokens.TEXT};")

            progress = QProgressBar()
            progress.setRange(0, 100)
            progress.setValue(max(0, min(100, round(percent))))
            progress.setFormat(f"{percent:.1f}% used")
            progress.setAccessibleName(
                f"Storage usage for {mountpoint}"
            )

            layout.addWidget(heading)
            layout.addWidget(details)
            layout.addWidget(progress)
            self.storage_layout.addWidget(card)

        self.storage_layout.addStretch()
