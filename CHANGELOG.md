# Changelog

## Unreleased

- **No reminders either.** The ramp-down watering reminders ("plain water only, half the
  usual amount") are gone from the dashboard strip and the flower cards, with
  `scheduling.ramp_down()` and the "ramping down" tile. The dashboard carries no alerts.
- **No capacity label, no "planned" status, no dashboard log.** The Spaces page's red
  "over capacity" label and reason line, and the red bars on the Spaces page and dashboard,
  are gone with `spacing.capacity_warning()`; spaces still show "N of M plants". Groups are
  vegetative, flowering, drying or done — `planned` is retired, existing planned groups were
  moved to vegetative, and older backups restore that way. The dashboard's "Log today"
  section is removed; entries are made from the Journal page and the group page.
- **No alerts, no planned flips.** The conflict checks ("Grp X is scheduled but not
  assigned to a space", "marked flowering but has no start date") are gone with
  `scheduling.conflicts()`, `GET /api/v1/conflicts`, the schedule page's Alerts panel and
  the dashboard's alert chips; the dashboard strip keeps only the ramp-down watering
  reminders. A flip date can no longer be after today — the group form refuses it, the
  API answers 400, and `lifecycle.set_flip()` raises — because a flip is recorded when it
  happens.
- **The scheduler is gone.** Canopy records what the grower did, when they did it; it no
  longer recommends a schedule. Removed: openings (`scheduling.openings()`), flip
  suggestions (`suggest_start()`), the "Schedule" / "Schedule for …" buttons and their
  `POST /groups/<id>/schedule` route, `GET /api/v1/openings`, the dashboard's "Waiting for
  a slot" and "Upcoming openings" panels, the schedule page's Openings and Unscheduled
  lists, the group page's "Earliest opening" banner, and the Spaces page's "Coming up"
  planner (the page is now just "Spaces").
- **What happens to the plant rules the calendar.** A plant's run used to end at flip +
  flower days no matter what: the Super Blue Haze, harvested on day 48 of 77, kept its
  timeline bar to Oct 27, stayed counted in the tent, and its group warned "the calendar
  says this group should be flowering, but it is marked drying". A run now ends the day the
  plant is recorded leaving flower (harvest, cull, back to veg), and a plant still flowering
  past its projection reads as flowering today rather than dropping off the dashboard. The
  group page's "should be X, but it is marked Y" warning is gone: the app follows what
  was done rather than asking the grower to correct it, and so is the "Earliest opening"
  banner on an unscheduled group's page (the dashboard and Spaces page still list it
  under Waiting for a slot). Two related fixes: moving a flowering
  plant (flowering -> flowering) no longer counts as a new flip, and a same-day veg-then-flip
  no longer reads as the run ending the day it started.
- **Inventory filters as you type.** Search and every filter apply on each change, with no
  Filter button and no page reload. The page ships the whole inventory and
  `static/js/inventory.js` hides rows in place — about 1–24 ms per keystroke across 700
  strains — while `services/inventory.py` applies the same rules to the first render, so
  a reload, a shared link or a browser without JavaScript shows the same rows. The URL
  follows the controls. Search now matches every word rather than the whole phrase, and a
  typed `%` or `_` is literal. The plant counts came from loading each strain's plants
  one query at a time (705 queries); one grouped count now does it, taking the page from
  ~120 ms to ~50 ms.
- **Full cycle toggle on the timeline.** One button. Off is the chart as it was; on adds
  the pre-flower span to each bar and brings in groups that have not flipped yet. The
  span runs from the first lifecycle event that is not the flip, falling back to
  `started_on`, so it means "alive, not yet flowering" rather than strictly vegetative —
  only 2 of 34 scheduled units have a `vegetative` event to read. Server-side bounds still
  come from flower spans only, so the default is unchanged.
- **Check a space against what is in it.** `/spaces/<id>/check` lists what Canopy thinks is
  in a space, in walking order, with a tick per plant. Unticked plants get a dated note and
  a journal entry; nothing is killed, moved or re-dated.

- **A culled plant loses its flower card.** `Plant.is_flowering_on` is pure date
  arithmetic, so the Goji OG #8 pollen male — cut on the clone shelf with 17 days left on
  his estimated run — still read as in flower the next day. A group never had this problem
  because its span is read off `living_plants`; `LonePlant` now makes the same check.

- **A culled plant leaves the timeline.** The fix above took the card away but left the
  bar: `scheduled_units()` wrapped any groupless plant with a flip date, killed or not, so
  Goji OG #8 stayed on the timeline as flowering. Killed plants are now left out, as
  `Group.scheduled_plants` leaves them out of a group's span.

- **A plant on its own gets a flower card.** "In flower now" was built from groups alone,
  so seven plants flowering in the tent — Sour Diesel, Jack Herer, Green Crack Sr., London
  Pound Cake 2, SSDD 2B, GSC and Goji OG #8 — appeared on the timeline but had no card,
  which is the one part of the dashboard anyone reads. The cards now come from
  `scheduled_units()` like everything else, link through a new `href` that a group and a
  LonePlant both answer, and the ramp-down lookup is keyed by `number` rather than `id`,
  because a group id and a plant id can collide and `LonePlant.number` is offset past the
  real group numbers precisely so it cannot. The strip now counts runs, not groups.

- **A finished group no longer asks for a slot.** Culling the last plant in a group leaves
  it with no `flower_start`, which is the same shape as a group that has never run, so the
  dashboard and the schedule page both listed it under "Waiting for a slot" — Grp 35 turned
  up there with nothing in it. `Group.waiting_for_a_slot` now says what was meant: no flower
  date yet, and at least one plant that is neither killed nor harvested.

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
