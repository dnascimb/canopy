from __future__ import annotations

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from ..extensions import db
from ..forms import JournalForm
from ..models import TASKS, Group, JournalEntry, Plant
from ..services import scheduling as sched

bp = Blueprint("journal", __name__)


def _choices(form: JournalForm) -> None:
    form.group_id.choices = [(0, "— none —")] + [
        (g.id, g.label) for g in db.session.query(Group).order_by(Group.number)
    ]
    form.plant_id.choices = [(0, "— none —")] + [
        (p.id, f"{p.label} ({p.group.label})" if p.group else p.label)
        for p in db.session.query(Plant).order_by(Plant.label)
    ]


@bp.get("/")
def index():
    group_id = request.args.get("group", type=int)
    task = request.args.get("task", "")
    q = db.session.query(JournalEntry)
    if group_id:
        q = q.filter(JournalEntry.group_id == group_id)
    entries = q.order_by(JournalEntry.entry_date.desc(), JournalEntry.id.desc()).all()
    if task:
        entries = [e for e in entries if task in e.task_list]
    return render_template(
        "journal/index.html",
        entries=entries,
        group_id=group_id,
        task=task,
        tasks=TASKS,
        groups=db.session.query(Group).order_by(Group.number).all(),
    )


@bp.post("/quick")
def quick():
    """One-form daily log from the dashboard: date, group, task checkboxes, optional note."""
    form = JournalForm()
    _choices(form)
    if form.validate_on_submit():
        j = JournalEntry(
            entry_date=form.entry_date.data,
            group_id=form.group_id.data or None,
            plant_id=form.plant_id.data or None,
            title=form.derived_title,
            body=form.body.data or None,
            tasks=form.tasks_csv,
        )
        db.session.add(j)
        db.session.commit()
        flash(f"Logged: {j.title}.", "success")
    else:
        flash("Tick at least one task or add a title.", "error")
    return redirect(request.referrer or url_for("dashboard.index"))


@bp.route("/new", methods=["GET", "POST"])
def create():
    form = JournalForm(entry_date=sched.today())
    _choices(form)
    if request.method == "GET":
        if gid := request.args.get("group", type=int):
            form.group_id.data = gid
    if form.validate_on_submit():
        j = JournalEntry()
        form.populate_obj(j)
        j.title = form.derived_title
        j.tasks = form.tasks_csv
        j.group_id = form.group_id.data or None
        j.plant_id = form.plant_id.data or None
        db.session.add(j)
        db.session.commit()
        flash("Journal entry added.", "success")
        return redirect(url_for("journal.index"))
    return render_template("journal/form.html", form=form, entry=None)


@bp.route("/<int:entry_id>/edit", methods=["GET", "POST"])
def edit(entry_id: int):
    j = db.session.get(JournalEntry, entry_id) or abort(404)
    form = JournalForm(obj=j)
    _choices(form)
    if request.method == "GET":
        form.group_id.data = j.group_id or 0
        form.plant_id.data = j.plant_id or 0
        form.tasks.data = j.task_list
    if form.validate_on_submit():
        form.populate_obj(j)
        j.title = form.derived_title
        j.tasks = form.tasks_csv
        j.group_id = form.group_id.data or None
        j.plant_id = form.plant_id.data or None
        db.session.commit()
        flash("Saved changes.", "success")
        return redirect(url_for("journal.index"))
    return render_template("journal/form.html", form=form, entry=j)


@bp.post("/<int:entry_id>/delete")
def delete(entry_id: int):
    j = db.session.get(JournalEntry, entry_id) or abort(404)
    db.session.delete(j)
    db.session.commit()
    flash("Deleted entry.", "success")
    return redirect(request.referrer or url_for("journal.index"))
