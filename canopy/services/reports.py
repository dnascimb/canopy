"""Aggregations for the Reports page: survival per strain and why plants were lost."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field

from ..models import Plant, PlantStatus, Strain


@dataclass
class StrainStats:
    strain: Strain
    plants: int = 0
    killed: int = 0
    harvested: int = 0
    groups: set[int] = field(default_factory=set)

    @property
    def survival(self) -> float | None:
        finished = self.killed + self.harvested
        return None if finished == 0 else self.harvested / finished


def strain_stats(strains: Iterable[Strain]) -> list[StrainStats]:
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
    return sorted(stats.values(), key=lambda s: (-s.plants, s.strain.name))


def kill_reasons(plants: Iterable[Plant]) -> list[tuple[str, int]]:
    counts: dict[str, int] = defaultdict(int)
    for p in plants:
        if p.status == PlantStatus.killed:
            counts[(p.end_reason or "unspecified").strip().capitalize()] += 1
    return sorted(counts.items(), key=lambda kv: -kv[1])
