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
           services/spacing.py      locations, occupancy, moves, load series
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
   (`|d`, `|dlong`), and the 404 handler.
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
| `journal` | `/journal` | CRUD, space and task filters, `POST /quick` for the per-space checkbox log. |
| `help` | `/help` | Static walkthrough of the lifecycle transitions, rendered with the garden's real space names. |
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
| `spaces` | `name` (unique), `stage` (clone/vegetative/flowering), `also_hosts` (extra stages, CSV), `capacity ≥ 1` (plants it holds), `notes` | No dimensions: a space is a location, not a floor plan. `hosts`/`can_host()` read stage + also_hosts. Deleting a space nulls `groups.space_id` and `plants.space_id`. |
| `strains` | `name`, `breeder`, `lineage`, `seed_type` (regular/feminized/autoflower/clone), `flower_days ≥ 1`, `seeds_on_hand ≥ 0`, `size` (small/medium/large), `expression` (sativa/haze/indica/hybrid, nullable), `notes` | Unique on (`name`, `breeder`). Cannot be deleted while it has plants. |
| `groups` | `number` (unique int), `name` (optional), `space_id`, `status`, `color` (#rrggbb), `notes` | **No date columns.** `flower_start` / `flower_end` / `flower_days` are properties spanning the group's plants. Deleting a group unassigns its plants; harvests and journal entries cascade. |
| `plants` | `label`, `strain_id`, `group_id` (nullable), `space_id` (nullable explicit location), `status`, `started_on`, `ended_on`, `end_reason`, `flower_days_override` (nullable), `parent_id` (nullable self-reference, SET NULL), `notes` | Killed plants are retained. `parent` / `cuttings` walk the propagation line; `ancestry` climbs it, loop-safe. `flower_start` is derived from `plant_events`; `flower_days` falls back to the strain. |
| `plant_events` | `plant_id`, `on`, `from_status` (nullable), `to_status`, `space_id`, `note` | Append-only lifecycle log and the source of truth for flip dates. Written only by `services/lifecycle.py`. |
| `harvests` | `group_id` / `plant_id` (at least one), `harvested_on`, `notes` | No weights are recorded. Adding one marks the plants it covers harvested and moves the group to drying once nothing is left in flower. |
| `journal_entries` | `entry_date`, `space_id` / `group_id` / `plant_id` (all optional), `title`, `body`, `tasks` (comma-separated keys from `models.TASKS`), `photo_path` | `task_list` / `task_labels` are derived. Entries are notes only — nothing reads them back as data. |

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
* warning — scheduled group with no space, or with no living plants (only for groups not yet finished).

**`ramp_down(units, spaces)`** — returns `RampDown(unit, end, days_left, plants, spread)`
for every run standing in a *flowering* space whose harvest is between today and
`RAMP_DOWN_DAYS` (14) away, so the grower can start watering at half strength. Two
decisions worth knowing:

* The trigger is the **earliest** living plant to finish, not the latest. `Group.flower_end`
  is the max across plants, which would raise the alert too late for a run whose plants
  finish on different days; `spread` is set in that case and the message says "first plants".
* **Only flowering spaces count.** Nothing in veg or on the clone shelf is finishing
  anything, whatever dates its plants happen to carry.

`RampDown.lone_plant` is the `Plant` when the unit is a `LonePlant`, else `None`, so a
caller can link to the right page without knowing what a `LonePlant` is.

Space capacity is deliberately absent from this list: it is a number the grower sets,
reported by `spacing.capacity_warning()` against the space itself. It is evaluated only at
each distinct start/end date in that space (the occupancy step function can only change
there), counting living plants of groups flowering on that day, and falls back to current
occupancy where no schedule applies.

There is no floor-area model. Square footage per plant used to be derived from the strain's
size class and the room's stage; it was wrong by 17x for 38 clones in 16oz cups and could
not be fixed, since a plant graduates between 16oz, 32oz and 1–3 gallon pots at any stage.
`Plant.container` records the pot as a fact about the plant and drives nothing.

**`implied_status(group)`** — what the calendar says: planned/vegetative if unscheduled,
vegetative before the flip, flowering inside the window, drying after. The group page
offers a one‑click fix when this differs from the stored status.

**`ascii_timeline(rows, width=64)`** — month header, tick row with `+` at month starts
and `*` at today, one `=` bar per row, days suffix. Pure ASCII by design.

**`markdown_export(groups)`** — bulleted groups (killed plants struck through), event
table, ASCII timeline in a code fence.

## Space planning (services/spacing.py)

**Location.** `plant_location(plant, spaces)`: `None` for harvested/killed; otherwise the
explicit `plant.space`, else the group's space for flowering plants, else the first space
whose stage matches the plant's status (`STAGE_FOR_STATUS`).

**Occupancy.** `occupancy(spaces, plants)` buckets living plants by location into
`Occupancy` objects with `count`, `load` (count ÷ the plants the space holds), `over` and
`room_for()`. No square footage: see the note above.

**Hosting.** `Space.stage` is what a space is mainly for and `Space.also_hosts` lists the
rest; `hosts` / `can_host()` read both. `move_plants()` leaves a plant's status alone when
the destination can already host that stage, so a flowering male parked on the clone shelf
stays flowering; otherwise the space's own stage wins.

**Load series.** `load_series(space, groups, ref)` evaluates the schedule at every flip
and harvest date in that space (plus today) and returns `{date, count, groups}`
points. `peak(series, since=today)` is what `capacity_warning()` uses; the chart shows the full
series with the space's area as the capacity line.

**Moves.** `move_plants(plants, space)` sets `plant.space` and `plant.status =
STATUS_FOR_STAGE[space.stage]`, skipping harvested/killed plants. The group route also
sets the group's space, status and flip date when the destination is a flowering space.

**Conflicts** (`scheduling.conflicts`) now take `plants` too: for each flowering space
the projected peak from today onward is compared to area (if known) and to the maximum;
each space's current occupancy is checked for overflow.

## Reports (services/reports.py)

`strain_stats()` walks plants per strain for grown/harvested/killed counts and a survival
rate over the plants that actually finished. `kill_reasons()` tallies why plants were lost.

`time_in_stage()` answers how long a strain really takes, from `plant_events` rather than
from the breeder's number. It reads `lifecycle.stage_spans()` per plant and keeps only
stretches that are measurements:

* **Open stretches are excluded.** A plant three weeks into flower says nothing yet about
  the strain, and averaging it in would drag every figure down.
* **The stretch a cull ended is dropped.** A male pulled on day 55 did not teach us the
  strain finishes in 55 days. That plant's earlier, completed stretches still count.
* **Zero-day stretches are dropped** — a status set and corrected the same day is a typo,
  not a stage.

`StrainTiming.drift` is the observed flower length minus the one on the strain record, so
a strain that consistently finishes early is visible at a glance. Note that runs predating
the event log derive their flip from the old group dates, so they tend to reproduce the
strain's own number and show a drift of zero; only runs logged through `lifecycle` are
independent evidence.

Charts are the `hbars` and `steps` macros in
`templates/_charts.html`: server-rendered SVG scaled by `viewBox`, coloured with the CSS
tokens, so they print and need no JavaScript.

## Front end

* **Dashboard layout** — `.dash` is one column on a phone, two past 1080px
  (`"main log" / "main rail"`) and three past 1600px (`"main log rail"`). `.main` has no
  `max-width`, so a wide monitor is used rather than letterboxed; the third column is what
  stops the left column dead-ending while the rail runs on. Note the `grid-area` names are
  declared *inside* those queries — hoisting them out drops all three children into one
  cell and overlaps them at phone width.
* **What the phone shows** — alerts, what is in flower, today's log. Everything else
  (`.m-hide`: timeline, Waiting for a slot, Spaces, Next 30 days, openings) is replaced by
  a `.m-links` row pointing at the full pages.
* **Where reminders live** — the ramp-down alert renders twice: as a chip in `.alert-strip`
  directly under the page title, and as a line on the flower card itself via
  `ramp_by_group`. A panel lower down the page went unread in practice, and the card is
  where a grower is already looking when deciding what to pour.
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
tests/test_spacing.py   location rules, occupancy counts, spaces that host several
                        stages, load series & peak, capacity labels, moves (service and
                        routes), planner page, quick log, task filter, last-done, reports,
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
