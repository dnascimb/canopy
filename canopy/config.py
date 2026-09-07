"""Application configuration.

Values are read from environment variables prefixed with ``CANOPY_`` so the
same code runs unchanged in development, tests, Docker and production.
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

# Read .env before the settings below are evaluated, so `flask run`, gunicorn and any
# plain import of the app all see the same configuration.
load_dotenv()


class Config:
    SECRET_KEY = os.environ.get("CANOPY_SECRET_KEY", "dev-only-change-me")
    SQLALCHEMY_DATABASE_URI = os.environ.get("CANOPY_DATABASE_URL")  # resolved in create_app
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    WTF_CSRF_ENABLED = True
    DEFAULT_FLOWER_DAYS = int(os.environ.get("CANOPY_DEFAULT_FLOWER_DAYS", "70"))
    # Optional fixed "today" (ISO date) — handy for demos, screenshots and deterministic tests.
    TODAY_OVERRIDE: str | None = os.environ.get("CANOPY_TODAY")
    # Per-plant footprints (sq ft) as "small,medium,large" per stage; unset = defaults in
    # services/spacing.py. Example: CANOPY_FOOTPRINT_FLOWER="1.5,2,2.5"
    FOOTPRINT_SQFT: dict[str, dict[str, float]] = {}
    for _stage, _env in (
        ("clone", "CANOPY_FOOTPRINT_CLONE"),
        ("vegetative", "CANOPY_FOOTPRINT_VEG"),
        ("flowering", "CANOPY_FOOTPRINT_FLOWER"),
    ):
        if _raw := os.environ.get(_env):
            _vals = [float(v) for v in _raw.split(",")]
            FOOTPRINT_SQFT[_stage] = dict(zip(("small", "medium", "large"), _vals, strict=True))

    @staticmethod
    def default_db_path(instance_path: str) -> str:
        Path(instance_path).mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{Path(instance_path) / 'canopy.db'}"


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False
    TODAY_OVERRIDE = date(2026, 9, 7).isoformat()
    # Always the defaults in services/spacing.py, never whatever .env this machine has.
    FOOTPRINT_SQFT: dict[str, dict[str, float]] = {}
