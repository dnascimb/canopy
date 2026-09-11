from __future__ import annotations

from flask import Blueprint, render_template

from ..extensions import db
from ..models import Group, Plant, PlantStatus, Space, SpaceStage, Strain
from ..services import reports, spacing
from ..services import scheduling as sched

bp = Blueprint("reports", __name__)


@bp.get("/")
def index():
    ref = sched.today()
    strains = db.session.query(Strain).all()
    groups = db.session.query(Group).all()
    plants = db.session.query(Plant).all()
    stats = reports.strain_stats(strains)
    flower_spaces = [s for s in db.session.query(Space).all() if s.stage == SpaceStage.flowering]
    with_history = sorted(
        (s for s in stats if s.survival is not None), key=lambda s: (-s.survival, -s.plants)
    )
    return render_template(
        "reports/index.html",
        stats=stats,
        survival_items=[
            (s.strain.name, s.survival * 100, f"{s.harvested}/{s.harvested + s.killed}")
            for s in with_history
        ],
        reason_items=[(r, n, None) for r, n in reports.kill_reasons(plants)],
        timings=reports.time_in_stage(plants, ref=ref),
        PlantStatus=PlantStatus,
        load={s: spacing.load_series(s, groups, ref=ref) for s in flower_spaces},
        ref=ref,
    )
