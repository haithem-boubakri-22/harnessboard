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
            item.setPos(QPointF(new))

    def undo(self) -> None:
        for item, (old, _new) in self._moves.items():
            item.setPos(QPointF(old))


class RotatePartsCommand(QUndoCommand):
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
