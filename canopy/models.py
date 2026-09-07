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

import enum
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import CheckConstraint, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .extensions import db


class SeedType(enum.StrEnum):
    regular = "regular"
    feminized = "feminized"
    autoflower = "autoflower"
    clone = "clone"


class SpaceStage(enum.StrEnum):
    clone = "clone"
    vegetative = "vegetative"
    flowering = "flowering"


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
    notes: Mapped[str | None] = mapped_column(db.Text)

    groups: Mapped[list[Group]] = relationship(back_populates="space")
    plants: Mapped[list[Plant]] = relationship(back_populates="space")

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
    flower_start: Mapped[date | None] = mapped_column(db.Date)
    flower_days: Mapped[int] = mapped_column(default=70, nullable=False)
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

    __table_args__ = (CheckConstraint("flower_days >= 1", name="ck_group_flower_days"),)

    # ---- derived schedule -------------------------------------------------
    @property
    def label(self) -> str:
        return self.name or f"Grp {self.number}"

    @property
    def flower_end(self) -> date | None:
        if self.flower_start is None:
            return None
        return self.flower_start + timedelta(days=self.flower_days)

    def is_flowering_on(self, day: date) -> bool:
        return (
            self.flower_start is not None
            and self.flower_end is not None
            and self.flower_start <= day < self.flower_end
        )

    def day_of_flower(self, today: date) -> int | None:
        """1-based day in flower for *today*, or None if not in the window."""
        if not self.is_flowering_on(today):
            return None
        return (today - self.flower_start).days + 1

    def progress(self, today: date) -> float:
        """0.0–1.0 fraction of the flowering window elapsed."""
        if self.flower_start is None:
            return 0.0
        if today < self.flower_start:
            return 0.0
        if today >= self.flower_end:
            return 1.0
        return (today - self.flower_start).days / self.flower_days

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
    status: Mapped[PlantStatus] = mapped_column(
        db.Enum(PlantStatus, native_enum=False, length=20),
        default=PlantStatus.vegetative,
        nullable=False,
    )
    started_on: Mapped[date | None] = mapped_column(db.Date)
    ended_on: Mapped[date | None] = mapped_column(db.Date)
    end_reason: Mapped[str | None] = mapped_column(db.String(255))
    notes: Mapped[str | None] = mapped_column(db.Text)

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

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Plant {self.label}>"


class Harvest(TimestampMixin, db.Model):
    __tablename__ = "harvests"

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int | None] = mapped_column(db.ForeignKey("groups.id", ondelete="CASCADE"))
    plant_id: Mapped[int | None] = mapped_column(db.ForeignKey("plants.id", ondelete="CASCADE"))
    harvested_on: Mapped[date] = mapped_column(db.Date, nullable=False)
    wet_weight_g: Mapped[float | None] = mapped_column(db.Float)
    dry_weight_g: Mapped[float | None] = mapped_column(db.Float)
    notes: Mapped[str | None] = mapped_column(db.Text)

    group: Mapped[Group | None] = relationship(back_populates="harvests")
    plant: Mapped[Plant | None] = relationship(back_populates="harvests")

    __table_args__ = (
        CheckConstraint("group_id IS NOT NULL OR plant_id IS NOT NULL", name="ck_harvest_target"),
    )


class JournalEntry(TimestampMixin, db.Model):
    __tablename__ = "journal_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    entry_date: Mapped[date] = mapped_column(db.Date, nullable=False)
    group_id: Mapped[int | None] = mapped_column(db.ForeignKey("groups.id", ondelete="CASCADE"))
    plant_id: Mapped[int | None] = mapped_column(db.ForeignKey("plants.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(db.String(160), nullable=False)
    body: Mapped[str | None] = mapped_column(db.Text)
    tasks: Mapped[str | None] = mapped_column(db.String(255))  # comma-separated task keys

    group: Mapped[Group | None] = relationship(back_populates="journal_entries")
    plant: Mapped[Plant | None] = relationship(back_populates="journal_entries")

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
    "ph_ec": "Checked pH / EC",
    "ipm": "IPM / pest check",
    "defoliated": "Defoliated",
    "trained": "Trained / topped",
    "transplanted": "Transplanted",
    "flushed": "Flushed",
    "cloned": "Took clones",
    "cleaned": "Cleaned / reset",
}


def next_group_color(existing_count: int) -> str:
    return GROUP_PALETTE[existing_count % len(GROUP_PALETTE)]
