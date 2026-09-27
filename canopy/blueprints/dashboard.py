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

    units = sched.scheduled_units(groups, plants)
    ramp = sched.ramp_down(units, spaces, ref=ref)
    rows = sched.timeline_rows(units, ref=ref)
    # Every run in flower, not just the ones in a group: a plant standing on its own
    # is still a thing with a flip date and a harvest, and the cards are the only part
    # of this page anyone reads.
    active = [u for u in units if u.is_flowering_on(ref)]
    active.sort(key=lambda u: u.flower_end)
    unscheduled = [g for g in groups if g.waiting_for_a_slot]
    suggestions = {g.id: sched.suggest_start(g, groups, ref=ref) for g in unscheduled}

    quick = JournalForm(entry_date=ref)
    quick.space_id.choices = [(0, "— whole room —")] + [(s.id, s.name) for s in spaces]

    return render_template(
        "dashboard.html",
        rows=rows,
        active=active,
        unscheduled=unscheduled,
        suggestions=suggestions,
        upcoming=sched.upcoming(units, days=30, ref=ref),
        conflicts=sched.conflicts(groups, spaces, plants, ref=ref),
        ramp=ramp,
        # Keyed so a flower card can show its own reminder without scanning the list.
        # Keyed by number, not id: a group id and a plant id can collide, and
        # LonePlant.number is offset past the real group numbers precisely so it cannot.
        ramp_by_group={r.unit.number: r for r in ramp},
        occupancy=sorted(spacing.occupancy(spaces, plants).values(), key=lambda o: o.space.id),
        quick=quick,
        spaces=spaces,
        openings=sched.openings(units, ref=ref)[:5],
        counts=sched.plant_counts(plants),
        inventory=sched.inventory_summary(strains),
        ref=ref,
    )
