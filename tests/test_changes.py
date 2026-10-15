import json
from datetime import date

from canopy.extensions import db
from canopy.models import Change, Container, Group, JournalEntry, Plant, PlantEvent, PlantStatus
from canopy.services import activity, lifecycle, transfer
from canopy.services import journal as journal_out


def _last_call() -> Plant:
    return db.session.query(Plant).filter_by(label="Last Call").one()


def _lines(plant: Plant) -> list[str]:
    return [
        c.text for c in db.session.query(Change).filter_by(plant_id=plant.id).order_by(Change.id)
    ]


def test_demo_season_starts_with_a_backfilled_log(app):
    events = db.session.query(PlantEvent).count()
    assert db.session.query(Change).count() >= events
    assert db.session.query(Change).filter(Change.written.is_(True)).count() == 0


def test_a_dated_note_is_logged_on_its_own_date(client):
    p = _last_call()
    client.post(f"/plants/{p.id}/note", data={"noted_on": "2026-09-05", "text": "Up potted."})
    c = db.session.query(Change).order_by(Change.id.desc()).first()
    assert (c.on, c.text, c.plant_id, c.group_id) == (
        date(2026, 9, 5),
        "note: Up potted.",
        p.id,
        p.group_id,
    )


def test_a_field_edit_is_logged_with_old_and_new(app):
    p = _last_call()
    p.container = Container("1gal")
    db.session.commit()
    c = db.session.query(Change).order_by(Change.id.desc()).first()
    assert (c.text, c.task, c.on) == ("container: — → 1gal", "transplanted", date(2026, 9, 7))


def test_a_kill_is_one_line_with_its_reason(client):
    p = _last_call()
    before = len(_lines(p))
    client.post(f"/plants/{p.id}/kill", data={"ended_on": "2026-09-07", "end_reason": "Herm"})
    assert _lines(p)[before:] == ["vegetative → killed — Herm"]


def test_each_cutting_is_logged_once(client):
    p = _last_call()
    client.post(f"/plants/{p.id}/cuttings", data={"count": 2, "taken_on": "2026-09-07"})
    cuts = db.session.query(Plant).filter_by(parent_id=p.id).all()
    assert len(cuts) == 2
    for cut in cuts:
        lines = db.session.query(Change).filter_by(plant_id=cut.id).all()
        assert len(lines) == 1
        assert lines[0].text.startswith("added: Last Call, started as clone")
        assert lines[0].task == "cloned"


def test_redating_a_flip_reads_as_one_move(app):
    g = db.session.query(Group).filter_by(number=12).one()
    lifecycle.set_flip(g.plants, date(2026, 9, 1))
    db.session.commit()
    lifecycle.set_flip(g.plants, date(2026, 9, 3))
    db.session.commit()
    assert _lines(_last_call())[-1] == "flip moved from 2026-09-01 to 2026-09-03"


def test_a_paused_session_logs_nothing(app):
    before = db.session.query(Change).count()
    with activity.paused():
        _last_call().notes = "Quiet."
        db.session.commit()
    assert db.session.query(Change).count() == before


def test_autowrite_writes_one_entry_per_group_per_day_and_never_twice(client):
    p = _last_call()
    db.session.query(Change).update({"written": True})
    db.session.commit()
    client.post(f"/plants/{p.id}/note", data={"noted_on": "2026-09-07", "text": "Fed."})
    p.container = Container("1gal")
    db.session.commit()

    r = client.post("/journal/autowrite", follow_redirects=True)
    assert "Wrote 1 journal entry from 2 changes." in r.get_data(as_text=True)
    j = db.session.query(JournalEntry).order_by(JournalEntry.id.desc()).first()
    assert j.entry_date == date(2026, 9, 7)
    assert j.group_id == p.group_id
    assert j.title == f"{p.group.label}: 2 changes"
    assert "Last Call" in j.body and "- Last Call: note: Fed." in j.body
    assert j.task_list == ["transplanted"]

    r = client.post("/journal/autowrite", follow_redirects=True)
    assert "Nothing new to write." in r.get_data(as_text=True)


def test_autowrite_names_plants_with_the_same_change_on_one_line(app):
    db.session.query(Change).update({"written": True})
    g = db.session.query(Group).filter_by(number=12).one()
    for p in g.plants:
        lifecycle.record(p, PlantStatus.flowering, on=date(2026, 9, 7))
    db.session.commit()
    journal_out.autowrite()
    j = db.session.query(JournalEntry).order_by(JournalEntry.id.desc()).first()
    bullets = [line for line in j.body.splitlines() if line.startswith("- ")]
    assert len(bullets) == 1


def test_journal_exports_download_as_json_and_markdown(client):
    r = client.get("/journal/export.json")
    assert r.headers["Content-Disposition"] == (
        'attachment; filename="canopy-journal-2026-09-07.json"'
    )
    data = json.loads(r.get_data(as_text=True))
    assert len(data["entries"]) == db.session.query(JournalEntry).count()
    assert [e["date"] for e in data["entries"]] == sorted(e["date"] for e in data["entries"])

    r = client.get("/journal/export.md")
    assert r.headers["Content-Disposition"].endswith('.md"')
    md = r.get_data(as_text=True)
    assert md.startswith("# Grow journal")
    assert "\n## " in md and "\n### " in md


def test_a_backup_carries_the_log_and_an_old_one_gets_it_rebuilt(app):
    payload = transfer.dump()
    lines = len(payload["changes"])
    transfer.load(payload)
    assert db.session.query(Change).count() == lines

    del payload["changes"]
    transfer.load(payload)
    assert db.session.query(Change).count() >= db.session.query(PlantEvent).count()


def test_change_log_page_renders(client):
    r = client.get("/journal/changes")
    assert r.status_code == 200
    assert "started as" in r.get_data(as_text=True)
    assert "Autowrite (" in client.get("/journal/").get_data(as_text=True)


def test_clearing_a_flip_is_logged(app):
    p = _last_call()
    lifecycle.set_flip([p], date(2026, 9, 1))
    db.session.commit()
    lifecycle.clear_flip([p])
    db.session.commit()
    assert _lines(p)[-1] == "flip of 2026-09-01 removed"


def test_a_group_harvest_logs_the_group_and_each_plant(client):
    g = next(
        g
        for g in db.session.query(Group).order_by(Group.number)
        if any(p.status == PlantStatus.flowering for p in g.plants)
    )
    flowering = [p for p in g.plants if p.status == PlantStatus.flowering]
    before = db.session.query(Change).count()
    client.post(
        f"/groups/{g.id}/harvest",
        data={"plant_id": 0, "harvested_on": "2026-09-07", "notes": "Frosty"},
    )
    rows = db.session.query(Change).order_by(Change.id).offset(before).all()
    texts = [(c.subject, c.text) for c in rows]
    assert (g.label, "harvested — Frosty") in texts
    assert all((p.label, "flowering → harvested") in texts for p in flowering)
    assert (g.label, "flowering → drying") in texts
    assert all(c.on == date(2026, 9, 7) and c.group_id == g.id for c in rows)
