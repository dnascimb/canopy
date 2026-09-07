"""Capture documentation screenshots.

Starts Canopy in-process with a temporary database seeded with the demo season and
a fixed "today" (2026-09-07), then drives it with Playwright/Chromium and writes
PNGs to docs/screenshots/. Run with:  python scripts/screenshots.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
from pathlib import Path
from wsgiref.simple_server import WSGIRequestHandler, make_server

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
OUT = ROOT / "docs" / "screenshots"
PORT = int(os.environ.get("CANOPY_SHOT_PORT", "5077"))
TODAY = "2026-09-07"


class Quiet(WSGIRequestHandler):
    def log_message(self, *args):  # silence request log
        pass


def make_app():
    from canopy import create_app
    from canopy.config import Config
    from canopy.services.seed import seed_demo

    tmp = tempfile.mkdtemp(prefix="canopy-shots-")

    class ShotConfig(Config):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp}/shots.db"
        TODAY_OVERRIDE = TODAY
        WTF_CSRF_ENABLED = True

    app = create_app(ShotConfig)
    with app.app_context():
        seed_demo()
    return app


def main() -> None:
    from playwright.sync_api import sync_playwright

    app = make_app()
    server = make_server("127.0.0.1", PORT, app, handler_class=Quiet)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{PORT}"
    OUT.mkdir(parents=True, exist_ok=True)

    with app.app_context():
        from canopy.extensions import db
        from canopy.models import Group, Plant, Strain

        g6 = db.session.query(Group).filter_by(number=6).one().id
        g17 = db.session.query(Group).filter_by(number=17).one().id
        g4 = db.session.query(Group).filter_by(number=4).one().id
        p_zap = db.session.query(Plant).filter_by(label="Zap 3").one().id
        s_leb = db.session.query(Strain).filter_by(name="Lebanese Honey").one().id

    # CSS selectors whose bounding boxes are recorded for scripts/annotate.py
    boxes_for = {
        "dashboard": [
            ".nav",
            ".stat-strip",
            "[data-timeline]",
            ".flower-list",
            "section:has(.flower-list) + section .panel",
            ".main .grid-main-side > div:last-child section:nth-child(1) .panel",
            ".main .grid-main-side > div:last-child section:nth-child(2) .panel",
            ".main .grid-main-side > div:last-child section:nth-child(3) .panel",
            ".main .grid-main-side > div:last-child section:nth-child(4)",
            ".main .grid-main-side > div:last-child section:nth-child(5) .panel",
            ".page-head .actions",
        ],
        "schedule": [
            ".page-head .actions",
            "[data-timeline]",
            ".grid-main-side > section .panel",
            ".grid-main-side > div section:nth-child(1) .panel",
            ".grid-main-side > div section:nth-child(2) .panel",
            ".grid-main-side > div section:nth-child(3)",
        ],
        "group_detail": [
            ".page-head > div",
            ".page-head .actions",
            ".main > .progress",
            "section:has(> .section-head h2:text('Plants')) .panel",
            "section:has(> .section-head h2:text('Plants')) form.row",
            "#harvest .panel",
            ".grid-main-side > div:last-child section:first-child .panel",
            "#journal .quicklog",
            "#journal .journal",
        ],
        "group_unscheduled": [".alert.warning"],
        "inventory": [
            ".filters",
            ".page-head .actions",
            ".table-wrap",
            "tbody tr:first-child td:nth-child(7)",
        ],
        "plants": [".filters", ".table-wrap"],
        "spaces": [
            ".spaces",
            "section:nth-of-type(2) .panel",
            ".grid-main-side > section:first-child .panel",
            ".grid-main-side > section:last-child .panel",
        ],
        "reports": [
            ".main > .grid-2:nth-child(2)",
            ".main > .grid-2:nth-child(3)",
            "section:has(h2:text('Yield per group')) .panel",
        ],
        "groups": [".pill-nav", ".table-wrap"],
        "journal": [".page-head .actions", ".filters", ".journal > li:first-child"],
    }
    boxes: dict[str, list[dict]] = {}

    shots = [
        ("dashboard", "/", True),
        ("schedule", "/schedule/", True),
        ("groups", "/groups/?view=all", True),
        ("group_detail", f"/groups/{g6}", True),
        ("group_unscheduled", f"/groups/{g17}", False),
        ("group_with_kills", f"/groups/{g4}", True),
        ("group_form", "/groups/new", False),
        ("plants", "/plants/", True),
        ("plant_detail", f"/plants/{p_zap}", False),
        ("inventory", "/strains/", True),
        ("strain_detail", f"/strains/{s_leb}", False),
        ("spaces", "/spaces/", True),
        ("journal", "/journal/", True),
        ("reports", "/reports/", True),
        ("print", "/schedule/print", True),
    ]

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1360, "height": 860}, device_scale_factor=1)
        page.add_init_script("window.print = () => {};")
        for name, path, full in shots:
            page.goto(base + path)
            page.wait_for_timeout(350)
            page.screenshot(path=str(OUT / f"{name}.png"), full_page=full)
            if name in boxes_for:
                page.evaluate("window.scrollTo(0, 0)")
                boxes[name] = []
                for sel in boxes_for[name]:
                    loc = page.locator(sel).first
                    bb = loc.bounding_box() if loc.count() else None
                    boxes[name].append({"selector": sel, "box": bb})
            print("wrote", name)

        # Timeline hover tooltip
        page.goto(base + "/")
        page.wait_for_timeout(350)
        bar = page.locator(".tl-bar").nth(8)
        bar.hover()
        page.wait_for_timeout(200)
        page.locator(".panel").first.screenshot(path=str(OUT / "timeline_tooltip.png"))
        print("wrote timeline_tooltip")

        # Mobile layout
        mobile = browser.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2)
        mobile.goto(base + "/")
        mobile.wait_for_timeout(350)
        mobile.screenshot(path=str(OUT / "mobile_dashboard.png"), full_page=False)
        print("wrote mobile_dashboard")
        browser.close()
    (OUT / "boxes.json").write_text(json.dumps(boxes, indent=1))
    server.shutdown()


if __name__ == "__main__":
    main()
