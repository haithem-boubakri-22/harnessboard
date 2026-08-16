"""'Add part' dialog: register a new model into the library (SPEC.md §4).

Copies the chosen .step and icon into a new part folder under the library
root, and writes part.json — the library stays self-contained.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QWidget,
)

from harnessboard.library import Library
from harnessboard.project import valid_folder_name


class AddPartDialog(QDialog):
    def __init__(self, library: Library, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Add part to library")
        self.setMinimumWidth(520)
        self._library = library
        self.created_folder: Path | None = None

        layout = QFormLayout(self)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("model name incl. orientation, e.g. 4H0973713_left")
        layout.addRow("Model name:", self.name_edit)

        self.category_combo = QComboBox()
        self.category_combo.setEditable(True)
        self.category_combo.addItems(library.categories or ["Connector holders"])
        layout.addRow("Category:", self.category_combo)

        self.step_edit, step_row = self._path_row("3D models (*.step *.stp)")
        layout.addRow("3D model (.step):", step_row)

        self.icon_edit, icon_row = self._path_row(
            "Images (*.png *.jpg *.jpeg *.bmp *.svg)", preview=True
        )
        layout.addRow("Icon image:", icon_row)

        self.icon_preview = QLabel()
        self.icon_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_preview.setMinimumHeight(72)
        layout.addRow("", self.icon_preview)

        self.z_spin = QDoubleSpinBox()
        self.z_spin.setRange(0.0, 1000.0)
        self.z_spin.setDecimals(1)
        self.z_spin.setSuffix(" mm")
        layout.addRow("Z depth:", self.z_spin)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _path_row(self, file_filter: str, preview: bool = False):
        edit = QLineEdit()
        button = QPushButton("Browse…")

        def browse() -> None:
            path, _ = QFileDialog.getOpenFileName(self, "Choose file", "", file_filter)
            if path:
                edit.setText(path)
                if preview:
                    self._update_preview(path)

        button.clicked.connect(browse)
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.addWidget(edit, 1)
        row_layout.addWidget(button)
        return edit, row

    def _update_preview(self, path: str) -> None:
        pixmap = QPixmap(path)
        if not pixmap.isNull():
            self.icon_preview.setPixmap(
                pixmap.scaled(
                    64, 64,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )

    def accept(self) -> None:
        name = self.name_edit.text().strip()
        category = self.category_combo.currentText().strip()
        step_path = Path(self.step_edit.text().strip())
        icon_path = Path(self.icon_edit.text().strip())

        if not valid_folder_name(name) or not valid_folder_name(category):
            QMessageBox.warning(self, "Invalid name",
                                'Name and category must not be empty or contain <>:"/\\|?*')
            return
        if self._library.part_by_name(name) is not None:
            QMessageBox.warning(self, "Duplicate",
                                f"A part named '{name}' already exists in the library.")
            return
        if not step_path.is_file() or step_path.suffix.lower() not in (".step", ".stp"):
            QMessageBox.warning(self, "Missing 3D model", "Choose an existing .step file.")
            return
        if not icon_path.is_file():
            QMessageBox.warning(self, "Missing icon", "Choose an existing icon image.")
            return
        if self._library.root is None:
            QMessageBox.warning(self, "No library", "Set the library folder in Settings first.")
            return

        folder = self._library.root / category / name
        try:
            folder.mkdir(parents=True, exist_ok=False)
            shutil.copy2(step_path, folder / f"{name}{step_path.suffix.lower()}")
            shutil.copy2(icon_path, folder / f"icon{icon_path.suffix.lower()}")
            (folder / "part.json").write_text(
                json.dumps(
                    {"category": category, "z_depth": self.z_spin.value()}, indent=2
                ),
                encoding="utf-8",
            )
        except OSError as exc:
            QMessageBox.critical(self, "Add failed", f"Could not create the part:\n{exc}")
            return
        self.created_folder = folder
        super().accept()
