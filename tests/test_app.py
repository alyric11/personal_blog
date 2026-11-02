import sqlite3
import tempfile
import unittest
from pathlib import Path

from app import create_app, get_db


class FoundationTests(unittest.TestCase):
    def setUp(self):
        self.storage = tempfile.TemporaryDirectory()
        self.addCleanup(self.storage.cleanup)
        self.app = create_app(instance_path=self.storage.name)
        self.client = self.app.test_client()

    def test_existing_pages_and_css_are_served_unchanged(self):
        for filename in (
            "index.html", "about.html", "journals.html",
            "music.html", "links.html", "style.css",
        ):
            with self.subTest(filename=filename):
                response = self.client.get("/" + filename)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(
                    response.data, (Path(self.app.root_path) / filename).read_bytes()
                )
                response.close()
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        response.close()

    def test_internal_files_are_not_public(self):
        for path in (
            "/app.py", "/schema.sql", "/.git/config", "/posts.sqlite3",
            "/instance/posts.sqlite3", "/instance/uploads/private.jpg",
            "/%2e%2e/app.py", "/missing.html",
        ):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 404)
        self.assertEqual(self.client.post("/posts.html").status_code, 405)

    def test_posts_survive_restart(self):
        text = 'a thought, with commas\nand a second line :) বাংলা'
        with self.app.app_context():
            db = get_db()
            db.execute("INSERT INTO posts (text) VALUES (?)", (text,))
            db.commit()
        restarted = create_app(instance_path=self.storage.name)
        with restarted.app_context():
            post = get_db().execute("SELECT * FROM posts").fetchone()
            self.assertEqual(post["text"], text)
            self.assertTrue(post["created_at"].endswith("Z"))
            self.assertEqual(post["created_at"], post["updated_at"])
        self.assertTrue((Path(self.storage.name) / "uploads").is_dir())

    def test_image_limit_order_and_relationship(self):
        with self.app.app_context():
            db = get_db()
            post_id = db.execute("INSERT INTO posts DEFAULT VALUES").lastrowid
            for position in (3, 1, 0, 2):
                db.execute(
                    "INSERT INTO post_images (post_id, filename, position) VALUES (?, ?, ?)",
                    (post_id, f"image-{position}.jpg", position),
                )
            rows = db.execute(
                "SELECT position FROM post_images WHERE post_id = ? ORDER BY position",
                (post_id,),
            ).fetchall()
            self.assertEqual([row["position"] for row in rows], [0, 1, 2, 3])
            for parent, position in ((post_id, 4), (post_id, 0), (999, 0)):
                with self.assertRaises(sqlite3.IntegrityError):
                    db.execute(
                        "INSERT INTO post_images (post_id, filename, position) VALUES (?, ?, ?)",
                        (parent, "extra.jpg", position),
                    )
            db.execute("DELETE FROM posts WHERE id = ?", (post_id,))
            self.assertEqual(db.execute("SELECT COUNT(*) FROM post_images").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
