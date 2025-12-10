"""
Reusable activity list panel built on QListWidget.
- Displays provider activities with a clean summary string.
- Stores activity identifier in UserRole for retrieval.
"""

from __future__ import annotations
from typing import Iterable, Callable, Optional
from PySide6.QtWidgets import QWidget, QVBoxLayout, QListWidget, QListWidgetItem, QLabel
from PySide6.QtCore import Qt, Signal


class ActivityListPanel(QWidget):
    """
    Generic panel for displaying a list of activities.
    Emits 'selectionChanged' when the current item changes.
    """
    selectionChanged = Signal(object)  # Emits activity_id

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self.header_label = QLabel("Activities")
        layout.addWidget(self.header_label)

        self.list = QListWidget()
        # Default styling: borders between items, padding, highlight on selection
        self.list.setStyleSheet("""
            QListWidget::item {
                border-bottom: 1px solid #ccc;
                padding: 6px;
            }
            QListWidget::item:selected {
                background-color: #E8F4F8;
                color: #0066CC;
            }
        """)
        layout.addWidget(self.list)

        self.list.currentItemChanged.connect(self._on_current_changed)

    def set_header(self, text: str) -> None:
        self.header_label.setText(text)

    def populate(
        self,
        activities: Iterable[dict],
        summary_fn: Callable[[dict], str],
        id_key: str
    ) -> None:
        """
        Populate the list with activities.

        Args:
            activities: Iterable of raw activity dicts.
            summary_fn: Function to produce a summary string for each activity.
            id_key: Dict key used to fetch the activity identifier.
        """
        self.list.clear()
        for act in activities:
            summary = summary_fn(act)
            item = QListWidgetItem(summary)
            item.setData(Qt.UserRole, act.get(id_key))
            self.list.addItem(item)

    def current_activity_id(self) -> Optional[object]:
        item = self.list.currentItem()
        if not item:
            return None
        return item.data(Qt.UserRole)

    def _on_current_changed(self, current: QListWidgetItem, previous: QListWidgetItem) -> None:
        activity_id = None
        if current:
            activity_id = current.data(Qt.UserRole)
        self.selectionChanged.emit(activity_id)
