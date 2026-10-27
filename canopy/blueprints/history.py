from __future__ import annotations

from flask import Blueprint, render_template

from ..extensions import db
from ..models import Plant
from ..services import scheduling as sched

bp = Blueprint("history", __name__)


@bp.get("/")
def index():
    ref = sched.today()
    rows = sched.history_rows(db.session.query(Plant).all(), ref=ref)
    return render_template("history/index.html", rows=rows, ref=ref)
