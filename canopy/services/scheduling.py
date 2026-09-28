"""Scheduling logic.

Everything here is pure computation over model objects so it can be unit-tested
without a request context. The blueprints and API are thin wrappers around it.

Canopy records what the grower did, when they did it. It does not propose flip dates or
find slots, and it does not raise alerts about what the grower should fix: there are no
openings, suggestions or conflict checks here by design.

Key concepts
------------
* An **event** is a dated "start flower" or "end flower" milestone for a group.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta

from flask import current_app

from ..models import (
    Group,
    GroupStatus,
    Plant,
    PlantStatus,
    Space,
    Strain,
    _spun_color,
)


# ---------------------------------------------------------------------------
# "Today" — overridable for demos and tests
# ---------------------------------------------------------------------------
def today() -> date:
    override = current_app.config.get("TODAY_OVERRIDE") if current_app else None
    if override:
        return date.fromisoformat(override)
    return date.today()


# ---------------------------------------------------------------------------
# Scheduled units: a group, or a plant standing on its own
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class LonePlant:
    """A scheduled plant with no group, presented to the calendar as a group of one.

    Groups are containers. A plant outside one is still a thing with a flip date and a
    harvest, so it belongs on the timeline and in the event table exactly like a group.
    """

    plant: Plant

    @property
    def id(self) -> int:
        return self.plant.id

    @property
    def number(self) -> float:
        # Sorts after real groups without colliding with their integer numbers.
        return 10_000 + (self.plant.id or 0)

    @property
    def label(self) -> str:
        return self.plant.label

    @property
    def color(self) -> str:
        """Its own colour, deterministic from the plant id.

        Every lone plant used to be the same grey, which is the same misread as two groups
        sharing a colour: the timeline tells rows apart by colour. The offset keeps these
        clear of the handful of generated colours groups draw from.
        """
        return _spun_color(1000 + (self.plant.id or 0))

    @property
    def href(self) -> str:
        return f"/plants/{self.plant.id}"

    @property
    def status(self) -> GroupStatus:
        # The plant's own state, not whether it has a flip date: one harvested is drying.
        return {
            PlantStatus.flowering: GroupStatus.flowering,
            PlantStatus.harvested: GroupStatus.drying,
        }.get(self.plant.status, GroupStatus.vegetative)

    @property
    def space(self) -> Space | None:
        return self.plant.space

    @property
    def space_id(self) -> int | None:
        return self.plant.space_id

    @property
    def flower_start(self) -> date | None:
        return self.plant.flower_start

    @property
    def flower_end(self) -> date | None:
        return self.plant.flower_end

    @property
    def flower_days(self) -> int:
        return self.plant.flower_days

    @property
    def living_plants(self) -> list[Plant]:
        return [self.plant] if self.plant.is_alive else []

    def strain_labels(self) -> list[str]:
        return [self.plant.strain.name]

    def strain_summary(self) -> str:
        return ", ".join(self.strain_labels())

    def is_flowering_on(self, day: date) -> bool:
        # A culled plant is not flowering, whatever its dates still say. Group answers
        # this the same way — its span is read off living_plants — but Plant.is_flowering_on
        # is pure date arithmetic, so the check has to happen here.
        return self.plant.is_alive and self.plant.is_flowering_on(day)

    def day_of_flower(self, day: date) -> int | None:
        return self.plant.day_of_flower(day)

    def progress(self, day: date) -> float:
        return self.plant.progress(day)


def scheduled_units(groups: Iterable[Group], plants: Iterable[Plant] = ()) -> list:
    """Everything the calendar should show: groups, plus scheduled plants without one.

    A culled plant is left out, as Group.scheduled_plants leaves it out of a group's span.
    """
    units = list(groups)
    units += [
        LonePlant(p)
        for p in plants
        if p.group_id is None and p.is_alive and p.flower_start is not None
    ]
    return units


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Event:
    on: date
    kind: str  # "start" | "end"
    group: Group

    @property
    def label(self) -> str:
        if self.kind == "start":
            return f"{self.group.label} start flower"
        return f"{self.group.label} end flower ({self.group.flower_days} days)"


def events(groups: Iterable[Group]) -> list[Event]:
    out: list[Event] = []
    for g in groups:
        if g.flower_start is None:
            continue
        out.append(Event(g.flower_start, "start", g))
        out.append(Event(g.flower_end, "end", g))
    # Ends before starts on the same day so "X ends / Y starts" reads naturally.
    return sorted(out, key=lambda e: (e.on, 0 if e.kind == "end" else 1, e.group.number))


def upcoming(groups: Iterable[Group], *, days: int = 30, ref: date | None = None) -> list[Event]:
    ref = ref or today()
    horizon = ref + timedelta(days=days)
    return [e for e in events(groups) if ref <= e.on <= horizon]


# ---------------------------------------------------------------------------
# Timeline rows (consumed by the JS Gantt and the ASCII renderer)
# ---------------------------------------------------------------------------
def pre_flower_start(unit: Group) -> date | None:
    """The earliest date we know a unit existed, before it flipped.

    Deliberately "before flower" rather than strictly vegetative. A strict veg-start would
    read the first `vegetative` event, and almost nothing has one: when this was written,
    2 of 34 scheduled units did, against 25 that have a usable start date. So this takes
    the first lifecycle event that is not the flip, and falls back to the plant's own
    `started_on`. The bar it draws is "alive but not yet flowering", which is the thing
    worth seeing on a calendar, and it sharpens on its own as more events get logged.
    """
    out: list[date] = []
    for p in unit.living_plants:
        before = [e.on for e in p.events if e.to_status != PlantStatus.flowering]
        if before:
            out.append(min(before))
        elif p.started_on:
            out.append(p.started_on)
    if not out:
        return None
    first = min(out)
    # A start date recorded after the fact can land on or after the flip — Jack Herer was
    # entered as starting Sep 7 and flipped Sep 4. There is no pre-flower span to draw
    # there, and drawing one gives a 1px sliver that reads as real data.
    if unit.flower_start is not None and first >= unit.flower_start:
        return None
    return first


def timeline_rows(
    groups: Iterable[Group], *, ref: date | None = None, include_unflipped: bool = False
) -> list[dict]:
    ref = ref or today()
    rows = []
    for g in sorted(groups, key=lambda g: (g.flower_start or date.max, g.number)):
        pre = pre_flower_start(g)
        if g.flower_start is None and not (include_unflipped and pre):
            continue
        flipped = g.flower_start is not None
        rows.append(
            {
                "id": g.id,
                # A lone plant is not a group, so it cannot be linked as one. Callers used
                # to build "/groups/<id>" from the id above and 404 on every lone plant.
                "href": getattr(g, "href", None) or f"/groups/{g.id}",
                "number": g.number,
                "label": g.label,
                "start": g.flower_start.isoformat() if flipped else None,
                "end": g.flower_end.isoformat() if flipped else None,
                # Where the bar for "alive but not yet flowering" begins. None when we have
                # no date at all for the unit before its flip.
                "pre_start": pre.isoformat() if pre else None,
                "days": g.flower_days if flipped else None,
                "color": g.color,
                "status": g.status.value,
                "space": g.space.name if g.space else None,
                "strains": g.strain_labels(),
                "plant_count": len(g.living_plants),
                "progress": round(g.progress(ref), 3) if flipped else 0,
                "day_of_flower": g.day_of_flower(ref) if flipped else None,
            }
        )
    return rows


def timeline_bounds(rows: list[dict], *, pad_days: int = 7) -> tuple[date, date]:
    if not rows:
        t = today()
        return t.replace(day=1), t + timedelta(days=90)
    # Flower spans only. The pre-flower span is deliberately excluded: including it would
    # stretch the axis back months and squash the flower bars in the default view, which is
    # the one view that must not change. The renderer widens the axis itself when a view
    # actually draws pre-flower bars.
    starts = [date.fromisoformat(r["start"]) for r in rows if r.get("start")]
    ends = [date.fromisoformat(r["end"]) for r in rows if r.get("end")]
    if not starts or not ends:
        t = today()
        return t.replace(day=1), t + timedelta(days=90)
    return min(starts) - timedelta(days=pad_days), max(ends) + timedelta(days=pad_days)


# ---------------------------------------------------------------------------
# Text exports (Markdown for note apps such as Joplin, plus an ASCII Gantt)
# ---------------------------------------------------------------------------
def _next_month(d: date) -> date:
    return (d.replace(day=28) + timedelta(days=4)).replace(day=1)


def ascii_timeline(rows: list[dict], *, width: int = 64, ref: date | None = None) -> str:
    """Plain-ASCII Gantt that survives any monospace renderer (Joplin, GitHub, terminals)."""
    if not rows:
        return "(no scheduled groups)"
    ref = ref or today()
    t0, t1 = timeline_bounds(rows, pad_days=0)
    t0 = t0.replace(day=1)
    total = max((t1 - t0).days, 1)

    def pos(d: date) -> int:
        return round((d - t0).days * width / total)

    label_w = max(len(r["label"]) for r in rows) + 1
    hdr = [" "] * width
    tick = ["-"] * width
    m = t0
    while m <= t1:
        p = pos(m)
        for i, ch in enumerate(m.strftime("%b").upper()):
            if p + i < width:
                hdr[p + i] = ch
        if p < width:
            tick[p] = "+"
        m = _next_month(m)
    tp = pos(ref)
    if 0 <= tp < width:
        tick[tp] = "*"

    lines = [" " * label_w + "|" + "".join(hdr), " " * label_w + "|" + "".join(tick)]
    for r in rows:
        s, e = pos(date.fromisoformat(r["start"])), pos(date.fromisoformat(r["end"]))
        bar = [" "] * width
        for i in range(s, min(max(e, s + 1), width)):
            bar[i] = "="
        lines.append(f"{r['label']:<{label_w}}|{''.join(bar)} {r['days']}d")
    lines.append(" " * label_w + "|" + "".join(tick))
    lines.append(f"{'':<{label_w}} * = today ({ref:%b %d})")
    return "\n".join(lines)


def markdown_export(groups: Iterable[Group], *, ref: date | None = None) -> str:
    """The bulleted-groups + schedule-table format used in grow notes."""
    ref = ref or today()
    groups = sorted(groups, key=lambda g: g.number)
    out = ["# Cultivation schedule", "", f"_Generated {ref:%b %d, %Y}_", "", "## Groups", ""]
    for g in groups:
        alive = ", ".join(p.label for p in g.living_plants) or "_(empty)_"
        dead = ", ".join(f"~~{p.label}~~" for p in g.killed_plants)
        line = f"- **{g.label}** — {alive}"
        if dead:
            line += f"  \n  killed: {dead}"
        out.append(line)
    out += ["", "## Schedule", "", "| date | event |", "| ---: | --- |"]
    for e in events(groups):
        out.append(f"| {e.on:%b %d} | {e.label} |")
    rows = timeline_rows(groups, ref=ref)
    out += ["", "## Timeline", "", "```", ascii_timeline(rows, ref=ref), "```", ""]
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Inventory helpers
# ---------------------------------------------------------------------------
def inventory_summary(strains: Iterable[Strain]) -> dict:
    strains = list(strains)
    return {
        "strains": len(strains),
        "seeds_on_hand": sum(s.seeds_on_hand for s in strains),
        "breeders": len({s.breeder for s in strains if s.breeder}),
    }


def plant_counts(plants: Iterable[Plant]) -> dict[str, int]:
    counts = {s.value: 0 for s in PlantStatus}
    for p in plants:
        counts[p.status.value] += 1
    return counts
