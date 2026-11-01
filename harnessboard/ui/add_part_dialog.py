"""'Add part' dialog: registers a model, auto-picks the minimal Z from a folder."""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
    QFormLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox,
    QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from harnessboard.library import ORIENTATIONS, Library
from harnessboard.project import valid_folder_name

STEP_SUFFIXES = {".step", ".stp"}
_FILENAME_RE = re.compile(
    r"_(rot_mir|rot|mir|std)_Z([0-9]+(?:\.[0-9]+)?)\.(?:step|stp)$",
    re.IGNORECASE,
)

def parse_step_filename(filename: str) -> tuple[str, float] | None:
    m = _FILENAME_RE.search(filename)
    if m is None:
        return None
    return m.group(1).lower(), float(m.group(2))

class AddPartDialog(QDialog):
    def __init__(self, library: Library, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Add part to library")
        self.setMinimumWidth(720)
        self.setMinimumHeight(520)
        self._library = library
        self.created_folder: Path | None = None
        self._entries: list[dict] = []

        outer = QVBoxLayout(self)
        form = QFormLayout()

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("model name, e.g. GR-40")
        form.addRow("Model name:", self.name_edit)

        self.category_combo = QComboBox()
        self.category_combo.setEditable(True)
        self.category_combo.addItems(library.categories or ["Connector holders"])
        form.addRow("Category:", self.category_combo)

        self.icon_edit, icon_row = self._path_row("Images (*.png *.jpg *.jpeg *.bmp *.svg)", preview=True)
        form.addRow("Standard Icon:", icon_row)

        self.icon_up_edit, icon_up_row = self._path_row("Images (*.png *.jpg *.jpeg *.bmp *.svg)", preview=True)
        form.addRow("Face Up Icon (Optional):", icon_up_row)

        self.icon_down_edit, icon_down_row = self._path_row("Images (*.png *.jpg *.jpeg *.bmp *.svg)", preview=True)
        form.addRow("Face Down Icon (Optional):", icon_down_row)

        outer.addLayout(form)
        outer.addWidget(QLabel("Step files (the app automatically selects the lowest Z):"))

        btn_row = QHBoxLayout()
        self.scan_btn = QPushButton("Scan folder…")
        self.scan_btn.clicked.connect(self._scan_folder)
        self.add_files_btn = QPushButton("Add file(s)…")
        self.add_files_btn.clicked.connect(self._add_files)
        self.remove_btn = QPushButton("Remove selected")
        self.remove_btn.clicked.connect(self._remove_selected)
        btn_row.addWidget(self.scan_btn)
        btn_row.addWidget(self.add_files_btn)
        btn_row.addWidget(self.remove_btn)
        btn_row.addStretch(1)
        outer.addLayout(btn_row)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["File", "Orientation", "Z (mm)"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        outer.addWidget(self.table, 1)

        self.hint_label = QLabel("Filename pattern: <any>_<orient>_Z<z>.step")
        self.hint_label.setStyleSheet("color: #666; font-size: 11px;")
        outer.addWidget(self.hint_label)

        self.icon_preview = QLabel()
        self.icon_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_preview.setMinimumHeight(72)
        outer.addWidget(self.icon_preview)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

        self._rebuild_table()

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
        if preview:
            # Use a lambda to ignore the text argument and pass the path
            edit.textChanged.connect(lambda text: self._update_preview(text))
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.addWidget(edit, 1)
        row_layout.addWidget(button)
        return edit, row

    def _update_preview(self, path: str) -> None:
        if not path:
            self.icon_preview.clear()
            return
        pixmap = QPixmap(path)
        if not pixmap.isNull():
            # We only have one preview label, so we just update it
            self.icon_preview.setPixmap(pixmap.scaled(64, 64, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

    def _scan_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Choose folder")
        if not folder:
            return
            
        path = Path(folder)
        step_files = [p for p in sorted(path.iterdir()) if p.is_file() and p.suffix.lower() in STEP_SUFFIXES]
        
        # Auto-detect icons in the folder
        for file in path.iterdir():
            if not file.is_file():
                continue
            f_lower = file.name.lower()
            if "up" in f_lower and not self.icon_up_edit.text():
                self.icon_up_edit.setText(str(file))
            elif "down" in f_lower and not self.icon_down_edit.text():
                self.icon_down_edit.setText(str(file))
            elif "icon" in f_lower and not self.icon_edit.text():
                self.icon_edit.setText(str(file))

        if step_files:
            self._add_paths(step_files)
        elif not self.icon_edit.text():
            # If there are no step files AND no icons, warn the user
            QMessageBox.information(self, "Empty folder", "That folder contains no step files or icons.")
            return

    def _add_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "Choose step files", "", "Step files (*.step *.stp)")
        if paths:
            self._add_paths([Path(p) for p in paths])

    def _add_paths(self, paths: list[Path]) -> None:
        existing_names = {e["filename"] for e in self._entries}
        for p in paths:
            if p.name in existing_names:
                continue
            parsed = parse_step_filename(p.name)
            orient, z = parsed if parsed else (None, None)
            self._entries.append({"src": p, "filename": p.name, "orient": orient, "z": z})
            existing_names.add(p.name)
        self._rebuild_table()

    def _remove_selected(self) -> None:
        rows = sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True)
        for r in rows:
            if 0 <= r < len(self._entries):
                self._entries.pop(r)
        self._rebuild_table()

    def _rebuild_table(self) -> None:
        self.table.setRowCount(len(self._entries))
        for row, entry in enumerate(self._entries):
            file_item = QTableWidgetItem(entry["filename"])
            if entry["orient"] is None:
                file_item.setForeground(QColor("#b00020"))
            self.table.setItem(row, 0, file_item)
            
            orient_item = QTableWidgetItem(entry["orient"] if entry["orient"] else "⚠ unmatched")
            if entry["orient"] is None:
                orient_item.setForeground(QColor("#b00020"))
            self.table.setItem(row, 1, orient_item)
            self.table.setItem(row, 2, QTableWidgetItem(f"{entry['z']:g}" if entry["z"] is not None else "—"))

    def accept(self) -> None:
        name = self.name_edit.text().strip()
        category = self.category_combo.currentText().strip()
        icon_path = Path(self.icon_edit.text().strip()) if self.icon_edit.text() else None
        icon_up_path = Path(self.icon_up_edit.text().strip()) if self.icon_up_edit.text() else None
        icon_down_path = Path(self.icon_down_edit.text().strip()) if self.icon_down_edit.text() else None

        if not valid_folder_name(name) or not valid_folder_name(category):
            QMessageBox.warning(self, "Invalid name", 'Name and category must not be empty or contain <>:"/\\|?*')
            return
        if self._library.part_by_name(name) is not None:
            QMessageBox.warning(self, "Duplicate", f"A part named '{name}' already exists in the library.")
            return
        if icon_path is None or not icon_path.is_file():
            QMessageBox.warning(self, "Missing icon", "Choose an existing icon image.")
            return

        matched = [e for e in self._entries if e["orient"] is not None]
        
        # If we have step files, find the minimal Z
        if matched:
            min_z = min(e["z"] for e in matched)
            selected = [e for e in matched if e["z"] == min_z]
            
            # Check for duplicate orientations at this minimal Z
            seen_orients = set()
            for e in selected:
                if e["orient"] in seen_orients:
                    QMessageBox.warning(self, "Duplicate variant", f"Two files map to {e['orient']} at Z={min_z}.\nRemove one or rename.")
                    return
                seen_orients.add(e["orient"])
        else:
            # No step files - this is allowed if we have an icon
            min_z = None
            selected = []

        if self._library.root is None:
            QMessageBox.warning(self, "No library", "Set the library folder in Settings first.")
            return

        folder = self._library.root / category / name
        try:
            folder.mkdir(parents=True, exist_ok=False)
            shutil.copy2(icon_path, folder / f"icon{icon_path.suffix.lower()}")
            if icon_up_path and icon_up_path.is_file():
                shutil.copy2(icon_up_path, folder / f"icon_up{icon_up_path.suffix.lower()}")
            if icon_down_path and icon_down_path.is_file():
                shutil.copy2(icon_down_path, folder / f"icon_down{icon_down_path.suffix.lower()}")

            steps_map: dict[str, str] = {}
            for e in selected:
                shutil.copy2(e["src"], folder / e["filename"])
                steps_map[e["orient"]] = e["filename"]

            meta = {"category": category, "z_depth": min_z}
            if steps_map:
                meta["steps"] = steps_map

            (folder / "part.json").write_text(
                json.dumps(meta, indent=2),
                encoding="utf-8",
            )
        except OSError as exc:
            QMessageBox.critical(self, "Add failed", f"Could not create the part:\n{exc}")
            return

        self.created_folder = folder
        super().accept()
