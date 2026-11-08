"""Split a board scene into global + per-block folders.

Folder layout (per board):
    <board>/
        layout.harn          global
        <BoardName>.pdf
        BOM_<BoardName>.xlsx
        BOM_<BoardName>.csv
        steps/<BlockName>/   global, grouped
        mcam/
        _README.txt
        <BlockName>/
            layout.harn      kind: "block"
            <BlockName>.pdf
            BOM_<BlockName>.xlsx
            BOM_<BlockName>.csv
            _README.txt
            steps/           flat
            mcam/
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from PySide6.QtGui import QUndoStack

from harnessboard.bom import bom_cables, bom_parts
from harnessboard.export_folder import export_folder


def _safe_name(name: str) -> str:
    return "".join(c for c in name if c not in '<>:"/\\|?*').strip() or "Unnamed"


def _block_to_dict(block, scene) -> dict:
    """Build the block's isolated serialized form (parts + cables only in this block)."""
    parts_in_block = [
        p for p in scene.part_items()
        if block.sceneBoundingRect().contains(p.pos())
    ]
    part_index = {p: i for i, p in enumerate(parts_in_block)}

    cables_in_block = [
        c for c in scene.cable_items()
        if c.start_item in part_index and c.end_item in part_index
    ]

    return {
        "kind": "block",
        "parent_board": "../layout.harn",
        "block_name": block.name,
        "version": 2,
        "labels_visible": scene.labels_visible,
        "boxes": [block.to_dict()],
        "parts": [p.to_dict() for p in parts_in_block],
        "cables": [c.to_dict(part_index) for c in cables_in_block],
    }


def serialize_current_block(scene) -> dict:
    """For when the app is in block-standalone mode — serialize the active scene."""
    boxes = scene.harness_boxes()
    if not boxes:
        raise ValueError("No harness block present in scene")
    # In block mode the scene contains only the block; use the same helper
    return _block_to_dict(boxes[0], scene)


def _sync_block_folder(block_dict: dict, block_folder: Path, scene, library,
                       parent_customer: str, parent_board: str, parent_type: str) -> None:
    """Write files for one block folder (layout.harn, PDF, BOM, steps, mcam, README)."""
    block_folder.mkdir(parents=True, exist_ok=True)
    block_name = block_dict["block_name"]

    # 1. layout.harn
    (block_folder / "layout.harn").write_text(
        json.dumps(block_dict, indent=2), encoding="utf-8"
    )

    # 2. Build an isolated scene and load it
    from harnessboard.ui.canvas import BoardScene  # late import to avoid cycles
    block_scene = BoardScene(QUndoStack())
    block_scene.load_dict(block_dict, library)

    # 3. Export PDF + BOM + steps + mcam into this folder
    parts = bom_parts(block_scene)
    cables = bom_cables(block_scene)
    info_override = {
        "customer": parent_customer,
        "number": f"{parent_board} / {block_name}",
        "type": parent_type,
    }
    export_folder(
        block_folder, block_scene, None, parts, cables,
        name_hint=block_name, flat_steps=True, info_override=info_override,
    )



def sync_board_and_blocks(harness, scene, library) -> dict:
    """Write global + per-block folders. Returns a summary for the status bar."""
    board_folder = harness.folder
    board_folder.mkdir(parents=True, exist_ok=True)

    # 1. Global layout.harn
    (board_folder / "layout.harn").write_text(
        json.dumps(scene.to_dict(), indent=2), encoding="utf-8"
    )

    # 2. Global export (PDF, BOM, steps grouped by block, mcam)
    parts = bom_parts(scene)
    cables = bom_cables(scene)
    global_result = export_folder(board_folder, scene, harness, parts, cables)

    # 3. Per-block folders
    block_names_written = []
    for block in scene.harness_boxes():
        block_dict = _block_to_dict(block, scene)
        block_folder = board_folder / _safe_name(block.name)
        try:
            _sync_block_folder(
                block_dict, block_folder, scene, library,
                parent_customer=harness.customer,
                parent_board=harness.number,
                parent_type=harness.htype,
            )
            block_names_written.append(block.name)
        except Exception as exc:
            print(f"⚠ Failed to write block folder {block.name}: {exc}")

    return {
        "folder": str(board_folder),
        "global_steps": global_result.get("steps_copied", 0),
        "blocks_written": block_names_written,
        "missing": global_result.get("missing", []),
    }
