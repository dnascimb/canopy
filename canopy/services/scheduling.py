"""Scheduling logic.

Everything here is pure computation over model objects so it can be unit-tested
without a request context. The blueprints and API are thin wrappers around it.

Key concepts
------------
* An **event** is a dated "start flower" or "end flower" milestone for a group.
* An **opening** is a date on which a flowering space frees up because a group
  finishes. Unscheduled groups can be slotted into the earliest opening.
* A **conflict** is a space whose plant capacity is exceeded on some day, or a
  group that is flowering without any space assigned.
* A **ramp-down** is a flowering run close enough to harvest that it should be
  watered at half strength.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta

from flask import current_app

from ..models import Group, GroupStatus, Plant, PlantStatus, Space, SpaceStage, Strain


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
        return "#9e9e9e"

    @property
    def status(self) -> GroupStatus:
        return GroupStatus.flowering if self.plant.flower_start else GroupStatus.planned

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

    def is_flowering_on(self, day: date) -> bool:
        return self.plant.is_flowering_on(day)

    def day_of_flower(self, day: date) -> int | None:
        return self.plant.day_of_flower(day)

    def progress(self, day: date) -> float:
        return self.plant.progress(day)


def scheduled_units(groups: Iterable[Group], plants: Iterable[Plant] = ()) -> list:
    """Everything the calendar should show: groups, plus scheduled plants without one."""
    units = list(groups)
    units += [LonePlant(p) for p in plants if p.group_id is None and p.flower_start is not None]
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
def timeline_rows(groups: Iterable[Group], *, ref: date | None = None) -> list[dict]:
    ref = ref or today()
    rows = []
    for g in sorted(groups, key=lambda g: (g.flower_start or date.max, g.number)):
        if g.flower_start is None:
            continue
        rows.append(
            {
                "id": g.id,
                "number": g.number,
                "label": g.label,
                "start": g.flower_start.isoformat(),
                "end": g.flower_end.isoformat(),
                "days": g.flower_days,
                "color": g.color,
                "status": g.status.value,
                "space": g.space.name if g.space else None,
                "strains": g.strain_labels(),
                "plant_count": len(g.living_plants),
                "progress": round(g.progress(ref), 3),
                "day_of_flower": g.day_of_flower(ref),
            }
        )
    return rows


def timeline_bounds(rows: list[dict], *, pad_days: int = 7) -> tuple[date, date]:
    if not rows:
        t = today()
        return t.replace(day=1), t + timedelta(days=90)
    start = min(date.fromisoformat(r["start"]) for r in rows) - timedelta(days=pad_days)
    end = max(date.fromisoformat(r["end"]) for r in rows) + timedelta(days=pad_days)
    return start, end


# ---------------------------------------------------------------------------
# Openings & suggestions
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Opening:
    on: date
    freed_by: Group
    space: Space | None


def openings(groups: Iterable[Group], *, ref: date | None = None) -> list[Opening]:
    """Dates on which a flowering slot frees up, from *ref* onward.

    A slot is considered taken again if another scheduled group starts in the same
    space on the same day (the usual "grp1 ends / grp7 starts" pattern).
    """
    ref = ref or today()
    scheduled = [g for g in groups if g.flower_start is not None]
    starts = {(g.space_id, g.flower_start) for g in scheduled}
    out = []
    for g in scheduled:
        end = g.flower_end
        if end < ref:
            continue
        if (g.space_id, end) in starts:
            continue  # already back-filled
        out.append(Opening(end, g, g.space))
    return sorted(out, key=lambda o: (o.on, o.freed_by.number))


def suggest_start(
    group: Group, all_groups: Iterable[Group], *, ref: date | None = None
) -> Opening | None:
    """Earliest opening a not-yet-scheduled group could take."""
    others = [g for g in all_groups if g.id != group.id]
    opens = openings(others, ref=ref)
    if group.space_id:
        same = [o for o in opens if o.space is None or o.space.id == group.space_id]
        opens = same or opens
    return opens[0] if opens else None


# ---------------------------------------------------------------------------
# Conflicts
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Conflict:
    severity: str  # "note" | "warning" | "error"
    message: str
    group: Group | None = None
    space: Space | None = None


def conflicts(
    groups: Iterable[Group],
    spaces: Iterable[Space],
    plants: Iterable[Plant] = (),
    *,
    ref: date | None = None,
) -> list[Conflict]:
    ref = ref or today()
    groups = list(groups)
    spaces = list(spaces)
    plants = list(plants)
    out: list[Conflict] = []

    # A group's dates come from its plants, so "scheduled with nothing in it" is no
    # longer a state that can exist and is not checked for.
    for g in groups:
        if g.status == GroupStatus.flowering and g.flower_start is None:
            out.append(
                Conflict("error", f"{g.label} is marked flowering but has no start date.", g)
            )
        if g.flower_start and g.space is None and g.flower_end >= ref:
            out.append(
                Conflict("warning", f"{g.label} is scheduled but not assigned to a space.", g)
            )

    # Space capacity is deliberately not reported here. It is an estimate from footprints
    # and dimensions, so it belongs on the spaces page as a label against the room in
    # question — see spacing.capacity_warning() — rather than in a list of things that
    # are actually wrong with the schedule.
    return out


# ---------------------------------------------------------------------------
# Ramp-down: cutting water back as a run finishes
# ---------------------------------------------------------------------------
RAMP_DOWN_DAYS = 14


@dataclass(frozen=True)
class RampDown:
    """A flowering run close enough to harvest that watering should be halved."""

    unit: Group | object
    end: date
    days_left: int
    plants: int
    spread: bool  # the run's plants do not all finish on the same day

    @property
    def label(self) -> str:
        return self.unit.label

    @property
    def when(self) -> str:
        if self.days_left == 0:
            return "today"
        if self.days_left == 1:
            return "tomorrow"
        return f"in {self.days_left} days"

    @property
    def message(self) -> str:
        first = ", first plants" if self.spread else ""
        return (
            f"{self.label} finishes {self.when}{first} — plain water only, half the usual amount."
        )

    @property
    def lone_plant(self) -> Plant | None:
        """The plant, when this run is one standing outside any group — else None.

        Lets a caller link to the right page without knowing what a LonePlant is.
        """
        return getattr(self.unit, "plant", None)


def ramp_down(
    units: Iterable[Group],
    spaces: Iterable[Space],
    *,
    ref: date | None = None,
    within: int = RAMP_DOWN_DAYS,
) -> list[RampDown]:
    """Flowering runs within *within* days of harvest, which want half water.

    Only runs standing in a flowering space qualify — nothing in veg or on the clone
    shelf is finishing anything. The trigger is the *earliest* living plant to finish,
    not the latest: once the first plants in a run are close, the whole run is being
    watered down together, so waiting for the last one would raise the alert too late.
    """
    ref = ref or today()
    flowering = {s.id for s in spaces if s.stage == SpaceStage.flowering}
    out: list[RampDown] = []
    for u in units:
        if u.space_id not in flowering:
            continue
        ends = [p.flower_end for p in u.living_plants if p.flower_end]
        if not ends:
            continue
        first, last = min(ends), max(ends)
        days_left = (first - ref).days
        if 0 <= days_left <= within:
            out.append(RampDown(u, first, days_left, len(ends), first != last))
    return sorted(out, key=lambda r: (r.days_left, r.label))


# ---------------------------------------------------------------------------
# Status helpers
# ---------------------------------------------------------------------------
def implied_status(group: Group, ref: date | None = None) -> GroupStatus:
    """What the calendar says a group's status should be, given its dates."""
    ref = ref or today()
    if group.flower_start is None:
        return GroupStatus.planned if not group.plants else GroupStatus.vegetative
    if ref < group.flower_start:
        return GroupStatus.vegetative
    if group.is_flowering_on(ref):
        return GroupStatus.flowering
    return GroupStatus.drying


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
