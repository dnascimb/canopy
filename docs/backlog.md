# Backlog

Ideas that would make Canopy easier to use or the grow easier to understand, roughly in
order of value ÷ effort. Each has a one-line sketch of where it would live.

## Next up

1. **Veg-phase planning on the timeline.** Add `veg_start` to Group and draw a second,
   dimmer bar before the flower bar so the veg tent's load is projected the same way the
   flower tent's is. (`models.Group`, `scheduling.timeline_rows`, `timeline.js`.)
2. **Task reminders.** Per-group cadence for watering/feeding ("every 2 days") with an
   "overdue" list on the dashboard derived from the journal. (`Group.water_every_days`,
   dashboard section.)
3. **Feed / EC / pH readings.** Numeric fields on quick-log entries (in/out pH, EC, ml of
   each nutrient) and a small line chart per group. (`JournalEntry` columns, `_charts.steps`.)
4. **Photos.** Attach an image to a journal entry; thumbnail strip on the group page.
   (Upload to `instance/uploads`, `JournalEntry.photo_path`.)
5. **Auth.** Optional single-user password (Flask-Login) for when the app leaves the LAN.

## Reporting & visualisation

6. **Yield vs. flower days scatter** per strain — did longer runs pay off?
7. **Room utilisation KPI**: average % of flower-tent area in use across the season, and
   "empty days" per slot — the number growers actually optimise for.
8. **Calendar heatmap of journal activity** (GitHub-style) to spot neglected weeks.
9. **Strain comparison card**: two strains side by side (yield, days, survival, notes).
10. **Harvest curing log**: jar dates, burp reminders, moisture readings, and a
    "ready" date on the dashboard.

## Planning

11. **What-if planner**: drag a bar on the timeline (or edit dates inline) and see load
    and conflicts update live before saving. (`PATCH /api/v1/groups/<id>` already exists.)
12. **Seed-run wizard**: pick strains and counts from inventory → creates the group,
    plants, decrements seeds, places them on the clone shelf, and shows the earliest
    flip date and whether they will fit in veg and flower.
13. **Multiple flower spaces with different photoperiods** (e.g. an auto tent): add
    `light_schedule` to Space; the suggestion engine prefers matching spaces.
14. **Perpetual-harvest optimiser**: given tent sizes and target harvest cadence, propose
    group sizes and flip dates that keep the flower tent near capacity.

## Quality of life

15. **Keyboard shortcuts**: `g d` dashboard, `g s` schedule, `n` new group, `/` search.
16. **Global search** across strains, plants, groups and journal text.
17. **iCalendar feed** of flips, harvests and reminders for phone calendars.
18. **CSV export** of strains, plants and harvests for spreadsheets.
19. **Dark/light toggle** (the token system already makes this a ~20-line change).
20. **Alembic migrations** so schema changes upgrade existing databases in place.
