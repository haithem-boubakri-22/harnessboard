"""Application entry point."""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from harnessboard.settings import AppSettings
from harnessboard.ui.main_window import MainWindow
from harnessboard.ui.settings_dialog import SettingsDialog


def _app_root() -> Path:
    """Directory to resolve bundled data and default project paths.

    Frozen (PyInstaller) -> folder containing the executable.
    Source               -> parent of the `harnessboard` package.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def main() -> int:
    app = QApplication(sys.argv)
    app.setOrganizationName("HarnessBoard")
    app.setApplicationName("HarnessBoard")

    settings = AppSettings()
    if not settings.is_configured():
        project_root = _app_root()
        sample = project_root / "sample_library"
        if not settings.library_root and sample.is_dir():
            settings.library_root = str(sample)
        if not settings.projects_root:
            settings.projects_root = str(project_root / "projects")
        dialog = SettingsDialog(settings)
        dialog.setWindowTitle("Welcome — set your folders")
        dialog.exec()

    window = MainWindow(settings)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
