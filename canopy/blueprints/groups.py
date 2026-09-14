from __future__ import annotations

from datetime import date

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from ..extensions import db
from ..forms import GroupForm, HarvestForm, JournalForm, MoveForm
from ..models import (
    Group,
    GroupStatus,
    Harvest,
    JournalEntry,
    Plant,
    PlantStatus,
    Space,
    SpaceStage,
    next_group_color,
)
from ..services import lifecycle, spacing
from ..services import scheduling as sched

bp = Blueprint("groups", __name__)


def _space_choices(form: GroupForm) -> None:
    form.space_id.choices = [(0, "— unassigned —")] + [
        (s.id, s.name) for s in db.session.query(Space).order_by(Space.name)
    ]


@bp.get("/")
def index():
    ref = sched.today()
    groups = db.session.query(Group).all()
    groups.sort(key=lambda g: (g.flower_start or date.max, g.number))
    view = request.args.get("view", "active")
    if view == "active":
        groups = [g for g in groups if g.status not in (GroupStatus.done,)]
    elif view == "done":
        groups = [g for g in groups if g.status == GroupStatus.done]
    return render_template("groups/index.html", groups=groups, view=view, ref=ref)


def _apply(form: GroupForm, g: Group) -> None:
    """Copy the group's own fields. Dates are not among them — see _apply_schedule."""
    g.number = form.number.data
    g.name = form.name.data or None
    g.space_id = form.space_id.data or None
    g.status = GroupStatus(form.status.data)
    g.notes = form.notes.data or None


def _apply_schedule(form: GroupForm, g: Group) -> str | None:
    """Push the form's flip date down onto the plants, which is where it lives.

    Returns a warning when there is nothing to apply it to.
    """
    plants = g.living_plants
    if form.flower_start.data:
        if not plants:
            return f"{g.label} has no plants yet — add some and the flip date will apply."
        lifecycle.set_flip(
            plants,
            form.flower_start.data,
            days=form.flower_days.data,
            space=g.space,
            note=f"Set on {g.label}.",
        )
    else:
        lifecycle.clear_flip(plants)
        for p in plants:
            p.flower_days_override = form.flower_days.data
    return None


@bp.route("/new", methods=["GET", "POST"])
def create():
    form = GroupForm()
    _space_choices(form)
    if request.method == "GET":
        last = db.session.query(db.func.max(Group.number)).scalar() or 0
        form.number.data = last + 1
        form.color.data = next_group_color(db.session.query(Group).count())
        if start := request.args.get("start"):
            form.flower_start.data = date.fromisoformat(start)
        if sid := request.args.get("space", type=int):
            form.space_id.data = sid
    if form.validate_on_submit():
        if db.session.query(Group).filter_by(number=form.number.data).first():
            form.number.errors.append("That group number is already in use.")
        else:
            g = Group()
            _apply(form, g)
            g.color = form.color.data or next_group_color(db.session.query(Group).count())
            db.session.add(g)
            db.session.flush()
            warning = _apply_schedule(form, g)
            db.session.commit()
            flash(f"Created {g.label}.", "success")
            if warning:
                flash(warning, "error")
            return redirect(url_for("groups.detail", group_id=g.id))
    return render_template("groups/form.html", form=form, group=None)


@bp.get("/<int:group_id>")
def detail(group_id: int):
    g = db.session.get(Group, group_id) or abort(404)
    ref = sched.today()
    all_groups = db.session.query(Group).all()
    harvest_form = HarvestForm(harvested_on=g.flower_end or ref)
    harvest_form.plant_id.choices = [(0, "Whole group")] + [
        (p.id, p.label) for p in g.living_plants
    ]
    journal_form = JournalForm(entry_date=ref)
    journal_form.space_id.choices = [(0, "")]
    move_form = MoveForm()
    spaces = db.session.query(Space).order_by(Space.id).all()
    move_form.space_id.choices = [(s.id, f"{s.name} · {s.stage.value}") for s in spaces]
    locations = {p.id: spacing.plant_location(p, spaces) for p in g.plants}
    return render_template(
        "groups/detail.html",
        group=g,
        ref=ref,
        implied=sched.implied_status(g, ref),
        suggestion=sched.suggest_start(g, all_groups, ref=ref) if g.flower_start is None else None,
        harvest_form=harvest_form,
        journal_form=journal_form,
        move_form=move_form,
        locations=locations,
        need_sqft=spacing.group_footprint(g, SpaceStage.flowering),
        PlantStatus=PlantStatus,
        GroupStatus=GroupStatus,
    )


@bp.post("/<int:group_id>/move")
def move(group_id: int):
    """Move every living plant in the group to a space (and align their status)."""
    g = db.session.get(Group, group_id) or abort(404)
    form = MoveForm()
    form.space_id.choices = [(s.id, s.name) for s in db.session.query(Space)]
    if form.validate_on_submit():
        space = db.session.get(Space, form.space_id.data) or abort(404)
        n = spacing.move_plants(g.living_plants, space, ref=sched.today())
        if space.stage == SpaceStage.flowering:
            g.space_id = space.id
            g.status = GroupStatus.flowering
        elif space.stage == SpaceStage.vegetative and g.status == GroupStatus.planned:
            g.status = GroupStatus.vegetative
        db.session.commit()
        flash(f"Moved {n} plant{'s' if n != 1 else ''} to {space.name}.", "success")
    return redirect(url_for("groups.detail", group_id=g.id))


@bp.route("/<int:group_id>/edit", methods=["GET", "POST"])
def edit(group_id: int):
    g = db.session.get(Group, group_id) or abort(404)
    form = GroupForm(obj=g)
    _space_choices(form)
    if request.method == "GET":
        form.space_id.data = g.space_id or 0
        form.status.data = g.status.value
        form.flower_start.data = g.flower_start
        form.flower_days.data = g.flower_days
    if form.validate_on_submit():
        clash = (
            db.session.query(Group)
            .filter(Group.number == form.number.data, Group.id != g.id)
            .first()
        )
        if clash:
            form.number.errors.append("That group number is already in use.")
        else:
            _apply(form, g)
            g.color = form.color.data or g.color
            warning = _apply_schedule(form, g)
            db.session.commit()
            flash("Saved changes.", "success")
            if warning:
                flash(warning, "error")
            return redirect(url_for("groups.detail", group_id=g.id))
    return render_template("groups/form.html", form=form, group=g)


@bp.post("/<int:group_id>/schedule")
def schedule(group_id: int):
    """Accept the suggested opening: set flower_start (and space) in one click."""
    g = db.session.get(Group, group_id) or abort(404)
    suggestion = sched.suggest_start(g, db.session.query(Group).all())
    if suggestion is None:
        flash("No opening available to suggest.", "error")
    else:
        if suggestion.space and not g.space_id:
            g.space_id = suggestion.space.id
        lifecycle.set_flip(
            g.living_plants,
            suggestion.on,
            space=g.space,
            note=f"Scheduled into the opening left by {suggestion.freed_by.label}.",
        )
        g.status = GroupStatus.flowering
        db.session.commit()
        flash(f"Scheduled {g.label} to flip on {suggestion.on:%b %d}.", "success")
    return redirect(url_for("groups.detail", group_id=g.id))


@bp.post("/<int:group_id>/status")
def set_status(group_id: int):
    g = db.session.get(Group, group_id) or abort(404)
    try:
        g.status = GroupStatus(request.form["status"])
    except (KeyError, ValueError):
        abort(400)
    today = sched.today()
    if g.status == GroupStatus.flowering:
        # Keep any flip the plants already have; only the unflipped start today.
        unflipped = [p for p in g.living_plants if p.flower_start is None]
        lifecycle.set_flip(unflipped, today, space=g.space, note=f"{g.label} marked flowering.")
        for p in g.living_plants:
            lifecycle.record(p, PlantStatus.flowering, on=today)
    elif g.status in (GroupStatus.drying, GroupStatus.done):
        for p in g.living_plants:
            if p.status == PlantStatus.flowering:
                end = p.flower_end or today
                lifecycle.record(
                    p, PlantStatus.harvested, on=end, note=f"{g.label} marked {g.status.value}."
                )
                p.ended_on = p.ended_on or end
    db.session.commit()
    flash(f"{g.label} is now {g.status.value}.", "success")
    return redirect(url_for("groups.detail", group_id=g.id))


@bp.post("/<int:group_id>/harvest")
def add_harvest(group_id: int):
    g = db.session.get(Group, group_id) or abort(404)
    form = HarvestForm()
    form.plant_id.choices = [(0, "Whole group")] + [(p.id, p.label) for p in g.living_plants]
    if form.validate_on_submit():
        on = form.harvested_on.data
        h = Harvest(
            group=g,
            plant_id=form.plant_id.data or None,
            harvested_on=on,
            notes=form.notes.data or None,
        )
        db.session.add(h)

        # Recording a harvest *is* harvesting: the plants it covers come down, and the
        # group starts drying once nothing is left in flower. Previously this only
        # raised a "the calendar says it should be drying" note and left it to you.
        # h.plant is not populated until the flush, so resolve it directly.
        one = db.session.get(Plant, h.plant_id) if h.plant_id else None
        covered = [one] if one else list(g.living_plants)
        picked = 0
        for p in covered:
            if p.status == PlantStatus.flowering:
                lifecycle.record(p, PlantStatus.harvested, on=on, note=f"Harvested from {g.label}.")
                p.ended_on = p.ended_on or on
                picked += 1

        moved = lifecycle.settle_group(g)
        db.session.commit()

        note = f"Harvest recorded — {picked} plant{'s' if picked != 1 else ''} down"
        flash(f"{note}, {g.label} is now drying." if moved else f"{note}.", "success")
    else:
        flash("Check the harvest form — a valid date is required.", "error")
    return redirect(url_for("groups.detail", group_id=g.id))


@bp.post("/<int:group_id>/journal")
def add_journal(group_id: int):
    g = db.session.get(Group, group_id) or abort(404)
    form = JournalForm()
    form.space_id.choices = [(0, "")]
    if form.validate_on_submit():
        j = JournalEntry(
            group_id=g.id,  # the URL says which group; there is nothing to pick
            entry_date=form.entry_date.data,
            title=form.derived_title,
            body=form.body.data or None,
            tasks=form.tasks_csv,
        )
        db.session.add(j)
        db.session.commit()
        flash("Journal entry added.", "success")
    else:
        flash("Journal entries need a date, and a task, title or note.", "error")
    return redirect(url_for("groups.detail", group_id=g.id) + "#journal")


@bp.post("/<int:group_id>/delete")
def delete(group_id: int):
    g = db.session.get(Group, group_id) or abort(404)
    for p in g.plants:
        p.group_id = None
    db.session.delete(g)
    db.session.commit()
    flash(f"Deleted {g.label}. Its plants were kept and unassigned.", "success")
    return redirect(url_for("groups.index"))
