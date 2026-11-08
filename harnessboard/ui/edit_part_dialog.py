"""Edit an existing part's metadata (Z, encombrement, category, icons).

Does NOT change the part name (folder name is identity). Step files remain
managed by dropping files in the folder + rescanning (F5).
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from PySide6.QtCore import Qt
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

from harnessboard.library import Part


class EditPartDialog(QDialog):
    def __init__(self, part: Part, library_categories: list[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Edit Part: {part.name}")
        self.setMinimumWidth(500)
        self._part = part
        self._moved_to: Path | None = None

        layout = QFormLayout(self)

        # Name — read-only
        name_lbl = QLabel(part.name)
        name_lbl.setStyleSheet("font-weight: bold;")
        layout.addRow("Model name:", name_lbl)

        # Category
        self.category_combo = QComboBox()
        self.category_combo.setEditable(True)
        cats = list(library_categories) if library_categories else [part.category]
        if part.category not in cats:
            cats.append(part.category)
        self.category_combo.addItems(cats)
        self.category_combo.setCurrentText(part.category)
        layout.addRow("Category:", self.category_combo)

        # Icons
        self.icon_edit, self.icon_row = self._icon_row(part.icon_path)
        layout.addRow("Standard Icon:", self.icon_row)

        self.icon_up_edit, self.icon_up_row = self._icon_row(part.icon_up_path)
        layout.addRow("Face Up Icon:", self.icon_up_row)

        self.icon_down_edit, self.icon_down_row = self._icon_row(part.icon_down_path)
        layout.addRow("Face Down Icon:", self.icon_down_row)

        # Z depth
        self.z_spin = QDoubleSpinBox()
        self.z_spin.setRange(0.0, 1000.0)
        self.z_spin.setDecimals(1)
        self.z_spin.setSuffix(" mm")
        self.z_spin.setValue(part.z_depth or 0.0)
        layout.addRow("Base Z Depth:", self.z_spin)

        # Encombrement
        self.encombrement_spin = QDoubleSpinBox()
        self.encombrement_spin.setRange(0.0, 1000.0)
        self.encombrement_spin.setDecimals(1)
        self.encombrement_spin.setSuffix(" mm")
        self.encombrement_spin.setValue(part.encombrement)
        layout.addRow("Encombrement:", self.encombrement_spin)

        # Info line
        info = QLabel("Step files are managed by the folder. Drop new *_<orient>_Z<z>.step files\nand press F5 to rescan — no need to edit them here.")
        info.setStyleSheet("color: #666; font-size: 11px;")
        info.setWordWrap(True)
        layout.addRow("", info)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _icon_row(self, current_path):
        edit = QLineEdit()
        edit.setText(str(current_path) if current_path else "")
        btn = QPushButton("Browse…")

        def browse():
            path, _ = QFileDialog.getOpenFileName(
                self, "Choose icon", "", "Images (*.png *.jpg *.jpeg *.bmp *.svg)"
            )
            if path:
                edit.setText(path)

        btn.clicked.connect(browse)
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(edit, 1)
        h.addWidget(btn)
        return edit, row

    def accept(self):
        category = self.category_combo.currentText().strip()
        z_value = self.z_spin.value()
        encombrement = self.encombrement_spin.value()

        if not category:
            QMessageBox.warning(self, "Invalid category", "Category cannot be empty.")
            return

        part = self._part

        # 1. Move folder if category changed
        new_folder = part.folder
        if category != part.category:
            root = part.folder.parent.parent
            new_folder = root / category / part.name
            if new_folder.exists():
                QMessageBox.warning(
                    self, "Folder exists",
                    f"Cannot move part: {new_folder} already exists."
                )
                return
            try:
                new_folder.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(part.folder), str(new_folder))
                self._moved_to = new_folder
            except OSError as exc:
                QMessageBox.critical(self, "Move failed", f"Could not move folder:\n{exc}")
                return

        # 2. Copy new icons if user picked different files
        self._sync_icon(part.icon_edit_path if hasattr(part, "icon_edit_path") else None, self.icon_edit.text(), new_folder, "icon")
        self._sync_icon(None, self.icon_up_edit.text(), new_folder, "icon_up")
        self._sync_icon(None, self.icon_down_edit.text(), new_folder, "icon_down")

        # 3. Update part.json
        meta_file = new_folder / "part.json"
        try:
            meta = json.loads(meta_file.read_text(encoding="utf-8")) if meta_file.is_file() else {}
        except (OSError, ValueError):
            meta = {}

        meta["category"] = category
        meta["z_depth"] = z_value
        meta["encombrement"] = encombrement

        try:
            meta_file.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        except OSError as exc:
            QMessageBox.critical(self, "Save failed", f"Could not write part.json:\n{exc}")
            return

        super().accept()

    def _sync_icon(self, _old, path_str, folder: Path, basename: str):
        if not path_str:
            return
        src = Path(path_str)
        if not src.is_file():
            return
        # If same file is already in place, skip
        existing = list(folder.glob(f"{basename}.*"))
        if existing and existing[0].resolve() == src.resolve():
            return
        try:
            for old in existing:
                old.unlink()
            shutil.copy2(src, folder / f"{basename}{src.suffix.lower()}")
        except OSError as exc:
            QMessageBox.warning(self, "Icon copy failed", f"{basename}:\n{exc}")
