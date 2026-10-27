"""The whole inventory as a download: one zip holding a JSON file and a Markdown file.

Every strain, whatever the page's filter shows. The JSON carries the same strain fields as
a backup (services/transfer.py) plus plant counts; the Markdown is for reading, one section
per breeder.
"""

from __future__ import annotations

import io
import json
import zipfile
from datetime import date

from sqlalchemy import func

from ..extensions import db
from ..models import Strain


def _strains() -> list[Strain]:
    return db.session.query(Strain).order_by(func.lower(Strain.name)).all()


def _row(s: Strain) -> dict:
    return {
        "id": s.id,
        "name": s.name,
        "breeder": s.breeder,
        "lineage": s.lineage,
        "seed_type": s.seed_type.value,
        "expression": s.expression.value if s.expression else None,
        "size": s.size.value,
        "flower_days": s.flower_days,
        "seeds_on_hand": s.seeds_on_hand,
        "plants": len(s.plants),
        "living_plants": len(s.living_plants),
        "notes": s.notes,
    }


def to_json(today: date) -> str:
    return json.dumps(
        {"exported_on": today.isoformat(), "strains": [_row(s) for s in _strains()]},
        indent=2,
        ensure_ascii=False,
    )


def to_markdown(today: date) -> str:
    strains = _strains()
    out = [
        "# Seed & clone inventory",
        "",
        f"Exported {today.strftime('%a %b %d, %Y')}. {len(strains)} strains.",
    ]
    by_breeder: dict[str, list[Strain]] = {}
    for s in strains:
        by_breeder.setdefault(s.breeder or "No breeder", []).append(s)
    for breeder in sorted(by_breeder, key=lambda b: (b == "No breeder", b.lower())):
        out += ["", f"## {breeder}"]
        for s in by_breeder[breeder]:
            r = _row(s)
            facts = [r["seed_type"], r["expression"], r["size"], f"{r['flower_days']} days"]
            out += ["", f"### {s.name}", "", " · ".join(f for f in facts if f)]
            if s.lineage:
                out.append(f"Lineage: {s.lineage}")
            if r["plants"]:
                out.append(f"Plants grown: {r['plants']} ({r['living_plants']} living)")
            if s.notes:
                out += ["", s.notes.replace("\r\n", "\n").strip()]
    return "\n".join(out) + "\n"


def to_zip(today: date) -> bytes:
    stem = f"canopy-inventory-{today.isoformat()}"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(f"{stem}.json", to_json(today))
        z.writestr(f"{stem}.md", to_markdown(today))
    return buf.getvalue()
