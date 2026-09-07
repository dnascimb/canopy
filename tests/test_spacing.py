from datetime import date

from canopy.extensions import db
from canopy.models import Group, Plant, PlantSize, PlantStatus, Space, SpaceStage, Strain
from canopy.services import reports, spacing
from canopy.services import scheduling as sched

REF = date(2026, 9, 7)


def spaces():
    return db.session.query(Space).order_by(Space.id).all()


def test_space_area_and_dimensions(app):
    flower = db.session.query(Space).filter_by(name="Flower Room").one()
    assert flower.area_sqft == 50.0
    assert flower.dimensions == "5 × 10 ft (50 sq ft)"
    assert Space(name="x").dimensions == "—"


def test_footprint_defaults_and_override(app):
    assert spacing.footprint(PlantSize.medium, SpaceStage.flowering) == 2.25
    app.config["FOOTPRINT_SQFT"] = {"flowering": {"medium": 2.0}}
    assert spacing.footprint(PlantSize.medium, SpaceStage.flowering) == 2.0
    assert spacing.footprint(PlantSize.large, SpaceStage.flowering) == 3.0  # untouched


def test_plant_location_rules(app):
    sp = spaces()
    clone = db.session.query(Plant).filter_by(label="Jack Herer cut 1").one()
    assert spacing.plant_location(clone, sp).name == "Clone Shelf"  # explicit
    veg = db.session.query(Plant).filter_by(label="Last Call").one()
    assert veg.space is None and spacing.plant_location(veg, sp).name == "Veg Tent"  # by stage
    flowering = db.session.query(Plant).filter_by(label="EQ Haze").one()
    assert spacing.plant_location(flowering, sp).name == "Flower Room"  # via group
    dead = db.session.query(Plant).filter_by(label="Zap 3").one()
    assert spacing.plant_location(dead, sp) is None


def test_occupancy_fits_and_room(app):
    occ = spacing.occupancy(spaces(), db.session.query(Plant).all())
    flower = next(o for o in occ.values() if o.space.name == "Flower Room")
    assert flower.count == 10 and flower.used_sqft == 25.5
    assert flower.fits(PlantSize.medium) == 22 and flower.fits(PlantSize.large) == 16
    assert flower.room_for(PlantSize.medium) == 10
    assert round(flower.load, 2) == 0.51 and not flower.over
    assert {g.number for g in flower.groups()} == {6, 7, 8, 9, 10, 11}
    veg = next(o for o in occ.values() if o.space.name == "Veg Tent")
    assert veg.count == 4 and veg.fits() == 10  # 8 sq ft / 0.75, capped at 12


def test_capacity_cap_beats_area(app):
    s = Space(name="Huge", stage=SpaceStage.flowering, width_ft=100, length_ft=100, capacity=3)
    assert spacing.Occupancy(s).fits() == 3


def test_load_series_and_peak(app):
    flower = db.session.query(Space).filter_by(name="Flower Room").one()
    series = spacing.load_series(flower, db.session.query(Group).all(), ref=REF)
    assert series[0]["date"] == "2026-05-12" and series[-1]["sqft"] == 0
    today = next(p for p in series if p["date"] == REF.isoformat())
    assert today["count"] == 10 and today["sqft"] == 25.5
    assert spacing.peak(series)["date"] == "2026-08-02"  # historical peak
    assert spacing.peak(series, since=REF)["date"] == REF.isoformat()


def test_conflicts_use_area_from_today(app):
    groups = db.session.query(Group).all()
    plants = db.session.query(Plant).all()
    assert sched.conflicts(groups, spaces(), plants, ref=REF) == []
    flower = db.session.query(Space).filter_by(name="Flower Room").one()
    flower.width_ft, flower.length_ft = 2, 4
    db.session.commit()
    msgs = [c.message for c in sched.conflicts(groups, spaces(), plants, ref=REF)]
    assert any("needs 25.5 sq ft on Sep 07 but has 8" in m for m in msgs)
    assert any("over capacity today" in m for m in msgs)


def test_move_plants_aligns_status(app):
    g = db.session.query(Group).filter_by(number=12).one()
    flower = db.session.query(Space).filter_by(name="Flower Room").one()
    n = spacing.move_plants(g.plants, flower)
    assert n == 1 and all(p.status == PlantStatus.flowering and p.space == flower for p in g.plants)
    killed = db.session.query(Plant).filter_by(label="Zap 3").one()
    assert spacing.move_plants([killed], flower) == 0


def test_group_move_route_flips_group(client):
    g = db.session.query(Group).filter_by(number=17).one()
    flower = db.session.query(Space).filter_by(name="Flower Room").one()
    r = client.post(f"/groups/{g.id}/move", data={"space_id": flower.id}, follow_redirects=True)
    assert r.status_code == 200 and b"Moved 1 plant" in r.data
    db.session.refresh(g)
    assert g.status.value == "flowering" and g.flower_start == REF and g.space == flower


def test_plant_move_route(client):
    p = db.session.query(Plant).filter_by(label="Last Call").one()
    clone = db.session.query(Space).filter_by(name="Clone Shelf").one()
    client.post(f"/plants/{p.id}/move", data={"space_id": clone.id}, follow_redirects=True)
    db.session.refresh(p)
    assert p.status.value == "clone" and p.space == clone


def test_spaces_planner_page(client):
    html = client.get("/spaces/").data.decode()
    assert "Coming up" in html and "Last Call" in html and "Spacing rules" in html
    assert "Flower Room load over the season" in html


def test_space_form_with_stage_and_dims(client):
    client.post(
        "/spaces/new",
        data={
            "name": "Tent B",
            "stage": "vegetative",
            "width_ft": 3,
            "length_ft": 3,
            "capacity": 9,
        },
        follow_redirects=True,
    )
    s = db.session.query(Space).filter_by(name="Tent B").one()
    assert s.stage.value == "vegetative" and s.area_sqft == 9.0


def test_quick_log_creates_titled_entry(client):
    g = db.session.query(Group).filter_by(number=8).one()
    r = client.post(
        "/journal/quick",
        data={
            "entry_date": "2026-09-07",
            "group_id": g.id,
            "plant_id": 0,
            "tasks": ["watered", "fed"],
            "body": "runoff 6.2",
        },
        follow_redirects=True,
    )
    assert b"Logged: Watered, Fed nutrients" in r.data
    e = [j for j in g.journal_entries if j.entry_date == REF][0]
    assert e.task_list == ["watered", "fed"] and e.body == "runoff 6.2"
    r = client.post(
        "/journal/quick",
        data={"entry_date": "2026-09-07", "group_id": 0, "plant_id": 0},
        follow_redirects=True,
    )
    assert b"Tick at least one task" in r.data


def test_journal_task_filter_and_last_done(client):
    html = client.get("/journal/?task=cloned").data.decode()
    assert "Took clones" in html and "Defoliation" not in html
    g = db.session.query(Group).filter_by(number=8).one()
    html = client.get(f"/groups/{g.id}").data.decode()
    assert "defoliated Sep 05" in html and "watered Sep 05" in html


def test_reports_page_and_stats(client):
    stats = reports.strain_stats(
        db.session.query(Strain).all(),
        db.session.query(__import__("canopy.models", fromlist=["Harvest"]).Harvest).all(),
    )
    top = stats[0]
    assert top.strain.name == "Gorilla Snacks" and round(top.dry_g) == 275 and top.harvested == 3
    ll = next(s for s in stats if s.strain.name == "Lemon Lime Haze")
    assert ll.killed == 5 and ll.survival == 0.0
    html = client.get("/reports/").data.decode()
    assert "Dry yield per strain" in html and "Gorilla Snacks" in html and "<svg" in html
    assert reports.kill_reasons(db.session.query(Plant).all())[0] == ("Culled", 3)


def test_api_spaces_and_locations(client):
    sp = client.get("/api/v1/spaces").get_json()
    flower = next(s for s in sp if s["name"] == "Flower Room")
    assert flower["fits"]["medium"] == 22 and flower["room_for"]["medium"] == 10
    load = client.get(f"/api/v1/spaces/{flower['id']}/load").get_json()
    assert load[-1]["sqft"] == 0
    plants = client.get("/api/v1/plants").get_json()
    assert next(p for p in plants if p["label"] == "Last Call")["location"] == "Veg Tent"


def test_backup_roundtrip_keeps_new_fields(client):
    payload = client.get("/schedule/backup.json").get_json()
    assert (
        payload["spaces"][0]["stage"] == "clone" and payload["journal_entries"][1]["tasks"] == "ipm"
    )
    client.post(
        "/schedule/restore",
        data={"payload": __import__("json").dumps(payload), "replace": "on"},
        follow_redirects=True,
    )
    assert db.session.query(Space).filter_by(name="Flower Room").one().area_sqft == 50.0
    assert (
        db.session.query(Plant).filter_by(label="Jack Herer cut 1").one().space.name
        == "Clone Shelf"
    )
