"""Export a self-contained folder with PDF + BOM + STEP + MCAM files."""
from __future__ import annotations

import shutil
from pathlib import Path

from harnessboard.bom import BomRow, CableRow
from harnessboard.csv_export import export_bom_csv
from harnessboard.excel_export import export_bom
from harnessboard.pdf_export import export_pdf


def export_folder(out_dir, scene, harness, bom_parts, bom_cables, name_hint=None, flat_steps=False, info_override=None) -> dict:
    out_dir = Path(out_dir)
    steps_dir = out_dir / "steps"
    mcam_dir = out_dir / "mcam"
    out_dir.mkdir(parents=True, exist_ok=True)
    mcam_dir.mkdir(exist_ok=True)
    
    # 1. Clean old steps folder to prevent ghost files
    if steps_dir.exists():
        shutil.rmtree(steps_dir)
    steps_dir.mkdir(exist_ok=True)

    info: dict = {}
    if info_override:
        info = dict(info_override)
    harness_name = "layout"
    if info_override:
        harness_name = "".join(
            c for c in info_override.get("number", "layout") if c not in '<>:"/\\|?*'
        ).split("/")[-1].strip()
        if not harness_name:
            harness_name = "layout"
    elif harness is not None:
        info = {
            "customer": harness.customer,
            "number": harness.number,
            "type": harness.htype,
        }
        harness_name = "".join(c for c in harness.number if c not in '<>:"/\\|?*')
    elif name_hint:
        harness_name = "".join(c for c in name_hint if c not in '<>:"/\\|?*')

    # 2. Map parts to their bounding boxes
    boxes = scene.harness_boxes()
    part_to_box = {}
    for item in scene.part_items():
        assigned = "Unassigned"
        for box in boxes:
            if box.sceneBoundingRect().contains(item.pos()):
                assigned = box.name.replace("/", "-")
                break
        part_to_box[item] = assigned

    # 3. Calculate Target Z for each Block
    box_z = {}
    for box in boxes:
        z_vals = []
        for item in scene.part_items():
            if box.sceneBoundingRect().contains(item.pos()) and item.part.z_depth is not None:
                z_vals.append(item.part.z_depth)
                
        block_target = max(z_vals) if z_vals else 0.0
        
        # Casing rule: it sets a minimum Z
        if box.has_casing:
            block_target = max(block_target, box.casing_z)
            
        box_name = box.name.replace("/", "-")
        box_z[box_name] = block_target if block_target > 0 else None
        print(f"DEBUG: Block '{box.name}' Target Z = {box_z[box_name]}")

    # 4. Copy step files
    copied_steps = []
    missing = []
    warnings = []
    seen = set()
    
    for item in scene.part_items():
        part = item.part
        orientation = item.orientation
        box_name = part_to_box[item]
        
        # Find the target Z for this part (block Z if inside a block, else its own Z)
        target_z = part.z_depth
        if box_name in box_z and box_z[box_name] is not None:
            target_z = box_z[box_name]

        box_steps_dir = steps_dir if flat_steps else (steps_dir / box_name)
        box_steps_dir.mkdir(parents=True, exist_ok=True)
        
        key = (box_name, part.name, orientation)
        if key in seen:
            continue
        seen.add(key)
        
        step_path = part.resolve_step(orientation, target_z)
        
        # Add a warning if the part's base Z is lower than the block's required Z
        if part.z_depth is not None and target_z is not None and part.z_depth < target_z:
            warnings.append(f"{part.name} max Z is {part.z_depth}, but block '{box_name}' requires {target_z}")
            
        if step_path is None or not step_path.is_file():
            missing.append(f"{box_name}: {part.name} [{orientation}]")
            continue
            
        dest = box_steps_dir / step_path.name
        if not dest.exists():
            shutil.copy2(step_path, dest)
            copied_steps.append(f"{box_name}/{dest.name}")
            
        # Copy MCAM files
        for mcam in part.folder.glob("*.mcam"):
            dest_mcam = mcam_dir / mcam.name
            if not dest_mcam.exists():
                shutil.copy2(mcam, dest_mcam)

    # 5. Exports with clean naming
    print("DEBUG: About to call export_pdf...", flush=True)
    try:
        export_pdf(out_dir / f"{harness_name}.pdf", scene, info, bom_parts, bom_cables)
        print("DEBUG: export_pdf finished successfully", flush=True)
        
        export_bom(out_dir / f"BOM_{harness_name}.xlsx", bom_parts, bom_cables, info)
        print("DEBUG: export_bom finished successfully", flush=True)
        
        export_bom_csv(out_dir / f"BOM_{harness_name}.csv", bom_parts, bom_cables, info)
        print("DEBUG: export_bom_csv finished successfully", flush=True)
    except Exception as exc:
        print(f"DEBUG: Export exception caught: {exc}", flush=True)
        return {"error": str(exc)}

    return {
        "folder": str(out_dir),
        "steps_copied": len(copied_steps),
        "mcam_copied": len(list(mcam_dir.glob("*.mcam"))),
        "missing": missing,
        "warnings": warnings,
    }
