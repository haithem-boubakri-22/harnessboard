"""Part library: scans the library root folder into Part objects.

Library layout (SPEC.md section 4):
    <library root>/
        cables.json                     designation -> diameter (mm)
        <Category>/[<Subcategory>/]
            <PartName>/                 one folder per orientation variant
                icon.png                2D icon (any common image format)
                <PartName>.step         3D model
                part.json               {"category": ..., "z_depth": ...}
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

ICON_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".svg"}
STEP_EXTENSIONS = {".step", ".stp"}


@dataclass
class Part:
    name: str                 # folder name = model name (identity everywhere)
    category: str             # from folder tree, e.g. "Connector holders"
    folder: Path
    icon_path: Path | None = None
    step_path: Path | None = None
    z_depth: float | None = None


@dataclass
class Library:
    root: Path | None = None
    parts: list[Part] = field(default_factory=list)
    cables: dict[str, float] = field(default_factory=dict)  # designation -> diameter
    errors: list[str] = field(default_factory=list)

    def part_by_name(self, name: str) -> Part | None:
        for part in self.parts:
            if part.name == name:
                return part
        return None

    @property
    def categories(self) -> list[str]:
        return sorted({p.category for p in self.parts})


def _is_part_folder(filenames: list[str]) -> bool:
    if "part.json" in filenames:
        return True
    return any(Path(f).suffix.lower() in STEP_EXTENSIONS for f in filenames)


def scan_library(root: str | Path) -> Library:
    root = Path(root)
    lib = Library(root=root)
    if not root.is_dir():
        lib.errors.append(f"Library folder not found: {root}")
        return lib

    cables_file = root / "cables.json"
    if cables_file.is_file():
        try:
            data = json.loads(cables_file.read_text(encoding="utf-8"))
            lib.cables = {str(k): float(v) for k, v in data.items()}
        except (ValueError, TypeError) as exc:
            lib.errors.append(f"cables.json unreadable: {exc}")

    for dirpath, dirnames, filenames in os.walk(root):
        folder = Path(dirpath)
        if folder == root or not _is_part_folder(filenames):
            continue
        dirnames.clear()  # a part folder has no part subfolders

        part = Part(
            name=folder.name,
            category=str(folder.parent.relative_to(root)) if folder.parent != root else "",
            folder=folder,
        )
        for f in filenames:
            suffix = Path(f).suffix.lower()
            if part.icon_path is None and suffix in ICON_EXTENSIONS:
                part.icon_path = folder / f
            elif part.step_path is None and suffix in STEP_EXTENSIONS:
                part.step_path = folder / f

        meta_file = folder / "part.json"
        if meta_file.is_file():
            try:
                meta = json.loads(meta_file.read_text(encoding="utf-8"))
                if meta.get("category"):
                    part.category = str(meta["category"])
                if meta.get("z_depth") is not None:
                    part.z_depth = float(meta["z_depth"])
            except (ValueError, TypeError) as exc:
                lib.errors.append(f"{part.name}: bad part.json ({exc})")

        if not part.category:
            part.category = "Uncategorized"
        lib.parts.append(part)

    lib.parts.sort(key=lambda p: (p.category.lower(), p.name.lower()))
    return lib
