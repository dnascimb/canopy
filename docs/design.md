# Canopy design notes

## Intent

Canopy is a tool a grower opens for thirty seconds between tasks: *what's in flower, what
comes down next, where can the next batch go.* The design therefore optimises for
scanning, not browsing. The one memorable element is the flowering timeline; everything
else is quiet tables and short lists that support it.

## Visual system

| Token | Value | Use |
| --- | --- | --- |
| `--bg` | `#1b1917` | Page. A warm charcoal rather than tinted black — reads like a dark room, not a terminal. |
| `--surface` / `--surface-2` | `#23201d` / `#2c2824` | Panels, hovered rows, inputs. |
| `--line` / `--line-strong` | `#3a352f` / `#4a443c` | Borders. |
| `--text` / `--text-soft` / `--muted` | `#ece6dc` / `#c9c1b5` / `#968c7f` | Three levels of emphasis, all warm. |
| `--accent` | `#f0a83a` | Grow‑light amber. Primary buttons, active nav, harvest events, openings, callouts. |
| `--green` | `#7cb342` | Flowering / living / start events. |
| `--red` | `#e0574b` | Killed, capacity errors, destructive buttons, the today line. |
| `--blue` | `#5aa9e6` | Vegetative. |

Group colours come from a 16‑step palette (`GROUP_PALETTE` in `models.py`) chosen to stay
legible with dark text on the timeline; each new group gets the next colour and can be
overridden per group.

**Type.** One sans family for reading (IBM Plex Sans if installed, otherwise the system
face) and one monospace family (IBM Plex Mono / SF Mono / Menlo) reserved for dates,
counts and the timeline, where tabular alignment matters. Headings are semibold with
slightly tight tracking; there are no all‑caps labels.

**Shape.** 6px radius on controls, 10px on panels. Borders carry structure; shadows are
used only on the floating tooltip.

**Motion.** None on load. Hover on timeline bars brightens them slightly; everything else
responds only to the user's action. `prefers-reduced-motion` disables transitions.

## Layout

```
┌──────────┬────────────────────────────────────────────────┐
│ brand    │ page title                          actions     │
│ nav      │ stat · stat · stat · stat · stat · stat         │
│          │ ┌──────────────── timeline ──────────────────┐  │
│          │ └────────────────────────────────────────────┘  │
│          │ ┌── main (2fr) ──────────┐ ┌── side (1fr) ───┐  │
│ today    │ │ cards / tables         │ │ lists / alerts  │  │
│ version  │ └────────────────────────┘ └─────────────────┘  │
└──────────┴────────────────────────────────────────────────┘
```

Left‑aligned throughout. A fixed 224px sidebar carries navigation and today's date; the
main column caps at 1280px so tables stay readable. Detail pages use the same 2:1 split:
the thing you act on (plants, events) on the left, reference and secondary forms on the
right. Below 860px the sidebar becomes a top bar with icons only and grids stack.

## UX principles

* **Enter facts, not conclusions.** Users type a flip date and a flower length; harvest
  dates, day counts, openings, conflicts and suggested slots are computed. Nothing that
  can be derived is stored or asked for.
* **Nothing is lost.** Killed plants remain with their reason; deleting a group keeps
  its plants; strains with history can't be deleted; every state change is a POST behind
  CSRF and, when destructive, a confirm.
* **One click for the common move.** "Schedule" on a waiting group, "Kill" on a plant row,
  status buttons on the group, "plan a group" on an opening — each pre‑fills the form.
* **Tell the user what the calendar thinks.** The status‑mismatch banner and the alerts
  panel surface disagreements instead of silently fixing them.
* **Copy is instruction.** Buttons say what happens ("Save harvest", "Mark killed"); flash
  messages repeat the same verb; empty states say what to do next; errors say what to fix.
* **Works where the notes live.** The Markdown/ASCII export mirrors the format growers
  already keep in Joplin/Obsidian; the print view is plain black‑on‑white.
* **Keyboard and screen readers.** Visible focus rings, `aria-label`s on icon‑only
  controls, native form controls, tables with real headers.

## Screens and their single job

| Screen | Job |
| --- | --- |
| Dashboard | "What's happening and what do I do next?" |
| Schedule | "Show me every date, and let me take it with me." |
| Groups / group | "Manage one batch from seed to jar." |
| Plants / plant | "Track and retire one plant." |
| Inventory / strain | "What do I have, and how has it performed?" |
| Spaces | "How full is each room and when does it open?" |
| Journal | "What did I notice, when?" — and, via the quick log, "what did I do today?" in ten seconds. |
| Spaces & planner | "Where is everything, how full is each tent, and what fits next?" |
| Reports | "What should I grow again?" |

## v1.1 additions

* **Chip checkboxes** for the quick log: pill-shaped labels that fill amber when
  checked, so a day's tasks read as tags rather than a form.
* **Charts are SVG rendered by Jinja** with the same tokens as the rest of the UI —
  amber bars, muted labels, a dashed red capacity line, a solid red today line. They
  scale with their panel and survive print.
* **Space cards** reuse the in-flower card shape; the left border colour encodes stage
  (amber clone, blue veg, green flower) and turns red when over capacity.
