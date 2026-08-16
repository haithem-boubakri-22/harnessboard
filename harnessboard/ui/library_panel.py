"""Library dock panel: visual search dropdown + category tree of parts.

The search field is the primary placement method (SPEC.md section 5):
typing a model name opens a dropdown of matching parts shown as icon
thumbnails, so variants that share a name are picked apart by eye.
"""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QCompleter,
    QLabel,
    QLineEdit,
    QListView,
    QListWidget,
    QListWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from harnessboard.library import Library, Part

PART_ROLE = Qt.ItemDataRole.UserRole + 1
THUMB = QSize(48, 48)
POPUP_THUMB = QSize(64, 64)


class LibraryPanel(QWidget):
    partActivated = Signal(object)        # emits a Part
    cableActivated = Signal(str, float)   # designation, diameter

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._library: Library | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        layout.addWidget(QLabel("Search part (type model name):"))
        self.search = QLineEdit()
        self.search.setPlaceholderText("e.g. 9J1973703…")
        self.search.setClearButtonEnabled(True)
        layout.addWidget(self.search)

        self._completer_model = QStandardItemModel(self)
        self._completer = QCompleter(self._completer_model, self)
        self._completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self._completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self._completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        popup = QListView()
        popup.setIconSize(POPUP_THUMB)
        popup.setUniformItemSizes(True)
        popup.setSpacing(2)
        self._completer.setPopup(popup)
        self.search.setCompleter(self._completer)
        self._completer.activated[str].connect(self._on_completer_activated)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setIconSize(THUMB)
        self.tree.itemDoubleClicked.connect(self._on_tree_activated)
        layout.addWidget(self.tree, 1)

        layout.addWidget(QLabel("Cables (double-click to draw):"))
        self.cable_list = QListWidget()
        self.cable_list.setMaximumHeight(110)
        self.cable_list.itemDoubleClicked.connect(self._on_cable_activated)
        layout.addWidget(self.cable_list)

        self.count_label = QLabel("No library loaded")
        layout.addWidget(self.count_label)

    def set_library(self, library: Library) -> None:
        self._library = library
        self._rebuild_completer(library)
        self._rebuild_tree(library)
        self.cable_list.clear()
        for designation in sorted(library.cables, key=str.lower):
            diameter = library.cables[designation]
            item = QListWidgetItem(f"{designation}   (Ø {diameter:g} mm)")
            item.setData(Qt.ItemDataRole.UserRole, (designation, diameter))
            self.cable_list.addItem(item)
        n_parts = len(library.parts)
        n_cables = len(library.cables)
        self.count_label.setText(f"{n_parts} parts, {n_cables} cables")

    def _on_cable_activated(self, item: QListWidgetItem) -> None:
        designation, diameter = item.data(Qt.ItemDataRole.UserRole)
        self.cableActivated.emit(designation, float(diameter))

    def _rebuild_completer(self, library: Library) -> None:
        self._completer_model.clear()
        for part in library.parts:
            item = QStandardItem(part.name)
            if part.icon_path:
                item.setIcon(QIcon(str(part.icon_path)))
            item.setData(part, PART_ROLE)
            item.setEditable(False)
            self._completer_model.appendRow(item)

    def _rebuild_tree(self, library: Library) -> None:
        self.tree.clear()
        by_category: dict[str, list[Part]] = {}
        for part in library.parts:
            by_category.setdefault(part.category, []).append(part)
        for category in sorted(by_category, key=str.lower):
            cat_item = QTreeWidgetItem([category])
            cat_item.setFlags(cat_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            self.tree.addTopLevelItem(cat_item)
            for part in by_category[category]:
                child = QTreeWidgetItem([part.name])
                if part.icon_path:
                    child.setIcon(0, QIcon(str(part.icon_path)))
                child.setData(0, PART_ROLE, part)
                cat_item.addChild(child)
            cat_item.setExpanded(True)

    def _on_completer_activated(self, text: str) -> None:
        # Several variants can share display text; take the exact model row
        # currently selected in the popup, falling back to first name match.
        popup = self._completer.popup()
        index = popup.currentIndex()
        part = index.data(PART_ROLE) if index.isValid() else None
        if part is None and self._library is not None:
            part = self._library.part_by_name(text)
        if part is not None:
            self.partActivated.emit(part)

    def _on_tree_activated(self, item: QTreeWidgetItem, _column: int) -> None:
        part = item.data(0, PART_ROLE)
        if part is not None:
            self.partActivated.emit(part)
