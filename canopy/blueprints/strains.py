from __future__ import annotations

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from ..extensions import db
from ..forms import StrainForm
from ..models import PlantSize, PlantStatus, SeedType, Strain

bp = Blueprint("strains", __name__)


@bp.get("/")
def index():
    q = request.args.get("q", "").strip()
    seed_type = request.args.get("type", "")
    query = db.session.query(Strain)
    if q:
        like = f"%{q}%"
        query = query.filter(
            (Strain.name.ilike(like)) | (Strain.breeder.ilike(like)) | (Strain.lineage.ilike(like))
        )
    if seed_type:
        query = query.filter(Strain.seed_type == SeedType(seed_type))
    strains = query.order_by(Strain.name).all()
    return render_template(
        "strains/index.html", strains=strains, q=q, seed_type=seed_type, seed_types=list(SeedType)
    )


@bp.route("/new", methods=["GET", "POST"])
def create():
    form = StrainForm()
    if form.validate_on_submit():
        s = Strain()
        form.populate_obj(s)
        s.seed_type = SeedType(form.seed_type.data)
        s.size = PlantSize(form.size.data)
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
