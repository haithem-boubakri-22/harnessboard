from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

ICON_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".svg"}
STEP_EXTENSIONS = {".step", ".stp"}

# The four orientation states. Order matters only for display.
ORIENTATIONS = ("std", "mir", "rot", "rot_mir")


@dataclass
class Part:
    name: str                 # folder name = model name (identity everywhere)
    category: str             # from folder tree
    folder: Path
    icon_path: Path | None = None
    # Legacy single-file fields (kept for back-compat):
    step_path: Path | None = None
    z_depth: float | None = None
    # New schema:
    z_depths: list[float] = field(default_factory=list)
    # orientation -> {z_depth: absolute step file path}
    steps: dict[str, dict[float, Path]] = field(default_factory=dict)

    def available_z(self, orientation: str = "std") -> list[float]:
        """Z depths available for this part (optionally per-orientation)."""
        if self.steps:
            bucket = self.steps.get(orientation) or {}
            return sorted(bucket)
        if self.z_depth is not None:
            return [self.z_depth]
        return []

    def default_z(self) -> float | None:
        for orient in ORIENTATIONS:
            zs = self.available_z(orient)
            if zs:
                return zs[0]
        return None

    def resolve_step(self, orientation: str, z: float | None) -> Path | None:
        """Best step file for a given orientation + Z. Snaps to nearest Z."""
        # New schema preferred:
        if self.steps:
            bucket = self.steps.get(orientation)
            if not bucket:
                return None
            if z is None:
                return bucket[sorted(bucket)[0]]
            best_z = min(bucket, key=lambda v: abs(v - z))
            return bucket[best_z]
        # Legacy fallback: only 'std' orientation exists.
        if orientation == "std":
            return self.step_path
        return None


@dataclass
class Library:
    root: Path | None = None
    parts: list[Part] = field(default_factory=list)
    cables: dict[str, float] = field(default_factory=dict)
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


def _load_step_map(
    part_folder: Path, meta: dict, errors: list[str]
) -> tuple[dict[str, dict[float, Path]], list[float]]:
    """Parse the 'steps' schema. Supports both old (nested by Z) and new (flat with z_depth)."""
    raw = meta.get("steps")
    if not isinstance(raw, dict):
        return {}, []
    
    default_z = float(meta.get("z_depth", 0.0))
    steps: dict[str, dict[float, Path]] = {}
    all_z: set[float] = set()
    
    for orient, value in raw.items():
        if orient not in ORIENTATIONS:
            errors.append(f"{part_folder.name}: unknown orientation '{orient}' — skipped")
            continue
            
        if isinstance(value, str):
            # New flat format: "std": "file.step"
            file_path = part_folder / value
            if file_path.is_file():
                steps[orient] = {default_z: file_path}
                all_z.add(default_z)
            else:
                errors.append(f"{part_folder.name}: missing file {value}")
        elif isinstance(value, dict):
            # Legacy nested format
            bucket = {}
            for z_str, rel_path in value.items():
                z = float(z_str)
                file_path = part_folder / str(rel_path)
                if file_path.is_file():
                    bucket[z] = file_path
                    all_z.add(z)
            if bucket:
                steps[orient] = bucket
                
    return steps, sorted(all_z)


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
        dirnames.clear()

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
                # legacy single-step fallback
                part.step_path = folder / f

        meta_file = folder / "part.json"
        if meta_file.is_file():
            try:
                meta = json.loads(meta_file.read_text(encoding="utf-8"))
                if meta.get("category"):
                    part.category = str(meta["category"])
                if meta.get("z_depth") is not None:
                    part.z_depth = float(meta["z_depth"])
                part.steps, zs_from_steps = _load_step_map(folder, meta, lib.errors)
                declared = meta.get("z_depths")
                if isinstance(declared, list):
                    part.z_depths = sorted(float(z) for z in declared)
                elif zs_from_steps:
                    part.z_depths = zs_from_steps
            except (ValueError, TypeError) as exc:
                lib.errors.append(f"{part.name}: bad part.json ({exc})")

        if not part.category:
            part.category = "Uncategorized"
        lib.parts.append(part)

    lib.parts.sort(key=lambda p: (p.category.lower(), p.name.lower()))
    return lib
