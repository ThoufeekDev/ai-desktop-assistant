"""Memory management page backed by JARVIS's existing SQLite store."""

from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from jarvis.memory import MemoryStore
from jarvis.gui.theme import tokens
from PySide6.QtCore import Qt

class MemoryPage(QWidget):
    """View, search, save, edit, and delete saved memories."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.store = MemoryStore()
        self._memories = []

        root = QVBoxLayout(self)
        root.setSpacing(12)

        intro = QLabel(
            "Manage facts JARVIS may use to personalize future answers. "
            "Changes apply to your existing local memory database."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet(f"color: {tokens.MUTED};")
        root.addWidget(intro)

        search_row = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search saved memories...")
        self.search_input.setAccessibleName("Search saved memories")
        self.search_input.returnPressed.connect(self.refresh)

        search_button = QPushButton("Search")
        search_button.clicked.connect(self.refresh)

        show_all_button = QPushButton("Show all")
        show_all_button.clicked.connect(self._show_all)

        search_row.addWidget(self.search_input, 1)
        search_row.addWidget(search_button)
        search_row.addWidget(show_all_button)
        root.addLayout(search_row)

        self.memory_table = QTableWidget(0, 3)
        self.memory_table.setObjectName("MemoryTable")
        self.memory_table.setAccessibleName("Saved memories")
        self.memory_table.setHorizontalHeaderLabels(
            ["ID", "Memory", "Saved"]
        )
        self.memory_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.memory_table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.memory_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.memory_table.setAlternatingRowColors(True)
        self.memory_table.setShowGrid(False)
        self.memory_table.verticalHeader().setVisible(False)
        self.memory_table.verticalHeader().setDefaultSectionSize(54)

        header = self.memory_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)

        self.memory_table.setStyleSheet(
            f"""
            QTableWidget#MemoryTable {{
                background-color: {tokens.SURFACE};
                alternate-background-color: {tokens.SURFACE_RAISED};
                color: {tokens.TEXT};
                border: 1px solid {tokens.BORDER};
                border-radius: 10px;
                padding: 6px;
                selection-background-color: {tokens.SURFACE_RAISED};
                selection-color: {tokens.ACCENT};
            }}

            QTableWidget#MemoryTable::item {{
                padding: 10px 8px;
                border: none;
                border-bottom: 1px solid {tokens.BORDER};
            }}

            QTableWidget#MemoryTable::item:hover {{
                background-color: {tokens.SURFACE_RAISED};
            }}

            QHeaderView::section {{
                background-color: {tokens.SURFACE_RAISED};
                color: {tokens.MUTED};
                padding: 12px 8px;
                border: none;
                border-bottom: 1px solid {tokens.BORDER};
                font-weight: 600;
            }}
            """
        )

        self.memory_table.itemDoubleClicked.connect(self._edit_selected)
        root.addWidget(self.memory_table, 1)

        self.status = QLabel("")
        self.status.setWordWrap(True)
        self.status.setStyleSheet(f"color: {tokens.MUTED};")
        root.addWidget(self.status)

        actions = QHBoxLayout()

        self.add_button = QPushButton("Add memory")
        self.add_button.setProperty("primary", True)
        self.add_button.clicked.connect(self._add_memory)

        self.edit_button = QPushButton("Edit selected")
        self.edit_button.clicked.connect(self._edit_selected)

        self.delete_button = QPushButton("Delete selected")
        self.delete_button.setProperty("danger", True)
        self.delete_button.clicked.connect(self._delete_selected)

        actions.addWidget(self.add_button)
        actions.addStretch()
        actions.addWidget(self.edit_button)
        actions.addWidget(self.delete_button)
        root.addLayout(actions)

        self.refresh()

    def refresh(self) -> None:
        """Reload all memories or show search matches."""
        query = self.search_input.text().strip()
        try:
            if query:
                self._memories = self.store.search(query, limit=100)
            else:
                self._memories = self.store.list_all()

            self.memory_table.setRowCount(len(self._memories))

            for row, memory in enumerate(self._memories):
                id_item = QTableWidgetItem(f"#{memory.id}")
                id_item.setData(256, memory.id)
                id_item.setTextAlignment(
                    Qt.AlignmentFlag.AlignCenter
                )

                content_item = QTableWidgetItem(memory.content)
                content_item.setToolTip(memory.content)

                saved_item = QTableWidgetItem(str(memory.created_at))
                saved_item.setToolTip(str(memory.created_at))

                self.memory_table.setItem(row, 0, id_item)
                self.memory_table.setItem(row, 1, content_item)
                self.memory_table.setItem(row, 2, saved_item)

            for memory in self._memories:
                item = QListWidgetItem(
                    f"#{memory.id}  {memory.content}\n"
                    f"Saved: {memory.created_at}"
                )
                item.setData(256, memory.id)
                item.setToolTip(memory.content)
                self.memory_list.addItem(item)

            self.status.setText(
                f"{len(self._memories)} memory item(s) shown."
            )
        except Exception as exc:
            self.status.setText(f"Could not load memories: {exc}")

    def _show_all(self) -> None:
        self.search_input.clear()
        self.refresh()

    def _selected_memory(self):
        row = self.memory_table.currentRow()

        if row < 0:
            QMessageBox.information(
                self,
                "Select a memory",
                "Please select a memory first.",
            )
            return None

        item = self.memory_table.item(row, 0)
        if item is None:
            return None

        memory_id = item.data(256)

        return next(
            (
                memory
                for memory in self._memories
                if memory.id == memory_id
            ),
            None,
        )

    def _memory_dialog(self, title: str, initial: str = "") -> str | None:
        dialog = QDialog(self)
        dialog.setWindowTitle(title)

        layout = QVBoxLayout(dialog)
        form = QFormLayout()

        editor = QLineEdit()
        editor.setText(initial)
        editor.setPlaceholderText("Enter a fact you want JARVIS to remember")
        form.addRow("Memory", editor)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None

        content = editor.text().strip()
        if not content:
            QMessageBox.warning(
                self,
                "Empty memory",
                "Memory content cannot be empty.",
            )
            return None

        return content

    def _add_memory(self) -> None:
        content = self._memory_dialog("Add memory")
        if content is None:
            return

        try:
            memory = self.store.save(content)
            self.search_input.clear()
            self.refresh()
            self.status.setText(f"Saved memory #{memory.id}.")
        except Exception as exc:
            QMessageBox.critical(self, "Save failed", str(exc))

    def _edit_selected(self, *_args) -> None:
        memory = self._selected_memory()
        if memory is None:
            return

        content = self._memory_dialog("Edit memory", memory.content)
        if content is None:
            return

        try:
            updated = self.store.update(memory.id, content)
            self.refresh()
            if updated is None:
                self.status.setText(
                    f"Memory #{memory.id} no longer exists."
                )
            else:
                self.status.setText(f"Updated memory #{memory.id}.")
        except Exception as exc:
            QMessageBox.critical(self, "Update failed", str(exc))

    def _delete_selected(self) -> None:
        memory = self._selected_memory()
        if memory is None:
            return

        answer = QMessageBox.question(
            self,
            "Delete memory?",
            f"Delete memory #{memory.id}?\n\n{memory.content}",
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        try:
            deleted = self.store.delete(memory.id)
            self.refresh()
            self.status.setText(
                f"Deleted memory #{memory.id}."
                if deleted
                else f"Memory #{memory.id} no longer exists."
            )
        except Exception as exc:
            QMessageBox.critical(self, "Delete failed", str(exc))
