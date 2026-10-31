"""Export a self-contained folder with PDF + BOM + STEP + MCAM files."""
from __future__ import annotations

import shutil
from pathlib import Path

from harnessboard.bom import BomRow, CableRow
from harnessboard.csv_export import export_bom_csv
from harnessboard.excel_export import export_bom
from harnessboard.pdf_export import export_pdf


def export_folder(out_dir, scene, harness, bom_parts, bom_cables) -> dict:
    out_dir = Path(out_dir)
    mcam_dir = out_dir / "mcam"
    out_dir.mkdir(parents=True, exist_ok=True)
    mcam_dir.mkdir(exist_ok=True)

    info: dict = {}
    if harness is not None:
        info = {
            "customer": harness.customer,
            "number": harness.number,
            "type": harness.htype,
        }

    # 1. Map parts to their bounding boxes
    boxes = scene.harness_boxes()
    part_to_box = {}
    for item in scene.part_items():
        assigned = "Unassigned"
        for box in boxes:
            if box.sceneBoundingRect().contains(item.pos()):
                assigned = box.name.replace("/", "-") # safety for folder names
                break
        part_to_box[item] = assigned

    # 2. Copy step files
    copied_steps = []
    missing = []
    seen = set()
    
    for item in scene.part_items():
        part = item.part
        orientation = item.orientation
        box_name = part_to_box[item]
        
        # Create folder for this box
        box_steps_dir = out_dir / "steps" / box_name
        box_steps_dir.mkdir(parents=True, exist_ok=True)
        
        key = (box_name, part.name, orientation)
        if key in seen:
            continue
        seen.add(key)
        
        # Resolve step: single Z now
        z = part.z_depth
        step_path = part.resolve_step(orientation, z)
        
        if step_path is None or not step_path.is_file():
            missing.append(f"{box_name}: {part.name} [{orientation}]")
            continue
            
        dest = box_steps_dir / step_path.name
        if not dest.exists():
            shutil.copy2(step_path, dest)
            copied_steps.append(f"{box_name}/{dest.name}")
            
        # Copy MCAM
        for mcam in part.folder.glob("*.mcam"):
            dest_mcam = mcam_dir / mcam.name
            if not dest_mcam.exists():
                shutil.copy2(mcam, dest_mcam)

    # 3. Exports
    try:
        export_pdf(out_dir / "layout.pdf", scene, info, bom_parts, bom_cables)
        export_bom(out_dir / "BOM.xlsx", bom_parts, bom_cables, info)
        export_bom_csv(out_dir / "BOM.csv", bom_parts, bom_cables, info)
    except Exception as exc:
        return {"error": str(exc)}

    return {
        "folder": str(out_dir),
        "steps_copied": len(copied_steps),
        "mcam_copied": len(list(mcam_dir.glob("*.mcam"))),
        "missing": missing,
    }
