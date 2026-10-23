"""'Add part' dialog: register a new model into the library.

New schema: the part folder holds one icon plus N step files, each
representing one (orientation, Z depth) combination. Filenames follow
    <any>_<orient>_Z<z>.step
where orient is one of std / mir / rot / rot_mir, and z is a float.

On OK the dialog:
  - creates <library>/<category>/<name>/
  - copies the chosen icon as icon.<ext>
  - copies every matched step file under its original name
  - writes part.json with z_depths + steps map (no Z field input)
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from harnessboard.library import ORIENTATIONS, Library
from harnessboard.project import valid_folder_name

STEP_SUFFIXES = {".step", ".stp"}

# Matches e.g. "GR-40_rot_mir_Z30.step" / "foo_std_Z25.5.stp".
# rot_mir is listed first so the engine prefers it over 'rot' on backtracking.
_FILENAME_RE = re.compile(
    r"_(rot_mir|rot|mir|std)_Z([0-9]+(?:\.[0-9]+)?)\.(?:step|stp)$",
    re.IGNORECASE,
)


def parse_step_filename(filename: str) -> tuple[str, float] | None:
    """Return (orientation, z) or None if the name doesn't match the pattern."""
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
        # Each entry: {src: Path, filename: str, orient: str|None, z: float|None}
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

        self.icon_edit, icon_row = self._path_row(
            "Images (*.png *.jpg *.jpeg *.bmp *.svg)", preview=True
        )
        form.addRow("Icon image:", icon_row)

        outer.addLayout(form)

        # --- step files panel -------------------------------------------
        outer.addWidget(QLabel("Step files (one per orientation × Z):"))

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

        self.hint_label = QLabel(
            "Filename pattern: <any>_<orient>_Z<z>.step  —  "
            "orient ∈ {std, mir, rot, rot_mir}  —  Z is any number"
        )
        self.hint_label.setStyleSheet("color: #666; font-size: 11px;")
        outer.addWidget(self.hint_label)

        # --- preview ----------------------------------------------------
        self.icon_preview = QLabel()
        self.icon_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_preview.setMinimumHeight(72)
        outer.addWidget(self.icon_preview)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

        self._rebuild_table()

    # -------------------------------------------------------------- helpers
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
            edit.textChanged.connect(self._update_preview)

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
            self.icon_preview.setPixmap(
                pixmap.scaled(
                    64, 64,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )

    # -------------------------------------------------------- file inputs
    def _scan_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Choose step folder")
        if not folder:
            return
        files = [
            p for p in sorted(Path(folder).iterdir())
            if p.is_file() and p.suffix.lower() in STEP_SUFFIXES
        ]
        if not files:
            QMessageBox.information(
                self, "No step files", "That folder contains no .step / .stp files."
            )
            return
        self._add_paths(files)
        # If the folder has an icon.png and we don't have one yet, use it.
        if not self.icon_edit.text():
            for candidate in ("icon.png", "icon.jpg", "icon.jpeg", "icon.svg"):
                p = Path(folder) / candidate
                if p.is_file():
                    self.icon_edit.setText(str(p))
                    break

    def _add_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Choose step files", "", "Step files (*.step *.stp)"
        )
        if paths:
            self._add_paths([Path(p) for p in paths])

    def _add_paths(self, paths: list[Path]) -> None:
        existing_names = {e["filename"] for e in self._entries}
        for p in paths:
            if p.name in existing_names:
                continue
            parsed = parse_step_filename(p.name)
            orient, z = parsed if parsed else (None, None)
            self._entries.append(
                {"src": p, "filename": p.name, "orient": orient, "z": z}
            )
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

            if entry["orient"] is None:
                orient_item = QTableWidgetItem("⚠ unmatched")
                orient_item.setForeground(QColor("#b00020"))
            else:
                orient_item = QTableWidgetItem(entry["orient"])
            self.table.setItem(row, 1, orient_item)

            z_text = f"{entry['z']:g}" if entry["z"] is not None else "—"
            self.table.setItem(row, 2, QTableWidgetItem(z_text))

    # -------------------------------------------------------------- accept
    def accept(self) -> None:
        name = self.name_edit.text().strip()
        category = self.category_combo.currentText().strip()
        icon_path = Path(self.icon_edit.text().strip()) if self.icon_edit.text() else None

        # --- name / category checks --------------------------------
        if not valid_folder_name(name) or not valid_folder_name(category):
            QMessageBox.warning(
                self, "Invalid name",
                'Name and category must not be empty or contain <>:"/\\|?*',
            )
            return
        if self._library.part_by_name(name) is not None:
            QMessageBox.warning(
                self, "Duplicate",
                f"A part named '{name}' already exists in the library.",
            )
            return

        # --- icon checks -------------------------------------------
        if icon_path is None or not icon_path.is_file():
            QMessageBox.warning(self, "Missing icon", "Choose an existing icon image.")
            return

        # --- step files checks -------------------------------------
        matched = [e for e in self._entries if e["orient"] is not None]
        unmatched = [e for e in self._entries if e["orient"] is None]

        if not matched:
            QMessageBox.warning(
                self, "No step files",
                "Add at least one step file with a name matching "
                "<any>_<orient>_Z<z>.step.",
            )
            return

        # duplicate (orientation, z) detection
        seen: dict[tuple[str, float], str] = {}
        for e in matched:
            key = (e["orient"], e["z"])
            if key in seen:
                QMessageBox.warning(
                    self, "Duplicate variant",
                    f"Two files map to the same orientation/Z:\n"
                    f"  {seen[key]}\n  {e['filename']}\n"
                    f"({e['orient']} @ Z{e['z']:g})\n\n"
                    "Remove one or rename the file.",
                )
                return
            seen[key] = e["filename"]

        if unmatched:
            names = "\n".join(f"  • {e['filename']}" for e in unmatched)
            answer = QMessageBox.question(
                self, "Unmatched files",
                f"{len(unmatched)} file(s) don't match the pattern and will be skipped:\n\n"
                f"{names}\n\nProceed anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return

        if self._library.root is None:
            QMessageBox.warning(
                self, "No library", "Set the library folder in Settings first."
            )
            return

        # --- write to disk -----------------------------------------
        folder = self._library.root / category / name
        try:
            folder.mkdir(parents=True, exist_ok=False)
            shutil.copy2(icon_path, folder / f"icon{icon_path.suffix.lower()}")

            steps_map: dict[str, dict[str, str]] = {}
            z_values: set[float] = set()
            for e in matched:
                shutil.copy2(e["src"], folder / e["filename"])
                z_key = f"{e['z']:g}"
                steps_map.setdefault(e["orient"], {})[z_key] = e["filename"]
                z_values.add(e["z"])

            (folder / "part.json").write_text(
                json.dumps(
                    {
                        "category": category,
                        "z_depths": sorted(z_values),
                        "steps": steps_map,
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
        except OSError as exc:
            QMessageBox.critical(
                self, "Add failed", f"Could not create the part:\n{exc}"
            )
            return

        self.created_folder = folder
        super().accept()
