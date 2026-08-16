"""Projects structure: <projects root>/<Customer>/<Harness number>/ (SPEC.md §3).

Each harness folder holds:
    harness.json    {"customer", "number", "type"}
    layout.harn     the board layout
    *.step          copies of every placed part's 3D model
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

HARNESS_TYPES = ["Assembly", "Molding", "Q-GATE"]
_INVALID = set('<>:"/\\|?*')


def valid_folder_name(name: str) -> bool:
    name = name.strip()
    return bool(name) and not any(c in _INVALID for c in name)


@dataclass
class Harness:
    customer: str
    number: str
    htype: str
    folder: Path

    @property
    def layout_file(self) -> Path:
        return self.folder / "layout.harn"

    @property
    def meta_file(self) -> Path:
        return self.folder / "harness.json"

    def save_meta(self) -> None:
        self.meta_file.write_text(
            json.dumps(
                {"customer": self.customer, "number": self.number, "type": self.htype},
                indent=2,
            ),
            encoding="utf-8",
        )


def list_customers(root: str | Path) -> list[str]:
    root = Path(root)
    if not root.is_dir():
        return []
    return sorted((p.name for p in root.iterdir() if p.is_dir()), key=str.lower)


def load_harness(folder: str | Path) -> Harness | None:
    folder = Path(folder)
    meta_file = folder / "harness.json"
    if not meta_file.is_file():
        return None
    try:
        meta = json.loads(meta_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return Harness(
        customer=str(meta.get("customer", folder.parent.name)),
        number=str(meta.get("number", folder.name)),
        htype=str(meta.get("type", HARNESS_TYPES[0])),
        folder=folder,
    )


def list_harnesses(root: str | Path, customer: str) -> list[Harness]:
    customer_dir = Path(root) / customer
    if not customer_dir.is_dir():
        return []
    harnesses = []
    for folder in sorted(customer_dir.iterdir(), key=lambda p: p.name.lower()):
        if not folder.is_dir():
            continue
        harness = load_harness(folder)
        if harness is None and (folder / "layout.harn").is_file():
            # layout without metadata: still openable, assume defaults
            harness = Harness(customer, folder.name, HARNESS_TYPES[0], folder)
        if harness is not None:
            harnesses.append(harness)
    return harnesses


def create_harness(
    root: str | Path, customer: str, number: str, htype: str
) -> Harness:
    folder = Path(root) / customer.strip() / number.strip()
    folder.mkdir(parents=True, exist_ok=True)
    harness = Harness(customer.strip(), number.strip(), htype, folder)
    harness.save_meta()
    return harness
