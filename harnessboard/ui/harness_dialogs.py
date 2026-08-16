"""Dialogs for creating and opening harnesses."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QMessageBox,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from harnessboard.project import (
    HARNESS_TYPES,
    Harness,
    create_harness,
    list_customers,
    list_harnesses,
    valid_folder_name,
)


class NewHarnessDialog(QDialog):
    def __init__(self, projects_root: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("New harness")
        self.setMinimumWidth(420)
        self._root = projects_root
        self.harness: Harness | None = None

        layout = QFormLayout(self)
        self.customer_combo = QComboBox()
        self.customer_combo.setEditable(True)
        self.customer_combo.addItems(list_customers(projects_root))
        self.customer_combo.setCurrentText("")
        layout.addRow("Customer / project:", self.customer_combo)

        self.number_edit = QLineEdit()
        self.number_edit.setPlaceholderText("e.g. 9Y4 971 279 AD")
        layout.addRow("Harness number:", self.number_edit)

        self.type_combo = QComboBox()
        self.type_combo.addItems(HARNESS_TYPES)
        layout.addRow("Harness type:", self.type_combo)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def accept(self) -> None:
        customer = self.customer_combo.currentText().strip()
        number = self.number_edit.text().strip()
        if not valid_folder_name(customer) or not valid_folder_name(number):
            QMessageBox.warning(
                self,
                "Invalid name",
                'Customer and harness number must not be empty or contain <>:"/\\|?*',
            )
            return
        folder = None
        for harness in list_harnesses(self._root, customer):
            if harness.number.lower() == number.lower():
                folder = harness.folder
                break
        if folder is not None:
            QMessageBox.warning(
                self, "Already exists", f"This harness already exists:\n{folder}"
            )
            return
        self.harness = create_harness(
            self._root, customer, number, self.type_combo.currentText()
        )
        super().accept()


class OpenHarnessDialog(QDialog):
    def __init__(self, projects_root: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Open harness")
        self.resize(460, 420)
        self.harness: Harness | None = None

        layout = QVBoxLayout(self)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Customer / harness", "Type"])
        self.tree.setColumnWidth(0, 280)
        layout.addWidget(self.tree)

        for customer in list_customers(projects_root):
            harnesses = list_harnesses(projects_root, customer)
            if not harnesses:
                continue
            top = QTreeWidgetItem([customer])
            top.setFlags(top.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            self.tree.addTopLevelItem(top)
            for harness in harnesses:
                child = QTreeWidgetItem([harness.number, harness.htype])
                child.setData(0, Qt.ItemDataRole.UserRole, harness)
                top.addChild(child)
            top.setExpanded(True)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.tree.itemDoubleClicked.connect(lambda *_: self.accept())

    def accept(self) -> None:
        item = self.tree.currentItem()
        harness = item.data(0, Qt.ItemDataRole.UserRole) if item else None
        if harness is None:
            QMessageBox.information(self, "Pick a harness", "Select a harness to open.")
            return
        self.harness = harness
        super().accept()
