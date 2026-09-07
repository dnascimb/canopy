from canopy.extensions import db
from canopy.models import Group


def test_health(client):
    assert client.get("/api/v1/health").get_json() == {"status": "ok", "today": "2026-09-07"}


def test_timeline(client):
    d = client.get("/api/v1/timeline").get_json()
    assert d["today"] == "2026-09-07"
    assert d["start"] == "2026-05-05" and d["end"] == "2026-12-27"
    assert len(d["rows"]) == 16


def test_events_openings_conflicts(client):
    ev = client.get("/api/v1/events").get_json()
    assert ev[0] == {
        "date": "2026-05-12",
        "kind": "start",
        "group_id": ev[0]["group_id"],
        "label": "Goji 3x start flower",
    }
    op = client.get("/api/v1/openings").get_json()
    assert op[0]["date"] == "2026-10-25" and op[0]["freed_by"] == "Grp 10"
    assert client.get("/api/v1/conflicts").get_json() == []


def test_groups_and_patch(client):
    gs = client.get("/api/v1/groups").get_json()
    g7 = next(g for g in gs if g["number"] == 7)
    assert g7["flower_end"] == "2026-11-17" and g7["day_of_flower"] == 42
    r = client.patch(f"/api/v1/groups/{g7['id']}", json={"flower_days": 105, "notes": "via api"})
    assert r.status_code == 200
    assert r.get_json()["flower_end"] == "2026-11-10"
    assert db.session.get(Group, g7["id"]).notes == "via api"
    assert client.get("/api/v1/groups/999999").status_code == 404


def test_strains_plants_export(client):
    assert any(
        s["name"] == "Lebanese Honey" and s["flower_days"] == 56
        for s in client.get("/api/v1/strains").get_json()
    )
    plants = client.get("/api/v1/plants").get_json()
    assert any(p["label"] == "Zap 3" and p["status"] == "killed" for p in plants)
    dump = client.get("/api/v1/export").get_json()
    assert set(dump) >= {
        "schema",
        "spaces",
        "strains",
        "groups",
        "plants",
        "harvests",
        "journal_entries",
    }
    assert client.get("/api/v1/export.md").data.startswith(b"# Cultivation schedule")
