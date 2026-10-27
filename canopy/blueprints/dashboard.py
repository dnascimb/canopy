from __future__ import annotations

from flask import Blueprint, render_template

from ..extensions import db
from ..models import Group, Plant, Space, SpaceStage
from ..services import scheduling as sched
from ..services import spacing

bp = Blueprint("dashboard", __name__)


@bp.get("/")
def index():
    groups = db.session.query(Group).all()
    spaces = db.session.query(Space).all()
    plants = db.session.query(Plant).all()
    ref = sched.today()

    units = sched.scheduled_units(groups, plants)
    rows = sched.recent_rows(sched.timeline_rows(units, ref=ref, include_unflipped=True), ref=ref)
    # Tabs beside the flowering timeline: time spent on the clone shelf and in the veg tent.
    stay_tabs = [
        (s, sched.recent_rows(sched.space_rows(plants, s, ref=ref), ref=ref))
        for stage in (SpaceStage.vegetative, SpaceStage.clone)
        for s in sorted(spaces, key=lambda s: s.id)
        if s.stage == stage
    ]
    # Every run in flower, not just the ones in a group: a plant standing on its own
    # is still a thing with a flip date and a harvest, and the cards are the only part
    # of this page anyone reads.
    active = [u for u in units if u.is_flowering_on(ref)]
    active.sort(key=lambda u: u.flower_end)

    return render_template(
        "dashboard.html",
        rows=rows,
        stay_tabs=stay_tabs,
        active=active,
        upcoming=sched.upcoming(units, days=30, ref=ref),
        occupancy=sorted(spacing.occupancy(spaces, plants).values(), key=lambda o: o.space.id),
        spaces=spaces,
        ref=ref,
    )
