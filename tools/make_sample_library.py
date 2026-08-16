"""Generate a placeholder part library for development.

Creates the folder structure described in SPEC.md section 4:
one folder per variant, each with icon.png + <name>.step + part.json,
plus cables.json at the library root. Replace with real data later by
pointing the app's settings at the real library folder.
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent / "sample_library"

STEP_TEMPLATE = """ISO-10303-21;
HEADER;
FILE_DESCRIPTION(('placeholder model - replace with real part'),'2;1');
FILE_NAME('{name}.step','2026-08-16',(''),(''),'','','');
FILE_SCHEMA(('AUTOMOTIVE_DESIGN {{ 1 0 10303 214 1 1 1 1 }}'));
ENDSEC;
DATA;
ENDSEC;
END-ISO-10303-21;
"""


def connector_icon(color: str, pins: int = 3) -> Image.Image:
    """Horizontal connector body with pins pointing right."""
    img = Image.new("RGBA", (128, 128), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([14, 40, 84, 88], radius=10, outline=color, width=5)
    d.rounded_rectangle([26, 50, 72, 78], radius=5, outline=color, width=3)
    step = 48 // (pins + 1)
    for i in range(1, pins + 1):
        y = 40 + i * step
        d.line([84, y, 112, y], fill=color, width=5)
    return img


def grommet_icon(color: str) -> Image.Image:
    img = Image.new("RGBA", (128, 128), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([24, 24, 104, 104], outline=color, width=6)
    d.ellipse([44, 44, 84, 84], outline=color, width=4)
    return img


def clip_icon(color: str) -> Image.Image:
    img = Image.new("RGBA", (128, 128), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.line([20, 64, 108, 64], fill=color, width=6)
    d.rectangle([54, 44, 74, 84], outline=color, width=5)
    d.line([64, 84, 64, 112], fill=color, width=5)
    d.polygon([(56, 112), (72, 112), (64, 124)], fill=color)
    return img


def terminal_icon(color: str) -> Image.Image:
    img = Image.new("RGBA", (128, 128), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([70, 40, 118, 88], outline=color, width=6)
    d.rectangle([14, 54, 74, 74], outline=color, width=5)
    return img


def rotated(img: Image.Image, angle: float) -> Image.Image:
    return img.rotate(angle, expand=False, resample=Image.BICUBIC)


PARTS = {
    # category: {part_name: (icon_image, z_depth)}
    "Connector holders": {
        "9J1973703_flat": (connector_icon("#202020", 4), 30),
        "9J1973703_up": (rotated(connector_icon("#202020", 4), 90), 38),
        "9J1973703_down": (rotated(connector_icon("#202020", 4), -90), 38),
        "4H0973713_flat": (connector_icon("#404040", 3), 25),
        "4H0973713_left": (rotated(connector_icon("#404040", 3), 45), 32),
        "4H0973713_right": (rotated(connector_icon("#404040", 3), -45), 32),
        "1J0973722_flat": (connector_icon("#000000", 2), 28),
    },
    "Grommet holders": {
        "GR-40": (grommet_icon("#202020"), 20),
        "GR-60": (grommet_icon("#404040"), 22),
    },
    "Clips": {
        "CLIP_T25": (clip_icon("#cc2222"), 10),
        "CLIP_T30": (clip_icon("#2244cc"), 12),
    },
    "Terminals": {
        "RING_M6": (terminal_icon("#22aa33"), 8),
        "RING_M8": (terminal_icon("#116622"), 8),
    },
}

CABLES = {
    "FLRY 2X0.5": 4.2,
    "FLRY 4X1.5": 7.8,
    "COAX RG174": 2.8,
}


def main() -> None:
    for category, parts in PARTS.items():
        for name, (icon, z_depth) in parts.items():
            folder = ROOT / category / name
            folder.mkdir(parents=True, exist_ok=True)
            icon.save(folder / "icon.png")
            (folder / f"{name}.step").write_text(
                STEP_TEMPLATE.format(name=name), encoding="utf-8"
            )
            (folder / "part.json").write_text(
                json.dumps({"category": category, "z_depth": z_depth}, indent=2),
                encoding="utf-8",
            )
    (ROOT / "cables.json").write_text(
        json.dumps(CABLES, indent=2), encoding="utf-8"
    )
    total = sum(len(p) for p in PARTS.values())
    print(f"Sample library written to {ROOT} ({total} parts, {len(CABLES)} cables)")


if __name__ == "__main__":
    main()
