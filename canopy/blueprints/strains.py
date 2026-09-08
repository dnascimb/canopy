from __future__ import annotations

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from sqlalchemy import func

from ..extensions import db
from ..forms import StrainForm
from ..models import Expression, PlantSize, PlantStatus, SeedType, Strain

bp = Blueprint("strains", __name__)

NO_BREEDER = "__none__"

# Flower-length buckets, week-aligned because that is how flower time is quoted.
DAY_RANGES: dict[str, tuple[str, int | None, int | None]] = {
    "-56": ("8 weeks or less", None, 56),
    "57-63": ("9 weeks (57-63)", 57, 63),
    "64-70": ("10 weeks (64-70)", 64, 70),
    "71-77": ("11 weeks (71-77)", 71, 77),
    "78-84": ("12 weeks (78-84)", 78, 84),
    "85-": ("13 weeks or more", 85, None),
}


@bp.get("/")
def index():
    q = request.args.get("q", "").strip()
    seed_type = request.args.get("type", "")
    breeder = request.args.get("breeder", "")
    days = request.args.get("days", "")
    expression = request.args.get("expression", "")
    query = db.session.query(Strain)
    if q:
        like = f"%{q}%"
        query = query.filter(
            (Strain.name.ilike(like)) | (Strain.breeder.ilike(like)) | (Strain.lineage.ilike(like))
        )
    if seed_type:
        query = query.filter(Strain.seed_type == SeedType(seed_type))
    if expression:
        query = query.filter(Strain.expression == Expression(expression))
    if breeder == NO_BREEDER:
        query = query.filter((Strain.breeder.is_(None)) | (Strain.breeder == ""))
    elif breeder:
        query = query.filter(Strain.breeder == breeder)
    if days in DAY_RANGES:
        _, low, high = DAY_RANGES[days]
        if low is not None:
            query = query.filter(Strain.flower_days >= low)
        if high is not None:
            query = query.filter(Strain.flower_days <= high)
    # Ascending by default. Case-insensitive so this matches the locale-aware order
    # sortable.js re-applies client-side; SQLite's default collation is not.
    strains = query.order_by(func.lower(Strain.name)).all()
    breeders = [
        b for (b,) in db.session.query(Strain.breeder).distinct().order_by(Strain.breeder) if b
    ]
    return render_template(
        "strains/index.html",
        strains=strains,
        q=q,
        seed_type=seed_type,
        breeder=breeder,
        days=days,
        expression=expression,
        seed_types=list(SeedType),
        expressions=list(Expression),
        breeders=breeders,
        day_ranges=DAY_RANGES,
        no_breeder=NO_BREEDER,
        filtered=bool(q or seed_type or breeder or days or expression),
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
