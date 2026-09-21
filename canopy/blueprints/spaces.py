from __future__ import annotations

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from ..extensions import db
from ..forms import SpaceForm
from ..models import Group, JournalEntry, Plant, Space, SpaceStage
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
    series = {
        s.id: spacing.load_series(s, sched.scheduled_units(groups, plants), ref=ref)
        for s in flower_spaces
    }

    # Planning table: groups that have not flipped yet, and what they need in flower.
    waiting = [
        g for g in groups if g.living_plants and (g.flower_start is None or g.flower_start > ref)
    ]
    plan = []
    for g in sorted(waiting, key=lambda g: (g.flower_start or ref, g.number)):
        target = g.space or spacing.default_space(SpaceStage.flowering, spaces)
        need = len(g.living_plants)
        room_now = occ[target.id].room_for() if target else None
        opening = next(
            (o for o in openings if o.space is None or (target and o.space.id == target.id)), None
        )
        plan.append(
            {
                "group": g,
                "target": target,
                "plants": need,
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
        breach={
            s.id: spacing.capacity_warning(
                s, sched.scheduled_units(groups, plants), occ[s.id], ref=ref
            )
            for s in spaces
        },
        stages=list(SpaceStage),
        ref=ref,
    )


def _apply(form: SpaceForm, s: Space) -> None:
    extra = [x for x in (form.also_hosts.data or []) if x and x != form.stage.data]
    form.populate_obj(s)
    s.stage = SpaceStage(form.stage.data)
    s.also_hosts = ",".join(extra) or None


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
    if request.method == "GET":
        form.also_hosts.data = [x.value for x in s.hosts if x != s.stage]
    if form.validate_on_submit():
        _apply(form, s)
        db.session.commit()
        flash("Saved changes.", "success")
        return redirect(url_for("spaces.index"))
    return render_template("spaces/form.html", form=form, space=s)


@bp.route("/<int:space_id>/check", methods=["GET", "POST"])
def check(space_id: int):
    """Audit a space against what Canopy thinks is in it.

    Non-destructive. Confirming is one tick per plant; anything left unticked is *flagged*,
    not killed or moved, because "I did not see it" and "it is gone" are different claims
    and only the grower can tell them apart.

    Rows are grouped and sorted for a stable, scannable list. That is not a claim about the
    order anyone walks a tent in.
    """
    s = db.session.get(Space, space_id) or abort(404)
    ref = sched.today()
    spaces = db.session.query(Space).all()
    here = [
        p
        for p in db.session.query(Plant).all()
        if (loc := spacing.plant_location(p, spaces)) is not None and loc.id == s.id
    ]
    here.sort(key=lambda p: ((p.group.label if p.group else "~"), p.label))

    if request.method == "POST":
        seen = {int(x) for x in request.form.getlist("present")}
        found = [p for p in here if p.id in seen]
        missing = [p for p in here if p.id not in seen]
        extra = (request.form.get("extra") or "").strip()
        for p in missing:
            note = f"Not found in the {ref.isoformat()} check of {s.name}."
            p.notes = f"{p.notes} {note}".strip() if p.notes else note
        body = [f"Checked {s.name}: {len(found)} of {len(here)} confirmed."]
        if missing:
            body.append("Not found: " + ", ".join(p.label for p in missing) + ".")
        if extra:
            body.append("Here but not in Canopy: " + extra)
        db.session.add(
            JournalEntry(
                entry_date=ref,
                space_id=s.id,
                title=f"Checked {s.name}",
                body="\n\n".join(body),
            )
        )
        db.session.commit()
        flash(
            f"{len(found)} confirmed, {len(missing)} flagged as not found."
            if missing
            else f"All {len(found)} confirmed.",
            "success",
        )
        return redirect(url_for("spaces.check", space_id=s.id))

    groups: dict[str, list[Plant]] = {}
    for p in here:
        groups.setdefault(p.group.label if p.group else "No group", []).append(p)
    return render_template(
        "spaces/check.html",
        space=s,
        plants=here,
        grouped=groups,
        ref=ref,
        last=db.session.query(JournalEntry)
        .filter(JournalEntry.space_id == s.id, JournalEntry.title.like("Checked %"))
        .order_by(JournalEntry.entry_date.desc(), JournalEntry.id.desc())
        .first(),
    )


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
