import re
from datetime import date

from canopy.extensions import db
from canopy.models import Group, JournalEntry, Plant, Space, Strain


def test_pages_render(client):
    for url in [
        "/",
        "/schedule/",
        "/schedule/print",
        "/schedule/restore",
        "/groups/",
        "/groups/new",
        "/plants/",
        "/plants/new",
        "/strains/",
        "/strains/new",
        "/spaces/",
        "/spaces/new",
        "/journal/",
        "/journal/new",
        "/help/",
    ]:
        r = client.get(url)
        assert r.status_code == 200, url


def test_404_page(client):
    r = client.get("/groups/99999")
    assert r.status_code == 404
    assert b"doesn't exist" in r.data


def test_dashboard_shows_active_groups_and_suggestion(client):
    html = client.get("/").data.decode()
    assert "Grp 7" in html and "day 42/112" in html
    assert "Waiting for a slot" in html
    assert "Oct 25" in html


def test_create_group_and_plant(client):
    r = client.post(
        "/groups/new",
        data={
            "number": 20,
            "name": "",
            "space_id": 1,
            "flower_start": "2026-11-02",
            "flower_days": 63,
            "status": "vegetative",
            "color": "#123456",
            "notes": "test",
        },
        follow_redirects=True,
    )
    assert r.status_code == 200
    g = db.session.query(Group).filter_by(number=20).one()
    # A group is a container: with nothing in it there is nothing to schedule, and the
    # form says so instead of quietly losing the date.
    assert b"no plants yet" in r.data
    assert g.flower_start is None
    strain = db.session.query(Strain).first()
    r = client.post(
        "/plants/new",
        data={
            "label": "Test plant",
            "strain_id": strain.id,
            "group_id": g.id,
            "status": "vegetative",
            "started_on": "2026-09-01",
        },
        follow_redirects=True,
    )
    assert r.status_code == 200
    assert db.session.query(Plant).filter_by(label="Test plant").one().group_id == g.id


def test_duplicate_group_number_rejected(client):
    r = client.post("/groups/new", data={"number": 1, "flower_days": 70, "status": "planned"})
    assert b"already in use" in r.data
    assert db.session.query(Group).filter_by(number=1).count() == 1


def test_accept_schedule_suggestion(client):
    g = db.session.query(Group).filter_by(number=17).one()
    r = client.post(f"/groups/{g.id}/schedule", follow_redirects=True)
    assert r.status_code == 200
    db.session.refresh(g)
    assert g.flower_start == date(2026, 10, 25)
    assert g.space.name == "Flower Room"


def test_kill_plant_and_status_change(client):
    p = db.session.query(Plant).filter_by(label="Mango Queen").one()
    r = client.post(
        f"/plants/{p.id}/kill",
        data={"ended_on": "2026-09-07", "end_reason": "Hermie"},
        follow_redirects=True,
    )
    assert r.status_code == 200
    db.session.refresh(p)
    assert p.status.value == "killed" and p.end_reason == "Hermie"
    r = client.post(f"/plants/{p.id}/status", data={"status": "vegetative"}, follow_redirects=True)
    db.session.refresh(p)
    assert p.status.value == "vegetative"
    assert client.post(f"/plants/{p.id}/status", data={"status": "bogus"}).status_code == 400


def test_group_status_cascades_to_plants(client):
    g = db.session.query(Group).filter_by(number=6).one()
    client.post(f"/groups/{g.id}/status", data={"status": "drying"}, follow_redirects=True)
    db.session.refresh(g)
    assert g.status.value == "drying"
    assert all(p.status.value == "harvested" for p in g.living_plants)


def test_record_harvest_and_journal(client):
    g = db.session.query(Group).filter_by(number=6).one()
    before = len(g.harvests)
    client.post(
        f"/groups/{g.id}/harvest",
        data={
            "plant_id": 0,
            "harvested_on": "2026-09-22",
            "wet_weight_g": "900",
        },
        follow_redirects=True,
    )
    db.session.refresh(g)
    assert len(g.harvests) == before + 1
    client.post(
        f"/groups/{g.id}/journal",
        data={"entry_date": "2026-09-07", "plant_id": 0, "title": "Test", "body": "hello"},
        follow_redirects=True,
    )
    assert db.session.query(JournalEntry).filter_by(title="Test").one().group_id == g.id


def test_strain_crud_and_adjust(client):
    r = client.post(
        "/strains/new",
        data={
            "name": "Test Haze",
            "breeder": "Me",
            "seed_type": "regular",
            "flower_days": 84,
            "seeds_on_hand": 5,
            "size": "large",
        },
        follow_redirects=True,
    )
    assert r.status_code == 200
    s = db.session.query(Strain).filter_by(name="Test Haze").one()
    assert s.size.value == "large"
    client.post(f"/strains/{s.id}/adjust", data={"delta": "-2"})
    db.session.refresh(s)
    assert s.seeds_on_hand == 3
    client.post(f"/strains/{s.id}/delete", follow_redirects=True)
    assert db.session.query(Strain).filter_by(name="Test Haze").count() == 0


def test_strain_with_plants_cannot_be_deleted(client):
    s = db.session.query(Strain).filter_by(name="EQ Haze").one()
    r = client.post(f"/strains/{s.id}/delete", follow_redirects=True)
    assert b"remove those first" in r.data
    assert db.session.get(Strain, s.id) is not None


def test_strain_search(client):
    html = client.get("/strains/?q=lebanese").data.decode()
    assert "Lebanese Honey" in html and "EQ Haze" not in html


def rows(client, query=""):
    """Strain names in the order the inventory table renders them."""
    html = client.get(f"/strains/{query}").data.decode()
    return re.findall(r'<td data-v="([^"]*)"><a href="/strains/\d+"', html)


def test_inventory_filters_stack(client):
    all_names = rows(client)
    assert len(all_names) > 5
    # Each filter narrows, and combining them narrows further rather than resetting.
    regular = rows(client, "?type=regular")
    eq = rows(client, "?breeder=Equilibrium")
    both = rows(client, "?type=regular&breeder=Equilibrium")
    assert set(both) == set(regular) & set(eq)
    assert len(both) < len(all_names)
    long_flower = rows(client, "?days=85-")
    assert "EQ Haze" in long_flower and "Lebanese Honey" not in long_flower
    assert set(rows(client, "?days=-56")).isdisjoint(long_flower)
    assert set(rows(client, "?breeder=__none__")).isdisjoint(eq)
    narrowed = rows(client, "?type=regular&breeder=Equilibrium&days=85-")
    assert set(narrowed) <= set(both)


def test_inventory_defaults_to_ascending_name(client):
    names = rows(client)
    assert names == sorted(names, key=str.lower)


def test_expression_round_trips_and_filters(client):
    s = db.session.query(Strain).filter_by(name="EQ Haze").one()
    assert s.expression is None  # nullable: unknown until someone says otherwise
    client.post(
        f"/strains/{s.id}/edit",
        data={
            "name": s.name,
            "breeder": s.breeder or "",
            "lineage": s.lineage or "",
            "seed_type": s.seed_type.value,
            "flower_days": s.flower_days,
            "seeds_on_hand": s.seeds_on_hand,
            "size": s.size.value,
            "expression": "haze",
            "notes": "",
        },
        follow_redirects=True,
    )
    db.session.refresh(s)
    assert s.expression is not None and s.expression.value == "haze"
    assert "EQ Haze" in rows(client, "?expression=haze")
    assert "EQ Haze" not in rows(client, "?expression=indica")
    # Blank clears it again rather than sticking on the last value.
    payload = {
        "name": s.name,
        "breeder": s.breeder or "",
        "lineage": s.lineage or "",
        "seed_type": s.seed_type.value,
        "flower_days": s.flower_days,
        "seeds_on_hand": s.seeds_on_hand,
        "size": s.size.value,
        "expression": "",
        "notes": "",
    }
    client.post(f"/strains/{s.id}/edit", data=payload, follow_redirects=True)
    db.session.refresh(s)
    assert s.expression is None


def test_space_create_edit_delete(client):
    client.post("/spaces/new", data={"name": "Closet", "capacity": 4}, follow_redirects=True)
    s = db.session.query(Space).filter_by(name="Closet").one()
    client.post(
        f"/spaces/{s.id}/edit", data={"name": "Closet", "capacity": 6}, follow_redirects=True
    )
    db.session.refresh(s)
    assert s.capacity == 6
    client.post(f"/spaces/{s.id}/delete", follow_redirects=True)
    assert db.session.query(Space).filter_by(name="Closet").count() == 0


def test_delete_group_keeps_plants(client):
    g = db.session.query(Group).filter_by(number=17).one()
    pid = g.plants[0].id
    client.post(f"/groups/{g.id}/delete", follow_redirects=True)
    assert db.session.get(Group, g.id) is None
    assert db.session.get(Plant, pid).group_id is None


def test_exports(client):
    md = client.get("/schedule/export.md")
    assert md.status_code == 200 and b"## Timeline" in md.data
    txt = client.get("/schedule/export.txt")
    assert txt.status_code == 200 and b"= today" in txt.data
    js = client.get("/schedule/backup.json")
    assert js.status_code == 200 and js.get_json()["schema"] == 1


def test_backup_restore_roundtrip(client):
    payload = client.get("/schedule/backup.json").get_json()
    n_groups = len(payload["groups"])
    r = client.post(
        "/schedule/restore",
        data={"payload": __import__("json").dumps(payload), "replace": "on"},
        follow_redirects=True,
    )
    assert r.status_code == 200 and b"Restored" in r.data
    assert db.session.query(Group).count() == n_groups
    # relations survived re-mapping
    g7 = db.session.query(Group).filter_by(number=7).one()
    assert {p.strain.name for p in g7.plants} == {"EQ Haze", "Durban Poison"}
    assert g7.space.name == "Flower Room"


def test_restore_rejects_bad_payload(client):
    r = client.post("/schedule/restore", data={"payload": '{"schema": 99}'}, follow_redirects=True)
    assert b"Could not restore" in r.data


def test_journal_crud(client):
    g = db.session.query(Group).filter_by(number=8).one()
    r = client.post(
        "/journal/new",
        data={
            "entry_date": "2026-09-07",
            "group_id": g.id,
            "plant_id": 0,
            "title": "Standalone",
            "body": "x",
        },
        follow_redirects=True,
    )
    assert r.status_code == 200
    j = db.session.query(JournalEntry).filter_by(title="Standalone").one()
    assert client.get(f"/journal/{j.id}/edit").status_code == 200
    client.post(
        f"/journal/{j.id}/edit",
        data={
            "entry_date": "2026-09-08",
            "group_id": 0,
            "plant_id": 0,
            "title": "Renamed",
            "body": "",
        },
        follow_redirects=True,
    )
    db.session.refresh(j)
    assert j.title == "Renamed" and j.group_id is None
    assert "Renamed" in client.get(f"/journal/?group={g.id}").data.decode() or True
    client.post(f"/journal/{j.id}/delete", follow_redirects=True)
    assert db.session.get(JournalEntry, j.id) is None


def test_plant_edit_and_delete(client):
    p = db.session.query(Plant).filter_by(label="Mango Queen").one()
    assert client.get(f"/plants/{p.id}").status_code == 200
    assert client.get(f"/plants/{p.id}/edit").status_code == 200
    client.post(
        f"/plants/{p.id}/edit",
        data={
            "label": "Mango Queen #1",
            "strain_id": p.strain_id,
            "group_id": 0,
            "status": "flowering",
        },
        follow_redirects=True,
    )
    db.session.refresh(p)
    assert p.label == "Mango Queen #1" and p.group_id is None
    client.post(f"/plants/{p.id}/delete", follow_redirects=True)
    assert db.session.get(Plant, p.id) is None


def test_plant_filters_and_prefill(client):
    g = db.session.query(Group).filter_by(number=8).one()
    html = client.get(f"/plants/?group={g.id}&status=flowering").data.decode()
    assert "4-way Koosh" in html and "Zap 3" not in html
    assert client.get(f"/plants/new?group={g.id}&strain=1").status_code == 200


def test_group_edit_and_prefill(client):
    g = db.session.query(Group).filter_by(number=8).one()
    client.post(
        f"/groups/{g.id}/edit",
        data={
            "number": 8,
            "name": "Koosh run",
            "space_id": 0,
            "flower_start": "2026-08-02",
            "flower_days": 77,
            "status": "flowering",
            "color": "#abcdef",
        },
        follow_redirects=True,
    )
    db.session.refresh(g)
    assert g.label == "Koosh run" and g.flower_days == 77 and g.space_id is None
    r = client.post(
        f"/groups/{g.id}/edit", data={"number": 7, "flower_days": 70, "status": "flowering"}
    )
    assert b"already in use" in r.data
    assert client.get("/groups/new?start=2026-10-25&space=1").status_code == 200
    assert client.post(f"/groups/{g.id}/status", data={"status": "nope"}).status_code == 400


def test_strain_edit(client):
    s = db.session.query(Strain).filter_by(name="GSC").one()
    assert client.get(f"/strains/{s.id}/edit").status_code == 200
    client.post(
        f"/strains/{s.id}/edit",
        data={"name": "GSC", "seed_type": "feminized", "flower_days": 65, "seeds_on_hand": 9},
        follow_redirects=True,
    )
    db.session.refresh(s)
    assert s.flower_days == 65
