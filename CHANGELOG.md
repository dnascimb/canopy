# Changelog

## Unreleased

- **Half-water reminders as a run finishes.** The dashboard's Alerts panel now flags every
  run standing in a flowering space whose harvest is within two weeks — "Franco SLH
  finishes in 6 days — water at half the usual amount." It fires on the earliest living
  plant to finish rather than the last, so a run whose plants finish on different days is
  flagged when the first ones are close and the message says "first plants". Runs in veg
  or on the clone shelf are never flagged. A lone plant gets the same reminder as a group.
  The "schedule alerts" tile counts these alongside conflicts, though the amber warning
  styling still belongs to conflicts alone — this is a reminder, not something wrong.

- **Time in each stage.** A new Reports section showing how long each strain actually
  spends as a clone, seedling, in veg and in flower, averaged over finished runs, next to
  the flower length on its strain record and the drift between them. Built on the
  lifecycle log, so it measures what happened rather than quoting the breeder. Only
  finished stretches count; the stretch a cull ended and same-day corrections are left
  out. Runs that predate the event log inherit their dates from the old group columns and
  so agree with the strain by construction — the caveat is on the page.

- **Weights are gone entirely.** `harvests.wet_weight_g` follows the dry weight out; a
  harvest now records a date, a target and notes. The `grams` template filter went with
  it. Existing databases need `ALTER TABLE harvests DROP COLUMN wet_weight_g`.
- **Recording a harvest brings the plants down.** It marks everything it covers as
  harvested with an end date, writes each plant's lifecycle event, and moves the group to
  *drying* once nothing is left in flower. Harvesting a single plant leaves the rest
  flowering. Previously this only raised a "the calendar says it should be drying" note.

- **Photos on journal entries.** A **Photo** button on each space's daily log and a field on
  the full entry form. Files are stored under `instance/uploads` under a generated name —
  the browser's filename is never used as a path — and served through a route that cannot
  reach outside that folder. Deleting an entry deletes its photo; replacing one removes the
  old file. A photo on its own is a valid entry, titled "Photo". Existing databases need
  `ALTER TABLE journal_entries ADD COLUMN photo_path VARCHAR(255)`.
- The daily log now reports why a submission was rejected — "Images only, please." — rather
  than a generic nudge.

- **Take several cuttings at once.** A control on any living plant: how many, into which
  space, on what date. They are numbered from the mother (`Mango #7 c1`, `c2`, …),
  continuing where a previous batch left off, each linked back to her and each opening its
  own lifecycle log.
- New plants get a first lifecycle row — `lifecycle.born()` — so the "life so far" strip
  starts from the day a plant arrives rather than from its first move.

- Long notes are truncated to 200 characters in the plants table, with the whole note kept
  on hover, so one 659-character note no longer stretches a row.
- A new plant defaults to `seedling` rather than `vegetative`; **Take a cutting** still
  defaults to `clone`. Plants are usually added the day they start.

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
