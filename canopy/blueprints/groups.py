from __future__ import annotations

from datetime import date

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from ..extensions import db
from ..forms import GroupForm, HarvestForm, JournalForm, MoveForm
from ..models import (
    TASKS,
    Group,
    GroupStatus,
    Harvest,
    JournalEntry,
    PlantStatus,
    Space,
    SpaceStage,
    next_group_color,
)
from ..services import scheduling as sched
from ..services import spacing

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
            form.populate_obj(g)
            g.status = GroupStatus(form.status.data)
            g.space_id = form.space_id.data or None
            g.color = form.color.data or next_group_color(db.session.query(Group).count())
            db.session.add(g)
            db.session.commit()
            flash(f"Created {g.label}.", "success")
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
    journal_form.group_id.choices = [(g.id, g.label)]
    journal_form.plant_id.choices = [(0, "Group-level")] + [(p.id, p.label) for p in g.plants]
    move_form = MoveForm()
    spaces = db.session.query(Space).order_by(Space.id).all()
    move_form.space_id.choices = [(s.id, f"{s.name} · {s.stage.value}") for s in spaces]
    locations = {p.id: spacing.plant_location(p, spaces) for p in g.plants}
    last_done = _last_tasks(g)
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
        last_done=last_done,
        need_sqft=spacing.group_footprint(g, SpaceStage.flowering),
        PlantStatus=PlantStatus,
        GroupStatus=GroupStatus,
        dry_total=sum(h.dry_weight_g or 0 for h in g.harvests),
        wet_total=sum(h.wet_weight_g or 0 for h in g.harvests),
    )


def _last_tasks(g: Group) -> list[tuple[str, date]]:
    """Most recent date each common task was logged for the group."""
    seen: dict[str, date] = {}
    for j in sorted(g.journal_entries, key=lambda j: j.entry_date, reverse=True):
        for t in j.task_list:
            seen.setdefault(t, j.entry_date)
    return [(TASKS[k], seen[k]) for k in TASKS if k in seen]


@bp.post("/<int:group_id>/move")
def move(group_id: int):
    """Move every living plant in the group to a space (and align their status)."""
    g = db.session.get(Group, group_id) or abort(404)
    form = MoveForm()
    form.space_id.choices = [(s.id, s.name) for s in db.session.query(Space)]
    if form.validate_on_submit():
        space = db.session.get(Space, form.space_id.data) or abort(404)
        n = spacing.move_plants(g.living_plants, space)
        if space.stage == SpaceStage.flowering:
            g.space_id = space.id
            if g.status in (GroupStatus.planned, GroupStatus.vegetative):
                g.status = GroupStatus.flowering
                g.flower_start = g.flower_start or sched.today()
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
    if form.validate_on_submit():
        clash = (
            db.session.query(Group)
            .filter(Group.number == form.number.data, Group.id != g.id)
            .first()
        )
        if clash:
            form.number.errors.append("That group number is already in use.")
        else:
            form.populate_obj(g)
            g.status = GroupStatus(form.status.data)
            g.space_id = form.space_id.data or None
            db.session.commit()
            flash("Saved changes.", "success")
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
        g.flower_start = suggestion.on
        if suggestion.space and not g.space_id:
            g.space_id = suggestion.space.id
        if g.status == GroupStatus.planned:
            g.status = GroupStatus.vegetative
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
    if g.status == GroupStatus.flowering:
        for p in g.living_plants:
            p.status = PlantStatus.flowering
        if g.flower_start is None:
            g.flower_start = sched.today()
    elif g.status in (GroupStatus.drying, GroupStatus.done):
        for p in g.living_plants:
            if p.status == PlantStatus.flowering:
                p.status = PlantStatus.harvested
                p.ended_on = p.ended_on or g.flower_end or sched.today()
    db.session.commit()
    flash(f"{g.label} is now {g.status.value}.", "success")
    return redirect(url_for("groups.detail", group_id=g.id))


@bp.post("/<int:group_id>/harvest")
def add_harvest(group_id: int):
    g = db.session.get(Group, group_id) or abort(404)
    form = HarvestForm()
    form.plant_id.choices = [(0, "Whole group")] + [(p.id, p.label) for p in g.living_plants]
    if form.validate_on_submit():
        h = Harvest(group=g, plant_id=form.plant_id.data or None)
        form.populate_obj(h)
        h.plant_id = form.plant_id.data or None
        db.session.add(h)
        db.session.commit()
        flash("Harvest recorded.", "success")
    else:
        flash("Check the harvest form — a valid date is required.", "error")
    return redirect(url_for("groups.detail", group_id=g.id))


@bp.post("/<int:group_id>/journal")
def add_journal(group_id: int):
    g = db.session.get(Group, group_id) or abort(404)
    form = JournalForm()
    form.group_id.choices = [(g.id, g.label)]
    form.plant_id.choices = [(0, "Group-level")] + [(p.id, p.label) for p in g.plants]
    if form.validate_on_submit():
        j = JournalEntry(
            group_id=g.id,
            plant_id=form.plant_id.data or None,
            entry_date=form.entry_date.data,
            title=form.derived_title,
            body=form.body.data or None,
            tasks=form.tasks_csv,
        )
        db.session.add(j)
        db.session.commit()
        flash("Journal entry added.", "success")
    else:
        flash("Journal entries need a date and either a title or a ticked task.", "error")
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
