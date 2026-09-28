from datetime import date, timedelta

from canopy.extensions import db
from canopy.models import Group, Plant, Space, Strain
from canopy.services import scheduling as sched

REF = date(2026, 9, 7)


def groups():
    return db.session.query(Group).all()


def test_today_uses_override(app):
    assert sched.today() == REF


def test_events_sorted_ends_before_starts(app):
    ev = sched.events(groups())
    dates = [e.on for e in ev]
    assert dates == sorted(dates)
    # Sep 22: Grp 6 ends and Grp 12 starts — end must come first.
    sep22 = [e for e in ev if e.on == date(2026, 9, 22)]
    assert [e.kind for e in sep22] == ["end", "start"]
    assert sep22[0].label == "Grp 6 end flower (70 days)"
    assert sep22[1].label == "Grp 12 start flower"


def test_upcoming_window(app):
    up = sched.upcoming(groups(), days=30, ref=REF)
    assert {(e.on, e.kind) for e in up} == {
        (date(2026, 9, 22), "end"),
        (date(2026, 9, 22), "start"),
    }


def test_timeline_rows_shape(app):
    rows = sched.timeline_rows(groups(), ref=REF)
    assert [r["label"] for r in rows][:3] == ["Goji 3x", "Grp 1", "Grp 2"]
    g7 = next(r for r in rows if r["number"] == 7)
    assert g7["days"] == 112 and g7["end"] == "2026-11-17"
    assert g7["day_of_flower"] == 42
    assert g7["strains"] == ["EQ Haze", "Durban Poison"]
    assert all("start" not in r or r["start"] for r in rows)
    assert not any(r["label"] == "Next up" for r in rows)  # unscheduled groups excluded


def test_timeline_bounds_pads(app):
    rows = sched.timeline_rows(groups(), ref=REF)
    t0, t1 = sched.timeline_bounds(rows, pad_days=7)
    assert t0 == date(2026, 5, 5)
    assert t1 == date(2026, 12, 27)


def _run(label, *, flip, days=70):
    """A plant of its own on a known run, flipped *flip* for *days*."""
    from canopy.services import lifecycle

    p = Plant(label=label, strain=db.session.query(Strain).first())
    db.session.add(p)
    lifecycle.set_flip([p], flip, days=days)
    db.session.commit()
    return p


def test_a_run_harvested_early_ends_the_day_it_came_down(app):
    """The Super Blue Haze case: flipped for 77 days, harvested on day 49.

    The group said "the calendar says this group should be flowering, but it is marked
    drying" — the projection overruling what happened. What happens to the plant rules:
    its run ends on the harvest, and everything built on the dates follows.
    """
    from canopy.models import GroupStatus, PlantStatus
    from canopy.services import lifecycle

    g = Group(number=901, name="Early harvest", color="#123456")
    db.session.add(g)
    a, b = (
        _run("Early A", flip=date(2026, 7, 20), days=77),
        _run("Early B", flip=date(2026, 7, 20), days=77),
    )
    a.group = b.group = g
    down = date(2026, 9, 6)
    for p in (a, b):
        lifecycle.record(p, PlantStatus.harvested, on=down)
    lifecycle.settle_group(g)
    db.session.commit()

    assert a.flower_end == down and g.flower_end == down
    assert not g.is_flowering_on(REF) and not a.is_flowering_on(down)
    assert a.is_flowering_on(down - timedelta(days=1))
    assert g.status == GroupStatus.drying, "harvesting its plants settled the group"
    row = next(r for r in sched.timeline_rows(groups(), ref=REF) if r["label"] == g.label)
    assert row["end"] == down.isoformat(), "the bar stops at the harvest"


def test_a_plant_still_flowering_past_its_projection_is_still_flowering(app):
    p = _run("Running long", flip=date(2026, 6, 1), days=63)  # projected to end Aug 3
    assert p.status.value == "flowering"
    assert p.is_flowering_on(REF), "not harvested, so still in flower today"
    assert p.flower_end == REF + timedelta(days=1)


def test_a_culled_plant_ends_its_run_on_the_cull(app):
    from canopy.models import PlantStatus
    from canopy.services import lifecycle

    p = _run("Culled mid-run", flip=date(2026, 8, 1))
    lifecycle.record(p, PlantStatus.killed, on=date(2026, 8, 20))
    db.session.commit()
    assert p.flower_end == date(2026, 8, 20)


def test_a_flip_cannot_be_dated_in_the_future(app):
    """Canopy records what happened; a flip dated ahead of time is a plan, and it has none."""
    import pytest

    from canopy.services import lifecycle

    p = Plant(label="Not yet", strain=db.session.query(Strain).first())
    db.session.add(p)
    with pytest.raises(ValueError, match="future"):
        lifecycle.set_flip([p], REF + timedelta(days=1))
    assert p.flower_start is None
    lifecycle.set_flip([p], REF)  # today is fine
    assert p.flower_start == REF


def test_ascii_timeline_is_plain_ascii(app):
    rows = sched.timeline_rows(groups(), ref=REF)
    art = sched.ascii_timeline(rows, ref=REF)
    assert art.isascii()
    lines = art.splitlines()
    assert lines[0].lstrip().startswith("|MAY")
    assert any(line.startswith("Grp 7 ") and line.rstrip().endswith("112d") for line in lines)
    assert "* = today (Sep 07)" in art
    assert sched.ascii_timeline([], ref=REF) == "(no scheduled groups)"


def test_markdown_export_contains_groups_table_and_timeline(app):
    md = sched.markdown_export(groups(), ref=REF)
    assert "## Groups" in md and "## Schedule" in md and "## Timeline" in md
    assert "- **Grp 1** — Swazipulco F2, Gorilla Snacks I" in md
    assert "~~Lemon Lime Haze 1~~" in md
    assert "| Nov 17 | Grp 7 end flower (112 days) |" in md
    assert "```" in md


def test_plant_counts(app):
    counts = sched.plant_counts(db.session.query(Plant).all())
    assert counts["killed"] == 6
    assert counts["flowering"] == 10
    assert counts["clone"] == 3


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def units():
    return sched.scheduled_units(groups(), db.session.query(Plant).all())


def test_timeline_rows_link_a_lone_plant_to_its_own_page(app):
    """A lone plant is not a group, so "/groups/<id>" was a 404 on every one of them."""
    p = Plant(
        label="solo",
        strain=db.session.query(Strain).first(),
        space=db.session.query(Space).filter_by(name="Flower Room").one(),
    )
    db.session.add(p)
    from canopy.services import lifecycle

    lifecycle.set_flip([p], date(2026, 8, 1), days=60)
    db.session.commit()

    rows = sched.timeline_rows(units(), ref=REF)
    solo = next(r for r in rows if r["label"] == "solo")
    assert solo["href"] == f"/plants/{p.id}"
    assert all(r["href"] == f"/groups/{r['id']}" for r in rows if r["label"] != "solo")
    # And it is not the same grey as every other lone plant.
    assert solo["color"] != "#9e9e9e"


def test_a_flip_moves_plants_into_flower(app):
    """Recording a flip puts the plants in flower, in the space it names."""
    from canopy.models import PlantStatus, Space
    from canopy.services import lifecycle

    shelf = db.session.query(Space).filter_by(name="Clone Shelf").one()
    flower = db.session.query(Space).filter_by(name="Flower Room").one()
    p = Plant(
        label="unrooted",
        strain=db.session.query(Strain).first(),
        status=PlantStatus.clone,
        space=shelf,
    )
    db.session.add(p)
    assert p.space is shelf
    lifecycle.set_flip([p], REF, space=flower)
    db.session.commit()
    assert p.status == PlantStatus.flowering and p.space_id == flower.id


def test_same_day_veg_then_flip_is_not_the_end_of_the_run(app):
    """PNG 1 and 2 went into veg and into flower on the same day, then were culled weeks on."""
    from canopy.models import PlantEvent, PlantStatus
    from canopy.services import lifecycle

    p = Plant(label="Same day", strain=db.session.query(Strain).first(), status=PlantStatus.clone)
    db.session.add(p)
    on = date(2026, 8, 1)
    db.session.add(PlantEvent(plant=p, on=on, to_status=PlantStatus.vegetative))
    db.session.flush()
    lifecycle.set_flip([p], on)
    db.session.flush()
    lifecycle.record(p, PlantStatus.killed, on=date(2026, 8, 25))
    db.session.commit()
    assert p.flower_start == on and p.flower_end == date(2026, 8, 25)


def test_moving_a_flowering_plant_does_not_restart_its_run(app):
    """A male parked on the clone shelf for pollen logs flowering -> flowering."""
    from canopy.models import PlantEvent, PlantStatus

    p = _run("Pollen male", flip=date(2026, 8, 20), days=60)
    db.session.add(
        PlantEvent(
            plant=p,
            on=date(2026, 9, 1),
            from_status=PlantStatus.flowering,
            to_status=PlantStatus.flowering,
            note="Moved to the clone shelf.",
        )
    )
    db.session.commit()
    assert p.flower_start == date(2026, 8, 20)
    assert p.flower_end == date(2026, 10, 19)


def test_a_lone_plant_reports_its_own_state(app):
    from canopy.models import GroupStatus, PlantStatus
    from canopy.services import lifecycle

    p = _run("Lone", flip=date(2026, 8, 1))
    assert sched.LonePlant(p).status == GroupStatus.flowering
    lifecycle.record(p, PlantStatus.harvested, on=date(2026, 9, 1))
    db.session.commit()
    assert sched.LonePlant(p).status == GroupStatus.drying
