"""Draw numbered callouts on documentation screenshots.

Uses element bounding boxes recorded by scripts/screenshots.py (docs/screenshots/boxes.json)
so the callouts always line up with the real layout. Writes <name>_annotated.png.
Run after screenshots.py:  python scripts/annotate.py
"""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
SHOTS = ROOT / "docs" / "screenshots"
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
ACCENT = (240, 168, 58)
INK = (42, 28, 5)


def annotate(name: str, entries: list[dict]) -> None:
    src = SHOTS / f"{name}.png"
    if not src.exists():
        print("skip", name)
        return
    im = Image.open(src).convert("RGBA")
    overlay = Image.new("RGBA", im.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    font = ImageFont.truetype(FONT, 17)
    r = 15
    for i, entry in enumerate(entries, start=1):
        bb = entry.get("box")
        if not bb:
            continue
        x0, y0 = bb["x"] - 4, bb["y"] - 4
        x1, y1 = bb["x"] + bb["width"] + 4, bb["y"] + bb["height"] + 4
        d.rounded_rectangle((x0, y0, x1, y1), radius=6, outline=ACCENT + (235,), width=2)
        cx, cy = int(x0) + 2, int(y0) + 2  # badge on the top-left corner of the box
        d.ellipse(
            (cx - r, cy - r, cx + r, cy + r), fill=ACCENT + (255,), outline=INK + (255,), width=2
        )
        t = str(i)
        tb = d.textbbox((0, 0), t, font=font)
        d.text(
            (cx - (tb[2] - tb[0]) / 2 - tb[0], cy - (tb[3] - tb[1]) / 2 - tb[1]),
            t,
            font=font,
            fill=INK + (255,),
        )
    Image.alpha_composite(im, overlay).convert("RGB").save(
        SHOTS / f"{name}_annotated.png", optimize=True
    )
    print("wrote", f"{name}_annotated.png")


if __name__ == "__main__":
    boxes = json.loads((SHOTS / "boxes.json").read_text())
    for name, entries in boxes.items():
        annotate(name, entries)
