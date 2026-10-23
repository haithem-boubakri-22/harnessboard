from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QKeySequence, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
    QMenu,
)

from harnessboard.library import ORIENTATIONS, Library, Part
from harnessboard.ui.cable import SNAP_DISTANCE, CableItem, rounded_path
from harnessboard.ui.commands import (
    AddPartsCommand,
    MovePartsCommand,
    RemovePartsCommand,
    RotatePartsCommand,
    SetOrientationCommand,
)

ICON_SIZE = 64
SCENE_RECT = QRectF(0, 0, 4000, 3000)
GRID_STEP = 50

_BADGE_TEXT = {"mir": "M", "rot": "R", "rot_mir": "MR"}
_BIT_TOGGLE = {
    "mirror": {"std": "mir", "mir": "std", "rot": "rot_mir", "rot_mir": "rot"},
    "rotate": {"std": "rot", "rot": "std", "mir": "rot_mir", "rot_mir": "mir"},
}


def part_pixmap(part: Part) -> QPixmap:
    pixmap = QPixmap(str(part.icon_path)) if part.icon_path else QPixmap()
    if pixmap.isNull():
        pixmap = QPixmap(ICON_SIZE, ICON_SIZE)
        pixmap.fill(QColor("#c0c0c0"))
    return pixmap.scaled(
        ICON_SIZE, ICON_SIZE,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )


class PartItem(QGraphicsPixmapItem):
    """A placed part. Item position = icon center (offset is negative half-size)."""

    def __init__(self, part: Part, labels_visible: bool = True) -> None:
        super().__init__(part_pixmap(part))
        self.part = part
        self.orientation = "std"
        self._labels_visible = labels_visible
        w, h = self.pixmap().width(), self.pixmap().height()
        self.setOffset(-w / 2, -h / 2)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setShapeMode(QGraphicsPixmapItem.ShapeMode.BoundingRectShape)

        self.label = QGraphicsSimpleTextItem(part.name, self)
        self.label.setFont(QFont("Segoe UI", 8))
        self.label.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.label.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
        rect = self.label.boundingRect()
        self.label.setPos(-rect.width() / 2, h / 2 + 4)
        self.label.setVisible(labels_visible)

        # Small orientation badge, top-right corner. Hidden for "std".
        self.badge = QGraphicsSimpleTextItem("", self)
        self.badge.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
        self.badge.setBrush(QColor("#c00000"))
        self.badge.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
        self.badge.setZValue(10)
        self.badge.setVisible(False)

    # --- orientation ------------------------------------------------
    def set_orientation(self, orient: str) -> None:
        if orient not in ORIENTATIONS:
            orient = "std"
        self.orientation = orient
        self._update_badge()
        self.update()

    def _update_badge(self) -> None:
        if self.orientation == "std" or not self._labels_visible:
            self.badge.setVisible(False)
            return
        self.badge.setText(_BADGE_TEXT[self.orientation])
        r = self.badge.boundingRect()
        w = self.pixmap().width()
        h = self.pixmap().height()
        self.badge.setPos(w / 2 - r.width(), -h / 2)
        self.badge.setVisible(True)

    def set_labels_visible(self, visible: bool) -> None:
        self._labels_visible = visible
        self.label.setVisible(visible)
        self._update_badge()

    # --- Qt hooks ---------------------------------------------------
    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            scene = self.scene()
            if isinstance(scene, BoardScene):
                scene.part_moved(self)
        return super().itemChange(change, value)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        super().paint(painter, option, widget)
        if self.isSelected():
            pen = QPen(QColor("#0078d7"), 1.5, Qt.PenStyle.DashLine)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self.boundingRect().adjusted(1, 1, -1, -1))

    # --- serialization ----------------------------------------------
    def to_dict(self) -> dict:
        return {
            "name": self.part.name,
            "x": self.pos().x(),
            "y": self.pos().y(),
            "rotation": self.rotation(),
            "orientation": self.orientation,
            "label_x": self.label.pos().x(),
            "label_y": self.label.pos().y(),
        }

    def apply_dict(self, data: dict) -> None:
        self.setPos(float(data.get("x", 0)), float(data.get("y", 0)))
        self.setRotation(float(data.get("rotation", 0)))
        if "label_x" in data:
            self.label.setPos(float(data["label_x"]), float(data["label_y"]))
        self.set_orientation(str(data.get("orientation", "std")))


class BoardScene(QGraphicsScene):
    def __init__(self, undo_stack, parent=None) -> None:
        super().__init__(SCENE_RECT, parent)
        self.undo_stack = undo_stack
        self.labels_visible = True
        self._move_start: dict = {}

    # --- part queries -------------------------------------------------
    def part_items(self) -> list[PartItem]:
        return [i for i in self.items() if isinstance(i, PartItem)]

    def selected_parts(self) -> list[PartItem]:
        return [i for i in self.selectedItems() if isinstance(i, PartItem)]

    # --- cables ---------------------------------------------------------
    def cable_items(self) -> list[CableItem]:
        return [i for i in self.items() if isinstance(i, CableItem)]

    def selected_cables(self) -> list[CableItem]:
        return [i for i in self.selectedItems() if isinstance(i, CableItem)]

    def part_moved(self, part_item: PartItem) -> None:
        for cable in self.cable_items():
            if cable.start_item is part_item or cable.end_item is part_item:
                cable.update_path()

    def part_attached(self, part_item: PartItem) -> bool:
        return any(
            c.start_item is part_item or c.end_item is part_item
            for c in self.cable_items()
        )

    def nearest_cable(self, pos: QPointF, max_dist: float = SNAP_DISTANCE):
        best = None
        best_point = None
        best_d = max_dist
        for cable in self.cable_items():
            point, d = cable.nearest_point(pos)
            if d < best_d:
                best, best_point, best_d = cable, point, d
        return (best, best_point) if best is not None else (None, None)

    # --- labels -------------------------------------------------------
    def set_labels_visible(self, visible: bool) -> None:
        self.labels_visible = visible
        for item in self.part_items():
            item.set_labels_visible(visible)
        for cable in self.cable_items():
            cable.label.setVisible(visible)

    # --- context menu (NEW) -------------------------------------------
    def contextMenuEvent(self, event) -> None:
        # Select the part under the cursor if it isn't already selected.
        for it in self.items(event.scenePos()):
            part_item = it if isinstance(it, PartItem) else (
                it.parentItem() if isinstance(it.parentItem(), PartItem) else None
            )
            if part_item is not None:
                if not part_item.isSelected():
                    self.clearSelection()
                    part_item.setSelected(True)
                break

        selected = self.selected_parts()
        if not selected:
            super().contextMenuEvent(event)
            return

        menu = QMenu()
        orient_menu = menu.addMenu("Orientation")
        common = selected[0].orientation
        for item in selected[1:]:
            if item.orientation != common:
                common = None
                break
        for orient in ORIENTATIONS:
            action = orient_menu.addAction(orient)
            action.setCheckable(True)
            action.setChecked(common == orient)
            action.triggered.connect(
                lambda checked=False, o=orient, items=list(selected):
                self.undo_stack.push(SetOrientationCommand(items, o))
            )

        menu.addSeparator()
        menu.addAction(
            "Rotate 15° CW (R)",
            lambda: self.undo_stack.push(RotatePartsCommand(list(selected), 15)),
        )
        menu.addAction(
            "Rotate 15° CCW (Shift+R)",
            lambda: self.undo_stack.push(RotatePartsCommand(list(selected), -15)),
        )
        menu.exec(event.screenPos())

    # --- undoable move tracking ----------------------------------------
    def mousePressEvent(self, event) -> None:
        super().mousePressEvent(event)
        if event.button() == Qt.MouseButton.LeftButton:
            self._move_start = {i: QPointF(i.pos()) for i in self.selected_parts()}

    def mouseReleaseEvent(self, event) -> None:
        super().mouseReleaseEvent(event)
        if event.button() == Qt.MouseButton.LeftButton and self._move_start:
            moves = {
                item: (old, QPointF(item.pos()))
                for item, old in self._move_start.items()
                if item.pos() != old
            }
            if moves:
                self.undo_stack.push(MovePartsCommand(moves))
            self._move_start = {}

    # --- serialization --------------------------------------------------
    def to_dict(self) -> dict:
        parts = sorted(self.part_items(), key=lambda i: (i.pos().y(), i.pos().x()))
        part_index = {item: i for i, item in enumerate(parts)}
        return {
            "app": "HarnessBoard",
            "version": 2,
            "labels_visible": self.labels_visible,
            "parts": [item.to_dict() for item in parts],
            "cables": [cable.to_dict(part_index) for cable in self.cable_items()],
        }

    def load_dict(self, data: dict, library: Library) -> list[str]:
        warnings: list[str] = []
        self.clear()
        self.undo_stack.clear()
        self.labels_visible = bool(data.get("labels_visible", True))
        loaded_parts: list[PartItem | None] = []
        for entry in data.get("parts", []):
            name = str(entry.get("name", ""))
            part = library.part_by_name(name)
            if part is None:
                warnings.append(f"Part not in library, skipped: {name}")
                loaded_parts.append(None)
                continue
            item = PartItem(part, self.labels_visible)
            item.apply_dict(entry)
            self.addItem(item)
            loaded_parts.append(item)
        for entry in data.get("cables", []):
            cable = CableItem.from_dict(entry, loaded_parts, self.labels_visible)
            self.addItem(cable)
        return warnings


class BoardView(QGraphicsView):
    partsDeleted = Signal(list)
    statusMessage = Signal(str)

    def __init__(self, scene: BoardScene, parent=None) -> None:
        super().__init__(scene, parent)
        self.board_scene = scene
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setBackgroundBrush(QColor("#fafafa"))
        self._pending_part: Part | None = None
        self._ghost: QGraphicsPixmapItem | None = None
        self._pan_last = None
        self._clipboard: list[dict] = []
        self._clipboard_parts: dict[str, Part] = {}
        self._cable_designation: str | None = None
        self._cable_diameter: float = 0.0
        self._cable_points: list[QPointF] = []
        self._cable_start_item: PartItem | None = None
        self._cable_preview = None

    # --- background grid -------------------------------------------------
    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:
        super().drawBackground(painter, rect)
        pen = QPen(QColor(0, 0, 0, 18))
        pen.setCosmetic(True)
        painter.setPen(pen)
        left = int(rect.left()) - int(rect.left()) % GRID_STEP
        top = int(rect.top()) - int(rect.top()) % GRID_STEP
        x = left
        while x < rect.right():
            painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
            x += GRID_STEP
        y = top
        while y < rect.bottom():
            painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
            y += GRID_STEP

    # --- placement mode ---------------------------------------------------
    def place_part(self, part: Part) -> None:
        self.cancel_placement()
        self.cancel_cable()
        self._pending_part = part
        self._ghost = QGraphicsPixmapItem(part_pixmap(part))
        w, h = self._ghost.pixmap().width(), self._ghost.pixmap().height()
        self._ghost.setOffset(-w / 2, -h / 2)
        self._ghost.setOpacity(0.5)
        self._ghost.setZValue(1000)
        self.board_scene.addItem(self._ghost)
        cursor_pos = self.mapToScene(self.mapFromGlobal(self.cursor().pos()))
        self._ghost.setPos(cursor_pos)
        self.viewport().setCursor(Qt.CursorShape.CrossCursor)
        self.setFocus()

    def cancel_placement(self) -> None:
        if self._ghost is not None:
            self.board_scene.removeItem(self._ghost)
            self._ghost = None
        self._pending_part = None
        self.viewport().unsetCursor()

    @property
    def is_placing(self) -> bool:
        return self._pending_part is not None

    # --- cable drawing mode -------------------------------------------------
    def draw_cable(self, designation: str, diameter: float) -> None:
        self.cancel_placement()
        self.cancel_cable()
        self._cable_designation = designation
        self._cable_diameter = diameter
        self.viewport().setCursor(Qt.CursorShape.CrossCursor)
        self.setFocus()
        self.statusMessage.emit(
            f"Drawing cable {designation} (Ø{diameter:g} mm) — click points; "
            "click a part to attach; double-click to finish; Esc cancels"
        )

    def cancel_cable(self) -> None:
        if self._cable_preview is not None:
            self.board_scene.removeItem(self._cable_preview)
            self._cable_preview = None
        self._cable_designation = None
        self._cable_points = []
        self._cable_start_item = None
        self.viewport().unsetCursor()

    @property
    def is_drawing_cable(self) -> bool:
        return self._cable_designation is not None

    def _part_at(self, scene_pos: QPointF) -> PartItem | None:
        for item in self.board_scene.items(scene_pos):
            if isinstance(item, PartItem):
                return item
        return None

    def _update_cable_preview(self, cursor_pos: QPointF | None) -> None:
        from PySide6.QtWidgets import QGraphicsPathItem

        pts = list(self._cable_points)
        if cursor_pos is not None:
            pts.append(cursor_pos)
        if len(pts) < 2:
            return
        if self._cable_preview is None:
            self._cable_preview = QGraphicsPathItem()
            pen = QPen(QColor("#888888"), max(2.0, min(self._cable_diameter, 12.0)),
                       Qt.PenStyle.DashLine)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            self._cable_preview.setPen(pen)
            self._cable_preview.setZValue(999)
            self.board_scene.addItem(self._cable_preview)
        self._cable_preview.setPath(rounded_path(pts))

    def _cable_click(self, scene_pos: QPointF) -> None:
        part = self._part_at(scene_pos)
        attach = None
        point = scene_pos
        if part is not None:
            if self.board_scene.part_attached(part):
                self.statusMessage.emit(
                    f"{part.part.name} already has a cable (one cable per attachment) "
                    "— point placed next to it instead"
                )
            else:
                attach = part
                point = part.pos()

        if not self._cable_points:
            self._cable_points = [QPointF(point)]
            self._cable_start_item = attach
            return

        self._cable_points.append(QPointF(point))
        if attach is not None:
            self._finish_cable(end_item=attach)

    def _finish_cable(self, end_item: PartItem | None = None) -> None:
        if len(self._cable_points) >= 2 and self._cable_designation is not None:
            cable = CableItem(
                self._cable_designation,
                self._cable_diameter,
                self._cable_points,
                start_item=self._cable_start_item,
                end_item=end_item,
                labels_visible=self.board_scene.labels_visible,
            )
            self.board_scene.undo_stack.push(
                AddPartsCommand(self.board_scene, [cable], "Draw cable")
            )
            self.statusMessage.emit(f"Cable {self._cable_designation} drawn")
        self.cancel_cable()

    # --- editing operations ------------------------------------------------
    def delete_selected(self) -> None:
        parts = self.board_scene.selected_parts()
        cables = self.board_scene.selected_cables()
        items = parts + cables
        if items:
            names = [item.part.name for item in parts]
            self.board_scene.undo_stack.push(
                RemovePartsCommand(self.board_scene, items)
            )
            if names:
                self.partsDeleted.emit(names)

    def rotate_selected(self, delta: float) -> None:
        items = self.board_scene.selected_parts()
        if items:
            self.board_scene.undo_stack.push(RotatePartsCommand(items, delta))

    def _toggle_orientation_bit(self, bit: str) -> None:
        items = self.board_scene.selected_parts()
        if not items:
            return
        target = _BIT_TOGGLE[bit][items[0].orientation]
        self.board_scene.undo_stack.push(SetOrientationCommand(items, target))
        self.statusMessage.emit(f"Orientation → {target}")

    def copy_selected(self) -> None:
        items = self.board_scene.selected_parts()
        self._clipboard = [item.to_dict() for item in items]
        self._clipboard_parts = {item.part.name: item.part for item in items}

    def paste(self) -> None:
        if not self._clipboard:
            return
        new_items = []
        for entry in self._clipboard:
            part = self._clipboard_parts.get(entry["name"])
            if part is None:
                continue
            item = PartItem(part, self.board_scene.labels_visible)
            item.apply_dict(entry)
            item.setPos(item.pos() + QPointF(24, 24))
            new_items.append(item)
        if new_items:
            self.board_scene.undo_stack.push(
                AddPartsCommand(self.board_scene, new_items, "Paste part(s)")
            )
            self.board_scene.clearSelection()
            for item in new_items:
                item.setSelected(True)

    # --- zoom ----------------------------------------------------------------
    def zoom(self, factor: float) -> None:
        current = self.transform().m11()
        if 0.1 <= current * factor <= 8.0:
            self.scale(factor, factor)

    def zoom_fit(self) -> None:
        items = self.board_scene.part_items()
        if not items:
            return
        rect = QRectF()
        for item in items:
            rect = rect.united(item.sceneBoundingRect())
        self.fitInView(rect.adjusted(-80, -80, 80, 80), Qt.AspectRatioMode.KeepAspectRatio)

    def wheelEvent(self, event) -> None:
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self.zoom(factor)

    # --- mouse ------------------------------------------------------------
    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.MiddleButton:
            self._pan_last = event.position()
            self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        if self.is_drawing_cable:
            scene_pos = self.mapToScene(event.position().toPoint())
            if event.button() == Qt.MouseButton.LeftButton:
                self._cable_click(scene_pos)
                event.accept()
                return
            if event.button() == Qt.MouseButton.RightButton:
                if self._cable_points:
                    self._cable_points.pop()
                    self._update_cable_preview(scene_pos)
                else:
                    self.cancel_cable()
                event.accept()
                return
        if self._pending_part is not None:
            if event.button() == Qt.MouseButton.LeftButton:
                item = PartItem(self._pending_part, self.board_scene.labels_visible)
                drop_pos = self.mapToScene(event.position().toPoint())
                cable, snap_point = self.board_scene.nearest_cable(drop_pos)
                item.setPos(snap_point if cable is not None else drop_pos)
                self.board_scene.undo_stack.push(
                    AddPartsCommand(self.board_scene, [item])
                )
                keep_placing = bool(
                    event.modifiers() & Qt.KeyboardModifier.ControlModifier
                )
                if not keep_placing:
                    self.cancel_placement()
                    self.board_scene.clearSelection()
                    item.setSelected(True)
                event.accept()
                return
            if event.button() == Qt.MouseButton.RightButton:
                self.cancel_placement()
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._pan_last is not None:
            delta = event.position() - self._pan_last
            self._pan_last = event.position()
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - int(delta.x())
            )
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - int(delta.y())
            )
            event.accept()
            return
        if self._ghost is not None:
            self._ghost.setPos(self.mapToScene(event.position().toPoint()))
        if self.is_drawing_cable and self._cable_points:
            self._update_cable_preview(self.mapToScene(event.position().toPoint()))
        super().mouseMoveEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        if self.is_drawing_cable:
            self._finish_cable()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.MiddleButton:
            self._pan_last = None
            self.viewport().unsetCursor()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    # --- keyboard ------------------------------------------------------------
    def keyPressEvent(self, event) -> None:
        key = event.key()
        if key == Qt.Key.Key_Escape:
            if self.is_drawing_cable:
                self.cancel_cable()
            elif self.is_placing:
                self.cancel_placement()
            else:
                self.board_scene.clearSelection()
        elif key == Qt.Key.Key_Delete:
            self.delete_selected()
        elif key == Qt.Key.Key_R:
            delta = -15.0 if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else 15.0
            self.rotate_selected(delta)
        elif key == Qt.Key.Key_M:
            self._toggle_orientation_bit("mirror")
        elif key == Qt.Key.Key_O:
            self._toggle_orientation_bit("rotate")
        elif event.matches(QKeySequence.StandardKey.Copy):
            self.copy_selected()
        elif event.matches(QKeySequence.StandardKey.Paste):
            self.paste()
        else:
            super().keyPressEvent(event)
