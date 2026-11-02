"""Serve the existing site and prepare storage for the Posts feature."""

import sqlite3
from pathlib import Path

from flask import Flask, abort, current_app, g, send_from_directory


def get_db():
    """Reuse one database connection per request (or app context)."""
    if "db" not in g:
        g.db = sqlite3.connect(Path(current_app.instance_path) / "posts.sqlite3")
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def create_app(instance_path=None):
    app = Flask(__name__, static_folder=None, instance_path=instance_path)
    storage = Path(app.instance_path)
    (storage / "uploads").mkdir(parents=True, exist_ok=True)
    app.teardown_appcontext(close_db)

    with app.app_context():
        with app.open_resource("schema.sql", mode="r") as schema:
            get_db().executescript(schema.read())

    # Only these public files are served; Python, uploads and the DB stay private.
    public_files = {
        "index.html", "about.html", "journals.html", "posts.html",
        "music.html", "links.html", "style.css",
    }

    @app.get("/")
    def home():
        return send_from_directory(app.root_path, "index.html")

    @app.get("/<filename>")
    def page(filename):
        if filename not in public_files:
            abort(404)
        return send_from_directory(app.root_path, filename)

    return app
