"""The change log: one line for everything done to a plant, a group or a harvest.

Lines are written by a `before_flush` hook rather than by each route, so nothing that
changes a plant — a page, the API, a backfill script — can forget to log it. The hook
reads what the session is about to save and turns it into plain sentences:
"vegetative → flowering · Flower Room", "container: 16oz → 1gal", "note: Up potted".

A restore or the demo seed pauses the hook (`paused()`), then `backfill()` rebuilds the
lines from the plant events and harvests already on file.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date

from sqlalchemy import event, inspect

from ..extensions import db
from ..models import Change, Group, Harvest, Plant, PlantEvent, PlantStatus

_PAUSED = "canopy.changes_paused"
# Plants logged as a bare "added" this transaction, waiting for their first event.
_BARE = "canopy.bare_adds"

# Notes the app writes on its own events. They repeat what the line already says.
_ECHOES = ("Moved into ", "Harvested from ", "Marked flowering.")

# Plain names for the columns that get a "field: old → new" line.
_PLANT_FIELDS = {
    "label": "label",
    "started_on": "started",
    "ended_on": "ended",
    "end_reason": "end reason",
    "flower_days_override": "flower days",
    "container": "container",
}
_GROUP_FIELDS = {"number": "number", "name": "name"}

_DATED_NOTE = re.compile(r"^(\d{4}-\d{2}-\d{2}): (.+)$")


def watch() -> None:
    """Start logging. Safe to call once per app; the hook is registered only once."""
    if not event.contains(db.session, "before_flush", _before_flush):
        event.listen(db.session, "before_flush", _before_flush)
        event.listen(db.session, "after_commit", _forget)
        event.listen(db.session, "after_soft_rollback", _forget)


def _forget(session, *_args) -> None:
    session.info.pop(_BARE, None)


@contextmanager
def paused() -> Iterator[None]:
    """Write nothing to the log inside this block (a restore, the demo seed)."""
    info = db.session.info
    before = info.get(_PAUSED)
    info[_PAUSED] = True
    try:
        yield
    finally:
        info[_PAUSED] = before


def pending_count() -> int:
    return db.session.query(Change).filter(Change.written.is_(False)).count()


# ---------------------------------------------------------------------------
# The hook
# ---------------------------------------------------------------------------
def _today() -> date:
    from . import scheduling

    return scheduling.today()


def _show(value) -> str:
    if value is None or value == "":
        return "—"
    if isinstance(value, date):
        return value.isoformat()
    return str(getattr(value, "value", value))


def _clip(text: str, n: int = 500) -> str:
    return text if len(text) <= n else text[: n - 1] + "…"


def _is_birth(e: PlantEvent) -> bool:
    """The plant's first event. A flip of a plant already in flower also has no
    from_status, but it comes after others."""
    if e.from_status is not None:
        return False
    return not any(o is not e and o.on <= e.on for o in e.plant.events)


def _event_text(e: PlantEvent) -> str:
    where = f" · {e.space.name}" if e.space is not None else ""
    if _is_birth(e):
        text = f"added: {e.plant.strain.display_name}, started as {e.to_status.value}{where}"
    elif e.from_status is None:
        text = f"→ {e.to_status.value}{where}"
    else:
        text = e.label
    if e.note and not e.note.startswith(_ECHOES) and not e.note.endswith("marked flowering."):
        text += f" — {e.note}"
    return text


def _event_task(e: PlantEvent) -> str | None:
    if _is_birth(e) and (e.plant.parent_id or e.plant.parent) is not None:
        return "cloned"
    if e.note and e.note.startswith("Moved into "):
        return "transplanted"
    return None


def _notes_lines(old: str | None, new: str | None) -> list[tuple[date | None, str]]:
    """What changed in a notes field, as (date, line) pairs.

    Text added to the end is the usual case — the plant page's Add note does exactly
    that, prefixed with its date — so it is logged as the note itself, on its own date.
    Anything else is an edit, logged as one line.
    """
    old_n = (old or "").replace("\r\n", "\n").rstrip()
    new_n = (new or "").replace("\r\n", "\n").rstrip()
    if old_n == new_n:
        return []
    if new_n.startswith(old_n):
        out: list[tuple[date | None, str]] = []
        for para in new_n[len(old_n) :].strip().split("\n\n"):
            para = para.strip()
            if not para:
                continue
            m = _DATED_NOTE.match(para)
            if m:
                out.append((date.fromisoformat(m.group(1)), f"note: {m.group(2)}"))
            else:
                out.append((None, f"note: {para}"))
        return out
    return [(None, "notes edited")]


def _ref_change(state, rel: str, col: str, session) -> tuple[object, object] | None:
    """(old, new) objects for a many-to-one that changed, by relationship or by id."""
    rel_hist = state.attrs[rel].history
    col_hist = state.attrs[col].history
    model = state.mapper.relationships[rel].mapper.class_
    if col_hist.has_changes():
        old_id = col_hist.deleted[0] if col_hist.deleted else None
        new_id = col_hist.added[0] if col_hist.added else None
        if old_id == new_id:
            return None
        with session.no_autoflush:
            old = session.get(model, old_id) if old_id else None
            new = session.get(model, new_id) if new_id else None
        return old, new
    if rel_hist.has_changes():
        new = rel_hist.added[0] if rel_hist.added else None
        old_id = getattr(state.obj(), col)
        if new is not None and new.id is not None and new.id == old_id:
            return None
        if new is None and old_id is None:
            return None
        with session.no_autoflush:
            old = session.get(model, old_id) if old_id else None
        return old, new
    return None


def _name(obj) -> str:
    if obj is None:
        return "none"
    for attr in ("display_name", "label", "name"):
        if hasattr(obj, attr):
            return str(getattr(obj, attr))
    return str(obj)


def _before_flush(session, _ctx, _instances) -> None:
    if session.info.get(_PAUSED):
        return
    today = _today()
    rows: list[Change] = []

    def add(on, subject, text, *, plant=None, group=None, task=None):
        rows.append(
            Change(
                on=on or today,
                subject=_clip(subject, 160),
                text=_clip(text),
                plant=plant,
                group=group,
                task=task,
            )
        )

    new_plants = {id(o) for o in session.new if isinstance(o, Plant)}
    deleted_plants = {id(o) for o in session.deleted if isinstance(o, Plant)}
    deleted_groups = {id(o) for o in session.deleted if isinstance(o, Group)}
    new_events = [o for o in session.new if isinstance(o, PlantEvent)]
    gone_events = [o for o in session.deleted if isinstance(o, PlantEvent)]
    evented = {id(e.plant) for e in new_events if e.plant is not None}
    born = {id(e.plant) for e in new_events if e.plant is not None and _is_birth(e)}

    def live_group(g):
        return None if g is None or id(g) in deleted_groups else g

    # A flip re-dated by set_flip() deletes the old flowering event and adds a new one.
    # The old event has already been taken off plant.events, which unsets its plant, so
    # the owner is found by id.
    redated: dict[int, PlantEvent] = {}
    for e in gone_events:
        with session.no_autoflush:
            owner = e.plant or (session.get(Plant, e.plant_id) if e.plant_id else None)
        if owner is None or id(owner) in deleted_plants:
            continue
        if e.to_status == PlantStatus.flowering and any(
            n.plant is owner and n.to_status == PlantStatus.flowering for n in new_events
        ):
            redated[id(owner)] = e
            continue
        what = "flip" if e.to_status == PlantStatus.flowering else f"'{e.label}'"
        add(
            None,
            owner.label,
            f"{what} of {e.on.isoformat()} removed",
            plant=owner,
            group=live_group(owner.group),
        )

    for e in new_events:
        p = e.plant
        if p is None:
            continue
        old = redated.get(id(p))
        if old is not None and e.to_status == PlantStatus.flowering:
            text = f"flip moved from {old.on.isoformat()} to {e.on.isoformat()}"
        else:
            text = _event_text(e)
            hist = inspect(p).attrs.end_reason.history
            reason = hist.added[0] if hist.added else None
            if e.to_status == PlantStatus.killed and reason and reason not in text:
                text += f" — {reason}"
        if _is_birth(e):
            # A plant flushed on its own (to get an id) before its first event was logged
            # as a bare "added"; the event says more, so it replaces that line.
            bare = session.info.get(_BARE, {}).pop(p, None)
            if bare is not None:
                bare.on, bare.text, bare.task = e.on, _clip(text), _event_task(e)
                continue
        add(e.on, p.label, text, plant=p, group=live_group(p.group), task=_event_task(e))

    for p in [o for o in session.new if isinstance(o, Plant)]:
        if id(p) not in born:
            add(
                p.started_on,
                p.label,
                f"added: {p.strain.display_name}",
                plant=p,
                group=live_group(p.group),
                task="cloned" if p.parent is not None else None,
            )
            session.info.setdefault(_BARE, {})[p] = rows[-1]

    for p in [o for o in session.dirty if isinstance(o, Plant)]:
        if id(p) in new_plants or id(p) in deleted_plants:
            continue
        _plant_changed(session, p, add, evented=id(p) in evented, group=live_group(p.group))

    for p in [o for o in session.deleted if isinstance(o, Plant)]:
        add(None, p.label, "deleted", group=live_group(p.group))

    for g in [o for o in session.new if isinstance(o, Group)]:
        add(None, g.label, "created", group=g)
    for g in [o for o in session.dirty if isinstance(o, Group)]:
        if id(g) not in deleted_groups:
            _group_changed(session, g, add)
    for g in [o for o in session.deleted if isinstance(o, Group)]:
        add(None, g.label, "deleted")

    for h in [o for o in session.new if isinstance(o, Harvest)]:
        target = h.plant or h.group
        text = "harvested" + (f" — {h.notes}" if h.notes else "")
        group = h.group or (h.plant.group if h.plant else None)
        add(h.harvested_on, _name(target), text, plant=h.plant, group=live_group(group))
    for h in [o for o in session.deleted if isinstance(o, Harvest)]:
        target = h.plant or h.group
        if target is None or id(target) in deleted_plants | deleted_groups:
            continue
        add(
            None,
            _name(target),
            f"harvest of {h.harvested_on.isoformat()} removed",
            plant=h.plant if h.plant is not None and id(h.plant) not in deleted_plants else None,
            group=live_group(h.group),
        )

    session.add_all(rows)


def _plant_changed(session, p: Plant, add, *, evented: bool, group) -> None:
    state = inspect(p)

    def line(text, on=None, task=None):
        add(on, p.label, text, plant=p, group=group, task=task)

    # Status and location changes made through lifecycle already have their event line.
    if not evented:
        hist = state.attrs.status.history
        if hist.has_changes() and hist.deleted and hist.added and hist.deleted[0] != hist.added[0]:
            line(f"{_show(hist.deleted[0])} → {_show(hist.added[0])} (edited)")
        if moved := _ref_change(state, "space", "space_id", session):
            line(f"location: {_name(moved[0])} → {_name(moved[1])}", task="transplanted")
    for rel, col, word in (
        ("strain", "strain_id", "strain"),
        ("group", "group_id", "group"),
        ("parent", "parent_id", "taken from"),
    ):
        if changed := _ref_change(state, rel, col, session):
            line(f"{word}: {_name(changed[0])} → {_name(changed[1])}")
    for attr, word in _PLANT_FIELDS.items():
        if evented and attr in ("ended_on", "end_reason"):
            continue  # folded into the kill or harvest line
        hist = state.attrs[attr].history
        if not hist.has_changes():
            continue
        old = hist.deleted[0] if hist.deleted else None
        new = hist.added[0] if hist.added else None
        if old != new:
            task = "transplanted" if attr == "container" and new is not None else None
            line(f"{word}: {_show(old)} → {_show(new)}", task=task)
    hist = state.attrs.notes.history
    if hist.has_changes():
        old = hist.deleted[0] if hist.deleted else None
        new = hist.added[0] if hist.added else None
        for on, text in _notes_lines(old, new):
            line(text, on=on)


def _group_changed(session, g: Group, add) -> None:
    state = inspect(g)

    def line(text, on=None):
        add(on, g.label, text, group=g)

    hist = state.attrs.status.history
    if hist.has_changes() and hist.deleted and hist.added and hist.deleted[0] != hist.added[0]:
        line(f"{_show(hist.deleted[0])} → {_show(hist.added[0])}")
    if moved := _ref_change(state, "space", "space_id", session):
        line(f"space: {_name(moved[0])} → {_name(moved[1])}")
    for attr, word in _GROUP_FIELDS.items():
        hist = state.attrs[attr].history
        if hist.has_changes():
            old = hist.deleted[0] if hist.deleted else None
            new = hist.added[0] if hist.added else None
            if old != new:
                line(f"{word}: {_show(old)} → {_show(new)}")
    hist = state.attrs.notes.history
    if hist.has_changes():
        old = hist.deleted[0] if hist.deleted else None
        new = hist.added[0] if hist.added else None
        for on, text in _notes_lines(old, new):
            line(text, on=on)


# ---------------------------------------------------------------------------
# Backfill
# ---------------------------------------------------------------------------
def backfill() -> int:
    """Rebuild the log from the plant events and harvests on file. Returns lines added.

    Only for an empty log (a database from before the log existed, a restore of an old
    backup, the demo seed); with lines already there it does nothing. Edits to notes,
    labels or containers were never recorded, so those cannot come back.
    """
    if db.session.query(Change).count():
        return 0
    with paused(), db.session.no_autoflush:
        rows = _rebuild()
        db.session.add_all(rows)
        db.session.commit()
    return len(rows)


def _rebuild() -> list[Change]:
    rows: list[Change] = []
    started = set()
    for e in db.session.query(PlantEvent).order_by(PlantEvent.on, PlantEvent.id):
        p = e.plant
        if _is_birth(e):
            started.add(p.id)
        text = _event_text(e)
        if e.to_status == PlantStatus.killed and p.end_reason and p.end_reason not in text:
            text += f" — {p.end_reason}"
        rows.append(
            Change(
                on=e.on,
                subject=_clip(p.label, 160),
                text=_clip(text),
                plant=p,
                group=p.group,
                task=_event_task(e),
                created_at=e.created_at,
            )
        )
    for p in db.session.query(Plant).order_by(Plant.id):
        if p.id in started:
            continue
        rows.append(
            Change(
                on=p.started_on or p.created_at.date(),
                subject=_clip(p.label, 160),
                text=f"added: {p.strain.display_name}",
                plant=p,
                group=p.group,
                task="cloned" if p.parent_id else None,
                created_at=p.created_at,
            )
        )
    for h in db.session.query(Harvest).order_by(Harvest.harvested_on, Harvest.id):
        target = h.plant or h.group
        rows.append(
            Change(
                on=h.harvested_on,
                subject=_clip(_name(target), 160),
                text=_clip("harvested" + (f" — {h.notes}" if h.notes else "")),
                plant=h.plant,
                group=h.group or (h.plant.group if h.plant else None),
                created_at=h.created_at,
            )
        )
    return rows
