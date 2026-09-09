# Changelog

## Unreleased

- **A cutting can name the plant it came from.** `plants.parent_id` is a nullable
  self-reference, so a plant page shows *Taken from* with the line above it and *Cuttings*
  below. **Take a cutting** on any living plant opens the add form with the strain, status
  and mother already filled in. Existing databases need
  `ALTER TABLE plants ADD COLUMN parent_id INTEGER REFERENCES plants(id)`.
- The add-plant form takes a **lineage** for the strain, used when the strain is new or has
  none recorded. A lineage already on file is never overwritten from here.

- The plants table sorts on any column, defaulting to plant name A-Z. Status sorts by
  stage (clone through killed) rather than alphabetically, and group by number.

- **Strain is typed, not picked, when adding a plant.** A new pack of seeds or a cutting
  from outside is routinely a strain the inventory has never seen; typing an unknown name
  now adds it (seed type `clone` for a cutting, `regular` otherwise) instead of sending
  you off to create it first. Existing strains still suggest as you type, and matching
  ignores case.
- The add-plant form no longer shows *Ended on* or *End reason* — nothing has ended when
  you are adding it. Both remain when editing.

- **Help screen** at `/help`: every lifecycle transition and the control that performs it,
  written against the garden's own space names rather than generic placeholders.

- **The plant owns its schedule; a group is just a container.** `groups.flower_start` and
  `groups.flower_days` are gone. A plant's flip is read off the new `plant_events` log and
  its length from `flower_days_override` (falling back to the strain); a group reports the
  span of its plants. Moving one plant and moving a whole group are now literally the same
  call, and a plant with no group appears on the timeline and in events like a group of
  one. Existing databases need the events table, `plants.flower_days_override`, a
  synthesised flip event per scheduled plant, and the two group columns dropped.
- Backups gain a `plant_events` section; older backups without one are restored by
  rebuilding a flip event per plant from the group's old date, so they still load.
- Dropped the "scheduled but has no living plants" conflict — with dates derived from the
  plants, it describes a state that can no longer exist.

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
