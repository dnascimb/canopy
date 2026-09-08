from __future__ import annotations

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from ..extensions import db
from ..forms import JournalForm
from ..models import TASKS, JournalEntry, Space
from ..services import scheduling as sched

bp = Blueprint("journal", __name__)


def _choices(form: JournalForm) -> None:
    form.space_id.choices = [(0, "— whole room —")] + [
        (s.id, s.name) for s in db.session.query(Space).order_by(Space.id)
    ]


@bp.get("/")
def index():
    space_id = request.args.get("space", type=int)
    task = request.args.get("task", "")
    q = db.session.query(JournalEntry)
    if space_id:
        q = q.filter(JournalEntry.space_id == space_id)
    entries = q.order_by(JournalEntry.entry_date.desc(), JournalEntry.id.desc()).all()
    if task:
        entries = [e for e in entries if task in e.task_list]
    return render_template(
        "journal/index.html",
        entries=entries,
        space_id=space_id,
        task=task,
        tasks=TASKS,
        spaces=db.session.query(Space).order_by(Space.id).all(),
    )


@bp.post("/quick")
def quick():
    """Daily log from the dashboard: one section per space, ticked and noted."""
    form = JournalForm()
    _choices(form)
    if form.validate_on_submit():
        j = JournalEntry(
            entry_date=form.entry_date.data,
            space_id=form.space_id.data or None,
            title=form.derived_title,
            body=form.body.data or None,
            tasks=form.tasks_csv,
        )
        db.session.add(j)
        db.session.commit()
        where = f" · {j.space.name}" if j.space else ""
        flash(f"Logged: {j.title}{where}.", "success")
    else:
        flash("Tick a task, or write a note.", "error")
    return redirect(request.referrer or url_for("dashboard.index"))


@bp.route("/new", methods=["GET", "POST"])
def create():
    form = JournalForm(entry_date=sched.today())
    _choices(form)
    if request.method == "GET":
        if sid := request.args.get("space", type=int):
            form.space_id.data = sid
    if form.validate_on_submit():
        j = JournalEntry()
        form.populate_obj(j)
        j.title = form.derived_title
        j.tasks = form.tasks_csv
        j.space_id = form.space_id.data or None
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
        form.space_id.data = j.space_id or 0
        form.tasks.data = j.task_list
    if form.validate_on_submit():
        form.populate_obj(j)
        j.title = form.derived_title
        j.tasks = form.tasks_csv
        j.space_id = form.space_id.data or None
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
