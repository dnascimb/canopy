from __future__ import annotations

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)

from ..extensions import db
from ..forms import KillPlantForm, MoveForm, PlantForm
from ..models import Group, Plant, PlantStatus, SeedType, Space, Strain
from ..services import lifecycle, spacing
from ..services import scheduling as sched

bp = Blueprint("plants", __name__)


def _strain_names() -> list[str]:
    return [s.name for s in db.session.query(Strain).order_by(Strain.name)]


def _resolve_strain(name: str, status: PlantStatus) -> tuple[Strain, bool]:
    """Find the strain by name, or start one. Returns (strain, was_created).

    A pack of seeds or a cutting from outside is routinely a strain the inventory has
    never seen, so typing a new name here adds it rather than sending you elsewhere.
    """
    name = (name or "").strip()
    existing = (
        db.session.query(Strain).filter(db.func.lower(Strain.name) == name.lower()).first()
    )
    if existing:
        return existing, False
    fresh = Strain(
        name=name,
        # A cutting is a clone; anything else came from seed until told otherwise.
        seed_type=SeedType.clone if status == PlantStatus.clone else SeedType.regular,
        flower_days=current_app.config.get("DEFAULT_FLOWER_DAYS", 70),
    )
    db.session.add(fresh)
    db.session.flush()
    return fresh, True


def _populate_choices(form: PlantForm) -> None:
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
            known = db.session.get(Strain, sid)
            form.strain.data = known.name if known else None
        form.started_on.data = sched.today()
    if form.validate_on_submit():
        status = PlantStatus(form.status.data)
        strain, created = _resolve_strain(form.strain.data, status)
        p = Plant(
            label=form.label.data,
            strain=strain,
            status=status,
            group_id=form.group_id.data or None,
            space_id=form.space_id.data or None,
            started_on=form.started_on.data,
            notes=form.notes.data or None,
        )
        db.session.add(p)
        db.session.commit()
        flash(f"Added {p.label}.", "success")
        if created:
            flash(f"Added {strain.name} to the inventory too.", "success")
        if p.group_id:
            return redirect(url_for("groups.detail", group_id=p.group_id))
        return redirect(url_for("plants.detail", plant_id=p.id))
    return render_template(
        "plants/form.html", form=form, plant=None, strain_names=_strain_names()
    )


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
        form.strain.data = p.strain.name
    if form.validate_on_submit():
        status = PlantStatus(form.status.data)
        strain, created = _resolve_strain(form.strain.data, status)
        p.label = form.label.data
        p.strain = strain
        p.status = status
        p.group_id = form.group_id.data or None
        p.space_id = form.space_id.data or None
        p.started_on = form.started_on.data
        p.ended_on = form.ended_on.data
        p.end_reason = form.end_reason.data or None
        p.notes = form.notes.data or None
        db.session.commit()
        if created:
            flash(f"Added {strain.name} to the inventory too.", "success")
        flash("Saved changes.", "success")
        return redirect(url_for("plants.detail", plant_id=p.id))
    return render_template("plants/form.html", form=form, plant=p, strain_names=_strain_names())


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
