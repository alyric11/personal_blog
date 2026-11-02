"""Serve the site and its single-owner posting feature."""

import secrets
import sqlite3
from datetime import timedelta
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
    app = Flask(__name__, static_folder=None, template_folder="templates", instance_path=instance_path)
    storage = Path(app.instance_path)
    (storage / "uploads").mkdir(parents=True, exist_ok=True)
    secret_file = storage / "session-secret"
    try:
        with secret_file.open("x") as secret:
            secret_file.chmod(0o600)
            secret.write(secrets.token_hex(32))
    except FileExistsError:
        pass
    app.config.update(
        SECRET_KEY=secret_file.read_text(),
        MAX_CONTENT_LENGTH=22 * 1024 * 1024,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        PERMANENT_SESSION_LIFETIME=timedelta(hours=12),
    )
    app.config.from_prefixed_env()
    app.teardown_appcontext(close_db)

    with app.app_context():
        with app.open_resource("schema.sql", mode="r") as schema:
            get_db().executescript(schema.read())

    from posts import bp, set_password

    app.register_blueprint(bp)
    app.cli.add_command(set_password)

    # Only these public files are served; private storage stays inaccessible.
    public_files = {
        "index.html", "about.html", "journals.html",
        "music.html", "links.html", "style.css", "posts.css", "posts.js",
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
