from datetime import date

from canopy.extensions import db
from canopy.models import Group, Plant, PlantStatus, Strain
from canopy.services import lifecycle


def test_plant_owns_its_schedule(app):
    """A plant's flip is read off its events; the group is only the span of its plants."""
    strain = db.session.query(Strain).first()
    g = Group(number=900)
    p = Plant(label="P1", strain=strain, group=g)
    db.session.add_all([g, p])
    lifecycle.set_flip([p], date(2026, 7, 28), days=112)
    db.session.commit()

    assert p.flower_start == date(2026, 7, 28)
    assert p.flower_end == date(2026, 11, 17)
    assert p.is_flowering_on(date(2026, 9, 7))
    assert not p.is_flowering_on(date(2026, 11, 17))  # end date is exclusive
    assert p.day_of_flower(date(2026, 7, 28)) == 1
    assert p.day_of_flower(date(2026, 9, 7)) == 42
    assert round(p.progress(date(2026, 9, 7)), 3) == round(41 / 112, 3)

    # the group reports exactly what its one plant is doing
    assert (g.flower_start, g.flower_end, g.flower_days) == (p.flower_start, p.flower_end, 112)
    assert g.day_of_flower(date(2026, 9, 7)) == 42


def test_group_span_covers_plants_that_disagree(app):
    """Plants flipped on different days: the group spans from the first to the last."""
    strain = db.session.query(Strain).first()
    g = Group(number=902)
    early = Plant(label="early", strain=strain, group=g)
    late = Plant(label="late", strain=strain, group=g)
    db.session.add_all([g, early, late])
    lifecycle.set_flip([early], date(2026, 7, 1), days=60)
    lifecycle.set_flip([late], date(2026, 7, 15), days=60)
    db.session.commit()
    assert g.flower_start == date(2026, 7, 1)
    assert g.flower_end == date(2026, 9, 13)  # the later plant finishes last
    assert g.flower_days == 74


def test_unscheduled_group_has_no_end(app):
    g = Group(number=901)
    assert g.flower_end is None
    assert g.day_of_flower(date(2026, 9, 7)) is None
    assert g.progress(date(2026, 9, 7)) == 0.0


def test_group_label_falls_back_to_number(app):
    assert Group(number=3).label == "Grp 3"
    assert Group(number=3, name="Goji 3x").label == "Goji 3x"


def test_living_and_killed_plants(app):
    g = db.session.query(Group).filter_by(number=1).one()
    assert {p.label for p in g.killed_plants} == {"Lemon Lime Haze 1"}
    assert {p.label for p in g.living_plants} == {"Swazipulco F2", "Gorilla Snacks I"}
    assert g.strain_summary() == "Swazipulco F2, Gorilla Snacks"


def test_strain_display_name(app):
    s = db.session.query(Strain).filter_by(name="EQ Haze").one()
    assert s.display_name == "EQ Haze (Equilibrium)"
    assert db.session.query(Strain).filter_by(name="GSC").one().display_name == "GSC"


def test_space_occupancy_counts_living_plants_only(app):
    from canopy.models import Space

    room = db.session.query(Space).filter_by(name="Flower Room").one()
    ref = date(2026, 9, 7)
    active = {g.number for g in room.active_groups(ref)}
    assert active == {6, 7, 8, 9, 10, 11}
    assert room.plants_in_flower(ref) == 10


def test_plant_is_alive(app):
    p = Plant(label="x", status=PlantStatus.killed)
    assert not p.is_alive
    assert Plant(label="y").is_alive


# ---------------------------------------------------------------------------
# Group colours: the timeline tells bars apart by colour, so they must be unique
# ---------------------------------------------------------------------------
def test_next_group_color_skips_what_is_taken():
    from canopy.models import GROUP_PALETTE, next_group_color

    assert next_group_color([]) == GROUP_PALETTE[0]
    assert next_group_color([GROUP_PALETTE[0]]) == GROUP_PALETTE[1]
    # Case and blanks must not smuggle a duplicate through.
    assert next_group_color([GROUP_PALETTE[0].upper(), None, ""]) == GROUP_PALETTE[1]


def test_group_colors_stay_unique_past_the_palette():
    """The old rule indexed the palette by group count, so group 17 repeated group 1."""
    from canopy.models import GROUP_PALETTE, next_group_color

    used: list[str] = []
    for _ in range(len(GROUP_PALETTE) * 3):
        c = next_group_color(used)
        assert c not in used
        used.append(c)
    assert len(set(used)) == len(used)
    assert used[: len(GROUP_PALETTE)] == GROUP_PALETTE


def test_every_demo_group_has_its_own_colour(app):
    from canopy.models import Group

    colors = [g.color for g in db.session.query(Group).all()]
    assert len(set(colors)) == len(colors)


def test_creating_groups_does_not_reuse_a_colour(client, app):
    from canopy.models import Group

    for n in range(900, 906):
        client.post("/groups/new", data={"number": n, "name": f"c{n}"}, follow_redirects=True)
    colors = [g.color for g in db.session.query(Group).all()]
    assert len(set(colors)) == len(colors)
