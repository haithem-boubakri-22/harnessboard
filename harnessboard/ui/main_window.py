"""Main window: library dock (left), board canvas (center), details dock (right)."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence, QUndoStack
from PySide6.QtWidgets import (
    QDockWidget,
    QFileDialog,
    QMainWindow,
    QMessageBox,
)

import harnessboard
from harnessboard.bom import bom_cables, bom_parts, cable_z
from harnessboard.excel_export import export_bom
from harnessboard.library import Library, Part, scan_library
from harnessboard.project import Harness
from harnessboard.settings import AppSettings
from harnessboard.ui.add_part_dialog import AddPartDialog
from harnessboard.ui.bom_panel import BomPanel
from harnessboard.ui.canvas import BoardScene, BoardView
from harnessboard.ui.harness_dialogs import NewHarnessDialog, OpenHarnessDialog
from harnessboard.ui.library_panel import LibraryPanel
from harnessboard.ui.part_details import PartDetails
from harnessboard.ui.settings_dialog import SettingsDialog

FILE_FILTER = "HarnessBoard layout (*.harn)"


class MainWindow(QMainWindow):
    def __init__(self, settings: AppSettings) -> None:
        super().__init__()
        self.settings = settings
        self.library = Library()
        self.harness: Harness | None = None
        self.current_file: Path | None = None
        self.resize(1280, 800)

        self.undo_stack = QUndoStack(self)
        self.undo_stack.cleanChanged.connect(self._update_title)
        self.undo_stack.indexChanged.connect(self._sync_step_files)
        self.undo_stack.indexChanged.connect(self._refresh_bom)

        self.scene = BoardScene(self.undo_stack, self)
        self.view = BoardView(self.scene)
        self.view.partsDeleted.connect(self._on_parts_deleted)
        self.view.statusMessage.connect(self.statusBar().showMessage)
        self.setCentralWidget(self.view)

        self.library_panel = LibraryPanel(self)
        self.library_panel.partActivated.connect(self._on_part_activated)
        self.library_panel.cableActivated.connect(self.view.draw_cable)
        dock = QDockWidget("Part library", self)
        dock.setWidget(self.library_panel)
        dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)

        self.part_details = PartDetails(self)
        details_dock = QDockWidget("Part details", self)
        details_dock.setWidget(self.part_details)
        details_dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, details_dock)

        self.bom_panel = BomPanel(self)
        bom_dock = QDockWidget("BOM — Bill of Materials", self)
        bom_dock.setWidget(self.bom_panel)
        bom_dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, bom_dock)

        self._build_menu()
        self.statusBar().showMessage(
            "Ready — create or open a harness (File menu), pick parts in the library, "
            "click on the board to place them"
        )
        self._update_title()

        if self.settings.library_root:
            self.reload_library()

    # ------------------------------------------------------------- menus
    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("&File")
        self._add_action(file_menu, "&New harness…", QKeySequence.StandardKey.New, self.new_harness)
        self._add_action(file_menu, "&Open harness…", QKeySequence.StandardKey.Open, self.open_harness)
        self._add_action(file_menu, "&Save", QKeySequence.StandardKey.Save, self.save_file)
        file_menu.addSeparator()
        self._add_action(file_menu, "Open layout &file…", None, self.open_file)
        self._add_action(file_menu, "Save layout &as…", QKeySequence.StandardKey.SaveAs, self.save_file_as)
        file_menu.addSeparator()
        self._add_action(file_menu, "Export &BOM to Excel…", QKeySequence("Ctrl+E"), self.export_bom_excel)
        file_menu.addSeparator()
        self._add_action(file_menu, "E&xit", None, self.close)

        library_menu = self.menuBar().addMenu("&Library")
        self._add_action(library_menu, "&Add part…", QKeySequence("Ctrl+Shift+A"), self.add_part)
        self._add_action(library_menu, "&Rescan library", QKeySequence("F5"), self.reload_library)
        library_menu.addSeparator()
        self._add_action(library_menu, "Se&ttings…", None, self.open_settings)

        edit_menu = self.menuBar().addMenu("&Edit")
        undo_action = self.undo_stack.createUndoAction(self, "&Undo")
        undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        edit_menu.addAction(undo_action)
        redo_action = self.undo_stack.createRedoAction(self, "&Redo")
        redo_action.setShortcut(QKeySequence.StandardKey.Redo)
        edit_menu.addAction(redo_action)
        edit_menu.addSeparator()
        # Board shortcuts (Del, R, Ctrl+C/V) live on the view itself so they
        # never steal keystrokes from the search box; menu entries just call
        # the same slots.
        self._add_action(edit_menu, "&Copy", None, self.view.copy_selected)
        self._add_action(edit_menu, "&Paste", None, self.view.paste)
        self._add_action(edit_menu, "&Delete selected\tDel", None, self.view.delete_selected)
        self._add_action(edit_menu, "Rotate C&W\tR", None, lambda: self.view.rotate_selected(15))
        self._add_action(edit_menu, "Rotate CC&W\tShift+R", None, lambda: self.view.rotate_selected(-15))

        view_menu = self.menuBar().addMenu("&View")
        self.labels_action = QAction("Show &labels", self, checkable=True, checked=True)
        self.labels_action.toggled.connect(self.scene.set_labels_visible)
        view_menu.addAction(self.labels_action)
        view_menu.addSeparator()
        self._add_action(view_menu, "Zoom &in", QKeySequence.StandardKey.ZoomIn, lambda: self.view.zoom(1.15))
        self._add_action(view_menu, "Zoom &out", QKeySequence.StandardKey.ZoomOut, lambda: self.view.zoom(1 / 1.15))
        self._add_action(view_menu, "Zoom &fit", QKeySequence("Ctrl+0"), self.view.zoom_fit)

        help_menu = self.menuBar().addMenu("&Help")
        self._add_action(help_menu, "&About", None, self._about)

    def _add_action(self, menu, text, shortcut, slot) -> QAction:
        action = QAction(text, self)
        if shortcut is not None:
            action.setShortcut(shortcut)
        action.triggered.connect(slot)
        menu.addAction(action)
        return action

    # ------------------------------------------------------------ library
    def open_settings(self) -> None:
        dialog = SettingsDialog(self.settings, self)
        if dialog.exec():
            self.reload_library()

    def reload_library(self) -> None:
        root = self.settings.library_root
        if not root:
            self.statusBar().showMessage("No library folder set — open Library > Settings")
            return
        self.library = scan_library(root)
        self.library_panel.set_library(self.library)
        message = (
            f"Library loaded: {len(self.library.parts)} parts, "
            f"{len(self.library.cables)} cables"
        )
        if self.library.errors:
            message += f" — {len(self.library.errors)} problem(s)"
            QMessageBox.warning(self, "Library problems", "\n".join(self.library.errors))
        self.statusBar().showMessage(message)

    def add_part(self) -> None:
        if self.library.root is None:
            QMessageBox.information(
                self, "No library", "Set the library folder first (Library > Settings)."
            )
            return
        dialog = AddPartDialog(self.library, self)
        if dialog.exec():
            self.reload_library()
            self.statusBar().showMessage(f"Part added: {dialog.created_folder}")

    def _on_part_activated(self, part: Part) -> None:
        self.part_details.show_part(part)
        self.view.place_part(part)
        self.statusBar().showMessage(
            f"Placing {part.name} — click on the board (Ctrl+click for several, "
            "Esc to cancel)"
        )

    # ------------------------------------------------------- harness / sync
    def new_harness(self) -> None:
        if not self._ensure_projects_root() or not self._confirm_discard():
            return
        dialog = NewHarnessDialog(self.settings.projects_root, self)
        if not dialog.exec() or dialog.harness is None:
            return
        self._set_harness(dialog.harness, load_layout=False)
        self.scene.clear()
        self.undo_stack.clear()
        self.labels_action.setChecked(True)
        self._write_to(self.current_file)
        self.statusBar().showMessage(f"Harness created: {dialog.harness.folder}")

    def open_harness(self) -> None:
        if not self._ensure_projects_root() or not self._confirm_discard():
            return
        dialog = OpenHarnessDialog(self.settings.projects_root, self)
        if not dialog.exec() or dialog.harness is None:
            return
        self._set_harness(dialog.harness, load_layout=True)

    def _ensure_projects_root(self) -> bool:
        if self.settings.projects_root:
            Path(self.settings.projects_root).mkdir(parents=True, exist_ok=True)
            return True
        QMessageBox.information(
            self, "No projects folder", "Set the projects folder first (Library > Settings)."
        )
        return False

    def _set_harness(self, harness: Harness, load_layout: bool) -> None:
        self.harness = harness
        self.current_file = harness.layout_file
        if load_layout:
            data = {}
            if harness.layout_file.is_file():
                try:
                    data = json.loads(harness.layout_file.read_text(encoding="utf-8"))
                except (OSError, ValueError) as exc:
                    QMessageBox.critical(self, "Open failed", f"Could not read layout:\n{exc}")
            warnings = self.scene.load_dict(data, self.library)
            self.labels_action.setChecked(self.scene.labels_visible)
            self.undo_stack.setClean()
            self.view.zoom_fit()
            if warnings:
                QMessageBox.warning(self, "Missing parts", "\n".join(warnings))
            self.statusBar().showMessage(f"Opened harness {harness.number}")
        self._refresh_bom()
        self._update_title()

    def _sync_step_files(self) -> None:
        """Copy the .step of every placed part into the harness folder (SPEC §3)."""
        if self.harness is None:
            return
        for item in self.scene.part_items():
            part = item.part
            if part.step_path is None or not part.step_path.is_file():
                continue
            dest = self.harness.folder / part.step_path.name
            if not dest.exists():
                try:
                    shutil.copy2(part.step_path, dest)
                    self.statusBar().showMessage(f"Copied {dest.name} to harness folder")
                except OSError as exc:
                    QMessageBox.warning(
                        self, "Copy failed", f"Could not copy {part.step_path.name}:\n{exc}"
                    )

    def _refresh_bom(self) -> None:
        for cable in self.scene.cable_items():
            cable.set_z_standard(cable_z(self.scene, cable))
        self.bom_panel.refresh(self.scene)

    def export_bom_excel(self) -> None:
        parts = bom_parts(self.scene)
        cables = bom_cables(self.scene)
        if not parts and not cables:
            QMessageBox.information(self, "Empty board", "Nothing to export yet.")
            return
        if self.harness is not None:
            default = str(self.harness.folder / f"BOM {self.harness.number}.xlsx")
            info = {
                "customer": self.harness.customer,
                "number": self.harness.number,
                "type": self.harness.htype,
            }
        else:
            default = str(Path(self.settings.projects_root or ".") / "BOM.xlsx")
            info = {}
        path, _ = QFileDialog.getSaveFileName(
            self, "Export BOM", default, "Excel workbook (*.xlsx)"
        )
        if not path:
            return
        if not path.lower().endswith(".xlsx"):
            path += ".xlsx"
        try:
            export_bom(path, parts, cables, info)
        except OSError as exc:
            QMessageBox.critical(self, "Export failed", f"Could not write the file:\n{exc}")
            return
        self.statusBar().showMessage(f"BOM exported: {path}")

    def _on_parts_deleted(self, names: list[str]) -> None:
        """SPEC decision: deleting the last instance asks whether to remove the file."""
        if self.harness is None:
            return
        remaining = {item.part.name for item in self.scene.part_items()}
        orphan_files = []
        for name in sorted(set(names) - remaining):
            part = self.library.part_by_name(name)
            if part is None or part.step_path is None:
                continue
            dest = self.harness.folder / part.step_path.name
            if dest.is_file():
                orphan_files.append(dest)
        if not orphan_files:
            return
        file_list = "\n".join(f"  • {f.name}" for f in orphan_files)
        answer = QMessageBox.question(
            self,
            "Remove 3D files too?",
            "These parts are no longer on the board. Also remove their 3D models "
            f"from the harness folder?\n\n{file_list}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            for f in orphan_files:
                try:
                    f.unlink()
                except OSError as exc:
                    QMessageBox.warning(self, "Delete failed", f"{f.name}:\n{exc}")

    # ------------------------------------------------------------ file ops
    def _confirm_discard(self) -> bool:
        if self.undo_stack.isClean():
            return True
        answer = QMessageBox.question(
            self,
            "Unsaved changes",
            "The layout has unsaved changes. Save them first?",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
        )
        if answer == QMessageBox.StandardButton.Save:
            return self.save_file()
        return answer == QMessageBox.StandardButton.Discard

    def open_file(self) -> None:
        if not self._confirm_discard():
            return
        start_dir = str(self.current_file.parent if self.current_file else self.settings.projects_root or "")
        path, _ = QFileDialog.getOpenFileName(self, "Open layout", start_dir, FILE_FILTER)
        if not path:
            return
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "Open failed", f"Could not read the file:\n{exc}")
            return
        self.harness = None
        warnings = self.scene.load_dict(data, self.library)
        self.labels_action.setChecked(self.scene.labels_visible)
        self.current_file = Path(path)
        self.undo_stack.setClean()
        self._refresh_bom()
        self._update_title()
        self.view.zoom_fit()
        if warnings:
            QMessageBox.warning(self, "Missing parts", "\n".join(warnings))
        self.statusBar().showMessage(f"Opened {path}")

    def save_file(self) -> bool:
        if self.current_file is None:
            return self.save_file_as()
        return self._write_to(self.current_file)

    def save_file_as(self) -> bool:
        start_dir = str(self.current_file if self.current_file else self.settings.projects_root or "")
        path, _ = QFileDialog.getSaveFileName(self, "Save layout", start_dir, FILE_FILTER)
        if not path:
            return False
        if not path.lower().endswith(".harn"):
            path += ".harn"
        self.current_file = Path(path)
        return self._write_to(self.current_file)

    def _write_to(self, path: Path) -> bool:
        try:
            path.write_text(
                json.dumps(self.scene.to_dict(), indent=2), encoding="utf-8"
            )
        except OSError as exc:
            QMessageBox.critical(self, "Save failed", f"Could not write the file:\n{exc}")
            return False
        self.undo_stack.setClean()
        self._update_title()
        self.statusBar().showMessage(f"Saved {path}")
        return True

    def closeEvent(self, event) -> None:
        if self._confirm_discard():
            event.accept()
        else:
            event.ignore()

    # ------------------------------------------------------------ misc
    def _update_title(self) -> None:
        if self.harness is not None:
            name = f"{self.harness.customer} / {self.harness.number} [{self.harness.htype}]"
        elif self.current_file is not None:
            name = self.current_file.name
        else:
            name = "untitled"
        dirty = "" if self.undo_stack.isClean() else " *"
        self.setWindowTitle(f"{name}{dirty} — HarnessBoard {harnessboard.__version__}")

    def _about(self) -> None:
        QMessageBox.about(
            self,
            "About HarnessBoard",
            f"HarnessBoard {harnessboard.__version__}\n"
            "Layout software for harness manufacturing boards\n"
            "(Assembly / Molding / Q-GATE).",
        )
