"""Flask CLI commands: `flask --app wsgi <command>`."""

from __future__ import annotations

import json

import click
from flask import Flask

from .extensions import db


def register(app: Flask) -> None:
    @app.cli.command("init-db")
    def init_db() -> None:
        """Create database tables (no-op if they already exist)."""
        db.create_all()
        click.echo("Database ready.")

    @app.cli.command("seed-demo")
    def seed_demo_cmd() -> None:
        """Load the demo season (skips if the database already has strains)."""
        from .services.seed import seed_demo

        seed_demo()
        click.echo("Demo data loaded.")

    @app.cli.command("reset-db")
    @click.confirmation_option(prompt="Drop and recreate all tables?")
    def reset_db() -> None:
        """Drop all tables and recreate them. Destroys data."""
        db.drop_all()
        db.create_all()
        click.echo("Database reset.")

    @app.cli.command("export-markdown")
    def export_markdown() -> None:
        """Print the schedule as Markdown (groups, event table, ASCII timeline)."""
        from .models import Group
        from .services.scheduling import markdown_export

        click.echo(markdown_export(db.session.query(Group).all()))

    @app.cli.command("export-json")
    def export_json() -> None:
        """Print a full JSON backup of the database."""
        from .services.transfer import dump

        click.echo(json.dumps(dump(), indent=2))
