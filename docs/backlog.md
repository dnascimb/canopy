# Backlog

Ideas that would make Canopy easier to use or the grow easier to understand, roughly in
order of value ÷ effort. Each has a one-line sketch of where it would live.

## Next up

1. **Veg-phase planning on the timeline.** Draw a second, dimmer bar before the flower bar
   so the veg tent's load is projected the same way the flower tent's is. The plant owns
   its schedule, so this is a veg-start event read off `plant_events` rather than a column
   on Group. (`services/lifecycle.py`, `scheduling.timeline_rows`, `timeline.js`.)
2. **Task reminders.** Per-group cadence for watering/feeding ("every 2 days") with an
   "overdue" list on the dashboard. Note the journal is deliberately inert — nothing reads
   entries back — so a reminder needs its own cadence field rather than inferring from
   logs. (`Group.water_every_days`, dashboard section.)
3. **Feed / EC readings.** Numeric fields on quick-log entries (in/out EC, ml of each
   nutrient) and a small line chart per group. (`JournalEntry` columns, `_charts.steps`.)
4. **Auth.** Optional single-user password (Flask-Login) for when the app leaves the LAN.

## Reporting & visualisation

5. **Room utilisation KPI**: average % of flower-tent area in use across the season, and
   "empty days" per slot — the number growers actually optimise for.
6. **Calendar heatmap of journal activity** (GitHub-style) to spot neglected weeks.
7. **Strain comparison card**: two strains side by side — days to finish, survival,
   lineage, notes.
8. **Harvest curing log**: jar dates, burp reminders, moisture readings, and a
   "ready" date on the dashboard.

## Planning

9. **What-if planner**: drag a bar on the timeline (or edit dates inline) and see load
    and conflicts update live before saving. (`PATCH /api/v1/groups/<id>` already exists.)
10. **Seed-run wizard**: pick strains and counts from inventory → creates the group and
    its plants, places them on the clone shelf, and shows the earliest flip date and
    whether they will fit in veg and flower.
11. **Multiple flower spaces with different photoperiods** (e.g. an auto tent): add
    `light_schedule` to Space; the suggestion engine prefers matching spaces.
12. **Perpetual-harvest optimiser**: given tent sizes and target harvest cadence, propose
    group sizes and flip dates that keep the flower tent near capacity.
13. **Container-driven footprints.** Floor space is set by the pot, not by the strain's
    size class. Add `Plant.container` (16oz cup, 32oz cup, 1/2/3/5/7 gal) with a sq ft
    each, falling back to the current strain-size guess when unset. Everything flows
    through one function, `spacing.plant_footprint()`, so occupancy, `load_series`,
    conflicts and the planner all correct themselves at once.
    *Worked example:* 38 EQ Haze clones flowered from 16oz cups occupy a 2x2 ft block —
    4 sq ft, about 0.105 sq ft each. The model assumes 1.75 sq ft each and reports 66.5
    sq ft, so it flags "needs 84.75 sq ft but has 50" on a plan that fits with room to
    spare. Wrong by 17x, and in the direction that trains you to ignore the alerts.
14. **Per-group area override.** `Group.sqft_override` for anything planted as a block,
    where no per-plant arithmetic will do: "these 38 take one 2x2, full stop." One
    nullable column, read by `spacing.group_footprint()`.
15. **Proactive fit warnings.** For every waiting group, the earliest date it actually
    fits given projected load — surfaced before you commit, not after. "Grp 23's 7 plants
    have nowhere to go until Sep 22." Worth building only on top of 13 and 14; on today's
    numbers it would just repeat false alarms more loudly. (`services/spacing.py`,
    dashboard "Waiting for a slot".)
16. **Vertical space.** Spaces have width and length but no height, so nothing expresses
    that hazes run tall and slim — lots of headroom, little floor. Add `Space.height_ft`
    and a height class on Strain, and flag a tall strain scheduled into a short tent.
    Note that flowering from clone deliberately suppresses stretch, so height needs to be
    a property of the run rather than of the strain alone.

## Quality of life

17. **Keyboard shortcuts**: `g d` dashboard, `g s` schedule, `n` new group, `/` search.
18. **Global search** across strains, plants, groups and journal text.
19. **iCalendar feed** of flips, harvests and reminders for phone calendars.
20. **CSV export** of strains, plants and harvests for spreadsheets.
21. **Dark/light toggle** (the token system already makes this a ~20-line change).
22. **Alembic migrations** so schema changes upgrade existing databases in place. Six
    have now been hand-written — dry weight, strain expression, journal spaces, moving the
    schedule onto the plant, cutting parentage and journal photos — each a one-off script with its own verification.

## Deliberately not doing

* **Seed-count automation.** `seeds_on_hand` is a note to the grower. Nothing reads it and
  nothing changes it automatically.
* **Deriving anything from the journal.** Entries are notes to refer back to, not data.
  No "last watered" counters, no inferred schedules.
* **Weights and yield reporting.** Neither dry nor wet weight is recorded, and the
  yield-per-strain, grams-per-plant and yield-per-group reports went with them. A harvest
  is a date, a target and notes.
