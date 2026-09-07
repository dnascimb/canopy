from __future__ import annotations

import json

from flask import Blueprint, Response, flash, redirect, render_template, request, url_for

from ..extensions import db
from ..forms import ImportForm
from ..models import Group, Plant, Space
from ..services import scheduling as sched
from ..services import transfer

bp = Blueprint("schedule", __name__)


@bp.get("/")
def index():
    ref = sched.today()
    groups = db.session.query(Group).all()
    spaces = db.session.query(Space).all()
    rows = sched.timeline_rows(groups, ref=ref)
    return render_template(
        "schedule/index.html",
        rows=rows,
        events=sched.events(groups),
        openings=sched.openings(groups, ref=ref),
        conflicts=sched.conflicts(groups, spaces, db.session.query(Plant).all(), ref=ref),
        unscheduled=[g for g in groups if g.flower_start is None],
        ref=ref,
    )


@bp.get("/export.md")
def export_markdown():
    md = sched.markdown_export(db.session.query(Group).all())
    return Response(
        md,
        mimetype="text/markdown; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="canopy-schedule.md"'},
    )


@bp.get("/export.txt")
def export_ascii():
    rows = sched.timeline_rows(db.session.query(Group).all())
    return Response(sched.ascii_timeline(rows), mimetype="text/plain; charset=utf-8")


@bp.get("/print")
def print_view():
    ref = sched.today()
    groups = db.session.query(Group).all()
    rows = sched.timeline_rows(groups, ref=ref)
    return render_template(
        "schedule/print.html",
        rows=rows,
        events=sched.events(groups),
        ascii=sched.ascii_timeline(rows, ref=ref),
        groups=sorted(groups, key=lambda g: g.number),
        ref=ref,
    )


@bp.get("/backup.json")
def backup():
    return Response(
        json.dumps(transfer.dump(), indent=2),
        mimetype="application/json",
        headers={"Content-Disposition": 'attachment; filename="canopy-backup.json"'},
    )


@bp.route("/restore", methods=["GET", "POST"])
def restore():
    form = ImportForm()
    if form.validate_on_submit():
        try:
            payload = json.loads(form.payload.data)
            counts = transfer.load(payload, replace=request.form.get("replace") == "on")
        except (ValueError, KeyError) as exc:
            flash(f"Could not restore: {exc}", "error")
        else:
            summary = ", ".join(f"{v} {k.replace('_', ' ')}" for k, v in counts.items())
            flash(f"Restored {summary}.", "success")
            return redirect(url_for("dashboard.index"))
    return render_template("schedule/restore.html", form=form)
