"""Canopy — cultivation planning.

Application factory. Use ``create_app()`` for production/development and
``create_app(TestConfig)`` in tests.
"""

from __future__ import annotations

import logging
from datetime import date

from flask import Flask

from .config import Config
from .extensions import csrf, db


def create_app(config_object: type[Config] | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_object or Config)

    if not app.config.get("SQLALCHEMY_DATABASE_URI"):
        app.config["SQLALCHEMY_DATABASE_URI"] = Config.default_db_path(app.instance_path)

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    db.init_app(app)
    csrf.init_app(app)

    from . import cli
    from .blueprints import (
        api,
        dashboard,
        groups,
        journal,
        plants,
        reports,
        schedule,
        spaces,
        strains,
    )

    app.register_blueprint(dashboard.bp)
    app.register_blueprint(strains.bp, url_prefix="/strains")
    app.register_blueprint(plants.bp, url_prefix="/plants")
    app.register_blueprint(groups.bp, url_prefix="/groups")
    app.register_blueprint(schedule.bp, url_prefix="/schedule")
    app.register_blueprint(spaces.bp, url_prefix="/spaces")
    app.register_blueprint(journal.bp, url_prefix="/journal")
    app.register_blueprint(reports.bp, url_prefix="/reports")
    app.register_blueprint(api.bp, url_prefix="/api/v1")
    csrf.exempt(api.bp)
    cli.register(app)

    _register_template_helpers(app)

    @app.errorhandler(404)
    def not_found(_err):
        from flask import render_template

        return render_template("errors/404.html"), 404

    with app.app_context():
        db.create_all()

    return app


def _register_template_helpers(app: Flask) -> None:
    from .services import scheduling

    @app.context_processor
    def inject_globals():
        return {"today": scheduling.today(), "app_version": "1.1.0"}

    @app.template_filter("d")
    def fmt_date(value: date | None, fmt: str = "%b %d") -> str:
        return value.strftime(fmt) if value else "—"

    @app.template_filter("dlong")
    def fmt_date_long(value: date | None) -> str:
        return value.strftime("%a %b %d, %Y") if value else "—"

    @app.template_filter("todate")
    def to_date(value) -> date:
        return value if isinstance(value, date) else date.fromisoformat(value)

    @app.template_filter("grams")
    def fmt_grams(value: float | None) -> str:
        return f"{value:,.1f} g" if value is not None else "—"
