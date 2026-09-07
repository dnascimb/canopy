"""Demo dataset: a realistic 2026 season used by `flask seed-demo`, tests and screenshots."""

from __future__ import annotations

from datetime import date, timedelta

from ..extensions import db
from ..models import (
    Group,
    GroupStatus,
    Harvest,
    JournalEntry,
    Plant,
    PlantSize,
    PlantStatus,
    SeedType,
    Space,
    SpaceStage,
    Strain,
    next_group_color,
)

D = date

STRAINS = [
    # name, breeder, lineage, seed_type, flower_days, seeds_on_hand
    ("Goji 3x", None, "Goji OG line", "regular", 63, 4),
    ("Swazipulco F2", None, "Swazi x Acapulco Gold", "regular", 70, 6),
    ("Lemon Lime Haze", None, None, "regular", 70, 0),
    ("Gorilla Snacks", None, "Gorilla Glue x Scooby Snacks", "regular", 70, 3),
    ("Chili Verde", None, None, "regular", 70, 2),
    ("GSC", None, "OG Kush x Durban Poison", "feminized", 70, 5),
    ("Jack Herer", None, "Haze x (NL#5 x Shiva Skunk)", "regular", 70, 8),
    ("Sour Diesel", None, "Chemdawg 91 x Super Skunk", "regular", 70, 4),
    ("London Pound Cake", None, "Sunset Sherbet x unknown", "feminized", 63, 2),
    ("Green Crack", None, "Skunk #1 x Afghani", "regular", 63, 3),
    ("Pacific Nepalese", None, "Nepalese landrace", "regular", 70, 10),
    ("SSDD", None, "Sensi Star x Blue Dream", "regular", 70, 7),
    ("Zap", None, None, "regular", 70, 1),
    ("Boost Bx", None, "Boost backcross", "regular", 70, 9),
    ("Blazing Sword", None, None, "regular", 70, 5),
    ("Superboof", None, "Black Cherry Punch x Tropicana Cookies", "feminized", 63, 4),
    ("PNG-Siamese", None, "Papua New Guinea x Thai", "regular", 70, 6),
    ("Franco SLH", None, "Super Lemon Haze (Franco's cut)", "clone", 70, 0),
    ("Mango Hashplant", None, "Mango x Hashplant", "regular", 63, 6),
    ("Cultivators Choice O.P", None, "[[Haze/Sk1] x Sk1] x [Haze x Sk1]", "regular", 70, 12),
    ("EQ Haze", "Equilibrium", "Haze", "regular", 112, 8),
    ("Durban Poison", None, "South African landrace", "regular", 63, 10),
    ("4-way Koosh", "Equilibrium", None, "regular", 70, 6),
    ("Mango Queen", "Equilibrium", None, "regular", 70, 6),
    ("Super Blue Haze", "Equilibrium", "Super Silver Haze x Blueberry", "regular", 77, 6),
    ("Malawi x SSH F2", None, "Malawi Gold x Super Silver Haze", "regular", 84, 9),
    ("Crockett's Haze", None, "Crockett's Family Farms Haze", "regular", 77, 5),
    ("Last Call", None, "95 White Widow x Coca Cola / Rootbeer BC2", "regular", 70, 12),
    ("Original Recipe", None, "Original Haze x Coca Cola / Rootbeer BC2", "regular", 70, 12),
    (
        "Lebanese Honey",
        "Equilibrium",
        "Red Lebanese x (PNW HashPlant x Northern Lights #1)",
        "regular",
        56,
        11,
    ),
]

# number, name, space, flower_start, flower_days, plants[(label, strain, killed_reason|None, note|None)]
GROUPS = [
    (15, "Goji 3x", "Flower Room", D(2026, 5, 12), 63, [("Goji 3x", "Goji 3x", None, None)]),
    (
        1,
        None,
        "Flower Room",
        D(2026, 5, 26),
        70,
        [
            ("Swazipulco F2", "Swazipulco F2", None, None),
            ("Lemon Lime Haze 1", "Lemon Lime Haze", "Sickly leaves, never recovered", None),
            ("Gorilla Snacks I", "Gorilla Snacks", None, None),
        ],
    ),
    (
        2,
        None,
        "Flower Room",
        D(2026, 5, 31),
        70,
        [
            ("L. Lime 2", "Lemon Lime Haze", "Culled — weak growth", None),
            ("Gorilla Snacks 2", "Gorilla Snacks", None, None),
            ("Gorilla Snacks 3", "Gorilla Snacks", None, None),
        ],
    ),
    (
        3,
        None,
        "Flower Room",
        D(2026, 6, 9),
        70,
        [
            ("Lemon Lime 3", "Lemon Lime Haze", "Culled", None),
            ("Lemon Lime 4", "Lemon Lime Haze", "Culled", None),
            ("Lemon Lime 5", "Lemon Lime Haze", "Culled", None),
            ("Chili Verde", "Chili Verde", None, None),
            ("GSC", "GSC", None, None),
            ("Jack Herer", "Jack Herer", None, None),
            ("Sour Diesel", "Sour Diesel", None, None),
            ("London Pound Cake", "London Pound Cake", None, None),
            ("Green Crack", "Green Crack", None, None),
        ],
    ),
    (
        4,
        None,
        "Flower Room",
        D(2026, 6, 14),
        70,
        [
            (
                "Pacific Nepalese II",
                "Pacific Nepalese",
                None,
                "Short one and a tall one growing out of the same pot",
            ),
            ("Pacific Nepalese I", "Pacific Nepalese", None, None),
            ("SSDD I", "SSDD", None, None),
            ("SSDD II", "SSDD", None, None),
            ("Zap 3", "Zap", "Hermaphrodite", None),
            ("Boost Bx I", "Boost Bx", None, None),
            ("Boost Bx 2", "Boost Bx", None, None),
            ("Boost Bx 3", "Boost Bx", None, None),
        ],
    ),
    (
        5,
        None,
        "Flower Room",
        D(2026, 6, 21),
        70,
        [
            ("Blazing Sword (all)", "Blazing Sword", None, None),
            ("SSDD III", "SSDD", None, None),
            ("Superboof I", "Superboof", None, None),
            ("Superboof II", "Superboof", None, None),
        ],
    ),
    (
        16,
        "PNG-Siamese",
        "Flower Room",
        D(2026, 6, 22),
        70,
        [("PNG-Siamese", "PNG-Siamese", None, None)],
    ),
    (
        6,
        None,
        "Flower Room",
        D(2026, 7, 14),
        70,
        [
            ("Franco SLH", "Franco SLH", None, None),
            ("Mango Hashplant", "Mango Hashplant", None, None),
            ("Cultivators Choice O.P", "Cultivators Choice O.P", None, None),
        ],
    ),
    (
        7,
        None,
        "Flower Room",
        D(2026, 7, 28),
        112,
        [
            ("EQ Haze", "EQ Haze", None, "16-week flower — started from seed"),
            ("Durban Poison", "Durban Poison", None, None),
        ],
    ),
    (
        8,
        None,
        "Flower Room",
        D(2026, 8, 2),
        70,
        [("4-way Koosh", "4-way Koosh", None, None), ("Mango Queen", "Mango Queen", None, None)],
    ),
    (
        9,
        None,
        "Flower Room",
        D(2026, 8, 11),
        70,
        [("Super Blue Haze", "Super Blue Haze", None, None)],
    ),
    (
        10,
        None,
        "Flower Room",
        D(2026, 8, 16),
        70,
        [("Malawi x SSH F2", "Malawi x SSH F2", None, None)],
    ),
    (
        11,
        None,
        "Flower Room",
        D(2026, 8, 24),
        70,
        [("Crockett's Haze", "Crockett's Haze", None, None)],
    ),
    (
        12,
        None,
        "Flower Room",
        D(2026, 9, 22),
        70,
        [("Last Call", "Last Call", None, "Reg — 12 seeds")],
    ),
    (
        13,
        None,
        "Flower Room",
        D(2026, 10, 11),
        70,
        [("Original Recipe", "Original Recipe", None, "Reg — 12 seeds")],
    ),
    (
        14,
        None,
        "Flower Room",
        D(2026, 10, 20),
        56,
        [("Lebanese Honey", "Lebanese Honey", None, None)],
    ),
    # An unscheduled group so the "next opening" suggestion has something to work on.
    (17, "Next up", None, None, 70, [("Jack Herer 2", "Jack Herer", None, None)]),
]

HARVESTS = [
    # group number, plant label|None, date, wet, dry, notes
    (15, None, D(2026, 7, 7), 412.0, 96.5, "Frosty, dense. Early amber at day 60."),
    (1, "Swazipulco F2", D(2026, 7, 28), 380.0, 88.0, "Sativa stretch, airy tops"),
    (1, "Gorilla Snacks I", D(2026, 7, 28), 455.0, 110.0, None),
    (2, None, D(2026, 8, 2), 700.0, 165.0, "Both Gorilla Snacks combined"),
    (3, None, D(2026, 8, 11), 1620.0, 381.0, "Six plants; London Pound Cake was the standout"),
    (4, None, D(2026, 8, 16), 2100.0, 495.0, None),
    (5, None, D(2026, 8, 23), 1280.0, 302.0, None),
    (16, None, D(2026, 8, 24), 330.0, 74.0, "Very long, foxtailed colas"),
]

JOURNAL = [
    # date, group, plant, title, body, tasks
    (
        D(2026, 6, 2),
        1,
        "Lemon Lime Haze 1",
        "Culled",
        "Pale, twisted new growth. Pulled to free space.",
        "",
    ),
    (
        D(2026, 7, 5),
        4,
        "Zap 3",
        "Hermie spotted",
        "Bananas on lower nodes — removed immediately.",
        "ipm",
    ),
    (
        D(2026, 7, 28),
        7,
        None,
        "Flipped Grp 7",
        "EQ Haze and Durban into the room. Expect 16 weeks on the haze.",
        "transplanted,watered",
    ),
    (
        D(2026, 8, 30),
        6,
        None,
        "Week 7 check",
        "Franco SLH stacking well. Mango HP smells like ripe mango.",
        "watered,fed,ph_ec",
    ),
    (D(2026, 9, 3), 8, None, "Watered, fed", None, "watered,fed"),
    (D(2026, 9, 3), 9, None, "Watered", "Plain water, runoff 6.3", "watered,ph_ec"),
    (
        D(2026, 9, 5),
        8,
        None,
        "Defoliation",
        "Light defol on Koosh; Mango Queen left alone.",
        "defoliated,watered",
    ),
    (D(2026, 9, 6), 7, None, "Watered, fed", None, "watered,fed"),
    (
        D(2026, 9, 6),
        12,
        None,
        "Topped Last Call",
        "Topped above the 5th node; will flip in two weeks.",
        "trained,watered",
    ),
    (D(2026, 9, 7), 17, None, "Took clones", "6 cuts of Jack Herer 2 into the dome.", "cloned"),
]


def _size_for(name: str, flower_days: int) -> PlantSize:
    n = name.lower()
    if flower_days >= 77 or "haze" in n or "malawi" in n or "png" in n or "nepalese" in n:
        return PlantSize.large
    if any(k in n for k in ("pound cake", "gsc", "superboof", "goji")):
        return PlantSize.small
    return PlantSize.medium


def seed_demo() -> None:
    """Populate an empty database with the demo season. Idempotent: skips if data exists."""
    if db.session.query(Strain).count():
        return

    spaces = {
        "Clone Shelf": Space(
            name="Clone Shelf",
            stage=SpaceStage.clone,
            width_ft=4,
            length_ft=1.5,
            capacity=40,
            notes="Wire shelf with two 1020 trays under a T5",
        ),
        "Veg Tent": Space(
            name="Veg Tent",
            stage=SpaceStage.vegetative,
            width_ft=2,
            length_ft=4,
            capacity=12,
            notes="2 × 4, 18/6 under LED",
        ),
        "Flower Room": Space(
            name="Flower Room",
            stage=SpaceStage.flowering,
            width_ft=5,
            length_ft=10,
            capacity=36,
            notes="5 × 10 tent, 12/12",
        ),
    }
    db.session.add_all(spaces.values())

    strains: dict[str, Strain] = {}
    for name, breeder, lineage, st, fd, seeds in STRAINS:
        s = Strain(
            name=name,
            breeder=breeder,
            lineage=lineage,
            seed_type=SeedType(st),
            flower_days=fd,
            seeds_on_hand=seeds,
            size=_size_for(name, fd),
        )
        strains[name] = s
        db.session.add(s)

    ref = date(2026, 9, 7)
    groups: dict[int, Group] = {}
    plants: dict[tuple[int, str], Plant] = {}
    for i, (number, name, space, start, days, plist) in enumerate(GROUPS):
        g = Group(
            number=number,
            name=name,
            space=spaces.get(space) if space else None,
            flower_start=start,
            flower_days=days,
            color=next_group_color(i),
        )
        if start is None:
            g.status = GroupStatus.vegetative
        elif ref < start:
            g.status = GroupStatus.vegetative
        elif g.is_flowering_on(ref):
            g.status = GroupStatus.flowering
        else:
            g.status = GroupStatus.done
        groups[number] = g
        db.session.add(g)
        for label, strain, killed, note in plist:
            p = Plant(label=label, strain=strains[strain], group=g, notes=note)
            if killed:
                p.status = PlantStatus.killed
                p.end_reason = killed
                p.ended_on = start or ref
            elif g.status == GroupStatus.done:
                p.status = PlantStatus.harvested
                p.ended_on = g.flower_end
            elif g.status == GroupStatus.flowering:
                p.status = PlantStatus.flowering
            else:
                p.status = PlantStatus.vegetative
            p.started_on = (start - timedelta(days=56)) if start else None
            plants[(number, label)] = p
            db.session.add(p)

    for number, plabel, on, wet, dry, notes in HARVESTS:
        db.session.add(
            Harvest(
                group=groups[number],
                plant=plants.get((number, plabel)) if plabel else None,
                harvested_on=on,
                wet_weight_g=wet,
                dry_weight_g=dry,
                notes=notes,
            )
        )

    for on, number, plabel, title, body, tasks in JOURNAL:
        db.session.add(
            JournalEntry(
                entry_date=on,
                group=groups[number],
                plant=plants.get((number, plabel)) if plabel else None,
                title=title,
                body=body,
                tasks=tasks or None,
            )
        )

    # A few clones on the shelf, not yet in a group.
    for i in range(1, 4):
        db.session.add(
            Plant(
                label=f"Jack Herer cut {i}",
                strain=strains["Jack Herer"],
                status=PlantStatus.clone,
                space=spaces["Clone Shelf"],
                started_on=ref,
            )
        )

    db.session.commit()
