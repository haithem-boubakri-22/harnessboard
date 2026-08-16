"""BOM computation and per-cable Z-depth rule (SPEC.md §6, v1 rule).

Z per cable = the highest z_depth among every part attached to that cable:
its two endpoint parts (if attached) plus every part sitting on the line
(clips, terminals — anything whose center lies within snap distance of the
cable path).
"""
from __future__ import annotations

from dataclasses import dataclass

from harnessboard.ui.cable import SNAP_DISTANCE, CableItem
from harnessboard.ui.canvas import BoardScene, PartItem


def cable_attachments(scene: BoardScene, cable: CableItem) -> set[PartItem]:
    parts: set[PartItem] = set()
    if cable.start_item is not None:
        parts.add(cable.start_item)
    if cable.end_item is not None:
        parts.add(cable.end_item)
    for item in scene.part_items():
        _point, distance = cable.nearest_point(item.pos())
        if distance <= SNAP_DISTANCE:
            parts.add(item)
    return parts


def cable_z(scene: BoardScene, cable: CableItem) -> float | None:
    depths = [
        p.part.z_depth
        for p in cable_attachments(scene, cable)
        if p.part.z_depth is not None
    ]
    return max(depths) if depths else None


@dataclass
class BomRow:
    name: str
    category: str
    z_depth: float | None
    quantity: int


@dataclass
class CableRow:
    designation: str
    diameter: float
    z_standard: float | None


def bom_parts(scene: BoardScene) -> list[BomRow]:
    counts: dict[str, BomRow] = {}
    for item in scene.part_items():
        part = item.part
        row = counts.get(part.name)
        if row is None:
            counts[part.name] = BomRow(part.name, part.category, part.z_depth, 1)
        else:
            row.quantity += 1
    return sorted(counts.values(), key=lambda r: (r.category.lower(), r.name.lower()))


def bom_cables(scene: BoardScene) -> list[CableRow]:
    rows = [
        CableRow(c.designation, c.diameter, cable_z(scene, c))
        for c in scene.cable_items()
    ]
    return sorted(rows, key=lambda r: r.designation.lower())
