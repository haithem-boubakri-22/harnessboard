"""BOM computation and per-cable Z-depth rule (SPEC.md §6).

Z per cable = the highest *effective* Z among every part attached to it.
Effective Z = block target Z (max of base Zs, elevated by casing) for parts
inside a block, else the part's own base Z.
"""
from __future__ import annotations

from dataclasses import dataclass

from harnessboard.ui.cable import SNAP_DISTANCE, CableItem
from harnessboard.ui.canvas import BoardScene, PartItem


def _block_target_z(scene: BoardScene) -> dict:
    """Shared helper: {block: target_z or None}. Used by bom_parts and cable_z."""
    block_z = {}
    for box in scene.harness_boxes():
        z_vals = [
            item.part.z_depth
            for item in scene.part_items()
            if box.sceneBoundingRect().contains(item.pos()) and item.part.z_depth is not None
        ]
        target = max(z_vals) if z_vals else 0.0
        if box.has_casing:
            target = max(target, box.casing_z)
        block_z[box] = target if target > 0 else None
    return block_z


def _part_display_z(item: PartItem, scene: BoardScene, block_z: dict) -> float | None:
    """Effective Z for display = block target if inside a block, else base Z."""
    for box in scene.harness_boxes():
        if box.sceneBoundingRect().contains(item.pos()):
            if block_z.get(box) is not None:
                return block_z[box]
            break
    return item.part.z_depth


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
    block_z = _block_target_z(scene)
    depths = [
        _part_display_z(p, scene, block_z)
        for p in cable_attachments(scene, cable)
    ]
    depths = [z for z in depths if z is not None]
    return max(depths) if depths else None


@dataclass
class BomRow:
    name: str
    category: str
    z_depth: float | None
    quantity: int
    encombrement: float = 0.0

    @property
    def total_height(self) -> float | None:
        if self.z_depth is None:
            return None
        return self.z_depth + self.encombrement

    @property
    def height_display(self) -> str:
        if self.z_depth is None:
            return "—"
        if self.encombrement == 0.0:
            return f"{self.z_depth:g}"
        return f"{self.total_height:g} = {self.z_depth:g} + {self.encombrement:g}"


@dataclass
class CableRow:
    designation: str
    diameter: float
    z_standard: float | None


def bom_parts(scene: BoardScene) -> list[BomRow]:
    block_z = _block_target_z(scene)
    counts: dict[tuple, BomRow] = {}

    for item in scene.part_items():
        part = item.part
        display_z = _part_display_z(item, scene, block_z)

        key = (part.name, display_z)
        row = counts.get(key)
        if row is None:
            counts[key] = BomRow(
                part.name, part.category, display_z, 1,
                encombrement=part.encombrement,
            )
        else:
            row.quantity += 1

    return sorted(
        counts.values(),
        key=lambda r: (r.category.lower(), r.name.lower(), r.z_depth or 0),
    )


def bom_cables(scene: BoardScene) -> list[CableRow]:
    rows = [
        CableRow(c.designation, c.diameter, cable_z(scene, c))
        for c in scene.cable_items()
    ]
    return sorted(rows, key=lambda r: r.designation.lower())
