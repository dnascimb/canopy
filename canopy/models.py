"""SQLAlchemy models.

Domain summary
--------------
* **Space**   – a physical flowering area (tent, room, bench) with a plant capacity.
* **Strain**  – a cultivar in the seed/clone inventory. Carries the default flower time.
* **Group**   – a batch of plants that is flipped to flower together. The schedule is
                derived from ``flower_start`` + ``flower_days``.
* **Plant**   – an individual plant, always of one Strain, optionally in one Group.
* **Harvest** – yield record for a plant or a whole group.
* **JournalEntry** – dated free-text log attached to a group and/or plant.
"""

from __future__ import annotations

import colorsys
import enum
from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import CheckConstraint, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .extensions import db

DEFAULT_FLOWER_DAYS = 70


class SeedType(enum.StrEnum):
    regular = "regular"
    feminized = "feminized"
    autoflower = "autoflower"
    clone = "clone"


class SpaceStage(enum.StrEnum):
    clone = "clone"
    vegetative = "vegetative"
    flowering = "flowering"


class Expression(enum.StrEnum):
    """How a cultivar expresses, as catalogued in the collection index."""

    sativa = "sativa"
    haze = "haze"
    indica = "indica"
    hybrid = "hybrid"


class PlantSize(enum.StrEnum):
    small = "small"
    medium = "medium"
    large = "large"


class GroupStatus(enum.StrEnum):
    planned = "planned"
    vegetative = "vegetative"
    flowering = "flowering"
    drying = "drying"
    done = "done"


class PlantStatus(enum.StrEnum):
    clone = "clone"
    seedling = "seedling"
    vegetative = "vegetative"
    flowering = "flowering"
    # Cut and hanging. The group-level word for this is "drying"; at the plant level it is
    # the same state, so there is deliberately no separate `drying` status.
    harvested = "harvested"
    killed = "killed"


# A restrained palette that reads well on the dark timeline; groups cycle through it.
GROUP_PALETTE = [
    "#66bb6a",
    "#4db6ac",
    "#7cb342",
    "#9ccc65",
    "#aed581",
    "#ffb74d",
    "#ef5350",
    "#42a5f5",
    "#5c6bc0",
    "#ab47bc",
    "#ec407a",
    "#ffa726",
    "#26a69a",
    "#d4e157",
    "#8bc34a",
    "#ce93d8",
]


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(default=_now, onupdate=_now, nullable=False)


class Space(TimestampMixin, db.Model):
    __tablename__ = "spaces"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(db.String(80), unique=True, nullable=False)
    stage: Mapped[SpaceStage] = mapped_column(
        db.Enum(SpaceStage, native_enum=False, length=20),
        default=SpaceStage.flowering,
        nullable=False,
    )
    width_ft: Mapped[float | None] = mapped_column(db.Float)
    length_ft: Mapped[float | None] = mapped_column(db.Float)
    capacity: Mapped[int] = mapped_column(default=1, nullable=False)  # user-set maximum plants
    # Extra stages this space doubles up for, comma-separated (same shape as journal tasks).
    # A clone shelf is often also where a male sits to drop pollen and where veg overflows.
    also_hosts: Mapped[str | None] = mapped_column(db.String(60))
    notes: Mapped[str | None] = mapped_column(db.Text)

    groups: Mapped[list[Group]] = relationship(back_populates="space")
    plants: Mapped[list[Plant]] = relationship(back_populates="space")
    journal_entries: Mapped[list[JournalEntry]] = relationship(back_populates="space")

    __table_args__ = (CheckConstraint("capacity >= 1", name="ck_space_capacity"),)

    @property
    def area_sqft(self) -> float | None:
        if self.width_ft and self.length_ft:
            return round(self.width_ft * self.length_ft, 2)
        return None

    @property
    def dimensions(self) -> str:
        if self.area_sqft is None:
            return "—"
        w, l_ = self.width_ft, self.length_ft
        fmt = lambda v: f"{v:g}"  # noqa: E731
        return f"{fmt(w)} × {fmt(l_)} ft ({fmt(self.area_sqft)} sq ft)"

    def active_groups(self, today: date) -> list[Group]:
        return [g for g in self.groups if g.is_flowering_on(today)]

    def plants_in_flower(self, today: date) -> int:
        return sum(len(g.living_plants) for g in self.active_groups(today))

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Space {self.name}>"

    @property
    def hosts(self) -> frozenset[SpaceStage]:
        """Every stage this space can hold: its own, plus any it doubles up for.

        Moving a plant into a space it is already suited to is a relocation, not a
        transition — a flowering male parked on the clone shelf to drop pollen stays
        flowering.
        """
        extra = {SpaceStage(x) for x in (self.also_hosts or "").split(",") if x}
        return frozenset({self.stage} | extra)

    def can_host(self, stage: SpaceStage | None) -> bool:
        return stage is not None and stage in self.hosts


class Strain(TimestampMixin, db.Model):
    __tablename__ = "strains"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(db.String(120), nullable=False)
    breeder: Mapped[str | None] = mapped_column(db.String(120))
    lineage: Mapped[str | None] = mapped_column(db.String(255))
    seed_type: Mapped[SeedType] = mapped_column(
        db.Enum(SeedType, native_enum=False, length=20), default=SeedType.regular, nullable=False
    )
    flower_days: Mapped[int] = mapped_column(default=70, nullable=False)
    seeds_on_hand: Mapped[int] = mapped_column(default=0, nullable=False)
    size: Mapped[PlantSize] = mapped_column(
        db.Enum(PlantSize, native_enum=False, length=10), default=PlantSize.medium, nullable=False
    )
    # Nullable: plenty of strains predate the collection index and have no stated type.
    expression: Mapped[Expression | None] = mapped_column(
        db.Enum(Expression, native_enum=False, length=10)
    )
    notes: Mapped[str | None] = mapped_column(db.Text)

    plants: Mapped[list[Plant]] = relationship(back_populates="strain")

    __table_args__ = (
        UniqueConstraint("name", "breeder", name="uq_strain_name_breeder"),
        CheckConstraint("flower_days >= 1", name="ck_strain_flower_days"),
        CheckConstraint("seeds_on_hand >= 0", name="ck_strain_seeds"),
    )

    @property
    def display_name(self) -> str:
        return f"{self.name} ({self.breeder})" if self.breeder else self.name

    @property
    def living_plants(self) -> list[Plant]:
        return [p for p in self.plants if p.status != PlantStatus.killed]

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Strain {self.name}>"


class Group(TimestampMixin, db.Model):
    __tablename__ = "groups"

    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[int] = mapped_column(unique=True, nullable=False)
    name: Mapped[str | None] = mapped_column(db.String(120))
    space_id: Mapped[int | None] = mapped_column(db.ForeignKey("spaces.id", ondelete="SET NULL"))
    status: Mapped[GroupStatus] = mapped_column(
        db.Enum(GroupStatus, native_enum=False, length=20),
        default=GroupStatus.planned,
        nullable=False,
    )
    color: Mapped[str] = mapped_column(db.String(7), default="#66bb6a", nullable=False)
    notes: Mapped[str | None] = mapped_column(db.Text)

    space: Mapped[Space | None] = relationship(back_populates="groups")
    plants: Mapped[list[Plant]] = relationship(back_populates="group")
    harvests: Mapped[list[Harvest]] = relationship(
        back_populates="group", cascade="all, delete-orphan"
    )
    journal_entries: Mapped[list[JournalEntry]] = relationship(
        back_populates="group", cascade="all, delete-orphan"
    )

    # ---- schedule, derived from the plants ---------------------------------
    # A group is a container. Its span is whatever its plants are doing, so a group
    # and a lone plant behave identically everywhere.
    @property
    def label(self) -> str:
        return self.name or f"Grp {self.number}"

    @property
    def scheduled_plants(self) -> list[Plant]:
        return [p for p in self.living_plants if p.flower_start is not None]

    @property
    def flower_start(self) -> date | None:
        starts = [p.flower_start for p in self.scheduled_plants]
        return min(starts) if starts else None

    @property
    def flower_end(self) -> date | None:
        ends = [p.flower_end for p in self.scheduled_plants if p.flower_end]
        return max(ends) if ends else None

    @property
    def flower_days(self) -> int:
        """Span of the group's run. Equals the plants' own length when they agree."""
        if self.flower_start is None or self.flower_end is None:
            return DEFAULT_FLOWER_DAYS
        return (self.flower_end - self.flower_start).days

    def is_flowering_on(self, day: date) -> bool:
        return any(p.is_flowering_on(day) for p in self.scheduled_plants)

    def day_of_flower(self, today: date) -> int | None:
        """1-based day in flower for *today*, or None if nothing is in the window."""
        days = [p.day_of_flower(today) for p in self.scheduled_plants]
        days = [d for d in days if d is not None]
        return max(days) if days else None

    def progress(self, today: date) -> float:
        """0.0–1.0 fraction of the flowering window elapsed."""
        start, end = self.flower_start, self.flower_end
        if start is None or end is None or today < start:
            return 0.0
        if today >= end:
            return 1.0
        return (today - start).days / max((end - start).days, 1)

    @property
    def living_plants(self) -> list[Plant]:
        return [p for p in self.plants if p.status != PlantStatus.killed]

    @property
    def killed_plants(self) -> list[Plant]:
        return [p for p in self.plants if p.status == PlantStatus.killed]

    def strain_labels(self) -> list[str]:
        """Unique strain names of living plants, suffixed with ×N when repeated."""
        counts: dict[str, int] = {}
        for p in self.living_plants:
            counts[p.strain.name] = counts.get(p.strain.name, 0) + 1
        return [name if n == 1 else f"{name} ×{n}" for name, n in counts.items()]

    def strain_summary(self) -> str:
        return ", ".join(self.strain_labels())

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Group {self.number}>"


class Plant(TimestampMixin, db.Model):
    __tablename__ = "plants"

    id: Mapped[int] = mapped_column(primary_key=True)
    label: Mapped[str] = mapped_column(db.String(120), nullable=False)
    strain_id: Mapped[int] = mapped_column(db.ForeignKey("strains.id"), nullable=False)
    group_id: Mapped[int | None] = mapped_column(db.ForeignKey("groups.id", ondelete="SET NULL"))
    space_id: Mapped[int | None] = mapped_column(db.ForeignKey("spaces.id", ondelete="SET NULL"))
    # The plant this one was cut from. Kept when the mother is deleted, so a cutting is
    # never orphaned into claiming a parent that no longer exists.
    parent_id: Mapped[int | None] = mapped_column(db.ForeignKey("plants.id", ondelete="SET NULL"))
    status: Mapped[PlantStatus] = mapped_column(
        db.Enum(PlantStatus, native_enum=False, length=20),
        default=PlantStatus.vegetative,
        nullable=False,
    )
    started_on: Mapped[date | None] = mapped_column(db.Date)
    ended_on: Mapped[date | None] = mapped_column(db.Date)
    end_reason: Mapped[str | None] = mapped_column(db.String(255))
    # Planned flower length for this plant's run. None falls back to the strain.
    flower_days_override: Mapped[int | None] = mapped_column(db.Integer)
    notes: Mapped[str | None] = mapped_column(db.Text)

    events: Mapped[list[PlantEvent]] = relationship(
        back_populates="plant",
        cascade="all, delete-orphan",
        order_by="PlantEvent.on, PlantEvent.id",
    )
    parent: Mapped[Plant | None] = relationship(back_populates="cuttings", remote_side="Plant.id")
    cuttings: Mapped[list[Plant]] = relationship(back_populates="parent")
    strain: Mapped[Strain] = relationship(back_populates="plants")
    group: Mapped[Group | None] = relationship(back_populates="plants")
    space: Mapped[Space | None] = relationship(back_populates="plants")
    harvests: Mapped[list[Harvest]] = relationship(
        back_populates="plant", cascade="all, delete-orphan"
    )
    journal_entries: Mapped[list[JournalEntry]] = relationship(
        back_populates="plant", cascade="all, delete-orphan"
    )

    @property
    def is_alive(self) -> bool:
        return self.status != PlantStatus.killed

    @property
    def ancestry(self) -> list[Plant]:
        """Mother, grandmother, and so on — oldest last. Loop-safe."""
        out: list[Plant] = []
        seen = {self.id}
        node = self.parent
        while node is not None and node.id not in seen:
            out.append(node)
            seen.add(node.id)
            node = node.parent
        return out

    # ---- schedule, owned by the plant --------------------------------------
    @property
    def flower_days(self) -> int:
        """This run's planned length: the plant's own, else the strain's default."""
        return self.flower_days_override or self.strain.flower_days

    @property
    def flower_start(self) -> date | None:
        """When this plant last entered flower, read off its lifecycle events."""
        flips = [e.on for e in self.events if e.to_status == PlantStatus.flowering]
        return max(flips) if flips else None

    @property
    def flower_end(self) -> date | None:
        start = self.flower_start
        return None if start is None else start + timedelta(days=self.flower_days)

    def is_flowering_on(self, day: date) -> bool:
        start, end = self.flower_start, self.flower_end
        return start is not None and end is not None and start <= day < end

    def day_of_flower(self, today: date) -> int | None:
        """1-based day in flower for *today*, or None if not in the window."""
        if not self.is_flowering_on(today):
            return None
        return (today - self.flower_start).days + 1

    def progress(self, today: date) -> float:
        start, end = self.flower_start, self.flower_end
        if start is None or today < start:
            return 0.0
        if today >= end:
            return 1.0
        return (today - start).days / self.flower_days

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Plant {self.label}>"


class Harvest(TimestampMixin, db.Model):
    __tablename__ = "harvests"

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int | None] = mapped_column(db.ForeignKey("groups.id", ondelete="CASCADE"))
    plant_id: Mapped[int | None] = mapped_column(db.ForeignKey("plants.id", ondelete="CASCADE"))
    harvested_on: Mapped[date] = mapped_column(db.Date, nullable=False)
    notes: Mapped[str | None] = mapped_column(db.Text)

    group: Mapped[Group | None] = relationship(back_populates="harvests")
    plant: Mapped[Plant | None] = relationship(back_populates="harvests")

    __table_args__ = (
        CheckConstraint("group_id IS NOT NULL OR plant_id IS NOT NULL", name="ck_harvest_target"),
    )


class PlantEvent(TimestampMixin, db.Model):
    """One step in a plant's life: a status change, a move, a kill, a harvest.

    Append-only and the source of truth for when a plant flipped. Everything the
    schedule knows about timing is read back off these rows.
    """

    __tablename__ = "plant_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    plant_id: Mapped[int] = mapped_column(
        db.ForeignKey("plants.id", ondelete="CASCADE"), nullable=False
    )
    on: Mapped[date] = mapped_column(db.Date, nullable=False)
    from_status: Mapped[PlantStatus | None] = mapped_column(
        db.Enum(PlantStatus, native_enum=False, length=20)
    )
    to_status: Mapped[PlantStatus] = mapped_column(
        db.Enum(PlantStatus, native_enum=False, length=20), nullable=False
    )
    space_id: Mapped[int | None] = mapped_column(db.ForeignKey("spaces.id", ondelete="SET NULL"))
    note: Mapped[str | None] = mapped_column(db.String(255))

    plant: Mapped[Plant] = relationship(back_populates="events")
    space: Mapped[Space | None] = relationship()

    @property
    def label(self) -> str:
        where = f" · {self.space.name}" if self.space else ""
        if self.from_status is None:
            return f"started as {self.to_status.value}{where}"
        return f"{self.from_status.value} → {self.to_status.value}{where}"

    def __repr__(self) -> str:  # pragma: no cover
        return f"<PlantEvent {self.plant_id} {self.on} {self.to_status}>"


class JournalEntry(TimestampMixin, db.Model):
    __tablename__ = "journal_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    entry_date: Mapped[date] = mapped_column(db.Date, nullable=False)
    group_id: Mapped[int | None] = mapped_column(db.ForeignKey("groups.id", ondelete="CASCADE"))
    plant_id: Mapped[int | None] = mapped_column(db.ForeignKey("plants.id", ondelete="CASCADE"))
    space_id: Mapped[int | None] = mapped_column(db.ForeignKey("spaces.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(db.String(160), nullable=False)
    body: Mapped[str | None] = mapped_column(db.Text)
    tasks: Mapped[str | None] = mapped_column(db.String(255))  # comma-separated task keys
    # Filename inside the instance uploads folder. The file itself lives outside the
    # database and outside git; a JSON backup carries the name, not the picture.
    photo_path: Mapped[str | None] = mapped_column(db.String(255))

    group: Mapped[Group | None] = relationship(back_populates="journal_entries")
    plant: Mapped[Plant | None] = relationship(back_populates="journal_entries")
    space: Mapped[Space | None] = relationship(back_populates="journal_entries")

    @property
    def task_list(self) -> list[str]:
        return [t for t in (self.tasks or "").split(",") if t]

    @property
    def task_labels(self) -> list[str]:
        return [TASKS.get(t, t) for t in self.task_list]


# Common grow tasks for the quick log (key -> label). Order is the display order.
TASKS: dict[str, str] = {
    "watered": "Watered",
    "fed": "Fed nutrients",
    "ipm": "Pest/Mold treatment",
    "defoliated": "Defoliated",
    "trained": "Trained / topped",
    "transplanted": "Transplanted",
    "flushed": "Flushed",
    "cloned": "Took clones",
    "cleaned": "Cleaned / reset",
}


def _spun_color(step: int) -> str:
    """A colour off the hue circle, in the palette's tonal family.

    Golden-angle steps so successive colours land far apart rather than as near-identical
    neighbours.
    """
    hue = (step * 137.508 % 360) / 360
    r, g, b = colorsys.hls_to_rgb(hue, 0.60, 0.52)
    return f"#{round(r * 255):02x}{round(g * 255):02x}{round(b * 255):02x}"


def next_group_color(used: Iterable[str] = ()) -> str:
    """A colour no other group is using.

    Timeline bars are told apart by colour, so two groups sharing one is a genuine
    misread — and the old rule (palette indexed by group count, modulo its length)
    guaranteed a collision on group 17 and broke again whenever a group was deleted.
    The palette is still preferred, in order; past it the hue circle takes over so the
    supply never runs out.
    """
    taken = {c.lower() for c in used if c}
    for c in GROUP_PALETTE:
        if c.lower() not in taken:
            return c
    step = 1
    while step < 1000:
        c = _spun_color(step)
        if c.lower() not in taken:
            return c
        step += 1
    return GROUP_PALETTE[0]  # pragma: no cover - 1000 distinct colours in play
