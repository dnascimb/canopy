# Canopy technical guide

## Stack

| Layer | Choice | Why |
| --- | --- | --- |
| Language | Python 3.11+ | Type hints, `StrEnum`, `datetime.UTC`. |
| Web | Flask 3 (app factory + blueprints) | Small, explicit, server‑rendered; easy to reason about and to extend with Claude Code. |
| ORM | SQLAlchemy 2 (`Mapped[]` typed models) via Flask‑SQLAlchemy 3 | Portable across SQLite/PostgreSQL/MySQL. |
| Forms | Flask‑WTF / WTForms | Validation with user‑facing messages, CSRF on every mutation. |
| Templates | Jinja2 | One `base.html`, macros for repeated components. |
| Front end | Hand‑written CSS + vanilla JS | ~600 lines of CSS, one 150‑line Gantt renderer; no build step, no framework, no CDN. |
| Storage | SQLite by default | Zero‑config; switch with `CANOPY_DATABASE_URL`. |
| Tests | pytest + coverage | In‑memory SQLite, CSRF disabled, pinned "today". |
| Lint | Ruff | `E F I B UP N W`, line length 100. |
| Screenshots | Playwright (Chromium) + Pillow | `scripts/screenshots.py` self‑hosts the app; `scripts/annotate.py` draws callouts from measured element boxes. |

## Architecture

```
request ─▶ blueprint (canopy/blueprints/*.py)
               │  query models, validate forms
               ▼
           services/scheduling.py   pure functions: events, rows, openings, conflicts, exports
           services/spacing.py      locations, footprints, occupancy, fit estimates, load series
           services/reports.py      per-strain / per-group aggregations
           services/transfer.py     JSON dump / load
               │
               ▼
           templates/*.html  ──▶  static/js/timeline.js renders the Gantt from inlined JSON
           blueprints/api.py ──▶  same service output as JSON at /api/v1
```

### Application factory

`canopy/__init__.py:create_app(config_object=None)`:

1. Loads `Config` (or `TestConfig`) from `canopy/config.py`; every setting is an
   environment variable prefixed `CANOPY_`.
2. Resolves the database URL (default `instance/canopy.db`).
3. Initialises `db` and `csrf` (`canopy/extensions.py`).
4. Registers blueprints with URL prefixes; exempts the API blueprint from CSRF.
5. Registers CLI commands, Jinja globals (`today`, `app_version`) and filters
   (`|d`, `|dlong`, `|grams`), and the 404 handler.
6. `db.create_all()` so a fresh checkout runs without a migration step.

### Blueprints

| Blueprint | Prefix | Responsibility |
| --- | --- | --- |
| `dashboard` | `/` | Season overview. |
| `schedule` | `/schedule` | Events, openings, conflicts, print, exports, backup/restore. |
| `groups` | `/groups` | CRUD, schedule‑suggestion accept, status changes (with plant cascade), harvest and journal sub‑forms. |
| `plants` | `/plants` | CRUD, kill, status. |
| `strains` | `/strains` | Inventory CRUD, search, seed adjust. |
| `spaces` | `/spaces` | CRUD, occupancy. |
| `journal` | `/journal` | CRUD, task filter, `POST /quick` for the checkbox log. |
| `reports` | `/reports` | Per-strain and per-group charts and tables. |
| `api` | `/api/v1` | JSON read endpoints + `PATCH /groups/<id>`. |

Blueprints never compute schedule facts themselves; they call `services.scheduling`.

## Data model

```
Space 1 ──< Group 1 ──< Plant >── 1 Strain
              │           │
              ├──< Harvest >──┤      (harvest belongs to a group and/or a plant)
              └──< JournalEntry >──┘  (entry belongs to a group and/or a plant)
```

| Table | Key columns | Notes |
| --- | --- | --- |
| `spaces` | `name` (unique), `stage` (clone/vegetative/flowering), `width_ft`, `length_ft`, `capacity ≥ 1` (user maximum), `notes` | `area_sqft` is derived. Deleting a space nulls `groups.space_id` and `plants.space_id`. |
| `strains` | `name`, `breeder`, `lineage`, `seed_type` (regular/feminized/autoflower/clone), `flower_days ≥ 1`, `seeds_on_hand ≥ 0`, `size` (small/medium/large), `notes` | Unique on (`name`, `breeder`). Cannot be deleted while it has plants. |
| `groups` | `number` (unique int), `name` (optional), `space_id`, `flower_start` (nullable), `flower_days ≥ 1`, `status`, `color` (#rrggbb), `notes` | `flower_end` is a property, never stored. Deleting a group unassigns its plants; harvests and journal entries cascade. |
| `plants` | `label`, `strain_id`, `group_id` (nullable), `space_id` (nullable explicit location), `status` (clone/seedling/vegetative/flowering/harvested/killed), `started_on`, `ended_on`, `end_reason`, `notes` | Killed plants are retained. |
| `harvests` | `group_id` / `plant_id` (at least one), `harvested_on`, `wet_weight_g`, `notes` | |
| `journal_entries` | `entry_date`, `group_id` / `plant_id`, `title`, `body`, `tasks` (comma-separated keys from `models.TASKS`) | `task_list` / `task_labels` are derived. |

All tables carry `created_at` / `updated_at` (UTC, naive). Enums are stored as short
strings (`native_enum=False`) so the schema is identical on every database.

### Derived properties (models.py)

* `Group.flower_end = flower_start + timedelta(flower_days)`; `None` if unscheduled.
* `Group.is_flowering_on(day)`: `start <= day < end` (end exclusive).
* `Group.day_of_flower(today)`: 1‑based, `None` outside the window.
* `Group.progress(today)`: 0–1 fraction of the window elapsed.
* `Group.living_plants` / `killed_plants`; `strain_summary()` lists distinct living strain names in plant order.
* `Space.active_groups(today)`, `Space.plants_in_flower(today)`.

## Scheduling algorithms (services/scheduling.py)

All functions accept an optional `ref` date and fall back to `today()`, which honours
`CANOPY_TODAY`. Nothing here touches the request or the session, so every function is
unit‑testable with plain model instances.

**`events(groups)`** — for each scheduled group emit `(start, "start")` and
`(end, "end")`; sort by `(date, end‑before‑start, group.number)`. The ordering rule makes
the classic "Grp 6 ends / Grp 12 starts" pair read naturally.

**`upcoming(groups, days=30)`** — events within `[ref, ref+days]`.

**`timeline_rows(groups)`** — the JSON rows consumed by the Gantt, ASCII export and API:
label, ISO start/end, days, colour, status, space, strain names of living plants, plant
count, progress and day of flower. Sorted by start date then number; unscheduled groups
are omitted.

**`timeline_bounds(rows, pad_days=7)`** — min start − pad to max end + pad.

**`openings(groups)`** — every scheduled group's end date on or after `ref`, *except*
where another scheduled group in the same space starts on exactly that date (the slot is
already back‑filled). Sorted by date.

**`suggest_start(group, all_groups)`** — the first opening excluding the group itself;
if the group already has a space, prefer openings in that space.

**`conflicts(groups, spaces)`** — returns `Conflict(severity, message, group?, space?)`:

* error — group marked flowering with no start date;
* warning — scheduled group with no space, or with no living plants (only for groups not yet finished);
* error — space capacity exceeded. Capacity is evaluated only at each distinct start/end
  date in that space (the occupancy step function can only change there), counting
  living plants of groups flowering on that day.

**`implied_status(group)`** — what the calendar says: planned/vegetative if unscheduled,
vegetative before the flip, flowering inside the window, drying after. The group page
offers a one‑click fix when this differs from the stored status.

**`ascii_timeline(rows, width=64)`** — month header, tick row with `+` at month starts
and `*` at today, one `=` bar per row, days suffix. Pure ASCII by design.

**`markdown_export(groups)`** — bulleted groups (killed plants struck through), event
table, ASCII timeline in a code fence.

## Space planning (services/spacing.py)

**Footprints.** `DEFAULT_FOOTPRINT_SQFT[stage][size]` gives square feet per plant;
`footprint_table()` overlays `app.config["FOOTPRINT_SQFT"]` (built in `config.py` from
`CANOPY_FOOTPRINT_CLONE/_VEG/_FLOWER = "small,medium,large"`).

**Location.** `plant_location(plant, spaces)`: `None` for harvested/killed; otherwise the
explicit `plant.space`, else the group's space for flowering plants, else the first space
whose stage matches the plant's status (`STAGE_FOR_STATUS`).

**Occupancy.** `occupancy(spaces, plants)` buckets living plants by location into
`Occupancy` objects with `count`, `used_sqft` (sum of footprints at the *space's* stage),
`load` (area-based when dimensions exist, else count ÷ maximum), `over`, `fits(size)` =
`min(maximum, ⌊area ÷ footprint⌋)` and `room_for(size)` = the same on the remaining area
and remaining count.

**Load series.** `load_series(space, groups, ref)` evaluates the schedule at every flip
and harvest date in that space (plus today) and returns `{date, count, sqft, groups}`
points. `peak(series, since=today)` is what conflicts use; the chart shows the full
series with the space's area as the capacity line.

**Moves.** `move_plants(plants, space)` sets `plant.space` and `plant.status =
STATUS_FOR_STAGE[space.stage]`, skipping harvested/killed plants. The group route also
sets the group's space, status and flip date when the destination is a flowering space.

**Conflicts** (`scheduling.conflicts`) now take `plants` too: for each flowering space
the projected peak from today onward is compared to area (if known) and to the maximum;
each space's current occupancy is checked for overflow.

## Reports (services/reports.py)

`strain_stats()` walks plants per strain for grown/harvested/killed counts and attributes
harvest weights: plant-level harvests to that plant's strain, group-level harvests split
evenly across the group's non-killed plants. `group_yields()` and `kill_reasons()` feed
the remaining tables. Charts are the `hbars` and `steps` macros in
`templates/_charts.html`: server-rendered SVG scaled by `viewBox`, coloured with the CSS
tokens, so they print and need no JavaScript.

## Front end

* **`static/css/app.css`** — tokens in `:root`, then layout (sidebar + main grid),
  then components (`.panel`, `.stat`, `.btn`, `.badge`, tables, forms, `.timeline`,
  `.flower-card`, `.events`, `.kv`, `.journal`), utilities, responsive rules (≤860px:
  sidebar becomes a top bar; grids collapse; `min-width: 0` on grid children so the
  timeline scrolls inside its panel), and print rules.
* **`static/js/timeline.js`** — `Timeline.mount('[data-timeline]')` reads the inlined
  JSON (`<script type="application/json">`) or fetches `/api/v1/timeline`, then builds
  the month header (year shown on the first cell and every January), rows, bars with an
  elapsed overlay, month gridlines, the today line and a tooltip. Bars link to the group.
  Dates are handled in UTC to avoid off‑by‑one drift across time zones.
* No external requests: fonts fall back to system faces so the app works offline and
  screenshots are deterministic.

## Security

* CSRF tokens on every HTML form (`{{ csrf() }}`); destructive actions are POST behind a
  confirm dialog.
* The JSON API is CSRF‑exempt and has **no authentication** — Canopy is designed for a
  trusted LAN or behind a reverse proxy with auth. Put it behind basic auth / Tailscale /
  a VPN before exposing it.
* Jinja auto‑escaping is on; the timeline tooltip escapes strings before `innerHTML`.
* Set `CANOPY_SECRET_KEY` in production; the default is for development only.
* SQL is parameterised through SQLAlchemy; no raw SQL.

## Testing

```
tests/conftest.py       app/client/runner fixtures; fresh in-memory DB + demo seed per test
tests/test_models.py    derived dates, exclusive end, labels, living/killed, occupancy
tests/test_scheduling.py events ordering, upcoming window, rows, bounds, openings back-fill,
                        suggestion, conflicts (clean/capacity/no space/no plants), implied
                        status, ASCII + Markdown export, inventory/plant counts
tests/test_routes.py    every page renders, CRUD flows, duplicate numbers, suggestion accept,
                        kill + status, status cascade, harvest/journal, search, backup/restore
tests/test_api.py       health, timeline, events/openings/conflicts, groups + PATCH, exports
tests/test_cli.py       init-db, seed-demo, export-markdown, export-json
tests/test_spacing.py   area/dimensions, footprint overrides, location rules, occupancy/fits,
                        cap vs area, load series & peak, area-based conflicts, moves (service
                        and routes), planner page, quick log, task filter, last-done, reports,
                        spaces API, backup round-trip of new fields
```

`pytest --cov=canopy` reports ~97% line coverage. Tests assert against fixed facts of the
demo season (today = 2026‑09‑07), e.g. Grp 7 flips 2026‑07‑28 for 112 days → day 42 today,
ends 2026‑11‑17; the first opening is 2026‑10‑25 when Grp 10 finishes.

## Deployment

**Docker** (recommended): `docker compose up --build` builds a `python:3.12-slim` image,
runs `init-db`, serves with Gunicorn (2 workers) on port 8000 and stores the SQLite file
in the `canopy-data` volume. Set `CANOPY_SECRET_KEY` in the environment.

**Bare metal**: `pip install -r requirements.txt gunicorn && gunicorn -b 0.0.0.0:8000 -w 2 wsgi:app`
behind nginx/Caddy. Point `CANOPY_DATABASE_URL` at PostgreSQL for multi‑user use.

**Backups**: `flask --app wsgi export-json > backup.json` (or the Schedule → Backup
button). SQLite users can also just copy `instance/canopy.db`.

**Schema changes**: the app calls `db.create_all()`, which adds new tables but not new
columns. For existing databases add Flask‑Migrate/Alembic (the models are ready for it)
or restore from a JSON backup after resetting.

## Extending

Common extensions and where they go:

| Want | Touch |
| --- | --- |
| Feeding/EC/pH log | New model + blueprint, journal‑style; link to group/plant. |
| Veg duration planning | Add `veg_start` to Group; extend `timeline_rows` with a second bar. |
| Multiple rooms with different photoperiods | Already supported via Spaces; add a `light_schedule` column if needed. |
| Auth | Flask‑Login on the blueprints, or a reverse proxy. |
| Calendar feed | New route producing iCalendar from `scheduling.events()`. |
| Charts of yield per strain | `Harvest` joined to `Plant.strain`; render with the existing table styles or a small `<canvas>`. |
