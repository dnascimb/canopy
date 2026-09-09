from __future__ import annotations

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from ..extensions import db
from ..forms import KillPlantForm, MoveForm, PlantForm
from ..models import Group, Plant, PlantStatus, Space, Strain
from ..services import lifecycle, spacing
from ..services import scheduling as sched

bp = Blueprint("plants", __name__)


def _populate_choices(form: PlantForm) -> None:
    form.strain_id.choices = [
        (s.id, s.display_name) for s in db.session.query(Strain).order_by(Strain.name)
    ]
    form.group_id.choices = [(0, "— no group —")] + [
        (g.id, g.label) for g in db.session.query(Group).order_by(Group.number)
    ]
    form.space_id.choices = [(0, "— by stage (automatic) —")] + [
        (s.id, f"{s.name} · {s.stage.value}") for s in db.session.query(Space).order_by(Space.id)
    ]


def _space_choices(form: MoveForm) -> None:
    form.space_id.choices = [
        (s.id, f"{s.name} · {s.stage.value}") for s in db.session.query(Space).order_by(Space.id)
    ]


@bp.get("/")
def index():
    status = request.args.get("status", "")
    group_id = request.args.get("group", type=int)
    strain_id = request.args.get("strain", type=int)
    space_id = request.args.get("space", type=int)
    query = db.session.query(Plant)
    if status:
        query = query.filter(Plant.status == PlantStatus(status))
    if group_id:
        query = query.filter(Plant.group_id == group_id)
    if strain_id:
        query = query.filter(Plant.strain_id == strain_id)
    plants = query.all()
    spaces = db.session.query(Space).order_by(Space.id).all()
    locations = {p.id: spacing.plant_location(p, spaces) for p in plants}
    if space_id:
        plants = [p for p in plants if locations[p.id] and locations[p.id].id == space_id]
    plants.sort(key=lambda p: (p.group.number if p.group else 9999, p.label))
    return render_template(
        "plants/index.html",
        plants=plants,
        locations=locations,
        spaces=spaces,
        space_id=space_id,
        status=status,
        group_id=group_id,
        strain_id=strain_id,
        statuses=list(PlantStatus),
        groups=db.session.query(Group).order_by(Group.number).all(),
        strains=db.session.query(Strain).order_by(Strain.name).all(),
        counts=sched.plant_counts(db.session.query(Plant).all()),
    )


@bp.route("/new", methods=["GET", "POST"])
def create():
    form = PlantForm()
    _populate_choices(form)
    if request.method == "GET":
        if gid := request.args.get("group", type=int):
            form.group_id.data = gid
        if sid := request.args.get("strain", type=int):
            form.strain_id.data = sid
        form.started_on.data = sched.today()
    if form.validate_on_submit():
        p = Plant()
        form.populate_obj(p)
        p.status = PlantStatus(form.status.data)
        p.group_id = form.group_id.data or None
        p.space_id = form.space_id.data or None
        db.session.add(p)
        db.session.commit()
        flash(f"Added {p.label}.", "success")
        if p.group_id:
            return redirect(url_for("groups.detail", group_id=p.group_id))
        return redirect(url_for("plants.detail", plant_id=p.id))
    return render_template("plants/form.html", form=form, plant=None)


@bp.get("/<int:plant_id>")
def detail(plant_id: int):
    p = db.session.get(Plant, plant_id) or abort(404)
    kill_form = KillPlantForm(ended_on=sched.today())
    move_form = MoveForm()
    _space_choices(move_form)
    spaces = db.session.query(Space).all()
    return render_template(
        "plants/detail.html",
        plant=p,
        kill_form=kill_form,
        move_form=move_form,
        location=spacing.plant_location(p, spaces),
        spans=lifecycle.stage_spans(p, ref=sched.today()),
        history=lifecycle.history(p),
    )


@bp.route("/<int:plant_id>/edit", methods=["GET", "POST"])
def edit(plant_id: int):
    p = db.session.get(Plant, plant_id) or abort(404)
    form = PlantForm(obj=p)
    _populate_choices(form)
    if request.method == "GET":
        form.group_id.data = p.group_id or 0
        form.space_id.data = p.space_id or 0
    if form.validate_on_submit():
        form.populate_obj(p)
        p.status = PlantStatus(form.status.data)
        p.group_id = form.group_id.data or None
        p.space_id = form.space_id.data or None
        db.session.commit()
        flash("Saved changes.", "success")
        return redirect(url_for("plants.detail", plant_id=p.id))
    return render_template("plants/form.html", form=form, plant=p)


@bp.post("/<int:plant_id>/kill")
def kill(plant_id: int):
    p = db.session.get(Plant, plant_id) or abort(404)
    form = KillPlantForm()
    if form.validate_on_submit():
        lifecycle.record(p, PlantStatus.killed, on=form.ended_on.data,
                         note=form.end_reason.data or None)
        p.ended_on = form.ended_on.data
        p.end_reason = form.end_reason.data or None
        db.session.commit()
        flash(f"Marked {p.label} as killed.", "success")
    else:
        flash("Enter a valid date.", "error")
    return redirect(request.referrer or url_for("plants.detail", plant_id=p.id))


@bp.post("/<int:plant_id>/move")
def move(plant_id: int):
    p = db.session.get(Plant, plant_id) or abort(404)
    form = MoveForm()
    _space_choices(form)
    if form.validate_on_submit():
        space = db.session.get(Space, form.space_id.data) or abort(404)
        if spacing.move_plants([p], space, ref=sched.today()):
            db.session.commit()
            flash(f"Moved {p.label} to {space.name}.", "success")
        else:
            flash(f"{p.label} is {p.status.value} and can't be moved.", "error")
    return redirect(request.referrer or url_for("plants.detail", plant_id=p.id))


@bp.post("/<int:plant_id>/status")
def set_status(plant_id: int):
    p = db.session.get(Plant, plant_id) or abort(404)
    try:
        target = PlantStatus(request.form["status"])
    except (KeyError, ValueError):
        abort(400)
    today = sched.today()
    if target == PlantStatus.flowering and p.flower_start is None:
        lifecycle.set_flip([p], today, note="Marked flowering.")
    else:
        lifecycle.record(p, target, on=today)
    if target in (PlantStatus.harvested, PlantStatus.killed) and not p.ended_on:
        p.ended_on = today
    db.session.commit()
    flash(f"{p.label} is now {p.status.value}.", "success")
    return redirect(request.referrer or url_for("plants.detail", plant_id=p.id))


@bp.post("/<int:plant_id>/delete")
def delete(plant_id: int):
    p = db.session.get(Plant, plant_id) or abort(404)
    gid = p.group_id
    db.session.delete(p)
    db.session.commit()
    flash(f"Deleted {p.label}.", "success")
    return redirect(url_for("groups.detail", group_id=gid) if gid else url_for("plants.index"))
