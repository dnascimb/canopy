"""Space planning: where plants are, how much room they take, and how many fit.

Footprints are square feet per plant and depend on the *stage* of the space and the
*size class* of the strain. They are deliberately conservative "comfortable" numbers
rather than maximum-cram values; tune ``FOOTPRINT_SQFT`` to taste.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date

from flask import current_app

from ..models import Group, Plant, PlantSize, PlantStatus, Space, SpaceStage

# Default sq ft per plant, by space stage then plant size class (small, medium, large).
# Override with CANOPY_FOOTPRINT_CLONE / _VEG / _FLOWER = "small,medium,large".
DEFAULT_FOOTPRINT_SQFT: dict[SpaceStage, dict[PlantSize, float]] = {
    SpaceStage.clone: {PlantSize.small: 0.1, PlantSize.medium: 0.15, PlantSize.large: 0.2},
    SpaceStage.vegetative: {PlantSize.small: 0.5, PlantSize.medium: 0.75, PlantSize.large: 1.0},
    SpaceStage.flowering: {PlantSize.small: 1.5, PlantSize.medium: 2.25, PlantSize.large: 3.0},
}


def footprint_table() -> dict[SpaceStage, dict[PlantSize, float]]:
    """Footprints in effect: app config overrides (from env) on top of the defaults."""
    table = {st: dict(v) for st, v in DEFAULT_FOOTPRINT_SQFT.items()}
    cfg = current_app.config.get("FOOTPRINT_SQFT") if current_app else None
    for stage, sizes in (cfg or {}).items():
        table[SpaceStage(stage)].update({PlantSize(k): float(v) for k, v in sizes.items()})
    return table


STAGE_FOR_STATUS: dict[PlantStatus, SpaceStage | None] = {
    PlantStatus.clone: SpaceStage.clone,
    PlantStatus.seedling: SpaceStage.clone,
    PlantStatus.vegetative: SpaceStage.vegetative,
    PlantStatus.flowering: SpaceStage.flowering,
    # Cut plants are off the floor: hanging somewhere, but not occupying a tent slot.
    PlantStatus.drying: None,
    PlantStatus.harvested: None,
    PlantStatus.killed: None,
}

STATUS_FOR_STAGE: dict[SpaceStage, PlantStatus] = {
    SpaceStage.clone: PlantStatus.clone,
    SpaceStage.vegetative: PlantStatus.vegetative,
    SpaceStage.flowering: PlantStatus.flowering,
}


def footprint(size: PlantSize, stage: SpaceStage) -> float:
    return footprint_table()[stage][size]


def plant_footprint(plant: Plant, stage: SpaceStage | None = None) -> float:
    stage = stage or STAGE_FOR_STATUS.get(plant.status)
    if stage is None:
        return 0.0
    return footprint(plant.strain.size, stage)


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
    def used_sqft(self) -> float:
        return round(sum(plant_footprint(p, self.space.stage) for p in self.plants), 2)

    @property
    def area(self) -> float | None:
        return self.space.area_sqft

    @property
    def free_sqft(self) -> float | None:
        return None if self.area is None else round(self.area - self.used_sqft, 2)

    @property
    def load(self) -> float:
        """0–1+ fraction of capacity used (area if known, else plant count vs max)."""
        if self.area:
            return self.used_sqft / self.area
        return self.count / self.space.capacity if self.space.capacity else 0.0

    @property
    def over(self) -> bool:
        return self.load > 1.0 or self.count > self.space.capacity

    def fits(self, size: PlantSize = PlantSize.medium) -> int:
        """How many plants of *size* the space could hold in total, empty."""
        by_area = math.floor(self.area / footprint(size, self.space.stage)) if self.area else None
        return min(self.space.capacity, by_area) if by_area is not None else self.space.capacity

    def room_for(self, size: PlantSize = PlantSize.medium) -> int:
        """How many more plants of *size* fit right now."""
        by_count = max(self.space.capacity - self.count, 0)
        if not self.area:
            return by_count
        by_area = max(
            math.floor((self.area - self.used_sqft) / footprint(size, self.space.stage)), 0
        )
        return min(by_count, by_area)

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


def group_footprint(group: Group, stage: SpaceStage) -> float:
    return round(sum(footprint(p.strain.size, stage) for p in group.living_plants), 2)


def load_series(space: Space, groups: Iterable[Group], *, ref: date | None = None) -> list[dict]:
    """Projected occupancy of a flowering space over the season, from the schedule.

    Returns points at every start/end checkpoint (plus *ref* if given): date, plant
    count, used sq ft, active group labels.
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
                "sqft": round(sum(group_footprint(g, space.stage) for g in active), 2),
                "groups": [g.label for g in active],
            }
        )
    return out


def peak(series: list[dict], *, since: date | None = None) -> dict | None:
    pts = [p for p in series if since is None or date.fromisoformat(p["date"]) >= since]
    return max(pts, key=lambda p: (p["sqft"], p["count"]), default=None)


def capacity_warning(
    space: Space,
    groups: Iterable[Group],
    occupancy_now: Occupancy | None = None,
    *,
    ref: date | None = None,
) -> str | None:
    """Why *space* is in breach, or None. Lives on the spaces page, not in the alert list.

    Checks the schedule's projected peak first, since that is the more useful warning,
    and falls back to what is physically in the space today.
    """
    worst = peak(load_series(space, groups, ref=ref), since=ref)
    if worst:
        day = date.fromisoformat(worst["date"])
        if space.area_sqft and worst["sqft"] > space.area_sqft:
            return f"needs {worst['sqft']:g} sq ft on {day:%b %d} but has {space.area_sqft:g}"
        if worst["count"] > space.capacity:
            return f"{worst['count']} plants on {day:%b %d}, over the {space.capacity} maximum"
    if occupancy_now is not None and occupancy_now.over:
        return (
            f"over capacity today: {occupancy_now.count} plants, "
            f"{occupancy_now.used_sqft:g} sq ft used"
        )
    return None


def move_plants(plants: Iterable[Plant], space: Space, *, ref: date | None = None) -> int:
    """Relocate plants, align status with the destination stage, and log the move.

    Moving into a flowering space flips the plant: it starts its own run on *ref* unless
    it already has one. This is the only move path, so a single plant and a whole group
    go through exactly the same code and end up in exactly the same state.
    """
    from . import lifecycle  # local: lifecycle reads models, spacing is imported by it

    on = ref or date.today()
    target = STATUS_FOR_STAGE[space.stage]
    n = 0
    for p in plants:
        if p.status in (PlantStatus.drying, PlantStatus.harvested, PlantStatus.killed):
            continue
        if target == PlantStatus.flowering and p.flower_start is None:
            lifecycle.set_flip([p], on, space=space, note=f"Moved into {space.name}.")
        else:
            lifecycle.record(p, target, on=on, space=space, note=f"Moved into {space.name}.")
        n += 1
    return n
