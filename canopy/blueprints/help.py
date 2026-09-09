from __future__ import annotations

from flask import Blueprint, render_template

from ..extensions import db
from ..models import Space, SpaceStage
from ..services import spacing

bp = Blueprint("help", __name__)


@bp.get("/")
def index():
    """How to move a plant through its life, named after this garden's own spaces."""
    spaces = sorted(db.session.query(Space).all(), key=lambda s: s.id)
    return render_template(
        "help/index.html",
        spaces=spaces,
        clone_space=spacing.default_space(SpaceStage.clone, spaces),
        veg_space=spacing.default_space(SpaceStage.vegetative, spaces),
        flower_space=spacing.default_space(SpaceStage.flowering, spaces),
    )
