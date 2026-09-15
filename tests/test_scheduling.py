from datetime import date

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


def test_openings_skip_backfilled_slots(app):
    opens = sched.openings(groups(), ref=REF)
    # Grp 6 ends Sep 22 but Grp 12 starts that day in the same space => not an opening.
    assert all(o.on != date(2026, 9, 22) for o in opens)
    assert [(o.on, o.freed_by.number) for o in opens[:3]] == [
        (date(2026, 10, 25), 10),
        (date(2026, 11, 2), 11),
        (date(2026, 11, 17), 7),
    ]


def test_suggest_start_for_unscheduled_group(app):
    g = db.session.query(Group).filter_by(number=17).one()
    s = sched.suggest_start(g, groups(), ref=REF)
    assert s is not None
    assert s.on == date(2026, 10, 25)
    assert s.freed_by.number == 10
    assert s.space.name == "Flower Room"


def test_conflicts_clean_on_demo_data(app):
    assert sched.conflicts(groups(), db.session.query(Space).all(), ref=REF) == []


def test_capacity_is_not_a_schedule_conflict(app):
    """Over-capacity is a spaces-page label now, not an entry in the alert list."""
    from canopy.services import spacing

    room = db.session.query(Space).filter_by(name="Flower Room").one()
    room.capacity = 5
    db.session.commit()
    assert sched.conflicts(groups(), [room], ref=REF) == []
    warn = spacing.capacity_warning(room, groups(), ref=REF)
    assert warn is not None and "over the 5 maximum" in warn


def test_conflict_scheduled_without_a_space(app):
    """A flipped plant whose group has no space still needs somewhere to go."""
    from canopy.models import Plant, Strain
    from canopy.services import lifecycle

    g = Group(number=950)
    p = Plant(label="stray", strain=db.session.query(Strain).first(), group=g)
    db.session.add_all([g, p])
    lifecycle.set_flip([p], date(2026, 10, 1), days=60)
    db.session.commit()
    msgs = [c.message for c in sched.conflicts(groups(), [], ref=REF)]
    assert "Grp 950 is scheduled but not assigned to a space." in msgs
    # "scheduled but has no living plants" is gone: the dates come *from* the plants,
    # so a scheduled group without any is no longer a state that can exist.
    assert not any("no living plants" in m for m in msgs)


def test_implied_status(app):
    assert (
        sched.implied_status(db.session.query(Group).filter_by(number=6).one(), REF).value
        == "flowering"
    )
    assert (
        sched.implied_status(db.session.query(Group).filter_by(number=12).one(), REF).value
        == "vegetative"
    )
    assert (
        sched.implied_status(db.session.query(Group).filter_by(number=1).one(), REF).value
        == "drying"
    )
    assert (
        sched.implied_status(db.session.query(Group).filter_by(number=17).one(), REF).value
        == "vegetative"
    )


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


def test_inventory_and_plant_counts(app):
    inv = sched.inventory_summary(db.session.query(Strain).all())
    assert inv["strains"] == 30
    assert inv["breeders"] == 1
    counts = sched.plant_counts(db.session.query(Plant).all())
    assert counts["killed"] == 6
    assert counts["flowering"] == 10
    assert counts["clone"] == 3


# ---------------------------------------------------------------------------
# Ramp-down: half water as a run finishes
# ---------------------------------------------------------------------------
def spaces():
    return db.session.query(Space).all()


def units():
    return sched.scheduled_units(groups(), db.session.query(Plant).all())


def test_ramp_down_quiet_when_nothing_is_close(app):
    """Grp 6 finishes Sep 22, 15 days out — one day beyond the window, so no alert."""
    assert sched.ramp_down(units(), spaces(), ref=REF) == []


def test_ramp_down_catches_a_run_inside_the_window(app):
    rows = sched.ramp_down(units(), spaces(), ref=REF, within=15)
    assert [r.label for r in rows] == ["Grp 6"]
    r = rows[0]
    assert r.days_left == 15 and r.end == date(2026, 9, 22)
    assert "plain water only, half the usual amount" in r.message
    assert not r.spread


def test_ramp_down_only_looks_at_flowering_spaces(app):
    """A run parked in veg is not finishing anything, whatever its dates say."""
    g6 = next(g for g in groups() if g.number == 6)
    g6.space = db.session.query(Space).filter_by(name="Veg Tent").one()
    db.session.commit()
    assert sched.ramp_down(units(), spaces(), ref=REF, within=15) == []


def test_ramp_down_triggers_on_the_earliest_plant_not_the_last(app):
    """One plant finishing early pulls the whole run's alert forward, and says so."""
    g6 = next(g for g in groups() if g.number == 6)
    early = g6.living_plants[0]
    early.flower_days_override = early.flower_days - 5
    db.session.commit()

    rows = sched.ramp_down(units(), spaces(), ref=REF, within=15)
    assert [r.label for r in rows] == ["Grp 6"]
    r = rows[0]
    assert r.end == date(2026, 9, 17) and r.days_left == 10
    assert r.spread
    assert "first plants" in r.message


def test_ramp_down_ignores_runs_already_past_their_date(app):
    rows = sched.ramp_down(units(), spaces(), ref=REF, within=365)
    assert rows and all(r.days_left >= 0 for r in rows)


def test_ramp_down_covers_a_plant_standing_on_its_own(app):
    """Groups are containers — a lone plant gets the same alert, and links to itself."""
    p = Plant(
        label="solo",
        strain=db.session.query(Strain).first(),
        space=db.session.query(Space).filter_by(name="Flower Room").one(),
    )
    db.session.add(p)
    from canopy.services import lifecycle

    lifecycle.set_flip([p], date(2026, 7, 10), days=60)  # ends Sep 08... within window
    p.flower_days_override = 65  # ends Sep 13, 6 days out
    db.session.commit()

    rows = sched.ramp_down(units(), spaces(), ref=REF, within=14)
    solo = next(r for r in rows if r.label == "solo")
    assert solo.days_left == 6
    assert solo.lone_plant is p


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
