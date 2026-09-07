from __future__ import annotations

from flask import Blueprint, render_template

from ..extensions import db
from ..models import Group, Harvest, Plant, Space, SpaceStage, Strain
from ..services import reports, spacing
from ..services import scheduling as sched

bp = Blueprint("reports", __name__)


@bp.get("/")
def index():
    ref = sched.today()
    strains = db.session.query(Strain).all()
    harvests = db.session.query(Harvest).all()
    groups = db.session.query(Group).all()
    plants = db.session.query(Plant).all()
    stats = reports.strain_stats(strains, harvests)
    flower_spaces = [s for s in db.session.query(Space).all() if s.stage == SpaceStage.flowering]
    with_yield = [s for s in stats if s.dry_g > 0]
    with_history = sorted(
        (s for s in stats if s.survival is not None), key=lambda s: (-s.survival, -s.plants)
    )
    gpp = sorted((s for s in with_yield if s.g_per_plant), key=lambda s: -s.g_per_plant)
    return render_template(
        "reports/index.html",
        stats=stats,
        yield_items=[
            (s.strain.name, s.dry_g, f"{s.harvested} plant{'s' if s.harvested != 1 else ''}")
            for s in with_yield
        ],
        gpp_items=[(s.strain.name, s.g_per_plant, None) for s in gpp],
        survival_items=[
            (s.strain.name, s.survival * 100, f"{s.harvested}/{s.harvested + s.killed}")
            for s in with_history
        ],
        reason_items=[(r, n, None) for r, n in reports.kill_reasons(plants)],
        yields=reports.group_yields(groups),
        load={s: spacing.load_series(s, groups, ref=ref) for s in flower_spaces},
        ref=ref,
    )
