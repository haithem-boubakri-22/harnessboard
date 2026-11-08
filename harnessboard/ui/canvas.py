from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal, QSizeF
from PySide6.QtGui import QColor, QFont, QKeySequence, QPainter, QPen, QPixmap, QTransform, QBrush
from PySide6.QtWidgets import (
    QMessageBox,
    QGraphicsRectItem,
    QGraphicsItem,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
    QMenu,
    QInputDialog,
)

from harnessboard.library import ORIENTATIONS, Library, Part
from harnessboard.ui.cable import SNAP_DISTANCE, CableItem, rounded_path
from harnessboard.ui.harness_dialogs import HarnessBlockPropertiesDialog
from harnessboard.ui.commands import (
    AddPartsCommand,
    MovePartsCommand,
    RemovePartsCommand,
    RotatePartsCommand,
    SetOrientationCommand,
    SetFaceStateCommand,
)

ICON_SIZE = 64
SCENE_RECT = QRectF(0, 0, 4000, 3000)
GRID_STEP = 50

_BADGE_TEXT = {"mir": "M", "rot": "R", "rot_mir": "MR"}
_BIT_TOGGLE = {
    "mirror": {"std": "mir", "mir": "std", "rot": "rot_mir", "rot_mir": "rot"},
    "rotate": {"std": "rot", "rot": "std", "mir": "rot_mir", "rot_mir": "mir"},
}


def part_pixmap(part: Part, face_state: str = "std") -> QPixmap:
    path = part.icon_path
    if face_state == "up" and part.icon_up_path:
        path = part.icon_up_path
    elif face_state == "down" and part.icon_down_path:
        path = part.icon_down_path
        
    pixmap = QPixmap(str(path)) if path else QPixmap()
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
        self.face_state = "std"  # "std", "up", "down"
        self._labels_visible = labels_visible
        w, h = self.pixmap().width(), self.pixmap().height()
        self.setOffset(-w / 2, -h / 2)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setShapeMode(QGraphicsPixmapItem.ShapeMode.BoundingRectShape)

        self.label = QGraphicsSimpleTextItem(part.name, self)
        self.label.setFont(QFont("Segoe UI", 8))
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
    def set_face_state(self, state: str) -> None:
        # Block switching to a face if the image doesn't exist
        if state == "up" and not self.part.icon_up_path:
            return
        if state == "down" and not self.part.icon_down_path:
            return
            
        if state not in ("std", "up", "down"):
            state = "std"
        self.face_state = state
        self._apply_orientation_transform()

    def mouseReleaseEvent(self, event) -> None:
        # Detect a click (without dragging) to cycle the face state
        if event.button() == Qt.MouseButton.LeftButton:
            # We check if the item actually moved. If not, it was a click.
            # (Note: PartItem is already at its new position by the time this fires, 
            # so we rely on a small distance check or just let the user double click)
            pass
        super().mouseReleaseEvent(event)

    def set_orientation(self, orient: str) -> None:
        if orient not in ORIENTATIONS:
            orient = "std"
        self.orientation = orient
        self._apply_orientation_transform()
        self._update_badge()
        self.update()

    def _apply_orientation_transform(self) -> None:
        base_pixmap = part_pixmap(self.part, self.face_state)
        transform = QTransform()
        
        if self.orientation in ("mir", "rot_mir"):
            transform.scale(-1, 1)
        if self.orientation in ("rot", "rot_mir"):
            transform.rotate(90)
            
        transformed = base_pixmap.transformed(transform, Qt.TransformationMode.SmoothTransformation)
        self.setPixmap(transformed)
        
        w, h = transformed.width(), transformed.height()
        self.setOffset(-w / 2, -h / 2)
        self.label.setPos(-self.label.boundingRect().width() / 2, h / 2 + 4)

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
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            if getattr(self, "_is_dragging", False) and self.scene():
                delta = value - self.pos()
                new_center = value + self.rect().center()
                
                for item in self.scene().part_items():
                    # Check if the part is physically inside this block
                    if self.rect().contains(self.mapFromScene(item.pos())):
                        # Only move it if THIS block's center is the closest
                        this_dist = (item.pos() - new_center).manhattanLength()
                        is_closest = True
                        
                        for box in self.scene().harness_boxes():
                            if box is not self:
                                box_center = box.pos() + box.rect().center()
                                other_dist = (item.pos() - box_center).manhattanLength()
                                if other_dist < this_dist:
                                    is_closest = False
                                    break
                        
                        if is_closest:
                            item.setPos(item.pos() + delta)
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
            "face_state": self.face_state,
        }

    def apply_dict(self, data: dict) -> None:
        self.setPos(float(data.get("x", 0)), float(data.get("y", 0)))
        self.setRotation(float(data.get("rotation", 0)))
        self.set_orientation(str(data.get("orientation", "std")))
        self.set_face_state(str(data.get("face_state", "std")))



class HarnessBoxItem(QGraphicsRectItem):
    """A visual box representing a single harness on the board, with a title block."""
    def __init__(self, name: str = "New Harness", rect=QRectF(0, 0, 800, 600)) -> None:
        super().__init__(rect)
        self.name = name
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        
        self.setPen(QPen(QColor("#d81b60"), 1.5, Qt.PenStyle.SolidLine))
        self.setBrush(QColor(216, 27, 96, 10)) 
        self.setZValue(-10) 
        
        self._block_moves = False
        self._is_dragging = False
        self.has_casing = False
        self.casing_z = 30.0
        self._resizing = False
        self._resize_start_pos = None
        self._resize_start_rect = None

    def update_label(self):
        self.update()

    def set_name(self, new_name: str):
        self.name = new_name
        self.update_label()

    def _overlaps_other_blocks(self, proposed_rect: QRectF) -> bool:
        if not self.scene():
            return False
        for other in self.scene().harness_boxes():
            if other is not self:
                if proposed_rect.intersects(other.rect().translated(other.pos())):
                    return True
        return False

    def boundingRect(self) -> QRectF:
        # Inflate by a few pixels so Qt clears the pen outline and handle when moving
        return self.rect().adjusted(-3, -3, 3, 3)

    def paint(self, painter: QPainter, option, widget=None):
        rect = self.rect()
        
        # 1. Draw the base pink rectangle
        painter.setPen(self.pen())
        painter.setBrush(self.brush())
        painter.drawRect(rect)
        
        # 2. Draw the title block (clamped to the box size so it doesn't spill)
        block_w = min(rect.width(), max(150, len(self.name) * 12 + 40))
        block_h = min(rect.height(), 40)
        
        if block_w > 0 and block_h > 0:
            painter.setPen(QPen(QColor("#000000"), 1.0))
            painter.setBrush(QBrush(QColor("#ffffff")))
            table_rect = QRectF(rect.left(), rect.top(), block_w, block_h)
            painter.drawRect(table_rect)
            
            # Vertical separator inside table
            if block_w > 20:
                painter.drawLine(
                    QPointF(rect.left() + block_w * 0.7, rect.top()),
                    QPointF(rect.left() + block_w * 0.7, rect.top() + block_h)
                )
            
            # 3. Draw the text directly in the paint event
            if block_h > 10:
                painter.setPen(QColor("#000000"))
                font = QFont("", 10, QFont.Weight.Bold)
                painter.setFont(font)
                text_rect = table_rect.adjusted(5, 0, -5, 0)
                
                text = self.name
                if self.has_casing:
                    text += f" (Casing Z{self.casing_z:g})"
                    
                painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, text)
        
        # 4. Draw the resize handle
        if self.isSelected() or self._resizing:
            painter.setPen(QPen(QColor("#d81b60"), 1.0))
            painter.setBrush(QColor("#d81b60"))
            handle_size = 10
            hr = QRectF(
                rect.right() - handle_size, 
                rect.bottom() - handle_size, 
                handle_size, 
                handle_size
            )
            painter.drawRect(hr)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            # Check if clicking the bottom-right resize handle (15x15 area)
            if (event.pos().x() >= self.rect().width() - 15 and 
                event.pos().y() >= self.rect().height() - 15):
                self._resizing = True
                self._resize_start_pos = event.pos()
                self._resize_start_rect = self.rect()
                event.accept()
                return
            self._is_dragging = True
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._resizing:
            delta = event.pos() - self._resize_start_pos
            new_w = max(150, self._resize_start_rect.width() + delta.x())
            new_h = max(80, self._resize_start_rect.height() + delta.y())
            
            proposed_rect = QRectF(self.pos().x(), self.pos().y(), new_w, new_h)
            if not self._overlaps_other_blocks(proposed_rect):
                self.setRect(0, 0, new_w, new_h)
                
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._resizing:
            self._resizing = False
            event.accept()
            return
        self._is_dragging = False
        super().mouseReleaseEvent(event)

    def hoverMoveEvent(self, event):
        if (event.pos().x() >= self.rect().width() - 15 and 
            event.pos().y() >= self.rect().height() - 15):
            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)
        super().hoverMoveEvent(event)

    def mouseDoubleClickEvent(self, event):
        self.open_properties()
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event):
        menu = QMenu()
        action = menu.addAction("Properties...")
        action.triggered.connect(self.open_properties)
        
        # Signal up to MainWindow to open this block standalone
        scene = self.scene()
        if scene is not None:
            standalone_action = menu.addAction("Open this block standalone...")
            standalone_action.triggered.connect(lambda: scene.open_block_standalone_requested.emit(self))
        
        menu.exec(event.screenPos())

    def open_properties(self):
        dlg = HarnessBlockPropertiesDialog(self.name, self.has_casing, self.casing_z)
        if not dlg.exec():
            return
        new_name, new_casing, new_z = dlg.get_values()
        if not new_name:
            new_name = self.name
        if new_name != self.name:
            scene = self.scene()
            if scene is not None:
                for box in scene.harness_boxes():
                    if box is not self and box.name.lower() == new_name.lower():
                        msg = "A harness block named '" + new_name + "' already exists." + chr(10) + "Names must be unique."
                        QMessageBox.warning(None, "Duplicate Name", msg)
                        return
        scene = self.scene()
        if scene is not None and hasattr(scene, "undo_stack"):
            from harnessboard.ui.commands import SetBlockPropertiesCommand
            scene.undo_stack.push(
                SetBlockPropertiesCommand(self, new_name, new_casing, new_z)
            )
        else:
            self.name = new_name
            self.has_casing = new_casing
            self.casing_z = new_z
            self.update_label()
            self.update()

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            if self.scene():
                # 1. Overlap checks
                current_rect = self.rect().translated(self.pos())
                was_overlapping = self.scene().overlaps_any_box(current_rect, exclude=self)
                proposed_rect = self.rect().translated(value)
                will_overlap = self.scene().overlaps_any_box(proposed_rect, exclude=self)
                
                if will_overlap and not was_overlapping:
                    return self.pos()

                # 2. Move parts if we are selected (dragging) AND NOT during undo/redo
                if not getattr(self, "_block_moves", False) and self.isSelected():
                    delta = value - self.pos()
                    new_center = value + self.rect().center()
                    
                    for item in self.scene().part_items():
                        # Only move parts that are NOT selected (Qt moves selected parts automatically)
                        if not item.isSelected() and self.rect().contains(self.mapFromScene(item.pos())):
                            this_dist = (item.pos() - new_center).manhattanLength()
                            is_closest = True
                            
                            for box in self.scene().harness_boxes():
                                if box is not self:
                                    box_center = box.pos() + box.rect().center()
                                    other_dist = (item.pos() - box_center).manhattanLength()
                                    if other_dist < this_dist:
                                        is_closest = False
                                        break
                                        
                            if is_closest:
                                item.setPos(item.pos() + delta)
        return super().itemChange(change, value)

    def to_dict(self) -> dict:
        r = self.rect()
        return {
            "name": self.name,
            "x": self.pos().x(),
            "y": self.pos().y(),
            "w": r.width(),
            "h": r.height(),
            "has_casing": self.has_casing,
            "casing_z": self.casing_z
        }

    def apply_dict(self, data: dict):
        self.setPos(float(data.get("x", 0)), float(data.get("y", 0)))
        self.setRect(0, 0, float(data.get("w", 800)), float(data.get("h", 600)))
        self.name = str(data.get("name", "Harness"))
        self.has_casing = bool(data.get("has_casing", False))
        self.casing_z = float(data.get("casing_z", 30.0))
        self.update_label()
        self._block_moves = False
        self._is_dragging = False # Unfreeze

from PySide6.QtCore import Signal as _Signal


class BoardScene(QGraphicsScene):
    open_block_standalone_requested = _Signal(object)

    def __init__(self, undo_stack, parent=None) -> None:
        super().__init__(SCENE_RECT, parent)
        self.undo_stack = undo_stack
        self.labels_visible = True
        self._move_start: dict = {}

    # --- part queries -------------------------------------------------
    def part_items(self) -> list[PartItem]:
        return [i for i in self.items() if isinstance(i, PartItem)]

    def harness_boxes(self) -> list[HarnessBoxItem]:
        return [i for i in self.items() if isinstance(i, HarnessBoxItem)]

    def overlaps_any_box(self, proposed_rect: QRectF, exclude=None) -> bool:
        for other in self.harness_boxes():
            if other is not exclude:
                if proposed_rect.intersects(other.rect().translated(other.pos())):
                    return True
        return False

    def next_harness_name(self) -> str:
        existing = {b.name.lower() for b in self.harness_boxes()}
        i = 1
        while ("harness " + str(i)) in existing:
            i += 1
        return "Harness " + str(i)
        
    def selected_boxes(self) -> list[HarnessBoxItem]:
        return [i for i in self.selectedItems() if isinstance(i, HarnessBoxItem)]

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
        # If right-clicking a Harness Block (and not a part on top of it), let the block handle it.
        for it in self.items(event.scenePos()):
            if isinstance(it, (PartItem, CableItem)):
                break  # Found a part/cable, let it handle the right-click normally
            if isinstance(it, HarnessBoxItem):
                super().contextMenuEvent(event)
                return

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
        
        # Face State submenu
        face_menu = menu.addMenu("Face State")
        common_face = selected[0].face_state
        for item in selected[1:]:
            if item.face_state != common_face:
                common_face = None
                break
                
        for f_state, f_label in (("std", "Standard"), ("up", "Face Up"), ("down", "Face Down")):
            action = face_menu.addAction(f_label)
            action.setCheckable(True)
            action.setChecked(common_face == f_state)
            action.triggered.connect(
                lambda checked=False, s=f_state, items=list(selected): 
                self.undo_stack.push(SetFaceStateCommand(items, s))
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
            items_to_move = self.selected_parts() + self.selected_boxes()
            for box in self.selected_boxes():
                for item in self.part_items():
                    if box.sceneBoundingRect().contains(item.pos()) and item not in items_to_move:
                        items_to_move.append(item)
            self._move_start = {i: QPointF(i.pos()) for i in items_to_move}

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
            "boxes": [b.to_dict() for b in self.harness_boxes()],
            "parts": [item.to_dict() for item in parts],
            "cables": [cable.to_dict(part_index) for cable in self.cable_items()],
        }

    def load_dict(self, data: dict, library: Library) -> list[str]:
        warnings: list[str] = []
        self.clear()
        self.undo_stack.clear()
        self.labels_visible = bool(data.get("labels_visible", True))
        for entry in data.get("boxes", []):
            box = HarnessBoxItem()
            box.apply_dict(entry)
            self.addItem(box)

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
        self._drawing_box = False
        self._box_start = None
        self._preview_box = None

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
        boxes = self.board_scene.selected_boxes()
        for box in boxes:
            for item in self.board_scene.part_items():
                if box.sceneBoundingRect().contains(item.pos()) and item not in parts:
                    parts.append(item)
        items = parts + cables + boxes
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

    def set_face_state(self, state: str) -> None:
        items = self.board_scene.selected_parts()
        if items:
            self.board_scene.undo_stack.push(SetFaceStateCommand(items, state))
            self.statusMessage.emit(f"Face state → {state}")

    def _toggle_orientation_bit(self, bit: str) -> None:
        items = self.board_scene.selected_parts()
        if not items:
            return
        target = _BIT_TOGGLE[bit][items[0].orientation]
        self.board_scene.undo_stack.push(SetOrientationCommand(items, target))
        self.statusMessage.emit(f"Orientation → {target}")

    def copy_selected(self) -> None:
        boxes = self.board_scene.selected_boxes()
        items = self.board_scene.selected_parts()
        for box in boxes:
            for item in self.board_scene.part_items():
                if box.sceneBoundingRect().contains(item.pos()) and item not in items:
                    items.append(item)
        self._clipboard = [item.to_dict() for item in items]
        self._clipboard_parts = {item.part.name: item.part for item in items}
        self._clipboard_boxes = [b.to_dict() for b in boxes]

    def paste(self) -> None:
        if not getattr(self, "_clipboard", None) and not getattr(self, "_clipboard_boxes", None):
            return
            
        paste_delta = QPointF(50, 50)
        
        if getattr(self, "_clipboard_boxes", None):
            test_box = HarnessBoxItem()
            test_box.apply_dict(self._clipboard_boxes[0])
            
            boxes = self.board_scene.harness_boxes()
            if boxes:
                # Grid: 2 columns, matches the reference PDF layout
                GAP = 150
                COLUMNS = 2
                
                # Anchor = top-left of the block grid (uses pos() and rect() for precision)
                anchor_x = min(b.pos().x() for b in boxes)
                anchor_y = min(b.pos().y() for b in boxes)
                
                # Cell size = max of all blocks (past + new) so they never collide
                all_w = [b.rect().width() for b in boxes] + [test_box.rect().width()]
                all_h = [b.rect().height() for b in boxes] + [test_box.rect().height()]
                cell_w = max(all_w) + GAP
                cell_h = max(all_h) + GAP
                
                # Where does this new block belong in the grid?
                idx = len(boxes)   # 0-indexed slot for the new block
                col = idx % COLUMNS
                row = idx // COLUMNS
                
                new_pos = QPointF(anchor_x + col * cell_w, anchor_y + row * cell_h)
                
                # Collision fallback (only if user manually scattered blocks in weird places)
                for _ in range(50):
                    test_rect = QRectF(new_pos.x(), new_pos.y(),
                                       test_box.rect().width(), test_box.rect().height())
                    if not self.board_scene.overlaps_any_box(test_rect):
                        break
                    row += 1
                    new_pos = QPointF(anchor_x + col * cell_w, anchor_y + row * cell_h)
                    
                paste_delta = new_pos - test_box.pos()

        new_items = []
        
        for entry in getattr(self, "_clipboard_boxes", []):
            box = HarnessBoxItem()
            box.apply_dict(entry)
            box.set_name(self.board_scene.next_harness_name())
            box.setPos(box.pos() + paste_delta)
            new_items.append(box)
            
        for entry in getattr(self, "_clipboard", []):
            part = getattr(self, "_clipboard_parts", {}).get(entry["name"])
            if part is None:
                continue
            item = PartItem(part, self.board_scene.labels_visible)
            item.apply_dict(entry)
            item.setPos(item.pos() + paste_delta)
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
        # --- Ctrl+Drag to draw Harness Block ---
        if event.button() == Qt.MouseButton.LeftButton and (event.modifiers() & Qt.KeyboardModifier.ControlModifier):
            scene_pos = self.mapToScene(event.position().toPoint())
            items_under_cursor = self.board_scene.items(scene_pos)
            # Only draw if clicking on empty space (no parts, cables, or existing boxes)
            if not any(isinstance(i, (PartItem, CableItem, HarnessBoxItem)) for i in items_under_cursor):
                self._drawing_box = True
                self._box_start = scene_pos
                self._preview_box = QGraphicsRectItem()
                pen = QPen(QColor("#d81b60"), 1.5, Qt.PenStyle.DashLine)
                self._preview_box.setPen(pen)
                self._preview_box.setBrush(QColor(216, 27, 96, 20))
                self._preview_box.setZValue(1000)
                self.board_scene.addItem(self._preview_box)
                event.accept()
                return

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
        if self._drawing_box and self._preview_box:
            current_pos = self.mapToScene(event.position().toPoint())
            rect = QRectF(self._box_start, current_pos).normalized()
            self._preview_box.setRect(rect)
            event.accept()
            return

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
        if self._drawing_box and event.button() == Qt.MouseButton.LeftButton:
            self._drawing_box = False
            rect = self._preview_box.rect()
            self.board_scene.removeItem(self._preview_box)
            self._preview_box = None
            
            # Only create the box if it's large enough (prevents accidental clicks)
            if rect.width() > 50 and rect.height() > 50:
                box = HarnessBoxItem(self.board_scene.next_harness_name())
                box.setRect(0, 0, rect.width(), rect.height())
                box.setPos(rect.topLeft())
                self.board_scene.undo_stack.push(
                    AddPartsCommand(self.board_scene, [box], "Draw Harness Block")
                )
                self.board_scene.clearSelection()
                box.setSelected(True)
            event.accept()
            return

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
        elif key == Qt.Key.Key_U:
            self.set_face_state("up")
        elif key == Qt.Key.Key_D:
            self.set_face_state("down")
        elif key == Qt.Key.Key_S:
            self.set_face_state("std")
        elif event.matches(QKeySequence.StandardKey.Copy):
            self.copy_selected()
        elif event.matches(QKeySequence.StandardKey.Paste):
            self.paste()
        else:
            super().keyPressEvent(event)
