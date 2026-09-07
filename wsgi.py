"""WSGI entry point: `gunicorn wsgi:app` or `flask --app wsgi run`."""
from canopy import create_app

app = create_app()
