from __future__ import annotations

from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)

from ..extensions import db
from ..forms import JournalForm
from ..models import TASKS, JournalEntry, Space
from ..services import photos
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


@bp.get("/photo/<name>")
def photo(name: str):
    """Serve a stored photo. send_from_directory refuses anything outside the folder."""
    return send_from_directory(photos.upload_dir(), name)


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
            photo_path=photos.save(form.photo.data),
        )
        db.session.add(j)
        db.session.commit()
        where = f" · {j.space.name}" if j.space else ""
        flash(f"Logged: {j.title}{where}.", "success")
    else:
        # Say what was actually wrong — "images only" beats a generic nudge.
        reasons = [m for messages in form.errors.values() for m in messages]
        flash(reasons[0] if reasons else "Tick a task, or write a note.", "error")
    return redirect(request.referrer or url_for("dashboard.index"))


@bp.route("/new", methods=["GET", "POST"])
def create():
    form = JournalForm(entry_date=sched.today())
    _choices(form)
    if request.method == "GET":
        if sid := request.args.get("space", type=int):
            form.space_id.data = sid
    if form.validate_on_submit():
        j = JournalEntry(
            entry_date=form.entry_date.data,
            space_id=form.space_id.data or None,
            title=form.derived_title,
            body=form.body.data or None,
            tasks=form.tasks_csv,
            photo_path=photos.save(form.photo.data),
        )
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
        j.entry_date = form.entry_date.data
        j.title = form.derived_title
        j.body = form.body.data or None
        j.tasks = form.tasks_csv
        j.space_id = form.space_id.data or None
        if replacement := photos.save(form.photo.data):
            photos.delete(j.photo_path)
            j.photo_path = replacement
        elif request.form.get("remove_photo"):
            photos.delete(j.photo_path)
            j.photo_path = None
        db.session.commit()
        flash("Saved changes.", "success")
        return redirect(url_for("journal.index"))
    return render_template("journal/form.html", form=form, entry=j)


@bp.post("/<int:entry_id>/delete")
def delete(entry_id: int):
    j = db.session.get(JournalEntry, entry_id) or abort(404)
    photos.delete(j.photo_path)
    db.session.delete(j)
    db.session.commit()
    flash("Deleted entry.", "success")
    return redirect(request.referrer or url_for("journal.index"))
