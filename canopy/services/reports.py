"""Aggregations for the Reports page: survival per strain and why plants were lost."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date

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


@dataclass
class StrainTiming:
    """What a strain actually did, as opposed to what its packet says."""

    strain: Strain
    stages: dict[PlantStatus, list[int]] = field(default_factory=dict)

    def average(self, stage: PlantStatus) -> float | None:
        days = self.stages.get(stage)
        return round(sum(days) / len(days), 1) if days else None

    def runs(self, stage: PlantStatus) -> int:
        return len(self.stages.get(stage, ()))

    @property
    def observed_flower(self) -> float | None:
        return self.average(PlantStatus.flowering)

    @property
    def drift(self) -> float | None:
        """Observed flower length minus the length on the strain. Negative finishes early."""
        seen = self.observed_flower
        return None if seen is None else round(seen - self.strain.flower_days, 1)


def time_in_stage(plants: Iterable[Plant], *, ref: date | None = None) -> list[StrainTiming]:
    """Days each strain really spends in each stage, from the lifecycle log.

    Only *finished* stretches count: a plant three weeks into flower says nothing yet
    about how long that strain takes, and averaging it in would drag every figure down.
    """
    from . import lifecycle

    out: dict[int, StrainTiming] = {}
    for p in plants:
        spans = lifecycle.stage_spans(p, ref=ref)
        if p.status == PlantStatus.killed and spans:
            # The stretch the cull ended is not a measurement of anything — a male pulled
            # on day 55 did not teach us that the strain finishes in 55 days. Earlier,
            # completed stretches still count.
            spans = spans[:-1]
        for span in spans:
            if not span["closed"] or span["status"] in (
                PlantStatus.harvested,
                PlantStatus.killed,
            ):
                continue
            if span["days"] <= 0:
                # A stage that lasted no days is a same-day correction — someone fixing a
                # status they had just set — not a measurement of anything.
                continue
            timing = out.setdefault(p.strain_id, StrainTiming(p.strain))
            timing.stages.setdefault(span["status"], []).append(span["days"])
    return sorted(
        out.values(),
        key=lambda t: (t.observed_flower is None, -(t.runs(PlantStatus.flowering)), t.strain.name),
    )
