from __future__ import annotations

from datetime import date
from pathlib import Path

from PySide6.QtCore import QMarginsF, QRectF, Qt
from PySide6.QtGui import (
    QColor, QFont, QPageLayout, QPageSize, QPainter, QPen, QPdfWriter,
)

RESOLUTION = 300


def _font(px_per_mm: float, mm_size: float, bold: bool = False) -> QFont:
    f = QFont("DejaVu Sans")
    f.setPixelSize(max(1, int(mm_size * px_per_mm)))
    if bold:
        f.setWeight(QFont.Weight.Bold)
    return f


def export_pdf(path, scene, harness_info, bom_parts, bom_cables) -> None:
    writer = QPdfWriter(str(path))
    writer.setResolution(RESOLUTION)
    writer.setPageSize(QPageSize(QPageSize.PageSizeId.A3))
    writer.setPageOrientation(QPageLayout.Orientation.Landscape)
    writer.setPageMargins(QMarginsF(10, 10, 10, 10), QPageLayout.Unit.Millimeter)
    writer.setTitle("HarnessBoard layout")

    painter = QPainter()
    if not painter.begin(writer):
        raise OSError(f"Cannot begin PDF writer: {path}")
    try:
        _draw_page(painter, writer, scene, harness_info or {}, bom_parts, bom_cables)
    finally:
        painter.end()


def _draw_page(painter, writer, scene, info, bom_parts, bom_cables) -> None:
    page_rect = QRectF(0, 0, writer.width(), writer.height())
    px_per_mm = writer.resolution() / 25.4
    m = 6 * px_per_mm
    inner = page_rect.adjusted(m, m, -m, -m)
    band_h = inner.height() * 0.32
    layout_rect = QRectF(
        inner.left(), inner.top(),
        inner.width(), inner.height() - band_h - 4 * px_per_mm,
    )
    band_rect = QRectF(
        inner.left(), inner.bottom() - band_h, inner.width(), band_h,
    )
    _draw_scene(painter, scene, layout_rect)
    painter.setPen(QPen(QColor("#333333"), max(1.0, 0.3 * px_per_mm)))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRect(layout_rect)
    _draw_title_and_bom(painter, band_rect, info, bom_parts, bom_cables, px_per_mm)


MAX_SCALE = 2.5  # cap so small layouts don't blow up icons to 50+ mm


def _draw_scene(painter, scene, target_rect) -> None:
    from PySide6.QtWidgets import QGraphicsSimpleTextItem

    items = [i for i in scene.items() if i.parentItem() is None]
    if not items:
        return
    scene_rect = QRectF()
    for item in items:
        scene_rect = scene_rect.united(item.sceneBoundingRect())
    if scene_rect.isEmpty():
        return
    pad = max(scene_rect.width(), scene_rect.height()) * 0.05
    scene_rect = scene_rect.adjusted(-pad, -pad, pad, pad)
    s = min(
        target_rect.width() / scene_rect.width(),
        target_rect.height() / scene_rect.height(),
        MAX_SCALE,
    )
    new_w = scene_rect.width() * s
    new_h = scene_rect.height() * s
    ox = target_rect.left() + (target_rect.width() - new_w) / 2
    oy = target_rect.top() + (target_rect.height() - new_h) / 2

    
    label_px = max(12, int(12 * min(s, MAX_SCALE)))
    saved_fonts = []
    saved_visibility = []
    for it in scene.items():
        if isinstance(it, QGraphicsSimpleTextItem):
            parent = it.parentItem()
            if parent is not None and hasattr(parent, "designation"):
                saved_visibility.append((it, it.isVisible()))
                it.setVisible(False)
                continue
            saved_fonts.append((it, it.font()))
            f = it.font()
            f.setPixelSize(label_px)
            it.setFont(f)

    painter.save()
    painter.setClipRect(target_rect)
    painter.translate(ox, oy)
    painter.scale(s, s)
    painter.translate(-scene_rect.left(), -scene_rect.top())
    try:
        scene.render(painter, scene_rect, scene_rect, Qt.AspectRatioMode.IgnoreAspectRatio)
    finally:
        painter.restore()
        for it, font in saved_fonts:
            it.setFont(font)
        for it, visible in saved_visibility:
            it.setVisible(visible)


def _draw_title_and_bom(painter, band, info, bom_parts, bom_cables, px_per_mm) -> None:
    title_w = band.width() * 0.40
    bom_rect = QRectF(band.left(), band.top(),
                      band.width() - title_w - 3 * px_per_mm, band.height())
    title_rect = QRectF(bom_rect.right() + 3 * px_per_mm, band.top(),
                        title_w, band.height())
    _draw_bom(painter, bom_rect, bom_parts, bom_cables, px_per_mm)
    _draw_title_block(painter, title_rect, info, px_per_mm)


def _draw_bom(painter, rect, bom_parts, bom_cables, px_per_mm) -> None:
    painter.save()
    painter.setPen(QPen(QColor("#333333"), max(1.0, 0.3 * px_per_mm)))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRect(rect)

    title_h = 6 * px_per_mm
    row_h = 5.5 * px_per_mm
    sep_pen = QPen(QColor("#bbbbbb"), max(0.5, 0.15 * px_per_mm))

    painter.setFont(_font(px_per_mm, 3.5, bold=True))
    painter.drawText(
        QRectF(rect.left() + 2 * px_per_mm, rect.top() + 1 * px_per_mm,
               rect.width() - 4 * px_per_mm, title_h),
        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        "BILL OF MATERIALS",
    )

    cols = (0.40, 0.28, 0.12, 0.20)
    x_edges = [rect.left()]
    for frac in cols:
        x_edges.append(x_edges[-1] + frac * rect.width())

    y = rect.top() + title_h + 1 * px_per_mm
    max_y = rect.bottom() - 2 * px_per_mm

    def row(values, bold=False, fill=None):
        nonlocal y
        if y + row_h > max_y:
            return False
        if fill is not None:
            painter.fillRect(QRectF(rect.left(), y, rect.width(), row_h), fill)
        painter.setFont(_font(px_per_mm, 2.8, bold=bold))
        for i, val in enumerate(values):
            painter.drawText(
                QRectF(x_edges[i] + 1 * px_per_mm, y,
                       x_edges[i + 1] - x_edges[i] - 1 * px_per_mm, row_h),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, val,
            )
        painter.setPen(sep_pen)
        painter.drawLine(int(rect.left()), int(y + row_h),
                         int(rect.right()), int(y + row_h))
        painter.setPen(QPen(QColor("#333333"), max(1.0, 0.3 * px_per_mm)))
        y += row_h
        return True

    header_fill = QColor("#e8eef7")
    row(["Model name", "Category", "Qty", "Z (mm)"], bold=True, fill=header_fill)
    for r in bom_parts:
        if not row([
            r.name, r.category, str(r.quantity),
            f"{r.z_depth:g}" if r.z_depth is not None else "—",
        ]):
            break

    if y + row_h * 2 < max_y:
        y += row_h * 0.5
    row(["Designation", "Ø (mm)", "Z std (mm)"], bold=True, fill=header_fill)
    for c in bom_cables:
        if not row([
            c.designation, f"{c.diameter:g}",
            f"{c.z_standard:g}" if c.z_standard is not None else "—",
        ]):
            break

    painter.restore()


def _draw_title_block(painter, rect, info, px_per_mm) -> None:
    painter.save()
    painter.setPen(QPen(QColor("#333333"), max(1.0, 0.4 * px_per_mm)))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRect(rect)

    rows = [
        ("Project / Customer", info.get("customer", "")),
        ("Harness number", info.get("number", "")),
        ("Harness type", info.get("type", "")),
        ("Date", date.today().isoformat()),
        ("Revision", "A"),
        ("Author", ""),
        ("Scale", "Schematic (NTS)"),
        ("Software", "HarnessBoard"),
    ]
    label_w = rect.width() * 0.42
    row_h = rect.height() / len(rows)
    label_font = _font(px_per_mm, 2.8)
    value_font = _font(px_per_mm, 3.2, bold=True)
    line_pen = QPen(QColor("#bbbbbb"), max(0.5, 0.2 * px_per_mm))

    for i, (label, value) in enumerate(rows):
        y = rect.top() + i * row_h
        painter.setPen(line_pen)
        painter.drawLine(int(rect.left() + label_w), int(y),
                         int(rect.left() + label_w), int(y + row_h))
        painter.setFont(label_font)
        painter.drawText(
            QRectF(rect.left() + 2 * px_per_mm, y, label_w - 3 * px_per_mm, row_h),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, label,
        )
        painter.setFont(value_font)
        painter.drawText(
            QRectF(rect.left() + label_w + 2 * px_per_mm, y,
                   rect.width() - label_w - 4 * px_per_mm, row_h),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, str(value),
        )
        if i < len(rows) - 1:
            painter.setPen(line_pen)
            painter.drawLine(int(rect.left()), int(y + row_h),
                             int(rect.right()), int(y + row_h))

    painter.restore()
