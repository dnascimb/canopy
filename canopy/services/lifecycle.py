"""Plant lifecycle: recording what happened, and reading the schedule back off it.

A plant owns its own schedule. `plant_events` is the record of every step it took, and
`Plant.flower_start` is simply the last time it entered flower. Groups are containers —
their dates are the span of the plants inside them — so the same call flips one plant or
a hundred, and a plant with no group is scheduled exactly like one in a group.

Everything that changes a plant's status should come through here, so nothing slips into
a new state without leaving a trace.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date

from ..extensions import db
from ..models import Plant, PlantEvent, PlantStatus, Space


def record(
    plant: Plant,
    to_status: PlantStatus,
    *,
    on: date,
    space: Space | None = None,
    note: str | None = None,
) -> PlantEvent | None:
    """Move *plant* to *to_status* and log it. No-op when nothing would change."""
    if plant.status == to_status and (space is None or plant.space_id == space.id):
        return None
    event = PlantEvent(
        plant=plant,
        on=on,
        from_status=plant.status,
        to_status=to_status,
        space=space if space is not None else plant.space,
        note=note,
    )
    plant.status = to_status
    if space is not None:
        plant.space = space
    db.session.add(event)
    return event


def born(
    plant: Plant,
    *,
    on: date,
    space: Space | None = None,
    note: str | None = None,
) -> PlantEvent:
    """The first row in a plant's log.

    Not a transition — a plant arrives already in some state — so `record()` would see
    nothing changing and write nothing. `from_status` is None, which reads as
    "started as a clone" rather than "None to clone".
    """
    event = PlantEvent(
        plant=plant,
        on=on,
        from_status=None,
        to_status=plant.status,
        space=space if space is not None else plant.space,
        note=note,
    )
    db.session.add(event)
    return event


def _today() -> date:
    from . import scheduling

    return scheduling.today()


def set_flip(
    plants: Iterable[Plant],
    on: date,
    *,
    days: int | None = None,
    space: Space | None = None,
    note: str | None = None,
) -> int:
    """Put *plants* into flower on *on*, replacing any flip they already had.

    Idempotent: re-flipping to the same date rewrites the one event rather than stacking
    duplicates, so correcting a date never leaves a trail of contradictory flips.
    """
    n = 0
    for p in plants:
        if p.status == PlantStatus.killed:
            continue
        for stale in [e for e in p.events if e.to_status == PlantStatus.flowering]:
            p.events.remove(stale)
            db.session.delete(stale)
        db.session.add(
            PlantEvent(
                plant=p,
                on=on,
                from_status=None if p.status == PlantStatus.flowering else p.status,
                to_status=PlantStatus.flowering,
                space=space if space is not None else p.space,
                note=note,
            )
        )
        # A flip dated in the future is a plan, not a transition. The event is still
        # written, so the timeline and flower_start are right, but the plant keeps its
        # current status and location until the day arrives — otherwise scheduling a tray
        # of unrooted clones drops them into the flower tent today.
        if on <= _today():
            p.status = PlantStatus.flowering
            if space is not None:
                p.space = space
        if days is not None:
            p.flower_days_override = days
        n += 1
    return n


def clear_flip(plants: Iterable[Plant]) -> int:
    """Un-schedule: drop the flowering events, so the plants read as never flipped."""
    n = 0
    for p in plants:
        stale = [e for e in p.events if e.to_status == PlantStatus.flowering]
        for e in stale:
            p.events.remove(e)
            db.session.delete(e)
        n += len(stale)
    return n


def history(plant: Plant) -> list[PlantEvent]:
    """Oldest first — what the plant page draws its lifecycle strip from."""
    return sorted(plant.events, key=lambda e: (e.on, e.id or 0))


def stage_spans(plant: Plant, *, ref: date | None = None) -> list[dict]:
    """Contiguous stretches the plant spent in each status.

    Returns `{status, start, end, days}` per stretch, the last one running to *ref*
    (or to the plant's end date if it is finished).
    """
    events = history(plant)
    if not events:
        return []
    stop = plant.ended_on or ref or date.today()
    spans = []
    for i, e in enumerate(events):
        later = events[i + 1] if i + 1 < len(events) else None
        end = later.on if later else stop
        if end < e.on:
            end = e.on
        spans.append(
            {
                "status": e.to_status,
                "start": e.on,
                "end": end,
                "days": (end - e.on).days,
                # A stretch is only a measurement once it has finished. The last one is
                # still running unless the plant itself has ended.
                "closed": later is not None or plant.ended_on is not None,
            }
        )
    return spans


def settle_group(group) -> bool:
    """Move a group to *drying* once nothing in it is still in flower.

    Cutting the last flowering plant is what ends a group's run, whether that happened
    through a harvest record or by setting one plant's status by hand. Returns True if
    the group's status actually changed.
    """
    from ..models import GroupStatus, PlantStatus

    if group is None or group.status in (GroupStatus.drying, GroupStatus.done):
        return False
    if any(p.status == PlantStatus.flowering for p in group.living_plants):
        return False
    group.status = GroupStatus.drying
    return True
