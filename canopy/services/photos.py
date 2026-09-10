"""Photos attached to journal entries.

Files live under ``instance/uploads``, outside the database and outside git. The entry
stores only a generated filename, so nothing a browser sends is ever used as a path.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from flask import current_app
from werkzeug.datastructures import FileStorage


def upload_dir() -> Path:
    path = Path(current_app.instance_path) / current_app.config["UPLOAD_DIRNAME"]
    path.mkdir(parents=True, exist_ok=True)
    return path


def is_allowed(filename: str) -> bool:
    return Path(filename or "").suffix.lower() in current_app.config["ALLOWED_PHOTO_EXTENSIONS"]


def save(file: FileStorage | None) -> str | None:
    """Store an uploaded photo and return its filename, or None if there was none.

    The stored name is generated, never the one the browser supplied: only the extension
    survives, and only from the allow-list. That rules out traversal and collisions in
    one step.
    """
    if file is None or not file.filename:
        return None
    suffix = Path(file.filename).suffix.lower()
    if suffix not in current_app.config["ALLOWED_PHOTO_EXTENSIONS"]:
        return None
    name = f"{uuid.uuid4().hex}{suffix}"
    file.save(upload_dir() / name)
    return name


def delete(name: str | None) -> bool:
    """Remove a stored photo. Ignores anything that is not a plain filename."""
    if not name or Path(name).name != name:
        return False
    target = upload_dir() / name
    if target.is_file():
        target.unlink()
        return True
    return False


def orphans() -> list[str]:
    """Files on disk that no journal entry points at — safe to delete."""
    from ..extensions import db
    from ..models import JournalEntry

    known = {
        e.photo_path
        for e in db.session.query(JournalEntry).filter(JournalEntry.photo_path.isnot(None))
    }
    return sorted(f.name for f in upload_dir().iterdir() if f.is_file() and f.name not in known)
