"""Settings dialog: library root + projects root (SPEC.md decision log)."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QGridLayout,
    QLabel,
    QLineEdit,
    QPushButton,
)

from harnessboard.settings import AppSettings


class SettingsDialog(QDialog):
    def __init__(self, settings: AppSettings, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(560)
        self._settings = settings

        layout = QGridLayout(self)

        layout.addWidget(QLabel("Library folder (icons + 3D models):"), 0, 0)
        self.library_edit = QLineEdit(settings.library_root)
        layout.addWidget(self.library_edit, 0, 1)
        browse_lib = QPushButton("Browse…")
        browse_lib.clicked.connect(lambda: self._browse(self.library_edit))
        layout.addWidget(browse_lib, 0, 2)

        layout.addWidget(QLabel("Projects folder (customers / harnesses):"), 1, 0)
        self.projects_edit = QLineEdit(settings.projects_root)
        layout.addWidget(self.projects_edit, 1, 1)
        browse_proj = QPushButton("Browse…")
        browse_proj.clicked.connect(lambda: self._browse(self.projects_edit))
        layout.addWidget(browse_proj, 1, 2)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons, 2, 0, 1, 3)

    def _browse(self, edit: QLineEdit) -> None:
        path = QFileDialog.getExistingDirectory(self, "Choose folder", edit.text())
        if path:
            edit.setText(path)

    def accept(self) -> None:
        self._settings.library_root = self.library_edit.text().strip()
        self._settings.projects_root = self.projects_edit.text().strip()
        super().accept()
