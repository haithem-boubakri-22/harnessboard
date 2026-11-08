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
from harnessboard.export_folder import export_folder
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
        self.is_block_mode: bool = False
        self._block_parent_customer: str = ""
        self._block_parent_type: str = ""
        self.current_file: Path | None = None
        self.resize(1280, 800)

        self.undo_stack = QUndoStack(self)
        self.undo_stack.cleanChanged.connect(self._update_title)
        self.undo_stack.indexChanged.connect(self._refresh_bom)

        self.scene = BoardScene(self.undo_stack, self)
        self.scene.open_block_standalone_requested.connect(self._open_block_standalone)
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
        self._add_action(file_menu, "&Export (PDF + BOM + STEP)", QKeySequence("Ctrl+Shift+E"), self.export_full_folder)
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

    def export_full_folder(self, silent=False) -> bool:
        print(f"DEBUG: export_full_folder called. silent={silent}")
        if self.harness is None:
            print("DEBUG: export_full_folder returned early because harness is None")
            return False

        parts = bom_parts(self.scene)
        cables = bom_cables(self.scene)
        out_dir = self.harness.folder

        result = export_folder(out_dir, self.scene, self.harness, parts, cables)
        
        if "error" in result:
            print(f"EXPORT ERROR: {result['error']}")
            if not silent:
                QMessageBox.critical(self, "Export failed", result["error"])
            return False
        
        if not silent:
            lines = [
                f"Exported to: {result['folder']}",
                f"  STEP files: {result['steps_copied']}",
                f"  MCAM files: {result['mcam_copied']}",
            ]
            if result["missing"]:
                lines.append("")
                lines.append("Missing step files (skipped):")
                for m in result["missing"]:
                    lines.append(f"  - {m}")
            QMessageBox.information(self, "Export complete", "\n".join(lines))
            
        self.statusBar().showMessage(f"Exported to {result['folder']}")
        return True



    def open_block_file(self, block_path: Path) -> None:
        """Open a block .harn standalone (block-mode)."""
        try:
            data = json.loads(block_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "Open failed", f"Could not read block file:\n{exc}")
            return
        if data.get("kind") != "block":
            QMessageBox.warning(self, "Not a block file", "This file is not a harness block.")
            return
        self.scene.load_dict(data, self.library)
        self.is_block_mode = True
        self.harness = None
        self.current_file = block_path
        # Try to inherit parent metadata
        self._block_parent_customer = ""
        self._block_parent_type = ""
        parent = block_path.parent.parent / "harness.json"
        if parent.is_file():
            try:
                meta = json.loads(parent.read_text(encoding="utf-8"))
                self._block_parent_customer = meta.get("customer", "")
                self._block_parent_type = meta.get("type", "")
            except Exception:
                pass
        self.undo_stack.setClean()
        self._update_title()
        self.view.zoom_fit()
        self.statusBar().showMessage(f"Editing block: {block_path.parent.name}")

    def _open_block_standalone(self, block) -> None:
        """Open the block's layout.harn in isolation (new window)."""
        if self.harness is None:
            QMessageBox.warning(self, "No board", "Save the board first so the block folder exists.")
            return
        from harnessboard.board_split import _safe_name
        block_folder = self.harness.folder / _safe_name(block.name)
        block_file = block_folder / "layout.harn"
        if not block_file.is_file():
            QMessageBox.information(
                self, "Save board first",
                f"The block folder does not exist yet.\nSave the board (Ctrl+S) first to generate it.",
            )
            return
        # Relaunch in block mode
        import subprocess, sys
        subprocess.Popen([sys.executable, "-m", "harnessboard", "--block", str(block_file)])

    def _on_parts_deleted(self, names: list[str]) -> None:
        # Files are cleaned up automatically on the next Save/Export.
        pass

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
        if self.harness is None:
            return self._save_as_new_harness()
            
        if self.current_file is None:
            self.current_file = self.harness.layout_file
            
        return self._write_to(self.current_file)

    def _save_as_new_harness(self) -> bool:
        if not self._ensure_projects_root():
            return False
            
        dialog = NewHarnessDialog(self.settings.projects_root, self)
        if not dialog.exec() or dialog.harness is None:
            return False

        # Set harness but DO NOT clear the scene (so we save what the user drew)
        self.harness = dialog.harness
        self.current_file = self.harness.layout_file
        self._update_title()

        # Save current scene to the new harness folder
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

    def _validate_unique_harness_names(self) -> bool:
        boxes = self.scene.harness_boxes()
        seen = {}
        for box in boxes:
            key = box.name.lower()
            if key in seen:
                msg = ("Two harness blocks have the same name: '" + box.name + "'" +
                       chr(10) + chr(10) +
                       "Every harness block on the board must have a unique name before saving." +
                       chr(10) + chr(10) +
                       "Double-click a block to rename it.")
                QMessageBox.warning(self, "Duplicate Harness Names", msg)
                return False
            seen[key] = True
        return True

    def _write_to(self, path: Path) -> bool:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            QMessageBox.critical(self, "Save failed", f"Could not create folder:\n{exc}")
            return False

        # --- Block-standalone mode: save just this block's folder ---
        if getattr(self, "is_block_mode", False):
            try:
                from harnessboard.board_split import serialize_current_block
                from harnessboard.export_folder import export_folder
                block_dict = serialize_current_block(self.scene)
                path.write_text(json.dumps(block_dict, indent=2), encoding="utf-8")
            except Exception as exc:
                import traceback
                traceback.print_exc()
                QMessageBox.critical(self, "Save failed", f"Could not serialize block:\n{exc}")
                return False

            # Regenerate block PDF/BOM/steps
            try:
                from harnessboard.bom import bom_parts, bom_cables
                from harnessboard.export_folder import export_folder
                block_name = block_dict["block_name"]
                parts = bom_parts(self.scene)
                cables = bom_cables(self.scene)
                info = {
                    "customer": getattr(self, "_block_parent_customer", "") or "",
                    "number": block_name,
                    "type": getattr(self, "_block_parent_type", "") or "",
                }
                export_folder(
                    path.parent, self.scene, None, parts, cables,
                    name_hint=block_name, flat_steps=True, info_override=info,
                )
            except Exception as exc:
                import traceback
                traceback.print_exc()
                QMessageBox.warning(self, "Export Warning", f"Block saved, but PDF/BOM failed:\n{exc}")

            self.undo_stack.setClean()
            self._update_title()
            self.statusBar().showMessage(f"Saved block: {path}")
            return True

        # --- Global board mode ---
        try:
            path.write_text(json.dumps(self.scene.to_dict(), indent=2), encoding="utf-8")
        except OSError as exc:
            QMessageBox.critical(self, "Save failed", f"Could not write the file:\n{exc}")
            return False

        self.undo_stack.setClean()
        self._update_title()

        if self.harness is not None:
            try:
                from harnessboard.board_split import sync_board_and_blocks
                summary = sync_board_and_blocks(self.harness, self.scene, self.library)
                blocks = summary.get("blocks_written", [])
                msg = f"Saved. Global steps: {summary['global_steps']}"
                if blocks:
                    msg += f" | blocks: {', '.join(blocks)}"
                self.statusBar().showMessage(msg)
            except Exception as exc:
                import traceback
                traceback.print_exc()
                QMessageBox.warning(self, "Sync Warning", f"Layout saved, but block sync failed:\n{exc}")
        else:
            self.statusBar().showMessage(f"Saved {path}")

        return True




    def closeEvent(self, event) -> None:
        if self._confirm_discard():
            event.accept()
        else:
            event.ignore()

    # ------------------------------------------------------------ misc
    def _update_title(self) -> None:
        if getattr(self, "is_block_mode", False) and self.current_file is not None:
            name = f"[Block] {self.current_file.parent.name}"
        elif self.harness is not None:
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
