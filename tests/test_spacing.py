from datetime import date, timedelta

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


def test_capacity_warning_uses_area_from_today(app):
    """Capacity lives on the spaces page, not in the schedule's conflict list."""
    groups = db.session.query(Group).all()
    plants = db.session.query(Plant).all()
    flower = db.session.query(Space).filter_by(name="Flower Room").one()
    occ = spacing.occupancy(spaces(), plants)
    assert spacing.capacity_warning(flower, groups, occ[flower.id], ref=REF) is None
    assert sched.conflicts(groups, spaces(), plants, ref=REF) == []

    flower.width_ft, flower.length_ft = 2, 4
    db.session.commit()
    occ = spacing.occupancy(spaces(), plants)
    warn = spacing.capacity_warning(flower, groups, occ[flower.id], ref=REF)
    assert warn is not None and "needs 25.5 sq ft on Sep 07 but has 8" in warn
    # ...and it stays out of the conflict list, which is for genuinely broken schedules.
    assert not [c for c in sched.conflicts(groups, spaces(), plants, ref=REF) if c.space]


def test_capacity_warning_falls_back_to_today(app):
    """A space with no schedule behind it still reports what is physically in it."""
    veg = db.session.query(Space).filter_by(name="Veg Tent").one()
    veg.capacity = 1
    db.session.commit()
    occ = spacing.occupancy(spaces(), db.session.query(Plant).all())
    warn = spacing.capacity_warning(veg, db.session.query(Group).all(), occ[veg.id], ref=REF)
    assert warn is not None and "over capacity today" in warn


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


def test_quick_log_logs_against_a_space(client):
    veg = db.session.query(Space).filter_by(name="Veg Tent").one()
    r = client.post(
        "/journal/quick",
        data={
            "entry_date": "2026-09-07",
            "space_id": veg.id,
            "tasks": ["watered", "fed"],
            "body": "runoff 6.2",
        },
        follow_redirects=True,
    )
    assert b"Logged: Watered, Fed nutrients" in r.data
    e = [j for j in veg.journal_entries if j.entry_date == REF][0]
    assert e.task_list == ["watered", "fed"] and e.body == "runoff 6.2"
    assert e.group_id is None  # logged against the tent, not a group

    # Nothing in particular is required, but the entry has to say something.
    r = client.post(
        "/journal/quick",
        data={"entry_date": "2026-09-07", "space_id": veg.id},
        follow_redirects=True,
    )
    assert b"Tick a task, add a photo, or write a title or a note." in r.data

    # A bare note is enough, and still gets a usable title.
    r = client.post(
        "/journal/quick",
        data={"entry_date": "2026-09-07", "space_id": veg.id, "body": "topped a few"},
        follow_redirects=True,
    )
    assert b"Logged: Note" in r.data
    assert [j for j in veg.journal_entries if j.body == "topped a few"]


def test_journal_filters_by_space(client):
    html = client.get("/journal/?task=cloned").data.decode()
    assert "Took clones" in html and "Defoliation" not in html
    veg = db.session.query(Space).filter_by(name="Veg Tent").one()
    flower = db.session.query(Space).filter_by(name="Flower Room").one()
    client.post(
        "/journal/quick",
        data={"entry_date": "2026-09-07", "space_id": veg.id, "tasks": ["watered"]},
        follow_redirects=True,
    )
    shown = client.get(f"/journal/?space={veg.id}").data.decode()
    assert '<span class="chip">Watered</span>' in shown
    # The flower tent has nothing logged against it, so the list is empty. ("Watered"
    # still appears on the page — it is one of the task filter's options.)
    other = client.get(f"/journal/?space={flower.id}").data.decode()
    assert "No entries yet" in other and '<span class="chip">Watered</span>' not in other


def test_reports_page_and_stats(client):
    stats = reports.strain_stats(db.session.query(Strain).all())
    top = next(s for s in stats if s.strain.name == "Gorilla Snacks")
    assert top.harvested == 3
    ll = next(s for s in stats if s.strain.name == "Lemon Lime Haze")
    assert ll.killed == 5 and ll.survival == 0.0
    html = client.get("/reports/").data.decode()
    assert "Survival per strain" in html and "Gorilla Snacks" in html and "<svg" in html
    assert "Dry" not in html and "Yield per group" not in html
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


def test_a_lone_plant_schedules_exactly_like_a_group(app):
    """The asymmetry this replaced: a plant outside a group is a first-class thing.

    Moving one into flower gives it its own run and puts it on the calendar, with no
    group needed anywhere.
    """
    strain = db.session.query(Strain).filter_by(name="EQ Haze").one()
    flower = db.session.query(Space).filter_by(name="Flower Room").one()
    loose = Plant(label="loner", strain=strain, group=None, status=PlantStatus.vegetative)
    db.session.add(loose)
    db.session.commit()
    assert loose.flower_start is None

    # the same call the group route makes, on one ungrouped plant
    assert spacing.move_plants([loose], flower, ref=REF) == 1
    db.session.commit()

    assert loose.status == PlantStatus.flowering
    assert loose.flower_start == REF
    assert loose.flower_end == REF + timedelta(days=strain.flower_days)

    units = sched.scheduled_units(db.session.query(Group).all(), db.session.query(Plant).all())
    rows = sched.timeline_rows(units, ref=REF)
    assert "loner" in [r["label"] for r in rows]
    assert ("loner", "start") in [(e.group.label, e.kind) for e in sched.events(units)]

    # and it leaves a trace of how it got there
    assert [e.to_status for e in loose.events] == [PlantStatus.flowering]


def test_group_and_plant_moves_take_the_same_path(app):
    """Flipping via the group and via each plant must land in the same state."""
    strain = db.session.query(Strain).first()
    flower = db.session.query(Space).filter_by(name="Flower Room").one()
    g = Group(number=960)
    a = Plant(label="via-group", strain=strain, group=g, status=PlantStatus.vegetative)
    b = Plant(label="via-plant", strain=strain, group=None, status=PlantStatus.vegetative)
    db.session.add_all([g, a, b])
    db.session.commit()

    spacing.move_plants(g.living_plants, flower, ref=REF)  # group route
    spacing.move_plants([b], flower, ref=REF)  # plant route
    db.session.commit()

    assert (a.status, a.flower_start, a.flower_end) == (b.status, b.flower_start, b.flower_end)
    assert a.space == b.space == flower


def _png() -> bytes:
    """Smallest valid PNG — enough to prove the pipeline without a fixture file."""
    import base64

    return base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )


def test_quick_log_accepts_a_photo(client, app):
    import io

    from canopy.services import photos

    veg = db.session.query(Space).filter_by(name="Veg Tent").one()
    r = client.post(
        "/journal/quick",
        data={
            "entry_date": "2026-09-07",
            "space_id": veg.id,
            "tasks": ["watered"],
            "photo": (io.BytesIO(_png()), "phone-snap.png"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert r.status_code == 200
    entry = [j for j in veg.journal_entries if j.photo_path][0]
    # the browser's filename is never used as the path
    assert entry.photo_path != "phone-snap.png"
    assert entry.photo_path.endswith(".png") and len(entry.photo_path) == 36
    assert (photos.upload_dir() / entry.photo_path).is_file()

    # and it is served back
    served = client.get(f"/journal/photo/{entry.photo_path}")
    assert served.status_code == 200 and served.data == _png()

    # deleting the entry takes the file with it
    stored = photos.upload_dir() / entry.photo_path
    client.post(f"/journal/{entry.id}/delete", follow_redirects=True)
    assert not stored.exists()


def test_photo_upload_rejects_a_non_image(client):
    import io

    veg = db.session.query(Space).filter_by(name="Veg Tent").one()
    before = len(veg.journal_entries)
    r = client.post(
        "/journal/quick",
        data={
            "entry_date": "2026-09-07",
            "space_id": veg.id,
            "tasks": ["watered"],
            "photo": (io.BytesIO(b"#!/bin/sh\necho nope"), "sneaky.sh"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert b"Images only" in r.data
    db.session.expire_all()
    assert len(db.session.query(Space).filter_by(name="Veg Tent").one().journal_entries) == before


def test_a_photo_alone_is_a_valid_entry(client):
    import io

    veg = db.session.query(Space).filter_by(name="Veg Tent").one()
    r = client.post(
        "/journal/quick",
        data={
            "entry_date": "2026-09-07",
            "space_id": veg.id,
            "photo": (io.BytesIO(_png()), "just-a-picture.png"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert b"Logged: Photo" in r.data


def test_time_in_stage_only_counts_finished_stretches(app):
    """A plant still in flower says nothing yet about how long the strain takes."""
    from canopy.models import PlantEvent, PlantStatus

    strain = db.session.query(Strain).filter_by(name="EQ Haze").one()
    finished = Plant(
        label="finished", strain=strain, status=PlantStatus.harvested, ended_on=date(2026, 8, 10)
    )
    running = Plant(label="running", strain=strain, status=PlantStatus.flowering)
    db.session.add_all([finished, running])
    db.session.add_all(
        [
            PlantEvent(plant=finished, on=date(2026, 6, 1), to_status=PlantStatus.flowering),
            PlantEvent(plant=running, on=date(2026, 8, 1), to_status=PlantStatus.flowering),
        ]
    )
    db.session.commit()

    timing = next(
        t
        for t in reports.time_in_stage(db.session.query(Plant).all(), ref=REF)
        if t.strain.name == "EQ Haze"
    )
    # only the finished one: 1 Jun to 10 Aug
    assert timing.runs(PlantStatus.flowering) == 1
    assert timing.observed_flower == 70.0
    assert timing.drift == 70.0 - strain.flower_days


def test_a_cull_does_not_report_a_flower_length(app):
    """A male pulled on day 12 did not finish in 12 days."""
    from canopy.models import PlantEvent, PlantStatus

    strain = db.session.query(Strain).filter_by(name="Zap").one()
    culled = Plant(
        label="male",
        strain=strain,
        status=PlantStatus.killed,
        ended_on=date(2026, 6, 13),
        end_reason="Male",
    )
    db.session.add(culled)
    db.session.add(PlantEvent(plant=culled, on=date(2026, 6, 1), to_status=PlantStatus.flowering))
    db.session.commit()

    hit = [
        t
        for t in reports.time_in_stage(db.session.query(Plant).all(), ref=REF)
        if t.strain.name == "Zap"
    ]
    assert not any(t.observed_flower == 12.0 for t in hit)


def test_reports_page_shows_time_in_stage(client):
    html = client.get("/reports/").data.decode()
    assert "Time in each stage" in html and "On the strain" in html
