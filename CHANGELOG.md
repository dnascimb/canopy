# Changelog

## Unreleased

- **No half-water reminder for plants already cut.** `living_plants` counts harvested ones,
  so a run that was in a paper bag still asked to be watered. The reminder now looks only at
  plants still in flower.

- **Square footage is gone.** Spaces no longer have dimensions and plants no longer have a
  computed floor area. The old model guessed square feet from the strain's size class and
  the room's stage — wrong by 17x for 38 clones in 16oz cups, and unfixable, because a
  plant graduates between 16oz, 32oz and 1–3 gallon pots at any stage, for space or for
  health. A space is a location with a name, a stage and a plant cap; Canopy tracks counts,
  states and locations. `Space.width_ft`/`length_ft`, `area_sqft`, the footprint tables and
  `CANOPY_FOOTPRINT_*` are removed, along with the sq ft columns in the API and backups.
- **A space can double up.** `Space.also_hosts` lets one space serve several stages, so a
  clone shelf can also be pollen collection and veg overflow. Moving a plant somewhere that
  already suits it keeps its status instead of resetting it.
- **`Plant.container`** records the pot (16oz / 32oz / 1gal / 2gal / 3gal) as a plain fact,
  shown on the plant page and editable on its form.

  Existing databases need:
  `ALTER TABLE spaces ADD COLUMN also_hosts VARCHAR(60)`,
  `ALTER TABLE plants ADD COLUMN container VARCHAR(10)`,
  `ALTER TABLE spaces DROP COLUMN width_ft`, `ALTER TABLE spaces DROP COLUMN length_ft`.

- **A flip dated in the future no longer moves plants today.** `lifecycle.set_flip()` set
  `status=flowering` and the destination space immediately, whatever the date — so
  scheduling a group put its plants in the flower tent at once. Scheduling 38 unrooted EQ
  Haze clones for Sep 26 pushed the flower room to 74 plants against a capacity of 36 while
  the cuttings were still sitting in the tray. The event is still written, so the timeline
  and `flower_start` are unchanged; only the status and location wait for the day.

- **Timeline rows link to the right page.** A scheduled plant with no group appeared on the
  timeline like a group of one, but the row carried only an id and the renderer built
  `/groups/<id>` from it — so every lone plant 404'd. Rows now carry an explicit `href`.
- **Lone plants get their own colour** instead of all sharing one grey, for the same reason
  groups do: the timeline tells rows apart by colour.

- **Group colours are unique again.** `next_group_color()` indexed the palette by how many
  groups existed, modulo its 16 entries — so group 17 got group 1's colour, and deleting a
  group made the next one collide too. The real garden had 27 groups sharing 16 colours:
  10 collisions, including Super Blue Haze and Disruptor Beam sitting next to each other on
  the timeline in the same pink. It now takes the colours already in use and returns one
  nobody has, preferring the palette and falling back to golden-angle steps around the hue
  circle so it never runs out. Existing databases keep each colour's first claimant and
  reassign the duplicates.

- **Cutting one plant can take its group down.** Setting a plant to harvested by hand now
  moves its group to drying when nothing is left in flower, the same way recording a
  harvest does. Previously only the group-level harvest form did this, so cutting the last
  plant from the plant page left the group stuck on "flowering".
- The "group is drying once nothing is flowering" rule now lives in one place,
  `lifecycle.settle_group()`, shared by the harvest cascade and single-plant transitions.
  There is no separate `drying` plant status: at the plant level that state is
  `harvested`, and offering both would be two buttons for one thing.

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
