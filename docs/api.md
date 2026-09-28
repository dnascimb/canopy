# Canopy API reference (v1)

Base URL: `/api/v1`. All responses are JSON. No authentication — see the security notes
in the technical guide. Dates are ISO `YYYY-MM-DD`. The API honours `CANOPY_TODAY`.

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/health` | Liveness + effective "today". |
| GET | `/timeline` | Gantt payload: `today`, `start`, `end`, `rows[]`. |
| GET | `/events` | Every start/end of flower, sorted. |
| GET | `/groups` | All groups with plants and derived dates. |
| GET | `/groups/<id>` | One group. |
| PATCH | `/groups/<id>` | Update `flower_start`, `flower_days`, `status`, `space_id`, `name`, `notes`. |
| GET | `/spaces` | Spaces with current occupancy, load, and how many plants of each size fit / still fit. |
| GET | `/spaces/<id>/load` | Projected load of a flowering space at every flip/harvest date (plus today). |
| GET | `/strains` | Inventory (includes `size` and `expression`). |
| GET | `/plants` | All plants with `location`. |
| GET | `/export` | Full JSON backup (same as Schedule → Backup). |
| GET | `/export.md` | Markdown schedule (text/markdown). |

## Examples

```bash
curl -s localhost:5000/api/v1/health
# {"status":"ok","today":"2026-09-07"}

curl -s localhost:5000/api/v1/timeline | jq '.rows[] | {label, start, end, day_of_flower}'
# {"label":"Grp 7","start":"2026-07-28","end":"2026-11-17","day_of_flower":42} ...

# Push Grp 7's harvest a week earlier
curl -s -X PATCH localhost:5000/api/v1/groups/9 \
  -H 'Content-Type: application/json' \
  -d '{"flower_days": 105}' | jq '{label, flower_end}'
# {"label":"Grp 7","flower_end":"2026-11-10"}

# Record that a group went into flower today (a date after today is rejected with 400)
curl -s -X PATCH localhost:5000/api/v1/groups/17 \
  -H 'Content-Type: application/json' \
  -d '{"flower_start": "2026-09-07", "space_id": 1, "status": "flowering"}'

# How full is each tent right now?
curl -s localhost:5000/api/v1/spaces | jq '.[] | {name, stage, also_hosts, count, capacity, room_for}'

# Nightly backup
curl -s localhost:5000/api/v1/export > "canopy-$(date +%F).json"
```

## Schemas

### Timeline row

```json
{
  "id": 9, "number": 7, "label": "Grp 7",
  "start": "2026-07-28", "end": "2026-11-17", "days": 112,
  "color": "#ef5350", "status": "flowering", "space": "Flower Room",
  "strains": ["EQ Haze", "Durban Poison"], "plant_count": 2,
  "progress": 0.366, "day_of_flower": 42
}
```

### Group

```json
{
  "id": 9, "number": 7, "name": null, "label": "Grp 7",
  "space": "Flower Room", "space_id": 1,
  "flower_start": "2026-07-28", "flower_end": "2026-11-17", "flower_days": 112,
  "status": "flowering", "color": "#ef5350", "day_of_flower": 42,
  "plants": [
    {"id": 33, "label": "EQ Haze", "strain": "EQ Haze", "status": "flowering"},
    {"id": 34, "label": "Durban Poison", "strain": "Durban Poison", "status": "flowering"}
  ],
  "notes": null
}
```

### Event

```json
{"date": "2026-09-22", "kind": "end", "group_id": 8, "label": "Grp 6 end flower (70 days)"}
```

### Space (`/spaces`)

```json
{
  "id": 3, "name": "Flower Room", "stage": "flowering",
  "also_hosts": [], "capacity": 36,
  "plants": 10, "used_sqft": 25.5, "load": 0.51,
  "fits": {"small": 33, "medium": 22, "large": 16},
  "room_for": {"small": 16, "medium": 10, "large": 8}
}
```

### Load point (`/spaces/<id>/load`)

```json
{"date": "2026-09-07", "count": 10, "sqft": 25.5, "groups": ["Grp 6", "Grp 7", "Grp 8", "Grp 9", "Grp 10", "Grp 11"]}
```

### Backup (`/export`)

```json
{
  "schema": 1,
  "spaces": [...], "strains": [...], "groups": [...],
  "plants": [...], "harvests": [...], "journal_entries": [...]
}
```

IDs in a backup are re‑mapped on restore, so files can be merged into a database that
already has data (untick *Replace* in the UI).

## Errors

* `404` — unknown id.
* `400` — a `flower_start` after today returns `{"error": "A flip date can't be in the future — record it on the day it goes into flower."}`. An invalid enum value or malformed date in a PATCH body also gives 400, but Flask returns the default error page; wrap calls accordingly.
