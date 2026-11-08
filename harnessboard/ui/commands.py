"""Undoable commands for the board editor."""
from __future__ import annotations

from PySide6.QtCore import QPointF
from PySide6.QtGui import QUndoCommand


class AddPartsCommand(QUndoCommand):
    def __init__(self, scene, items, text: str = "Place part") -> None:
        super().__init__(text)
        self._scene = scene
        self._items = list(items)

    def redo(self) -> None:
        for item in self._items:
            self._scene.addItem(item)

    def undo(self) -> None:
        for item in self._items:
            self._scene.removeItem(item)


class RemovePartsCommand(QUndoCommand):
    def __init__(self, scene, items) -> None:
        super().__init__("Delete part(s)")
        self._scene = scene
        self._items = list(items)

    def redo(self) -> None:
        for item in self._items:
            self._scene.removeItem(item)

    def undo(self) -> None:
        for item in self._items:
            self._scene.addItem(item)


class MovePartsCommand(QUndoCommand):
    def __init__(self, moves: dict) -> None:
        """moves: {item: (old QPointF, new QPointF)}"""
        super().__init__("Move part(s)")
        self._moves = dict(moves)

    def redo(self) -> None:
        for item, (_old, new) in self._moves.items():
            if hasattr(item, "_block_moves"):
                item._block_moves = True
            item.setPos(QPointF(new))
            if hasattr(item, "_block_moves"):
                item._block_moves = False

    def undo(self) -> None:
        for item, (old, _new) in self._moves.items():
            if hasattr(item, "_block_moves"):
                item._block_moves = True
            item.setPos(QPointF(old))
            if hasattr(item, "_block_moves"):
                item._block_moves = False


class RotatePartsCommand(QUndoCommand):
    """Cosmetic canvas rotation (±15° steps). Independent from orientation."""

    def __init__(self, items, delta: float) -> None:
        super().__init__("Rotate part(s)")
        self._items = list(items)
        self._delta = delta

    def redo(self) -> None:
        for item in self._items:
            item.setRotation(item.rotation() + self._delta)

    def undo(self) -> None:
        for item in self._items:
            item.setRotation(item.rotation() - self._delta)


class SetOrientationCommand(QUndoCommand):
    """Set the orientation (std/mir/rot/rot_mir) of placed part(s)."""

    def __init__(self, items, new_orientation: str) -> None:
        super().__init__(f"Orientation → {new_orientation}")
        self._changes = [(item, item.orientation) for item in items]
        self._new = new_orientation

    def redo(self) -> None:
        for item, _old in self._changes:
            item.set_orientation(self._new)

    def undo(self) -> None:
        for item, old in self._changes:
            item.set_orientation(old)

class SetFaceStateCommand(QUndoCommand):
    """Change the face state (std / up / down) of placed part(s)."""
    def __init__(self, items, new_state: str) -> None:
        super().__init__(f"Change Face to {new_state}")
        self._changes = [(item, item.face_state) for item in items]
        self._new = new_state

    def redo(self) -> None:
        for item, _old in self._changes:
            item.set_face_state(self._new)

    def undo(self) -> None:
        for item, old in self._changes:
            item.set_face_state(old)


class SetBlockPropertiesCommand(QUndoCommand):
    """Change a harness block's name, casing flag, or casing Z value."""

    def __init__(self, block, new_name: str, new_has_casing: bool, new_casing_z: float) -> None:
        super().__init__("Change block properties")
        self._block = block
        self._old = (block.name, block.has_casing, block.casing_z)
        self._new = (new_name, new_has_casing, new_casing_z)

    def _apply(self, state) -> None:
        name, has_casing, casing_z = state
        self._block.name = name
        self._block.has_casing = has_casing
        self._block.casing_z = casing_z
        self._block.update_label()
        self._block.update()

    def redo(self) -> None:
        self._apply(self._new)

    def undo(self) -> None:
        self._apply(self._old)
