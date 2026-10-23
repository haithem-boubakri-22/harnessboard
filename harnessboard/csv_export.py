from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

from harnessboard.bom import BomRow, CableRow


def export_bom_csv(
    path: str | Path,
    parts: list[BomRow],
    cables: list[CableRow],
    harness_info: dict | None = None,
) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["HarnessBoard — Bill of Materials"])
        info = harness_info or {}
        for label, key in (
            ("Customer / project", "customer"),
            ("Harness number", "number"),
            ("Harness type", "type"),
        ):
            if info.get(key):
                w.writerow([label, str(info[key])])
        w.writerow(["Date", date.today().isoformat()])
        w.writerow([])
        w.writerow(["PARTS"])
        w.writerow(["Model name", "Category", "Quantity", "Z depth (mm)"])
        for r in parts:
            w.writerow(
                [r.name, r.category, r.quantity,
                 r.z_depth if r.z_depth is not None else ""]
            )
        w.writerow([])
        w.writerow(["CABLES"])
        w.writerow(["Designation", "Diameter (mm)", "Z standard (mm)"])
        for c in cables:
            w.writerow(
                [c.designation, c.diameter,
                 c.z_standard if c.z_standard is not None else ""]
            )
