
"""Storage page showing physical disks and mounted filesystem capacity."""

import subprocess

from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QProgressBar,
    QScrollArea,
    QVBoxLayout,
    QWidget,
    QGridLayout,
)

from jarvis.gui.theme import tokens
from jarvis.system_metrics import (
    get_mounted_storage,
    get_physical_disks,
)


class StoragePage(QWidget):
    """Display physical disks and mounted filesystem capacity."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        root = QVBoxLayout(self)
        root.setSpacing(12)

        header = QHBoxLayout()

        title = QLabel("Storage")
        title.setStyleSheet(
            f"color: {tokens.ACCENT}; font-size: 18px; font-weight: 600;"
        )

        refresh_button = QPushButton("Refresh")
        refresh_button.clicked.connect(self.refresh_storage)

        header.addWidget(title)
        header.addStretch()
        header.addWidget(refresh_button)
        root.addLayout(header)

        intro = QLabel(
            "View physical disks, partitions, and mounted filesystem "
            "capacity. This page only reads disk information and does "
            "not modify your disks."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet(f"color: {tokens.MUTED};")
        root.addWidget(intro)

        # Scrollable content keeps disk and partition details accessible.
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        self.content_layout = QVBoxLayout(content)
        self.content_layout.setContentsMargins(4, 4, 4, 4)
        self.content_layout.setSpacing(16)

        physical_title = QLabel("Physical disks")
        physical_title.setStyleSheet(
            f"color: {tokens.ACCENT}; font-size: 18px; font-weight: 600;"
        )
        self.content_layout.addWidget(physical_title)

        self.disk_layout = QGridLayout()
        self.disk_layout.setSpacing(14)
        self.disk_layout.setColumnStretch(0, 1)
        self.disk_layout.setColumnStretch(1, 1)
        self.disk_layout.setSpacing(12)
        self.content_layout.addLayout(self.disk_layout)

        mounted_title = QLabel("Mounted storage")
        mounted_title.setStyleSheet(
            f"color: {tokens.ACCENT}; font-size: 18px; font-weight: 600;"
        )
        self.content_layout.addWidget(mounted_title)

        self.storage_layout = QVBoxLayout()
        self.storage_layout.setSpacing(12)
        self.content_layout.addLayout(self.storage_layout)

        self.result_label = QLabel("")
        self.result_label.setWordWrap(True)
        self.result_label.setStyleSheet(f"color: {tokens.MUTED};")
        self.content_layout.addWidget(self.result_label)

        self.content_layout.addStretch()

        self.scroll_area.setWidget(content)
        root.addWidget(self.scroll_area, 1)

        self.refresh_storage()

    @staticmethod
    def _clear_layout(layout: QVBoxLayout) -> None:
        """Remove existing widgets and nested layouts."""
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()

            if widget is not None:
                widget.deleteLater()
            elif item.layout() is not None:
                StoragePage._clear_layout(item.layout())

    def refresh_storage(self) -> None:
        """Refresh physical disks and mounted filesystem information."""

        self._clear_layout(self.disk_layout)
        self._clear_layout(self.storage_layout)

        # Physical disks and their partitions.
        try:
            disks = get_physical_disks()
        except (
            OSError,
            ValueError,
            RuntimeError,
            subprocess.SubprocessError,
        ) as exc:
            error = QLabel(f"Could not read physical disks: {exc}")
            error.setWordWrap(True)
            error.setStyleSheet(f"color: {tokens.MUTED};")
            self.disk_layout.addWidget(error)
        else:
            if not disks:
                empty = QLabel("No physical disks were detected.")
                empty.setStyleSheet(f"color: {tokens.MUTED};")
                self.disk_layout.addWidget(empty)

            for disk in disks:
                card = QFrame()
                card.setObjectName("ManagerCard")
                card.setStyleSheet(
                    f"""
                    QFrame#ManagerCard {{
                        background-color: {tokens.SURFACE};
                        border: 1px solid {tokens.BORDER};
                        border-radius: 12px;
                    }}
                    """
                )

                layout = QVBoxLayout(card)
                layout.setContentsMargins(20, 16, 20, 16)
                layout.setSpacing(8)

                heading = QLabel(
                    f"{disk['path']} — {disk['size_gib']:.1f} GiB"
                )
                heading.setStyleSheet(
                    f"color: {tokens.ACCENT}; font-size: 16px; "
                    "font-weight: 600;"
                )

                details = QLabel(
                    f"Model: {disk['model']}\n"
                    f"Transport: {disk['transport']}"
                )
                details.setWordWrap(True)
                details.setStyleSheet(f"color: {tokens.TEXT};")

                layout.addWidget(heading)
                layout.addWidget(details)

                for partition in disk["partitions"]:
                    mounts = (
                        ", ".join(partition["mountpoints"])
                        or "Not mounted"
                    )

                    partition_card = QFrame()
                    partition_card.setObjectName("PartitionCard")
                    partition_card.setStyleSheet(
                        f"""
                        QFrame#PartitionCard {{
                            background-color: {tokens.SURFACE_RAISED};
                            border: 1px solid {tokens.BORDER};
                            border-radius: 8px;
                        }}
                        """
                    )

                    partition_layout = QVBoxLayout(partition_card)
                    partition_layout.setContentsMargins(12, 10, 12, 10)
                    partition_layout.setSpacing(4)

                    partition_heading = QLabel(
                        f"{partition['name']}  ·  "
                        f"{partition['size_gib']:.1f} GiB"
                    )
                    partition_heading.setStyleSheet(
                        f"color: {tokens.TEXT}; font-weight: 600; "
                        "background: transparent; border: none;"
                    )

                    partition_details = QLabel(
                        f"Filesystem: {partition['filesystem']}\n"
                        f"Mount: {mounts}"
                    )
                    partition_details.setWordWrap(True)
                    partition_details.setStyleSheet(
                        f"color: {tokens.MUTED}; "
                        "background: transparent; border: none;"
                    )

                    partition_layout.addWidget(partition_heading)
                    partition_layout.addWidget(partition_details)
                    layout.addWidget(partition_card)

                index = disks.index(disk)
                row, column = divmod(index, 2)
                self.disk_layout.addWidget(card, row, column)

        # Mounted filesystem capacity.
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
            card.setStyleSheet(
                f"""
                QFrame#ManagerCard {{
                    background-color: {tokens.SURFACE};
                    border: 1px solid {tokens.BORDER};
                    border-radius: 12px;
                }}
                """
            )

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
