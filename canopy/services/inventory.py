"""Inventory filtering.

The inventory page ships every strain and static/js/inventory.js narrows the rows in place
as the controls change. This is the server's half of the same filter: it decides which rows
the first render shows, so a reload, a shared link or a browser without JavaScript lands on
the same rows the live filter would. Keep the two in step — the rules are:

* search: every whitespace-separated word must appear, case-insensitively, in the name,
  the breeder or the lineage (each word may match a different one);
* type, expression: exact match;
* breeder: exact match, or ``NO_BREEDER`` for strains with none;
* days: the flower-length bucket in ``DAY_RANGES``, bounds inclusive.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..extensions import db
from ..models import Expression, SeedType, Strain

NO_BREEDER = "__none__"

# Flower-length buckets, week-aligned because that is how flower time is quoted.
DAY_RANGES: dict[str, tuple[str, int | None, int | None]] = {
    "-56": ("8 weeks or less", None, 56),
    "57-63": ("9 weeks (57-63)", 57, 63),
    "64-70": ("10 weeks (64-70)", 64, 70),
    "71-77": ("11 weeks (71-77)", 71, 77),
    "78-84": ("12 weeks (78-84)", 78, 84),
    "85-": ("13 weeks or more", 85, None),
}


@dataclass(frozen=True)
class StrainFilter:
    q: str = ""
    seed_type: str = ""
    breeder: str = ""
    expression: str = ""
    days: str = ""

    @classmethod
    def from_args(cls, args) -> StrainFilter:
        return cls(
            q=args.get("q", "").strip(),
            seed_type=args.get("type", ""),
            breeder=args.get("breeder", ""),
            expression=args.get("expression", ""),
            days=args.get("days", ""),
        )

    @property
    def active(self) -> bool:
        return bool(self.q or self.seed_type or self.breeder or self.expression or self.days)


def _like(term: str) -> str:
    """A LIKE pattern matching *term* literally, so a typed % or _ is not a wildcard."""
    return "%" + term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def matching_ids(f: StrainFilter) -> set[int]:
    """Ids of the strains *f* keeps. Unknown values are ignored rather than raising."""
    query = db.session.query(Strain.id)
    for term in f.q.split():
        like = _like(term)
        query = query.filter(
            Strain.name.ilike(like, escape="\\")
            | Strain.breeder.ilike(like, escape="\\")
            | Strain.lineage.ilike(like, escape="\\")
        )
    if f.seed_type in SeedType.__members__.values():
        query = query.filter(Strain.seed_type == SeedType(f.seed_type))
    if f.expression in Expression.__members__.values():
        query = query.filter(Strain.expression == Expression(f.expression))
    if f.breeder == NO_BREEDER:
        query = query.filter(Strain.breeder.is_(None) | (Strain.breeder == ""))
    elif f.breeder:
        query = query.filter(Strain.breeder == f.breeder)
    if f.days in DAY_RANGES:
        _, low, high = DAY_RANGES[f.days]
        if low is not None:
            query = query.filter(Strain.flower_days >= low)
        if high is not None:
            query = query.filter(Strain.flower_days <= high)
    return {i for (i,) in query}
