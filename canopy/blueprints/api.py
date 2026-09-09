"""Read/write JSON API (v1). CSRF-exempt; intended for scripts, dashboards and Claude Code."""

from __future__ import annotations

from datetime import date

from flask import Blueprint, abort, jsonify, request

from ..extensions import db
from ..models import Group, GroupStatus, Plant, PlantSize, Space, Strain
from ..services import lifecycle, spacing, transfer
from ..services import scheduling as sched

bp = Blueprint("api", __name__)


def _group(g: Group, ref: date) -> dict:
    return {
        "id": g.id,
        "number": g.number,
        "name": g.name,
        "label": g.label,
        "space": g.space.name if g.space else None,
        "space_id": g.space_id,
        "flower_start": g.flower_start.isoformat() if g.flower_start else None,
        "flower_end": g.flower_end.isoformat() if g.flower_end else None,
        "flower_days": g.flower_days,
        "status": g.status.value,
        "color": g.color,
        "day_of_flower": g.day_of_flower(ref),
        "plants": [
            {"id": p.id, "label": p.label, "strain": p.strain.name, "status": p.status.value}
            for p in g.plants
        ],
        "notes": g.notes,
    }


@bp.get("/health")
def health():
    return jsonify({"status": "ok", "today": sched.today().isoformat()})


@bp.get("/timeline")
def timeline():
    ref = sched.today()
    units = sched.scheduled_units(
        db.session.query(Group).all(), db.session.query(Plant).all()
    )
    rows = sched.timeline_rows(units, ref=ref)
    t0, t1 = sched.timeline_bounds(rows)
    return jsonify(
        {"today": ref.isoformat(), "start": t0.isoformat(), "end": t1.isoformat(), "rows": rows}
    )


@bp.get("/events")
def events():
    return jsonify(
        [
            {"date": e.on.isoformat(), "kind": e.kind, "group_id": e.group.id, "label": e.label}
            for e in sched.events(
                sched.scheduled_units(
                    db.session.query(Group).all(), db.session.query(Plant).all()
                )
            )
        ]
    )


@bp.get("/openings")
def openings():
    return jsonify(
        [
            {
                "date": o.on.isoformat(),
                "freed_by": o.freed_by.label,
                "group_id": o.freed_by.id,
                "space": o.space.name if o.space else None,
            }
            for o in sched.openings(
                sched.scheduled_units(
                    db.session.query(Group).all(), db.session.query(Plant).all()
                )
            )
        ]
    )


@bp.get("/conflicts")
def conflicts():
    groups = db.session.query(Group).all()
    spaces = db.session.query(Space).all()
    plants = db.session.query(Plant).all()
    return jsonify(
        [
            {
                "severity": c.severity,
                "message": c.message,
                "group_id": c.group.id if c.group else None,
            }
            for c in sched.conflicts(groups, spaces, plants)
        ]
    )


@bp.get("/spaces")
def list_spaces():
    """Spaces with current occupancy (by plant location) and fit estimates."""
    spaces = db.session.query(Space).order_by(Space.id).all()
    occ = spacing.occupancy(spaces, db.session.query(Plant).all())
    return jsonify(
        [
            {
                "id": s.id,
                "name": s.name,
                "stage": s.stage.value,
                "width_ft": s.width_ft,
                "length_ft": s.length_ft,
                "area_sqft": s.area_sqft,
                "capacity": s.capacity,
                "plants": occ[s.id].count,
                "used_sqft": occ[s.id].used_sqft,
                "load": round(occ[s.id].load, 3),
                "fits": {sz.value: occ[s.id].fits(sz) for sz in PlantSize},
                "room_for": {sz.value: occ[s.id].room_for(sz) for sz in PlantSize},
            }
            for s in spaces
        ]
    )


@bp.get("/spaces/<int:space_id>/load")
def space_load(space_id: int):
    s = db.session.get(Space, space_id) or abort(404)
    return jsonify(spacing.load_series(s, db.session.query(Group).all(), ref=sched.today()))


@bp.get("/groups")
def list_groups():
    ref = sched.today()
    return jsonify([_group(g, ref) for g in db.session.query(Group).order_by(Group.number)])


@bp.get("/groups/<int:group_id>")
def get_group(group_id: int):
    g = db.session.get(Group, group_id) or abort(404)
    return jsonify(_group(g, sched.today()))


@bp.patch("/groups/<int:group_id>")
def patch_group(group_id: int):
    """Update schedule fields: flower_start, flower_days, status, space_id, name, notes."""
    g = db.session.get(Group, group_id) or abort(404)
    data = request.get_json(silent=True) or {}
    days = int(data["flower_days"]) if "flower_days" in data else None
    if "flower_start" in data:
        if data["flower_start"]:
            lifecycle.set_flip(
                g.living_plants, date.fromisoformat(data["flower_start"]),
                days=days, space=g.space, note="Set through the API.",
            )
        else:
            lifecycle.clear_flip(g.living_plants)
    elif days is not None:
        for p in g.living_plants:
            p.flower_days_override = days
    if "status" in data:
        g.status = GroupStatus(data["status"])
    for key in ("space_id", "name", "notes"):
        if key in data:
            setattr(g, key, data[key])
    db.session.commit()
    return jsonify(_group(g, sched.today()))


@bp.get("/strains")
def list_strains():
    return jsonify(
        [
            {
                "id": s.id,
                "name": s.name,
                "breeder": s.breeder,
                "lineage": s.lineage,
                "seed_type": s.seed_type.value,
                "flower_days": s.flower_days,
                "seeds_on_hand": s.seeds_on_hand,
                "size": s.size.value,
                "expression": s.expression.value if s.expression else None,
                "plants": len(s.plants),
            }
            for s in db.session.query(Strain).order_by(Strain.name)
        ]
    )


@bp.get("/plants")
def list_plants():
    spaces = db.session.query(Space).all()
    out = []
    for p in db.session.query(Plant).order_by(Plant.id):
        loc = spacing.plant_location(p, spaces)
        out.append(
            {
                "id": p.id,
                "label": p.label,
                "strain": p.strain.name,
                "group_id": p.group_id,
                "group": p.group.label if p.group else None,
                "status": p.status.value,
                "location": loc.name if loc else None,
                "space_id": loc.id if loc else None,
            }
        )
    return jsonify(out)


@bp.get("/export")
def export_all():
    return jsonify(transfer.dump())


@bp.get("/export.md")
def export_md():
    return (
        sched.markdown_export(db.session.query(Group).all()),
        200,
        {"Content-Type": "text/markdown"},
    )
