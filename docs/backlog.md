# Backlog

Ideas that would make Canopy easier to use or the grow easier to understand, roughly in
order of value ÷ effort. Each has a one-line sketch of where it would live.

## Next up

1. **Veg-phase planning on the timeline.** Draw a second, dimmer bar before the flower bar
   so the veg tent's load is projected the same way the flower tent's is. The plant owns
   its schedule, so this is a veg-start event read off `plant_events` rather than a column
   on Group. (`services/lifecycle.py`, `scheduling.timeline_rows`, `timeline.js`.)
2. **Feed / EC readings.** Numeric fields on quick-log entries (in/out EC, ml of each
   nutrient) and a small line chart per group. (`JournalEntry` columns, `_charts.steps`.)
3. **Auth.** Optional single-user password (Flask-Login) for when the app leaves the LAN.

## Reporting & visualisation

4. **Calendar heatmap of journal activity** (GitHub-style) to spot neglected weeks.
5. **Strain comparison card**: two strains side by side — days to finish, survival,
   lineage, notes.
## Planning

6. **What-if planner**: drag a bar on the timeline (or edit dates inline) and see load
    and conflicts update live before saving. (`PATCH /api/v1/groups/<id>` already exists.)
7. **Seed-run wizard**: pick strains and counts from inventory → creates the group and
    its plants, places them on the clone shelf, and shows the earliest flip date and
    whether they will fit in veg and flower.
8. **Multiple flower spaces with different photoperiods** (e.g. an auto tent): add
    `light_schedule` to Space; the suggestion engine prefers matching spaces.
9. **Perpetual-harvest optimiser**: given tent sizes and target harvest cadence, propose
    group sizes and flip dates that keep the flower tent near capacity.
## Quality of life

10. **Keyboard shortcuts**: `g d` dashboard, `g s` schedule, `n` new group, `/` search.
11. **Global search** across strains, plants, groups and journal text.
12. **iCalendar feed** of flips, harvests and reminders for phone calendars.
13. **CSV export** of strains, plants and harvests for spreadsheets.
14. **Dark/light toggle** (the token system already makes this a ~20-line change).
15. **Alembic migrations** so schema changes upgrade existing databases in place. Six
    have now been hand-written — dry weight, strain expression, journal spaces, moving the
    schedule onto the plant, cutting parentage and journal photos — each a one-off script with its own verification.

## Deliberately not doing

* **Seed-count automation.** `seeds_on_hand` is a note to the grower. Nothing reads it and
  nothing changes it automatically.
* **Deriving anything from the journal.** Entries are notes to refer back to, not data.
  No "last watered" counters, no inferred schedules.
* **Floor area.** Spaces have no dimensions and plants have no square footage. Pot sizes
  are recorded on the plant but drive nothing: how many fit in a space is the grower's
  number, not a calculation. This retires the container-footprint, per-group area,
  proactive-fit and vertical-space items, which all existed to make an area model less
  wrong.
* **A harvest curing log.** Jar dates, burping and moisture readings are not tracked.
* **Making duplicate plant labels unique.** Two living plants can share a label and that is
  correct: a cutting carries its mother's name, which is how the line shows up in the tent.
  Plants are identified by id, not by label.
* **Weights and yield reporting.** Neither dry nor wet weight is recorded, and the
  yield-per-strain, grams-per-plant and yield-per-group reports went with them. A harvest
  is a date, a target and notes.
