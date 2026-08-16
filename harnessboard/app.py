"""Application entry point."""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from harnessboard.settings import AppSettings
from harnessboard.ui.main_window import MainWindow
from harnessboard.ui.settings_dialog import SettingsDialog


def main() -> int:
    app = QApplication(sys.argv)
    app.setOrganizationName("HarnessBoard")
    app.setApplicationName("HarnessBoard")

    settings = AppSettings()
    if not settings.is_configured():
        # First run: prefill with the bundled sample library so the app
        # opens with something browsable; user can change paths anytime.
        project_root = Path(__file__).resolve().parent.parent
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
