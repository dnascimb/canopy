from __future__ import annotations

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from sqlalchemy import func

from ..extensions import db
from ..forms import StrainForm
from ..models import Expression, Plant, PlantSize, PlantStatus, SeedType, Strain
from ..services import inventory

bp = Blueprint("strains", __name__)


@bp.get("/")
def index():
    """Every strain, with the ones outside the filter rendered hidden.

    The page ships the whole inventory so static/js/inventory.js can narrow it in place as
    the controls change, with no round trip per keystroke. See services/inventory.py.
    """
    f = inventory.StrainFilter.from_args(request.args)
    # Ascending by default. Case-insensitive so this matches the locale-aware order
    # sortable.js re-applies client-side; SQLite's default collation is not.
    strains = db.session.query(Strain).order_by(func.lower(Strain.name)).all()
    # One grouped count rather than loading every strain's plants to take a length.
    plant_counts = dict(
        db.session.query(Plant.strain_id, func.count(Plant.id)).group_by(Plant.strain_id)
    )
    breeders = [
        b for (b,) in db.session.query(Strain.breeder).distinct().order_by(Strain.breeder) if b
    ]
    return render_template(
        "strains/index.html",
        strains=strains,
        matching=inventory.matching_ids(f),
        plant_counts=plant_counts,
        q=f.q,
        seed_type=f.seed_type,
        breeder=f.breeder,
        days=f.days,
        expression=f.expression,
        seed_types=list(SeedType),
        expressions=list(Expression),
        breeders=breeders,
        day_ranges=inventory.DAY_RANGES,
        no_breeder=inventory.NO_BREEDER,
        filtered=f.active,
    )


@bp.route("/new", methods=["GET", "POST"])
def create():
    form = StrainForm()
    if form.validate_on_submit():
        s = Strain()
        form.populate_obj(s)
        s.seed_type = SeedType(form.seed_type.data)
        s.size = PlantSize(form.size.data)
        s.expression = Expression(form.expression.data) if form.expression.data else None
        db.session.add(s)
        db.session.commit()
        flash(f"Added {s.name} to inventory.", "success")
        return redirect(url_for("strains.detail", strain_id=s.id))
    return render_template("strains/form.html", form=form, strain=None)


@bp.get("/<int:strain_id>")
def detail(strain_id: int):
    s = db.session.get(Strain, strain_id) or abort(404)
    plants = sorted(s.plants, key=lambda p: (p.group.number if p.group else 9999, p.label))
    return render_template("strains/detail.html", strain=s, plants=plants, PlantStatus=PlantStatus)


@bp.route("/<int:strain_id>/edit", methods=["GET", "POST"])
def edit(strain_id: int):
    s = db.session.get(Strain, strain_id) or abort(404)
    form = StrainForm(obj=s)
    if form.validate_on_submit():
        form.populate_obj(s)
        s.seed_type = SeedType(form.seed_type.data)
        s.size = PlantSize(form.size.data)
        s.expression = Expression(form.expression.data) if form.expression.data else None
        db.session.commit()
        flash("Saved changes.", "success")
        return redirect(url_for("strains.detail", strain_id=s.id))
    return render_template("strains/form.html", form=form, strain=s)


@bp.post("/<int:strain_id>/delete")
def delete(strain_id: int):
    s = db.session.get(Strain, strain_id) or abort(404)
    if s.plants:
        flash("This strain has plants recorded; remove those first.", "error")
        return redirect(url_for("strains.detail", strain_id=s.id))
    db.session.delete(s)
    db.session.commit()
    flash(f"Deleted {s.name}.", "success")
    return redirect(url_for("strains.index"))


@bp.post("/<int:strain_id>/adjust")
def adjust(strain_id: int):
    """Quick +/- on seed count from the inventory table."""
    s = db.session.get(Strain, strain_id) or abort(404)
    delta = int(request.form.get("delta", 0))
    s.seeds_on_hand = max(0, s.seeds_on_hand + delta)
    db.session.commit()
    return redirect(request.referrer or url_for("strains.index"))
