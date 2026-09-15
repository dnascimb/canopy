"""Space planning: where plants are and how many a space holds.

The plant is the first-class thing here; a space is a loose location one or more plants
sit in. Its name says what it is mainly for, but any of them can be overloaded — a clone
shelf doubles as pollen collection and veg overflow — so a space declares the stages it
can host and caps how many plants it holds. Deliberately no square footage: floor area
was a guess from the strain's size class and the room's stage, and it was wrong by 17x
for a tray of clones in 16oz cups. Counts, states and locations are what get tracked.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date

from ..models import Group, Plant, PlantStatus, Space, SpaceStage

STAGE_FOR_STATUS: dict[PlantStatus, SpaceStage | None] = {
    PlantStatus.clone: SpaceStage.clone,
    PlantStatus.seedling: SpaceStage.clone,
    PlantStatus.vegetative: SpaceStage.vegetative,
    PlantStatus.flowering: SpaceStage.flowering,
    # Cut plants are nowhere: off the shelf and out of every count.
    PlantStatus.harvested: None,
    PlantStatus.killed: None,
}

STATUS_FOR_STAGE: dict[SpaceStage, PlantStatus] = {
    SpaceStage.clone: PlantStatus.clone,
    SpaceStage.vegetative: PlantStatus.vegetative,
    SpaceStage.flowering: PlantStatus.flowering,
}


def default_space(stage: SpaceStage, spaces: Iterable[Space]) -> Space | None:
    """The first space of a stage — where plants of that stage live unless told otherwise."""
    return next((s for s in sorted(spaces, key=lambda s: s.id) if s.stage == stage), None)


def plant_location(plant: Plant, spaces: Iterable[Space]) -> Space | None:
    """Where a plant is right now: explicit space, else its group's flowering space, else the
    default space for its stage. Harvested and killed plants are nowhere."""
    stage = STAGE_FOR_STATUS.get(plant.status)
    if stage is None:
        return None
    if plant.space is not None:
        return plant.space
    if stage == SpaceStage.flowering and plant.group and plant.group.space:
        return plant.group.space
    return default_space(stage, spaces)


@dataclass
class Occupancy:
    space: Space
    plants: list[Plant] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.plants)

    @property
    def load(self) -> float:
        """0-1+ fraction of the space's plant cap in use."""
        return self.count / self.space.capacity if self.space.capacity else 0.0

    @property
    def over(self) -> bool:
        return self.count > self.space.capacity

    def room_for(self) -> int:
        """How many more plants fit right now."""
        return max(self.space.capacity - self.count, 0)

    def groups(self) -> list[Group]:
        seen: list[Group] = []
        for p in self.plants:
            if p.group and p.group not in seen:
                seen.append(p.group)
        return seen


def occupancy(spaces: Iterable[Space], plants: Iterable[Plant]) -> dict[int, Occupancy]:
    spaces = list(spaces)
    occ = {s.id: Occupancy(s) for s in spaces}
    for p in plants:
        loc = plant_location(p, spaces)
        if loc is not None:
            occ[loc.id].plants.append(p)
    return occ


def load_series(space: Space, groups: Iterable[Group], *, ref: date | None = None) -> list[dict]:
    """Projected occupancy of a flowering space over the season, from the schedule.

    Returns points at every start/end checkpoint (plus *ref* if given): date, plant
    count, active group labels.
    """
    # "groups" here is whatever the caller schedules — real groups and lone plants alike.
    sg = [g for g in groups if g.space_id == space.id and g.flower_start]
    if not sg:
        return []
    days = {g.flower_start for g in sg} | {g.flower_end for g in sg}
    if ref:
        days.add(ref)
    days = sorted(days)
    out = []
    for d in days:
        active = [g for g in sg if g.is_flowering_on(d)]
        out.append(
            {
                "date": d.isoformat(),
                "count": sum(len(g.living_plants) for g in active),
                "groups": [g.label for g in active],
            }
        )
    return out


def peak(series: list[dict], *, since: date | None = None) -> dict | None:
    pts = [p for p in series if since is None or date.fromisoformat(p["date"]) >= since]
    return max(pts, key=lambda p: p["count"], default=None)


def capacity_warning(
    space: Space,
    groups: Iterable[Group],
    occupancy_now: Occupancy | None = None,
    *,
    ref: date | None = None,
) -> str | None:
    """Why *space* is over its plant cap, or None. A spaces-page label, not an alert.

    Checks the schedule's projected peak first, since that is the more useful warning,
    and falls back to what is physically in the space today.
    """
    worst = peak(load_series(space, groups, ref=ref), since=ref)
    if worst and worst["count"] > space.capacity:
        day = date.fromisoformat(worst["date"])
        return f"{worst['count']} plants on {day:%b %d}, over the {space.capacity} it holds"
    if occupancy_now is not None and occupancy_now.over:
        return f"{occupancy_now.count} plants today, over the {space.capacity} it holds"
    return None


def move_plants(plants: Iterable[Plant], space: Space, *, ref: date | None = None) -> int:
    """Relocate plants, align status with the destination stage, and log the move.

    Moving into a flowering space flips the plant: it starts its own run on *ref* unless
    it already has one. This is the only move path, so a single plant and a whole group
    go through exactly the same code and end up in exactly the same state.
    """
    from . import lifecycle  # local: lifecycle reads models, spacing is imported by it

    on = ref or date.today()
    n = 0
    for p in plants:
        if p.status in (PlantStatus.harvested, PlantStatus.killed):
            continue
        # A space that already hosts this plant's stage is a relocation, not a transition:
        # a flowering male parked on the clone shelf for pollen stays flowering, and veg
        # overflow onto that shelf stays vegetative. Otherwise the space's own stage wins.
        if space.can_host(STAGE_FOR_STATUS.get(p.status)):
            target = p.status
        else:
            target = STATUS_FOR_STAGE[space.stage]
        if target == PlantStatus.flowering and p.flower_start is None:
            lifecycle.set_flip([p], on, space=space, note=f"Moved into {space.name}.")
        else:
            lifecycle.record(p, target, on=on, space=space, note=f"Moved into {space.name}.")
        n += 1
    return n
