# Changelog

## Unreleased

- Quick-log tasks: dropped "Checked pH / EC", renamed "IPM / pest check" to
  "Pest/Mold treatment". Existing entries keep the `ipm` key and pick up the new label;
  `ph_ec` was stripped from the seeded entries that used it.

- **Journal entries can be logged against a space.** The dashboard's quick log is now one
  section per space, so a whole tent can be logged in a pass, and the journal filters by
  space. `journal_entries.space_id` is new; existing databases need
  `ALTER TABLE journal_entries ADD COLUMN space_id INTEGER REFERENCES spaces(id)`.
  The group and plant pickers are gone from the entry forms — the group page still
  attaches to its own group by context. Nothing is mandatory beyond the entry saying
  something, and a title-less note is titled "Note".
- **Dropped "last watered / fed" from group pages.** The journal is for notes, not
  tracking; nothing derives meaning from entries any more.

- **Space capacity is no longer an alert.** It moved off the dashboard and schedule lists
  onto the spaces page, as a red **over capacity** label on the room in breach with the
  reason beside it. It is an estimate from footprints and dimensions and cannot be
  dismissed, so it no longer follows you around; `conflicts()` reports only genuinely
  broken schedules. The card's red state now reflects the projected peak, not just today.
- **Removed dry weight.** `harvests.dry_weight_g` is gone, along with the dry-yield and
  grams-per-plant reports and the yield-per-group table. Harvests still record a wet
  weight, a date and notes. Existing databases need
  `ALTER TABLE harvests DROP COLUMN dry_weight_g`; 1.0/1.1 backups still restore, the
  field is simply ignored.
- Strains carry an **expression** (sativa / haze / indica / hybrid), nullable because
  plenty of strains have no stated type. Existing databases need
  `ALTER TABLE strains ADD COLUMN expression VARCHAR(10)`.
- The inventory filters on seed type, expression, breeder and flower-length bucket, all
  stacking, and every column sorts. Default order is strain name A-Z.
- The schedule's event table sorts on any column and shades future milestones.
- Timeline bars and dashboard cards collapse repeated strains to "Name xN".
- Configuration is read from `.env` via python-dotenv, covering gunicorn as well as the CLI.

## 1.1.0 — 2026-09-07

**Spaces & planner**
- Spaces have a stage (clone / vegetative / flowering), dimensions and a user-set maximum.
- Strains carry a size class (small / medium / large). Per-plant footprints by stage × size
  drive fit estimates; defaults are tunable with `CANOPY_FOOTPRINT_*`.
- Plants have a location (explicit or inferred from status / group). Bulk "move to" on a
  group and single "move to" on a plant, which also aligns status with the destination.
- Spaces page is now a planner: occupancy per space, room for N more of each size, season
  load chart for flower spaces, a "coming up" table of what each waiting group needs, and
  the spacing rules in effect.
- Capacity conflicts use area when dimensions are known, only from today forward; a
  warning is raised when any space is over capacity today.
- New `clone` plant status; demo season includes a clone shelf, veg tent and 5×10 flower tent.

**Journal**
- Quick log with task checkboxes on the dashboard and every group page; title is derived
  from ticked tasks when left blank. Task chips on entries; filter by task.
- "Last watered / fed / …" summary on each group.

**Reports** (new page)
- Dry yield and grams-per-plant per strain, survival per strain, kill reasons, yield per
  group, flower-space load over the season. Server-rendered SVG, prints cleanly.

**API**
- `GET /api/v1/spaces`, `GET /api/v1/spaces/<id>/load`; plants include `location`;
  strains include `size`; conflicts include occupancy warnings.

**Backup schema** stays at version 1 with additive fields (`stage`, `width_ft`,
`length_ft`, `size`, `space_id`, `tasks`); 1.0 backups restore unchanged.

## 1.0.0 — 2026-09-07
Initial release: inventory, groups, plants, schedule with Gantt, openings and conflicts,
harvests, journal, Markdown/ASCII/JSON exports, print view, API, tests, docs.
