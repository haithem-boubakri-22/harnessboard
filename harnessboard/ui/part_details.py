"""Details pane for the selected part (Phase 1 stand-in for canvas placement)."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QFormLayout, QLabel, QVBoxLayout, QWidget

from harnessboard.library import Part


class PartDetails(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
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
        layout.addStretch(1)

    def show_part(self, part: Part) -> None:
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
