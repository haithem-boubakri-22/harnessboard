"""Live BOM dock: parts with quantities, cables with their Z standard."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QTableWidget, QTableWidgetItem

from harnessboard.bom import bom_cables, bom_parts
from harnessboard.ui.canvas import BoardScene

HEADERS = ["Item", "Category", "Qty", "Z depth", "Ø"]


class BomPanel(QTableWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(0, len(HEADERS), parent)
        self.setHorizontalHeaderLabels(HEADERS)
        self.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.verticalHeader().setVisible(False)
        self.horizontalHeader().setStretchLastSection(True)
        self.setColumnWidth(0, 200)
        self.setColumnWidth(1, 150)
        self.setColumnWidth(2, 50)
        self.setColumnWidth(3, 80)

    def refresh(self, scene: BoardScene) -> None:
        parts = bom_parts(scene)
        cables = bom_cables(scene)
        self.setRowCount(0)

        def add_row(values, bold=False, tint=None):
            row = self.rowCount()
            self.insertRow(row)
            for col, value in enumerate(values):
                cell = QTableWidgetItem(str(value))
                cell.setFlags(Qt.ItemFlag.ItemIsEnabled)
                if bold:
                    font = QFont()
                    font.setBold(True)
                    cell.setFont(font)
                if tint is not None:
                    cell.setBackground(QColor(tint))
                if col in (2, 3, 4):
                    cell.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )
                self.setItem(row, col, cell)

        if parts:
            add_row(["PARTS", "", "", "", ""], bold=True, tint="#e8eef7")
            for r in parts:
                z = f"{r.z_depth:g} mm" if r.z_depth is not None else "—"
                add_row([r.name, r.category, r.quantity, z, ""])
        if cables:
            add_row(["CABLES", "", "", "Z standard", ""], bold=True, tint="#e8f7ea")
            for c in cables:
                z = f"{c.z_standard:g} mm" if c.z_standard is not None else "—"
                add_row([c.designation, "Cable", 1, z, f"{c.diameter:g} mm"])
        if not parts and not cables:
            add_row(["(board is empty)", "", "", "", ""])
