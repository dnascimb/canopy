"""Journal output: Autowrite from the change log, and JSON / Markdown exports.

Autowrite turns change-log lines nobody has written up yet into journal entries, one per
group per day. A plant with no group gets its own entry, except that cuttings taken off
one mother on one day share an entry under the mother. Each entry opens with what the
group or plant is (strain, breeder, lineage, where it is, day of flower on that date)
and lists what changed, with plants that had the same change named on one line.

Entries are ordinary journal entries once written: edit or delete them like any other.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import date

from ..extensions import db
from ..models import TASKS, Change, Group, JournalEntry, Plant, Space, Strain
from . import spacing


def _unit(c: Change) -> tuple[str, int]:
    """Which entry a line belongs in: its group, the mother of a fresh cutting, the plant."""
    if c.group_id is not None:
        return ("group", c.group_id)
    if c.plant is not None:
        p = c.plant
        if p.parent_id is not None and p.started_on == c.on:
            return ("plant", p.parent_id)
        return ("plant", p.id)
    return ("loose", c.id)


def _named(subjects: list[str]) -> str:
    counts = Counter(subjects)
    return ", ".join(s if n == 1 else f"{s} ×{n}" for s, n in counts.items())


def _change_lines(rows: list[Change], unit_label: str) -> list[str]:
    """One bullet per distinct change, naming every plant it happened to."""
    by_text: dict[str, list[str]] = {}
    for c in rows:
        by_text.setdefault(c.text, []).append(c.subject)
    lines = []
    for text, subjects in by_text.items():
        who = [s for s in subjects if s != unit_label]
        lines.append(f"- {_named(who)}: {text}" if who else f"- {text}")
    return lines


def _headline(items: list[Change]) -> str:
    """What the entry's title says happened, short enough to scan down a list."""
    texts = {c.text for c in items}
    if all(c.task == "cloned" for c in items):
        return f"took {len(items)} cuttings" if len(items) > 1 else "took a cutting"
    if all(t.startswith("added:") for t in texts):
        return f"added {len(items)} plants" if len(items) > 1 else "added"
    if len(texts) == 1:
        return items[0].text.split(" — ")[0]
    return f"{len(items)} changes"


def _strain_lines(strains: list[Strain]) -> list[str]:
    out = []
    for s in strains[:3]:
        line = s.display_name
        if s.lineage:
            line += f" — {s.lineage}"
        out.append(line + f" · {s.flower_days}d flower")
    if len(strains) > 3:
        out.append(f"and {len(strains) - 3} more strains")
    return out


def _context(
    group: Group | None, plant: Plant | None, on: date, spaces: list[Space]
) -> tuple[str, list[str], Space | None]:
    """The entry's label, its opening lines, and the space it belongs to."""
    if group is not None:
        # Strains from every plant, so a group whose last plant was just culled still says
        # what it was.
        strains = list({p.strain.id: p.strain for p in group.plants}.values())
        lines = []
        if len(group.living_plants) > 1:
            lines.append(f"Plants: {group.strain_summary()}")
        lines += _strain_lines(strains)
        where = group.space
        if where is not None:
            lines.append(f"Space: {where.name}")
        if (day := group.day_of_flower(on)) is not None:
            lines.append(f"Day {day} of flower ({group.flower_days}d run)")
        return group.label, lines, where
    assert plant is not None
    lines = _strain_lines([plant.strain])
    where = spacing.plant_location(plant, spaces)
    if where is not None:
        lines.append(f"Space: {where.name}")
    if plant.container is not None:
        lines.append(f"Container: {plant.container.value}")
    if (day := plant.day_of_flower(on)) is not None:
        lines.append(f"Day {day} of flower ({plant.flower_days}d run)")
    return plant.label, lines, where


def autowrite() -> tuple[int, int]:
    """Write up every unwritten change. Returns (entries written, changes covered)."""
    rows = (
        db.session.query(Change)
        .filter(Change.written.is_(False))
        .order_by(Change.on, Change.created_at, Change.id)
        .all()
    )
    if not rows:
        return 0, 0
    spaces = db.session.query(Space).order_by(Space.id).all()
    buckets: dict[tuple, list[Change]] = {}
    for c in rows:
        buckets.setdefault((c.on, *_unit(c)), []).append(c)

    written = 0
    for (on, kind, key), items in buckets.items():
        group = db.session.get(Group, key) if kind == "group" else None
        plant = db.session.get(Plant, key) if kind == "plant" else None
        if group is None and plant is None:
            label, lines, where = items[0].subject, [], None
        else:
            label, lines, where = _context(group, plant, on, spaces)
        changes = _change_lines(items, label)
        headline = _headline(items)
        title = f"{label}: {headline}"
        tasks = [t for t in TASKS if any(c.task == t for c in items)]
        body = "\n".join(lines + ([""] if lines else []) + changes)
        db.session.add(
            JournalEntry(
                entry_date=on,
                group=group,
                plant=plant,
                space=where,
                title=title if len(title) <= 160 else title[:159] + "…",
                body=body,
                tasks=",".join(tasks) or None,
            )
        )
        for c in items:
            c.written = True
        written += 1
    db.session.commit()
    return written, len(rows)


# ---------------------------------------------------------------------------
# Exports
# ---------------------------------------------------------------------------
def _entries() -> list[JournalEntry]:
    return db.session.query(JournalEntry).order_by(JournalEntry.entry_date, JournalEntry.id).all()


def to_json(today: date) -> str:
    """Every journal entry, oldest first. Photos are named, not embedded."""
    return json.dumps(
        {
            "exported_on": today.isoformat(),
            "entries": [
                {
                    "id": j.id,
                    "date": j.entry_date.isoformat(),
                    "title": j.title,
                    "body": j.body,
                    "tasks": j.task_labels,
                    "space": j.space.name if j.space else None,
                    "group": j.group.label if j.group else None,
                    "plant": j.plant.label if j.plant else None,
                    "plant_id": j.plant_id,
                    "photo": j.photo_path,
                }
                for j in _entries()
            ],
        },
        indent=2,
        ensure_ascii=False,
    )


def to_markdown(today: date) -> str:
    """Every journal entry, oldest first, one heading per day."""
    out = ["# Grow journal", "", f"Exported {today.strftime('%a %b %d, %Y')}."]
    day = None
    for j in _entries():
        if j.entry_date != day:
            day = j.entry_date
            out += ["", f"## {day.strftime('%a %b %d, %Y')}"]
        out += ["", f"### {j.title}"]
        where = [
            x
            for x in (
                j.space.name if j.space else None,
                j.group.label if j.group else None,
                j.plant.label if j.plant else None,
            )
            if x
        ]
        if where:
            out.append(f"_{' · '.join(where)}_")
        if j.task_labels:
            out.append(f"Tasks: {', '.join(j.task_labels)}")
        if j.body:
            out += ["", j.body.replace("\r\n", "\n").strip()]
        if j.photo_path:
            out += ["", f"Photo: `{j.photo_path}`"]
    return "\n".join(out) + "\n"
