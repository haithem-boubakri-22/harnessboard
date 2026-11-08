"""Details pane for the selected part (Phase 1 stand-in for canvas placement)."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QFormLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from harnessboard.library import Part


class PartDetails(QWidget):
    editRequested = Signal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._current_part = None
        layout = QVBoxLayout(self)

        self.icon_label = QLabel()
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_label.setMinimumHeight(140)
        layout.addWidget(self.icon_label)

        form = QFormLayout()
        self.name_label = QLabel("—")
        self.category_label = QLabel("—")
        self.z_label = QLabel("—")
        self.step_label = QLabel("—")
        self.step_label.setWordWrap(True)
        form.addRow("Model name:", self.name_label)
        form.addRow("Category:", self.category_label)
        form.addRow("Z depth:", self.z_label)
        form.addRow("3D model:", self.step_label)
        layout.addLayout(form)

        edit_row = QHBoxLayout()
        self.edit_button = QPushButton("Edit Part…")
        self.edit_button.setEnabled(False)
        self.edit_button.clicked.connect(self._on_edit_clicked)
        edit_row.addWidget(self.edit_button)
        edit_row.addStretch(1)
        layout.addLayout(edit_row)

        layout.addStretch(1)

    def _on_edit_clicked(self) -> None:
        if self._current_part is not None:
            self.editRequested.emit(self._current_part)

    def show_part(self, part: Part) -> None:
        self._current_part = part
        self.edit_button.setEnabled(True)
        if part.icon_path:
            pixmap = QPixmap(str(part.icon_path)).scaled(
                128, 128,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.icon_label.setPixmap(pixmap)
        else:
            self.icon_label.setText("(no icon)")
        self.name_label.setText(part.name)
        self.category_label.setText(part.category)
        self.z_label.setText(f"{part.z_depth:g} mm" if part.z_depth is not None else "—")
        self.step_label.setText(str(part.step_path) if part.step_path else "(missing)")
