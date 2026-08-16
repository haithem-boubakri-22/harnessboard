"""Cable graphics item: a polyline with auto-rounded corners (SPEC.md §5).

A cable carries its designation and diameter. Its two endpoints may be
attached to parts (one cable per attachment); attached endpoints follow the
part when it moves. Line width scales with the cable diameter.
"""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QFont, QPainterPath, QPainterPathStroker, QPen
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsPathItem,
    QGraphicsSimpleTextItem,
)

CORNER_RADIUS = 28.0
SNAP_DISTANCE = 20.0


def _dist(a: QPointF, b: QPointF) -> float:
    return math.hypot(a.x() - b.x(), a.y() - b.y())


def rounded_path(points: list[QPointF], radius: float = CORNER_RADIUS) -> QPainterPath:
    path = QPainterPath()
    if not points:
        return path
    path.moveTo(points[0])
    for i in range(1, len(points) - 1):
        prev, corner, nxt = points[i - 1], points[i], points[i + 1]
        len_in = _dist(prev, corner)
        len_out = _dist(corner, nxt)
        if len_in < 1e-6 or len_out < 1e-6:
            continue
        r = min(radius, len_in / 2, len_out / 2)
        entry = corner + (prev - corner) * (r / len_in)
        exit_ = corner + (nxt - corner) * (r / len_out)
        path.lineTo(entry)
        path.quadTo(corner, exit_)
    path.lineTo(points[-1])
    return path


def nearest_point_on_segment(p: QPointF, a: QPointF, b: QPointF) -> QPointF:
    ab = b - a
    denominator = ab.x() ** 2 + ab.y() ** 2
    if denominator < 1e-9:
        return QPointF(a)
    t = ((p.x() - a.x()) * ab.x() + (p.y() - a.y()) * ab.y()) / denominator
    t = max(0.0, min(1.0, t))
    return QPointF(a.x() + ab.x() * t, a.y() + ab.y() * t)


class _CableLabel(QGraphicsSimpleTextItem):
    """Designation label; remembers when the user drags it manually."""

    def itemChange(self, change, value):
        if (
            change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged
            and isinstance(self.parentItem(), CableItem)
            and not self.parentItem()._auto_positioning
        ):
            self.parentItem()._label_moved = True
        return super().itemChange(change, value)


class CableItem(QGraphicsPathItem):
    def __init__(
        self,
        designation: str,
        diameter: float,
        points: list[QPointF],
        start_item=None,
        end_item=None,
        labels_visible: bool = True,
    ) -> None:
        super().__init__()
        self.designation = designation
        self.diameter = float(diameter)
        self.points = [QPointF(p) for p in points]
        self.start_item = start_item
        self.end_item = end_item

        width = max(2.0, min(self.diameter, 12.0))
        pen = QPen(QColor("#1a1a1a"), width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        self.setPen(pen)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setZValue(-1)  # cables run under part icons

        self._label_moved = False
        self._auto_positioning = False
        self.label = _CableLabel(designation, self)
        self.label.setFont(QFont("Segoe UI", 8))
        self.label.setBrush(QColor("#555555"))
        self.label.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.label.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.label.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
        self.label.setVisible(labels_visible)
        self.update_path()

    # ------------------------------------------------------------ geometry
    def effective_points(self) -> list[QPointF]:
        pts = [QPointF(p) for p in self.points]
        if self.start_item is not None:
            pts[0] = self.start_item.pos()
        if self.end_item is not None:
            pts[-1] = self.end_item.pos()
        return pts

    def update_path(self) -> None:
        pts = self.effective_points()
        self.setPath(rounded_path(pts))
        if not self._label_moved:
            self._auto_positioning = True
            mid = self.path().pointAtPercent(0.5)
            self.label.setPos(mid + QPointF(6, -16))
            self._auto_positioning = False

    def shape(self) -> QPainterPath:
        stroker = QPainterPathStroker()
        stroker.setWidth(max(10.0, self.pen().widthF() + 8.0))
        return stroker.createStroke(self.path())

    def nearest_point(self, pos: QPointF) -> tuple[QPointF, float]:
        """Closest point on the (unrounded) polyline and its distance to pos."""
        pts = self.effective_points()
        best, best_d = QPointF(pts[0]), _dist(pos, pts[0])
        for a, b in zip(pts, pts[1:]):
            candidate = nearest_point_on_segment(pos, a, b)
            d = _dist(pos, candidate)
            if d < best_d:
                best, best_d = candidate, d
        return best, best_d

    # ------------------------------------------------------------ painting
    def paint(self, painter, option, widget=None) -> None:
        painter.setPen(self.pen())
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(self.path())
        if self.isSelected():
            pen = QPen(QColor("#0078d7"), self.pen().widthF() + 2, Qt.PenStyle.DashLine)
            pen.setCosmetic(False)
            painter.setPen(pen)
            painter.drawPath(self.path())

    def set_z_standard(self, z: float | None) -> None:
        """Show the cable's computed Z standard on its label (SPEC §6)."""
        if z is None:
            self.label.setText(self.designation)
        else:
            self.label.setText(f"{self.designation}  |  Z {z:g} mm")

    # ------------------------------------------------------------ data
    def to_dict(self, part_index: dict) -> dict:
        return {
            "designation": self.designation,
            "diameter": self.diameter,
            "points": [[p.x(), p.y()] for p in self.effective_points()],
            "start_part": part_index.get(self.start_item),
            "end_part": part_index.get(self.end_item),
            "label_x": self.label.pos().x(),
            "label_y": self.label.pos().y(),
            "label_moved": self._label_moved,
        }

    @staticmethod
    def from_dict(data: dict, parts: list, labels_visible: bool) -> "CableItem":
        points = [QPointF(x, y) for x, y in data.get("points", [])]

        def resolve(key: str):
            idx = data.get(key)
            if isinstance(idx, int) and 0 <= idx < len(parts):
                return parts[idx]
            return None

        cable = CableItem(
            str(data.get("designation", "?")),
            float(data.get("diameter", 0.0)),
            points,
            start_item=resolve("start_part"),
            end_item=resolve("end_part"),
            labels_visible=labels_visible,
        )
        if data.get("label_moved"):
            cable._label_moved = True
            cable.label.setPos(float(data.get("label_x", 0)), float(data.get("label_y", 0)))
        return cable
