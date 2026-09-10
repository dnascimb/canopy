"""Whole-database JSON backup and restore."""

from __future__ import annotations

from datetime import date

from ..extensions import db
from ..models import (
    Expression,
    Group,
    GroupStatus,
    Harvest,
    JournalEntry,
    Plant,
    PlantEvent,
    PlantSize,
    PlantStatus,
    SeedType,
    Space,
    SpaceStage,
    Strain,
)

SCHEMA_VERSION = 1


def _d(v: date | None) -> str | None:
    return v.isoformat() if v else None


def _pd(v: str | None) -> date | None:
    return date.fromisoformat(v) if v else None


def dump() -> dict:
    return {
        "schema": SCHEMA_VERSION,
        "spaces": [
            {
                "id": s.id,
                "name": s.name,
                "stage": s.stage.value,
                "width_ft": s.width_ft,
                "length_ft": s.length_ft,
                "capacity": s.capacity,
                "notes": s.notes,
            }
            for s in db.session.query(Space).order_by(Space.id)
        ],
        "strains": [
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
                "notes": s.notes,
            }
            for s in db.session.query(Strain).order_by(Strain.id)
        ],
        "groups": [
            {
                "id": g.id,
                "number": g.number,
                "name": g.name,
                "space_id": g.space_id,
                "flower_start": _d(g.flower_start),
                "flower_days": g.flower_days,
                "status": g.status.value,
                "color": g.color,
                "notes": g.notes,
            }
            for g in db.session.query(Group).order_by(Group.id)
        ],
        "plants": [
            {
                "id": p.id,
                "label": p.label,
                "strain_id": p.strain_id,
                "group_id": p.group_id,
                "space_id": p.space_id,
                "status": p.status.value,
                "started_on": _d(p.started_on),
                "ended_on": _d(p.ended_on),
                "end_reason": p.end_reason,
                "parent_id": p.parent_id,
                "flower_days_override": p.flower_days_override,
                "notes": p.notes,
            }
            for p in db.session.query(Plant).order_by(Plant.id)
        ],
        "harvests": [
            {
                "id": h.id,
                "group_id": h.group_id,
                "plant_id": h.plant_id,
                "harvested_on": _d(h.harvested_on),
                "notes": h.notes,
            }
            for h in db.session.query(Harvest).order_by(Harvest.id)
        ],
        "plant_events": [
            {
                "plant_id": e.plant_id,
                "on": _d(e.on),
                "from_status": e.from_status.value if e.from_status else None,
                "to_status": e.to_status.value,
                "space_id": e.space_id,
                "note": e.note,
            }
            for e in db.session.query(PlantEvent).order_by(PlantEvent.id)
        ],
        "journal_entries": [
            {
                "id": j.id,
                "entry_date": _d(j.entry_date),
                "group_id": j.group_id,
                "plant_id": j.plant_id,
                "space_id": j.space_id,
                "title": j.title,
                "body": j.body,
                "tasks": j.tasks,
                "photo_path": j.photo_path,
            }
            for j in db.session.query(JournalEntry).order_by(JournalEntry.id)
        ],
    }


def load(payload: dict, *, replace: bool = True) -> dict[str, int]:
    """Restore a backup produced by :func:`dump`. Returns counts per table."""
    if payload.get("schema") != SCHEMA_VERSION:
        raise ValueError(f"Unsupported schema version: {payload.get('schema')!r}")
    if replace:
        for model in (JournalEntry, Harvest, Plant, Group, Strain, Space):
            db.session.query(model).delete()
        db.session.flush()

    space_ids: dict[int, int] = {}
    for s in payload.get("spaces", []):
        obj = Space(
            name=s["name"],
            stage=SpaceStage(s.get("stage", "flowering")),
            width_ft=s.get("width_ft"),
            length_ft=s.get("length_ft"),
            capacity=s.get("capacity", 1),
            notes=s.get("notes"),
        )
        db.session.add(obj)
        db.session.flush()
        space_ids[s["id"]] = obj.id

    strain_ids: dict[int, int] = {}
    for s in payload.get("strains", []):
        obj = Strain(
            name=s["name"],
            breeder=s.get("breeder"),
            lineage=s.get("lineage"),
            seed_type=SeedType(s.get("seed_type", "regular")),
            flower_days=s.get("flower_days", 70),
            seeds_on_hand=s.get("seeds_on_hand", 0),
            size=PlantSize(s.get("size", "medium")),
            expression=Expression(s["expression"]) if s.get("expression") else None,
            notes=s.get("notes"),
        )
        db.session.add(obj)
        db.session.flush()
        strain_ids[s["id"]] = obj.id

    group_ids: dict[int, int] = {}
    for g in payload.get("groups", []):
        obj = Group(
            number=g["number"],
            name=g.get("name"),
            space_id=space_ids.get(g.get("space_id")),
            status=GroupStatus(g.get("status", "planned")),
            color=g.get("color", "#66bb6a"),
            notes=g.get("notes"),
        )
        db.session.add(obj)
        db.session.flush()
        group_ids[g["id"]] = obj.id

    plant_ids: dict[int, int] = {}
    for p in payload.get("plants", []):
        obj = Plant(
            label=p["label"],
            strain_id=strain_ids[p["strain_id"]],
            group_id=group_ids.get(p.get("group_id")),
            space_id=space_ids.get(p.get("space_id")),
            status=PlantStatus(p.get("status", "vegetative")),
            started_on=_pd(p.get("started_on")),
            ended_on=_pd(p.get("ended_on")),
            end_reason=p.get("end_reason"),
            flower_days_override=p.get("flower_days_override"),
            notes=p.get("notes"),
        )
        db.session.add(obj)
        db.session.flush()
        plant_ids[p["id"]] = obj.id

    # Parents are wired once every plant has an id, so order in the file does not matter.
    for p in payload.get("plants", []):
        if p.get("parent_id") and p["parent_id"] in plant_ids:
            db.session.get(Plant, plant_ids[p["id"]]).parent_id = plant_ids[p["parent_id"]]

    # The schedule lives on plant events. Newer backups carry them; older ones only have
    # the group's flip date, so rebuild one event per plant from that.
    if "plant_events" in payload:
        for e in payload["plant_events"]:
            db.session.add(
                PlantEvent(
                    plant_id=plant_ids[e["plant_id"]],
                    on=_pd(e["on"]),
                    from_status=PlantStatus(e["from_status"]) if e.get("from_status") else None,
                    to_status=PlantStatus(e["to_status"]),
                    space_id=space_ids.get(e.get("space_id")),
                    note=e.get("note"),
                )
            )
    else:
        starts = {g["id"]: g.get("flower_start") for g in payload.get("groups", [])}
        days = {g["id"]: g.get("flower_days", 70) for g in payload.get("groups", [])}
        for p in payload.get("plants", []):
            gid = p.get("group_id")
            if gid is None or not starts.get(gid):
                continue
            plant = db.session.get(Plant, plant_ids[p["id"]])
            plant.flower_days_override = days[gid]
            db.session.add(
                PlantEvent(
                    plant=plant,
                    on=_pd(starts[gid]),
                    to_status=PlantStatus.flowering,
                    space_id=space_ids.get(
                        next(g["space_id"] for g in payload["groups"] if g["id"] == gid)
                    ),
                    note="Rebuilt from the group's flip date in an older backup.",
                )
            )

    for h in payload.get("harvests", []):
        db.session.add(
            Harvest(
                group_id=group_ids.get(h.get("group_id")),
                plant_id=plant_ids.get(h.get("plant_id")),
                harvested_on=_pd(h["harvested_on"]),
                notes=h.get("notes"),
            )
        )
    for j in payload.get("journal_entries", []):
        db.session.add(
            JournalEntry(
                entry_date=_pd(j["entry_date"]),
                group_id=group_ids.get(j.get("group_id")),
                plant_id=plant_ids.get(j.get("plant_id")),
                space_id=space_ids.get(j.get("space_id")),
                title=j["title"],
                body=j.get("body"),
                tasks=j.get("tasks"),
                photo_path=j.get("photo_path"),
            )
        )
    db.session.commit()
    return {
        "spaces": len(space_ids),
        "strains": len(strain_ids),
        "groups": len(group_ids),
        "plants": len(plant_ids),
        "harvests": len(payload.get("harvests", [])),
        "journal_entries": len(payload.get("journal_entries", [])),
    }
