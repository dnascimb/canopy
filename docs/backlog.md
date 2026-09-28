# Backlog

Ideas that would make Canopy easier to use or the grow easier to understand, roughly in
order of value ÷ effort. Each has a one-line sketch of where it would live.

## Next up

1. **Feed / EC readings.** Numeric fields on quick-log entries (in/out EC, ml of each
   nutrient) and a small line chart per group. (`JournalEntry` columns, `_charts.steps`.)
2. **Auth.** Optional single-user password (Flask-Login) for when the app leaves the LAN.

## Reporting & visualisation

3. **Calendar heatmap of journal activity** (GitHub-style) to spot neglected weeks.
4. **Strain comparison card**: two strains side by side — days to finish, survival,
   lineage, notes.
## Groups and spaces

5. **Seed-run wizard**: pick strains and counts from inventory → creates the group and
    its plants and places them on the clone shelf.
6. **Multiple flower spaces with different photoperiods** (e.g. an auto tent): add
    `light_schedule` to Space.
## Quality of life

7. **Keyboard shortcuts**: `g d` dashboard, `g s` schedule, `n` new group, `/` search.
8. **Global search** across strains, plants, groups and journal text.
9. **iCalendar feed** of flips and harvests for phone calendars.
10. **CSV export** of strains, plants and harvests for spreadsheets.
11. **Dark/light toggle** (the token system already makes this a ~20-line change).
12. **Alembic migrations** so schema changes upgrade existing databases in place. Six
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
