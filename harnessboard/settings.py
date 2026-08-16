"""Persistent application settings (library root, projects root)."""
from __future__ import annotations

from PySide6.QtCore import QSettings


class AppSettings:
    def __init__(self) -> None:
        self._s = QSettings("HarnessBoard", "HarnessBoard")

    @property
    def library_root(self) -> str:
        return str(self._s.value("paths/library_root", ""))

    @library_root.setter
    def library_root(self, value: str) -> None:
        self._s.setValue("paths/library_root", value)

    @property
    def projects_root(self) -> str:
        return str(self._s.value("paths/projects_root", ""))

    @projects_root.setter
    def projects_root(self, value: str) -> None:
        self._s.setValue("paths/projects_root", value)

    def is_configured(self) -> bool:
        return bool(self.library_root) and bool(self.projects_root)
