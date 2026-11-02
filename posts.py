"""Owner login, public feed, and the three post actions."""

import hashlib
import io
import secrets
from functools import wraps
from pathlib import Path

import click
from flask import (
    Blueprint, abort, current_app, redirect, render_template,
    request, send_from_directory, session, url_for,
)
from flask.cli import with_appcontext
from PIL import Image, ImageOps, UnidentifiedImageError
from werkzeug.security import check_password_hash, generate_password_hash

from app import get_db

bp = Blueprint("posts", __name__)


def owner_hash():
    path = Path(current_app.instance_path) / "owner-password"
    return path.read_text() if path.exists() else ""


def owner_token():
    password_hash = owner_hash()
    return hashlib.sha256(password_hash.encode()).hexdigest() if password_hash else None


def is_owner():
    token = owner_token()
    return token is not None and session.get("owner") == token


def owner_required(view):
    @wraps(view)
    def guarded(*args, **kwargs):
        if not is_owner():
            abort(403)
        return view(*args, **kwargs)
    return guarded


def csrf_token():
    if "csrf" not in session:
        session["csrf"] = secrets.token_hex(32)
    return session["csrf"]


@bp.before_request
def check_csrf():
    if request.method == "POST":
        expected = session.get("csrf", "")
        submitted = request.form.get("csrf", "")
        if not expected or not secrets.compare_digest(expected.encode(), submitted.encode()):
            abort(400, "This form expired. Reload the page and try again.")


@bp.app_context_processor
def form_context():
    return {"owner": is_owner(), "csrf_token": csrf_token}


@click.command("set-password")
@click.password_option(confirmation_prompt=True)
@with_appcontext
def set_password(password):
    """Set or reset the only owner's password. Existing logins expire."""
    if len(password) < 12:
        raise click.ClickException("Use at least 12 characters.")
    path = Path(current_app.instance_path) / "owner-password"
    path.touch(mode=0o600, exist_ok=True)
    path.write_text(generate_password_hash(password))
    click.echo("Owner password saved. You can now sign in on the Posts page.")


@bp.route("/owner/login", methods=["GET", "POST"])
def login():
    if is_owner():
        return redirect(url_for("posts.feed"))
    error = None
    if request.method == "POST":
        stored = owner_hash()
        if stored and check_password_hash(stored, request.form.get("password", "")):
            session.clear()
            session["owner"] = owner_token()
            session.permanent = True
            return redirect(url_for("posts.feed"))
        error = "That password didn't match. Try again."
    return render_template("login.html", configured=bool(owner_hash()), error=error), 401 if error else 200


@bp.post("/owner/logout")
@owner_required
def logout():
    session.clear()
    return redirect(url_for("posts.feed"))


def post_with_images(row):
    post = dict(row)
    post["images"] = get_db().execute(
        "SELECT * FROM post_images WHERE post_id = ? ORDER BY position", (post["id"],)
    ).fetchall()
    return post


def find_post(post_id):
    row = get_db().execute("SELECT * FROM posts WHERE id = ?", (post_id,)).fetchone()
    if row is None:
        abort(404)
    return post_with_images(row)


@bp.get("/posts.html")
def feed():
    before = request.args.get("before", str(2**63 - 1))
    if not before.isdecimal() or len(before) > 19 or not 0 < int(before) <= 2**63 - 1:
        abort(400)
    rows = get_db().execute(
        "SELECT * FROM posts WHERE id < ? ORDER BY id DESC LIMIT 21", (int(before),)
    ).fetchall()
    posts = [post_with_images(row) for row in rows[:20]]
    return render_template(
        "posts.html", posts=posts, older=posts[-1]["id"] if len(rows) > 20 else None,
    )


@bp.get("/uploads/<filename>")
def uploaded_image(filename):
    if get_db().execute("SELECT 1 FROM post_images WHERE filename = ?", (filename,)).fetchone() is None:
        abort(404)
    response = send_from_directory(Path(current_app.instance_path) / "uploads", filename)
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


def prepare_image(upload):
    """Decode real images, correct phone orientation, and discard metadata."""
    content = upload.stream.read(5 * 1024 * 1024 + 1)
    if len(content) > 5 * 1024 * 1024:
        raise ValueError("Each image must be 5 MB or smaller.")
    try:
        with Image.open(io.BytesIO(content)) as image:
            if image.format not in {"JPEG", "PNG", "WEBP"} or getattr(image, "is_animated", False):
                raise ValueError("Choose still JPG, PNG, or WebP images.")
            if image.width * image.height > 20_000_000:
                raise ValueError("Each image must be 20 megapixels or smaller.")
            image = ImageOps.exif_transpose(image)
            image.thumbnail((2400, 2400))
            transparent = "A" in image.getbands() or "transparency" in image.info
            image = image.convert("RGBA" if transparent else "RGB")
            image.info.clear()
            output = io.BytesIO()
            image.save(output, format="PNG" if transparent else "JPEG", quality=90)
            return output.getvalue(), ".png" if transparent else ".jpg"
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as error:
        raise ValueError("One of those files isn't a readable image.") from error


def remove_files(filenames):
    for filename in filenames:
        try:
            (Path(current_app.instance_path) / "uploads" / filename).unlink(missing_ok=True)
        except OSError:
            current_app.logger.warning("Could not remove unused image %s", filename)


def save_post(post=None):
    text = request.form.get("text", "").strip()
    if len(text) > 10000:
        raise ValueError("Please keep a post to 10,000 characters or fewer.")
    existing = post["images"] if post else []
    removed = set(request.form.getlist("remove"))
    kept = [image for image in existing if str(image["id"]) not in removed]
    uploads = [file for file in request.files.getlist("images") if file.filename]
    if len(kept) + len(uploads) > 4:
        raise ValueError("A post can have up to four images. Remove some before adding more.")
    if not text and not kept and not uploads:
        raise ValueError("Write something or choose an image before publishing.")
    prepared = [prepare_image(file) for file in uploads]
    saved = []
    db = get_db()
    try:
        with db:
            if post:
                post_id = post["id"]
                db.execute(
                    "UPDATE posts SET text = ?, updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now') WHERE id = ?",
                    (text, post_id),
                )
                db.execute("DELETE FROM post_images WHERE post_id = ?", (post_id,))
            else:
                post_id = db.execute("INSERT INTO posts (text) VALUES (?)", (text,)).lastrowid
            filenames = [image["filename"] for image in kept]
            for content, extension in prepared:
                filename = secrets.token_hex(16) + extension
                saved.append(filename)
                (Path(current_app.instance_path) / "uploads" / filename).write_bytes(content)
                filenames.append(filename)
            for position, filename in enumerate(filenames):
                db.execute(
                    "INSERT INTO post_images (post_id, filename, position) VALUES (?, ?, ?)",
                    (post_id, filename, position),
                )
    except Exception:
        remove_files(saved)
        raise
    remove_files([image["filename"] for image in existing if str(image["id"]) in removed])


@bp.route("/posts/new", methods=["GET", "POST"])
@bp.route("/posts/<int:post_id>/edit", methods=["GET", "POST"])
@owner_required
def editor(post_id=None):
    post = find_post(post_id) if post_id is not None else None
    error = None
    if request.method == "POST":
        try:
            save_post(post)
        except ValueError as problem:
            error = str(problem)
        else:
            return redirect(url_for("posts.feed"))
    return render_template("editor.html", post=post, error=error), 400 if error else 200


@bp.route("/posts/<int:post_id>/delete", methods=["GET", "POST"])
@owner_required
def delete(post_id):
    post = find_post(post_id)
    if request.method == "POST":
        db = get_db()
        with db:
            db.execute("DELETE FROM posts WHERE id = ?", (post_id,))
        remove_files([image["filename"] for image in post["images"]])
        return redirect(url_for("posts.feed"))
    return render_template("delete.html", post=post)


@bp.app_errorhandler(413)
def too_large(error):
    return render_template("message.html", message="That upload is too large. Choose up to four images, each 5 MB or smaller."), 413


@bp.app_errorhandler(400)
@bp.app_errorhandler(403)
def form_error(error):
    message = error.description if error.code == 400 else "Please sign in as the owner to do that."
    return render_template("message.html", message=message), error.code
