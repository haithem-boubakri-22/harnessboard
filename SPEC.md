# Harness Board Layout Software — Specification (draft)

> Status: **idea complete — workflow walkthrough confirmed by the user.**
> This document is the single source of truth for the product idea.
> Tech stack: **Python + PySide6 (Qt)**.

## 1. What the software is

A **Windows desktop application** for planning the **manufacturing boards/tools of
automotive harnesses** — the fixtures that hold a harness while it is built or checked.

The user draws a **schematic 2D layout** (scale does not matter) made of:
- **fixture/holder models** (connector holders, clamps, forks, grommet holders…) placed as icons,
- **cables** drawn as lines connecting them,
- **on-line parts** (clips, terminals…) snapped onto the lines.

From that layout the software produces:
1. a **PDF drawing** (with title block and BOM table),
2. a **live BOM** (also exportable to Excel),
3. a **prepared 3D folder**: every placed model's `.step` copied into the harness
   folder, ready for the user to build the full board assembly in external CAD
   (CATIA/NX/…). The software itself never assembles 3D.

## 2. Harness types

Every harness is one of three types, chosen at creation:

| Type | Purpose |
|---|---|
| **Assembly** | assembly board |
| **Molding** | molding tool |
| **Q-GATE** | quality gate / checking fixture |

The type is stored as the harness's main property and drives the **Z-depth rules**
(section 6). More type-dependent behavior may be added later (user will provide
when recalled).

## 3. Project structure

```
Projects root/
└── Customer (e.g. BMW)/
    └── Harness number (e.g. 9Y4 971 279 AD)/
        ├── <copied .step files of every placed model>
        └── <project file of the layout>
```

- Placing a part in the layout copies its `.step` into the harness folder.
- A part placed multiple times → quantity N in the BOM, `.step` copied **once**.

## 4. Part library

A **library root folder**, organized by category (connector holders, grommet
holders, clips, terminals, …).

- **One folder per variant.** The same part in a different orientation is a
  separate folder (e.g. `1234567_left`, `1234567_right`), because orientation
  changes both the icon and the 3D model — and the Z depth (section 6).
- Each part folder contains:
  - the **2D icon** image (prepared by the user, e.g. exported from CAD),
  - the **`.step` 3D model**,
  - a **metadata file** holding the variant's data (base Z-depth values, …).
- Folder name = model name (identity used everywhere: search, BOM, labels).
- Part metadata: **category/type only** (from the folder tree). No supplier refs,
  no cavity counts.

### Adding parts from the UI

An **"Add part" dialog** registers a new model into the library without touching
folders manually: the user provides the `.step` file path, the icon image, and
the category. The files are **copied into the library folder structure** — the
library stays self-contained.

### Cables (special library entries)

- **No 3D model.** A cable entry is just a **designation** with one stored value:
  the **diameter**. No color, nothing else.
- Drawing a line = choosing which cable designation it is.

## 5. Layout editor

- Canvas: zoom/pan, undo/redo, copy/paste, delete, move/rotate icons.
- **Visual part search** (primary placement method): type a model name → dropdown
  of matching parts shown as **icon thumbnails**, because several entries share a
  name but differ in orientation. The icon is the disambiguator — you pick by eye.
- **Lines (cables)**: click waypoints between icons; corners rounded automatically.
  Each line carries its cable designation (→ diameter). Parallel lines = separate
  cables running side by side.
- **On-line parts**: clips/terminals are library parts that snap onto lines
  instead of standing alone. They count in the BOM.
- **Labels**: model name shown near each icon, toggleable, movable, printed on PDF.

## 6. Z-depth rules  ⚠ core domain logic — needs detail

**v1 rule (simplified, agreed):**

- Every variant stores its **Z depth value** in its metadata file
  (e.g. connector A = 35 mm, connector B = 30 mm).
- Along one cable, take the **highest** Z depth among its attachments
  (35 mm in the example) — that is the standard for all parts of that cable.
- The software **notes this value in the document** (drawing/report) so the
  user applies it manually to the 3D models in CAD. No automatic geometry.

**Later phases (data already stored, logic deferred):**

- Cable **diameter** and **harness type** (Assembly / Molding / Q-GATE) will
  influence the min Z — exact rules to be defined when needed.
- **Orientation** already influences Z naturally: each orientation is its own
  variant with its own stored value.
- Exactly **one cable per attachment**, always.

## 7. Outputs

- **Native project file** (save/reopen layouts).
- **PDF**: layout + standard title block (harness number, project, type, date,
  revision, author) + BOM table on the sheet.
- **BOM**: live table in the app (model name, category, quantity) + Excel export.
- **Prepared 3D folder** (section 3).

## 8. Decisions log

- Scale irrelevant; layout is schematic.
- Exactly one cable per attachment.
- Per-variant metadata file stores depth data; each orientation has its own folder/.step.
- Z leveled per cable: max of the attachments' min-Z wins for the whole cable.
- "Add part" dialog: register model via file path + icon + category; files are copied into the library.
- v1 Z rule: Z value stored per variant; max per cable; noted in the document for manual application in CAD.
- Deleting the last instance of a part from the drawing → popup asks whether to also remove its .step from the harness folder.
- Settings page: library root + projects root chosen once, remembered, changeable anytime.
- 3D assembly happens in external CAD; software only prepares the folder.
- One folder per variant (not one folder with many icons).
- Cables: designation + diameter only.
- BOM: in-app table + Excel + on PDF.
- Labels: yes, toggleable.
- Title block: yes, standard.

## 9. Open questions

1. Other harness-type-dependent behaviors (user will recall later).
2. Later-phase Z rules involving cable diameter + harness type (user will define
   when needed; diameter is stored per cable from day one).

## 10. Technical decisions

- **Stack**: Python 3 + PySide6 (Qt) — native Windows desktop app, QGraphicsScene
  canvas, built-in PDF export; free/open licensing.
- **Icons**: PNG with transparent background.
- **Part metadata**: `part.json` inside each part folder (`category`, `z_depth`).
- **Cable library**: single `cables.json` in the library root
  (`designation` → `diameter`), since cables have no files of their own.
- **Project file**: JSON (`.harn` extension), saved inside the harness folder.
- **BOM export**: .xlsx.

## 11. Build plan (phases)

1. **Library core** — settings page (library root + projects root), library
   scanner (folders → parts with icons/metadata), library panel with category
   tree and the visual search dropdown (name → icon thumbnails).
2. **Canvas editor** — place parts from search, move/rotate/delete, toggleable
   labels, zoom/pan, undo/redo, save/open project file.
3. **Projects & file sync** — create Customer → Harness (with type), copy .step
   on placement, "remove file too?" popup on last-instance delete, "Add part"
   dialog (copies files into library).
4. **Cables & on-line parts** — cables.json library, draw lines with waypoints
   and rounded corners (one cable per attachment), snap clips/terminals onto
   lines.
5. **BOM & Z** — live BOM table, per-cable Z (max of attachments' stored
   values), Excel export.
6. **PDF output** — drawing sheet with title block, BOM table, and Z notes.

Each phase ends with something you can run and click through.
