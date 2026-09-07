"""Aggregations for the Reports page: yield and survival per strain, yield per group."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date

from ..models import Group, Harvest, Plant, PlantStatus, Strain


@dataclass
class StrainStats:
    strain: Strain
    plants: int = 0
    killed: int = 0
    harvested: int = 0
    dry_g: float = 0.0
    wet_g: float = 0.0
    groups: set[int] = field(default_factory=set)

    @property
    def survival(self) -> float | None:
        finished = self.killed + self.harvested
        return None if finished == 0 else self.harvested / finished

    @property
    def g_per_plant(self) -> float | None:
        return None if self.harvested == 0 or self.dry_g == 0 else self.dry_g / self.harvested


def _attribute(h: Harvest) -> list[tuple[Strain, float, float]]:
    """Split a harvest's weights across strains. Plant-level harvests go to that strain;
    group-level harvests are divided equally among the group's harvested/living plants."""
    if h.plant is not None:
        return [(h.plant.strain, h.wet_weight_g or 0.0, h.dry_weight_g or 0.0)]
    if h.group is None:
        return []
    plants = [p for p in h.group.plants if p.status != PlantStatus.killed]
    if not plants:
        return []
    share_w = (h.wet_weight_g or 0.0) / len(plants)
    share_d = (h.dry_weight_g or 0.0) / len(plants)
    return [(p.strain, share_w, share_d) for p in plants]


def strain_stats(strains: Iterable[Strain], harvests: Iterable[Harvest]) -> list[StrainStats]:
    stats = {s.id: StrainStats(s) for s in strains}
    for st in stats.values():
        for p in st.strain.plants:
            st.plants += 1
            if p.status == PlantStatus.killed:
                st.killed += 1
            elif p.status == PlantStatus.harvested:
                st.harvested += 1
            if p.group_id:
                st.groups.add(p.group_id)
    for h in harvests:
        for strain, w, d in _attribute(h):
            if strain.id in stats:
                stats[strain.id].wet_g += w
                stats[strain.id].dry_g += d
    return sorted(stats.values(), key=lambda s: (-s.dry_g, -s.plants, s.strain.name))


@dataclass
class GroupYield:
    group: Group
    wet_g: float
    dry_g: float
    plants: int

    @property
    def g_per_plant(self) -> float | None:
        return self.dry_g / self.plants if self.plants and self.dry_g else None


def group_yields(groups: Iterable[Group]) -> list[GroupYield]:
    out = []
    for g in groups:
        if not g.harvests:
            continue
        out.append(
            GroupYield(
                g,
                sum(h.wet_weight_g or 0 for h in g.harvests),
                sum(h.dry_weight_g or 0 for h in g.harvests),
                len([p for p in g.plants if p.status != PlantStatus.killed]),
            )
        )
    return sorted(out, key=lambda y: y.group.flower_start or date.max)


def kill_reasons(plants: Iterable[Plant]) -> list[tuple[str, int]]:
    counts: dict[str, int] = defaultdict(int)
    for p in plants:
        if p.status == PlantStatus.killed:
            counts[(p.end_reason or "unspecified").strip().capitalize()] += 1
    return sorted(counts.items(), key=lambda kv: -kv[1])
