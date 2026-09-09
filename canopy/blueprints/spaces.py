from __future__ import annotations

from flask import Blueprint, abort, flash, redirect, render_template, url_for

from ..extensions import db
from ..forms import SpaceForm
from ..models import Group, Plant, PlantSize, Space, SpaceStage
from ..services import scheduling as sched
from ..services import spacing

bp = Blueprint("spaces", __name__)

STAGE_ORDER = {SpaceStage.clone: 0, SpaceStage.vegetative: 1, SpaceStage.flowering: 2}


@bp.get("/")
def index():
    """Space planner: what is where, how full each space is, and what fits next."""
    ref = sched.today()
    spaces = sorted(db.session.query(Space).all(), key=lambda s: (STAGE_ORDER[s.stage], s.id))
    groups = db.session.query(Group).all()
    plants = db.session.query(Plant).all()
    occ = spacing.occupancy(spaces, plants)
    openings = sched.openings(sched.scheduled_units(groups, plants), ref=ref)

    flower_spaces = [s for s in spaces if s.stage == SpaceStage.flowering]
    series = {s.id: spacing.load_series(s, sched.scheduled_units(groups, plants), ref=ref) for s in flower_spaces}

    # Planning table: groups that have not flipped yet, and what they need in flower.
    waiting = [
        g for g in groups if g.living_plants and (g.flower_start is None or g.flower_start > ref)
    ]
    plan = []
    for g in sorted(waiting, key=lambda g: (g.flower_start or ref, g.number)):
        target = g.space or spacing.default_space(SpaceStage.flowering, spaces)
        need = spacing.group_footprint(g, SpaceStage.flowering)
        room_now = occ[target.id].free_sqft if target and target.area_sqft else None
        opening = next(
            (o for o in openings if o.space is None or (target and o.space.id == target.id)), None
        )
        plan.append(
            {
                "group": g,
                "target": target,
                "need_sqft": need,
                "plants": len(g.living_plants),
                "fits_now": (room_now is not None and need <= room_now),
                "room_now": room_now,
                "opening": opening,
                "suggestion": sched.suggest_start(g, groups, ref=ref)
                if g.flower_start is None
                else None,
            }
        )

    return render_template(
        "spaces/index.html",
        spaces=spaces,
        occ=occ,
        series=series,
        plan=plan,
        openings=openings,
        breach={s.id: spacing.capacity_warning(s, sched.scheduled_units(groups, plants), occ[s.id], ref=ref) for s in spaces},
        footprints=spacing.footprint_table(),
        sizes=list(PlantSize),
        stages=list(SpaceStage),
        ref=ref,
    )


def _apply(form: SpaceForm, s: Space) -> None:
    form.populate_obj(s)
    s.stage = SpaceStage(form.stage.data)


@bp.route("/new", methods=["GET", "POST"])
def create():
    form = SpaceForm()
    if form.validate_on_submit():
        if db.session.query(Space).filter_by(name=form.name.data).first():
            form.name.errors.append("A space with that name already exists.")
        else:
            s = Space()
            _apply(form, s)
            db.session.add(s)
            db.session.commit()
            flash(f"Added {s.name}.", "success")
            return redirect(url_for("spaces.index"))
    return render_template("spaces/form.html", form=form, space=None)


@bp.route("/<int:space_id>/edit", methods=["GET", "POST"])
def edit(space_id: int):
    s = db.session.get(Space, space_id) or abort(404)
    form = SpaceForm(obj=s)
    if form.validate_on_submit():
        _apply(form, s)
        db.session.commit()
        flash("Saved changes.", "success")
        return redirect(url_for("spaces.index"))
    return render_template("spaces/form.html", form=form, space=s)


@bp.post("/<int:space_id>/delete")
def delete(space_id: int):
    s = db.session.get(Space, space_id) or abort(404)
    for g in s.groups:
        g.space_id = None
    for p in s.plants:
        p.space_id = None
    db.session.delete(s)
    db.session.commit()
    flash(f"Deleted {s.name}. Groups and plants in it are now unassigned.", "success")
    return redirect(url_for("spaces.index"))
