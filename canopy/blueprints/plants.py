from __future__ import annotations

import re

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
from markupsafe import Markup, escape

from ..extensions import db
from ..forms import KillPlantForm, MoveForm, PlantForm, TakeCuttingsForm
from ..models import Group, Plant, PlantStatus, SeedType, Space, SpaceStage, Strain
from ..services import lifecycle, spacing
from ..services import scheduling as sched

bp = Blueprint("plants", __name__)


def _strain_names() -> list[str]:
    return [s.name for s in db.session.query(Strain).order_by(Strain.name)]


def _resolve_strain(
    name: str, status: PlantStatus, lineage: str | None = None
) -> tuple[Strain, bool]:
    """Find the strain by name, or start one. Returns (strain, was_created).

    A pack of seeds or a cutting from outside is routinely a strain the inventory has
    never seen, so typing a new name here adds it rather than sending you elsewhere.
    """
    name = (name or "").strip()
    existing = db.session.query(Strain).filter(db.func.lower(Strain.name) == name.lower()).first()
    lineage = (lineage or "").strip() or None
    if existing:
        # Fill a blank rather than overwrite: the inventory entry is the authority.
        if lineage and not existing.lineage:
            existing.lineage = lineage
        return existing, False
    fresh = Strain(
        name=name,
        lineage=lineage,
        # A cutting is a clone; anything else came from seed until told otherwise.
        seed_type=SeedType.clone if status == PlantStatus.clone else SeedType.regular,
        flower_days=current_app.config.get("DEFAULT_FLOWER_DAYS", 70),
    )
    db.session.add(fresh)
    db.session.flush()
    return fresh, True


def _parent_choices(form: PlantForm, exclude: int | None = None) -> None:
    rows = db.session.query(Plant).filter(Plant.status != PlantStatus.killed).order_by(Plant.label)
    form.parent_id.choices = [(0, "— not a cutting —")] + [
        (p.id, f"{p.label} · {p.strain.name}") for p in rows if p.id != exclude
    ]


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
    plants.sort(key=lambda p: p.label.lower())
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
    _parent_choices(form)
    if request.method == "GET":
        if pid := request.args.get("parent", type=int):
            mother = db.session.get(Plant, pid)
            if mother:
                form.parent_id.data = mother.id
                form.strain.data = mother.strain.name
                form.status.data = PlantStatus.clone.value
        if gid := request.args.get("group", type=int):
            form.group_id.data = gid
        if sid := request.args.get("strain", type=int):
            known = db.session.get(Strain, sid)
            form.strain.data = known.name if known else None
        form.started_on.data = sched.today()
    if form.validate_on_submit():
        status = PlantStatus(form.status.data)
        strain, created = _resolve_strain(form.strain.data, status, form.lineage.data)
        p = Plant(
            label=form.label.data,
            strain=strain,
            status=status,
            group_id=form.group_id.data or None,
            space_id=form.space_id.data or None,
            parent_id=form.parent_id.data or None,
            started_on=form.started_on.data,
            notes=form.notes.data or None,
        )
        db.session.add(p)
        db.session.flush()
        lifecycle.born(
            p,
            on=p.started_on or sched.today(),
            note=f"Cutting from {p.parent.label}." if p.parent else "Added.",
        )
        db.session.commit()
        flash(f"Added {p.label}.", "success")
        if created:
            flash(
                Markup(
                    f"Added {escape(strain.name)} to the inventory too — "
                    f'<a href="{url_for("strains.edit", strain_id=strain.id)}">'
                    "fill in its lineage and breeder</a>."
                ),
                "success",
            )
        if p.group_id:
            return redirect(url_for("groups.detail", group_id=p.group_id))
        return redirect(url_for("plants.detail", plant_id=p.id))
    return render_template("plants/form.html", form=form, plant=None, strain_names=_strain_names())


@bp.get("/<int:plant_id>")
def detail(plant_id: int):
    p = db.session.get(Plant, plant_id) or abort(404)
    kill_form = KillPlantForm(ended_on=sched.today())
    move_form = MoveForm()
    _space_choices(move_form)
    spaces = db.session.query(Space).all()
    cuttings_form = TakeCuttingsForm(taken_on=sched.today())
    cuttings_form.space_id.choices = [(0, "— by stage (automatic) —")] + [
        (s.id, f"{s.name} · {s.stage.value}") for s in sorted(spaces, key=lambda s: s.id)
    ]
    clone_shelf = spacing.default_space(SpaceStage.clone, spaces)
    if clone_shelf:
        cuttings_form.space_id.data = clone_shelf.id
    return render_template(
        "plants/detail.html",
        plant=p,
        kill_form=kill_form,
        move_form=move_form,
        location=spacing.plant_location(p, spaces),
        cuttings_form=cuttings_form,
        spans=lifecycle.stage_spans(p, ref=sched.today()),
        history=lifecycle.history(p),
    )


@bp.route("/<int:plant_id>/edit", methods=["GET", "POST"])
def edit(plant_id: int):
    p = db.session.get(Plant, plant_id) or abort(404)
    form = PlantForm(obj=p)
    _populate_choices(form)
    _parent_choices(form, exclude=p.id)
    if request.method == "GET":
        form.group_id.data = p.group_id or 0
        form.space_id.data = p.space_id or 0
        form.parent_id.data = p.parent_id or 0
        form.strain.data = p.strain.name
        form.lineage.data = p.strain.lineage
    if form.validate_on_submit():
        status = PlantStatus(form.status.data)
        strain, created = _resolve_strain(form.strain.data, status, form.lineage.data)
        p.parent_id = form.parent_id.data or None
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
            flash(
                Markup(
                    f"Added {escape(strain.name)} to the inventory too — "
                    f'<a href="{url_for("strains.edit", strain_id=strain.id)}">'
                    "fill in its lineage and breeder</a>."
                ),
                "success",
            )
        flash("Saved changes.", "success")
        return redirect(url_for("plants.detail", plant_id=p.id))
    return render_template("plants/form.html", form=form, plant=p, strain_names=_strain_names())


@bp.post("/<int:plant_id>/kill")
def kill(plant_id: int):
    p = db.session.get(Plant, plant_id) or abort(404)
    form = KillPlantForm()
    if form.validate_on_submit():
        lifecycle.record(
            p, PlantStatus.killed, on=form.ended_on.data, note=form.end_reason.data or None
        )
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
    # Drying deliberately does not set ended_on: the plant is cut but the run is not
    # over until it comes out of the dry and is marked harvested.
    settled = lifecycle.settle_group(p.group)
    db.session.commit()
    flash(
        f"{p.label} is now {p.status.value}." + (f" {p.group.label} is drying." if settled else ""),
        "success",
    )
    return redirect(request.referrer or url_for("plants.detail", plant_id=p.id))


@bp.post("/<int:plant_id>/cuttings")
def take_cuttings(plant_id: int):
    """Take N cuttings off one plant, each linked back to it."""
    mother = db.session.get(Plant, plant_id) or abort(404)
    form = TakeCuttingsForm()
    spaces = db.session.query(Space).order_by(Space.id).all()
    form.space_id.choices = [(0, "— by stage (automatic) —")] + [
        (s.id, f"{s.name} · {s.stage.value}") for s in spaces
    ]
    if not form.validate_on_submit():
        flash("Tell me how many cuttings and when they were taken.", "error")
        return redirect(url_for("plants.detail", plant_id=mother.id))
    if not mother.is_alive or mother.status in (PlantStatus.drying, PlantStatus.harvested):
        flash(f"{mother.label} is {mother.status.value} — nothing to cut.", "error")
        return redirect(url_for("plants.detail", plant_id=mother.id))

    # Continue the mother's own numbering rather than restarting at 1.
    used = [
        int(m.group(1))
        for c in mother.cuttings
        if (m := re.fullmatch(rf"{re.escape(mother.label)} c(\d+)", c.label))
    ]
    start = max(used, default=0) + 1
    space = db.session.get(Space, form.space_id.data) if form.space_id.data else None

    made = []
    for i in range(form.count.data):
        cut = Plant(
            label=f"{mother.label} c{start + i}",
            strain=mother.strain,
            parent=mother,
            status=PlantStatus.clone,
            space=space,
            started_on=form.taken_on.data,
            notes=f"Cutting taken from {mother.label} on {form.taken_on.data:%d %b %Y}.",
        )
        db.session.add(cut)
        db.session.flush()
        lifecycle.born(cut, on=form.taken_on.data, space=space, note=f"Cut from {mother.label}.")
        made.append(cut)
    db.session.commit()

    where = f" into {space.name}" if space else ""
    flash(
        f"Took {len(made)} cutting{'s' if len(made) != 1 else ''} off {mother.label}"
        f"{where}: {made[0].label} to {made[-1].label}.",
        "success",
    )
    return redirect(url_for("plants.detail", plant_id=mother.id))


@bp.post("/<int:plant_id>/delete")
def delete(plant_id: int):
    p = db.session.get(Plant, plant_id) or abort(404)
    gid = p.group_id
    db.session.delete(p)
    db.session.commit()
    flash(f"Deleted {p.label}.", "success")
    return redirect(url_for("groups.detail", group_id=gid) if gid else url_for("plants.index"))
