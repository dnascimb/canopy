from __future__ import annotations

from flask import Blueprint, render_template

from ..extensions import db
from ..forms import JournalForm
from ..models import Group, Plant, Space, Strain
from ..services import scheduling as sched
from ..services import spacing

bp = Blueprint("dashboard", __name__)


@bp.get("/")
def index():
    groups = db.session.query(Group).all()
    spaces = db.session.query(Space).all()
    plants = db.session.query(Plant).all()
    strains = db.session.query(Strain).all()
    ref = sched.today()

    rows = sched.timeline_rows(groups, ref=ref)
    active = [g for g in groups if g.is_flowering_on(ref)]
    active.sort(key=lambda g: g.flower_end)
    unscheduled = [g for g in groups if g.flower_start is None]
    suggestions = {g.id: sched.suggest_start(g, groups, ref=ref) for g in unscheduled}

    quick = JournalForm(entry_date=ref)
    quick.space_id.choices = [(0, "— whole room —")] + [(s.id, s.name) for s in spaces]

    return render_template(
        "dashboard.html",
        rows=rows,
        active=active,
        unscheduled=unscheduled,
        suggestions=suggestions,
        upcoming=sched.upcoming(groups, days=30, ref=ref),
        conflicts=sched.conflicts(groups, spaces, plants, ref=ref),
        occupancy=sorted(spacing.occupancy(spaces, plants).values(), key=lambda o: o.space.id),
        quick=quick,
        spaces=spaces,
        openings=sched.openings(groups, ref=ref)[:5],
        counts=sched.plant_counts(plants),
        inventory=sched.inventory_summary(strains),
        ref=ref,
    )
