from datetime import date

from canopy.extensions import db
from canopy.models import Group, Plant, PlantStatus, Strain


def test_group_flower_end_is_derived(app):
    g = Group(number=900, flower_start=date(2026, 7, 28), flower_days=112)
    assert g.flower_end == date(2026, 11, 17)
    assert g.is_flowering_on(date(2026, 9, 7))
    assert not g.is_flowering_on(date(2026, 11, 17))  # end date is exclusive
    assert g.day_of_flower(date(2026, 7, 28)) == 1
    assert g.day_of_flower(date(2026, 9, 7)) == 42
    assert round(g.progress(date(2026, 9, 7)), 3) == round(41 / 112, 3)


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
