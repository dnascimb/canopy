# CLAUDE.md — working on Canopy with Claude Code

Canopy is a Flask 3 / SQLAlchemy 2 web app for cultivation planning (inventory, groups,
flowering schedule, space planning, journal, reports). This file tells Claude Code how the project is laid out, how to run
it, and the conventions to keep.

## Commands

```bash
pip install -r requirements-dev.txt          # deps incl. pytest, ruff, playwright
flask --app wsgi init-db && flask --app wsgi seed-demo
CANOPY_TODAY=2026-09-07 flask --app wsgi run --debug   # pinned "today" matches the demo season
pytest -q                                    # full suite (in-memory SQLite, CSRF off, today=2026-09-07)
pytest -q tests/test_scheduling.py -k openings
ruff check canopy tests && ruff format canopy tests
python scripts/screenshots.py && python scripts/annotate.py   # regenerate docs/screenshots
```

Always run `ruff` and `pytest` before finishing a change. Both must pass.

## Architecture in one paragraph

`canopy/__init__.py:create_app()` builds the app, registers blueprints and creates tables.
Models live in `canopy/models.py`. **All schedule maths lives in
`canopy/services/scheduling.py`** and is pure functions over model objects (events,
timeline rows, openings, suggestions, conflicts, ASCII/Markdown export). Blueprints under
`canopy/blueprints/` are thin: query → call service → render template or JSON. Templates
extend `templates/base.html` and use macros from `templates/_macros.html`. The Gantt is
rendered client-side by `static/js/timeline.js` from JSON that the templates inline
(`{{ timeline(rows, ref) }}` macro) and that `/api/v1/timeline` also serves.

## Domain rules to preserve

* `Group.flower_end = flower_start + flower_days`. It is **derived, never stored**. The end
  date is exclusive: a group is flowering on `start <= day < end`.
* `day_of_flower` is 1-based (flip day is day 1).
* A group with `flower_start is None` is *unscheduled*; it never appears on the timeline
  or in events, but does appear in "Waiting for a slot" with a suggested opening.
* An *opening* is a group's end date unless another group in the same space starts that
  same day (the "grp1 ends / grp7 starts" convention). See `scheduling.openings()`.
* Killed plants stay in the database with `status=killed`, `ended_on`, `end_reason`; they
  are excluded from `living_plants`, capacity counts and strain summaries, and shown
  struck-through in the Markdown export.
* "Today" comes from `scheduling.today()`, which honours `CANOPY_TODAY`. Never call
  `date.today()` directly in app code.
* Events on the same day sort **end before start**, then by group number.
* **Spaces have a stage** (clone / vegetative / flowering). A plant's *location* is
  `spacing.plant_location()`: explicit `plant.space`, else its group's space when
  flowering, else the first space of its stage. Harvested/killed plants are nowhere.
* **Footprints** (sq ft per plant) are `spacing.footprint_table()`: defaults in
  `DEFAULT_FOOTPRINT_SQFT` overridden by `app.config["FOOTPRINT_SQFT"]` (from
  `CANOPY_FOOTPRINT_*`). A space's effective capacity is `min(max plants, area ÷ footprint)`.
* Capacity is **not** a conflict. `spacing.capacity_warning(space, groups, occ)` returns
  the reason a space is in breach and the spaces page shows it as a red label on that
  space; `conflicts()` reports only genuinely broken schedules. It reads the projected
  peak from `load_series()` **on or after today** (history is not a warning) and falls
  back to current occupancy for spaces with no schedule behind them.
* `spacing.move_plants()` sets `plant.space` **and** aligns `plant.status` with the
  destination stage; never move plants by setting `space_id` alone.
* Journal `tasks` is a comma-separated string of keys from `models.TASKS`; use
  `JournalForm.tasks_csv` / `derived_title` when saving.

## Conventions

* Python 3.11+, type hints everywhere, `from __future__ import annotations`.
* Ruff (line length 100, rules E/F/I/B/UP/N/W). Run `ruff format`.
* Enums are `enum.StrEnum`; store them with `db.Enum(..., native_enum=False)`.
* Forms: WTForms in `forms.py`; populate select choices in the blueprint, not the form.
* Mutations are POST with CSRF (`{{ csrf() }}` macro). JSON API under `/api/v1` is
  CSRF-exempt.
* Flash messages use the same verb as the button ("Saved changes.", "Deleted Grp 3.").
* Templates: sentence case, no ALL-CAPS labels, minimal formatting. Reuse `.panel`,
  `.badge`, `.btn`, `.kv`, `.events`, `.flower-card` from `app.css` before adding CSS.
* Dates render through the `|d` (`Sep 07`) and `|dlong` (`Mon Sep 07, 2026`) filters.
* Tests: fixtures in `tests/conftest.py` seed the demo season; assert against known demo
  facts (e.g. Grp 7 flips 2026-07-28 for 112 days → ends 2026-11-17).

## Adding things

* **New field on a model** → `models.py` → `forms.py` → blueprint `populate_obj`/choices →
  template → `services/transfer.py` (dump/load) → API serialiser → tests.
* **New schedule rule** → function in `services/scheduling.py` with a unit test in
  `tests/test_scheduling.py`, then surface it in a template/API.
* **New space/capacity rule** → `services/spacing.py` + `tests/test_spacing.py`.
* **New report** → aggregation in `services/reports.py`, chart via the `hbars`/`steps`
  macros in `templates/_charts.html` (server-rendered SVG; no JS charting library).
* **New quick-log task** → add a key/label to `models.TASKS`; nothing else changes.
* **New screen** → blueprint module in `blueprints/`, register in `create_app`, template
  folder, nav link in `base.html`, route test in `tests/test_routes.py`, screenshot entry
  in `scripts/screenshots.py`.
* **Schema migration** → the app uses `db.create_all()`; for existing databases add an
  Alembic migration (Flask-Migrate is the intended path) or ship a one-off script.

## Things not to do

* Don't store computed dates (`flower_end`) or counts in the database.
* Don't add a CSS/JS framework; the design system is intentionally small.
* Don't put business logic in templates or blueprints — it belongs in `services/`.
* Don't change demo-season dates in `services/seed.py` without updating tests.
