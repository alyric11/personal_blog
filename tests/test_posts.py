import io
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from app import create_app, get_db


class PostingTests(unittest.TestCase):
    password = "a-password-for-tests-only"

    def setUp(self):
        self.storage = tempfile.TemporaryDirectory()
        self.addCleanup(self.storage.cleanup)
        self.app = create_app(instance_path=self.storage.name)
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()
        result = self.app.test_cli_runner().invoke(
            args=["set-password"], input=f"{self.password}\n{self.password}\n"
        )
        self.assertEqual(result.exit_code, 0, result.output)

    def token(self, path="/owner/login"):
        response = self.client.get(path)
        match = re.search(rb'name="csrf" value="([^"]+)"', response.data)
        self.assertIsNotNone(match, response.data)
        return match[1].decode()

    def login(self):
        response = self.client.post("/owner/login", data={
            "csrf": self.token(), "password": self.password,
        })
        self.assertEqual(response.status_code, 302)

    def image(self, color="red", filename="test.png"):
        data = io.BytesIO()
        Image.new("RGB", (12, 8), color).save(data, "PNG")
        data.seek(0)
        return data, filename

    def publish(self, text="hello", images=None):
        data = {"text": text, "csrf": self.token("/posts/new")}
        if images:
            data["images"] = images
        return self.client.post("/posts/new", data=data)

    def stored_posts(self):
        with self.app.app_context():
            return [dict(row) for row in get_db().execute("SELECT * FROM posts ORDER BY id")]

    def stored_images(self):
        with self.app.app_context():
            return [dict(row) for row in get_db().execute("SELECT * FROM post_images ORDER BY position")]

    def test_visitors_cannot_write_and_forms_need_csrf(self):
        self.assertNotIn(b"Write a post", self.client.get("/posts.html").data)
        token = self.token()
        for path in ("/posts/new", "/posts/1/edit", "/posts/1/delete", "/owner/logout"):
            self.assertEqual(self.client.post(path, data={"csrf": token}).status_code, 403)
        self.assertEqual(self.client.get("/posts/new").status_code, 403)
        self.assertEqual(self.client.post("/owner/login", data={"password": self.password}).status_code, 400)
        self.login()
        self.assertEqual(self.client.post("/posts/new", data={"text": "forged"}).status_code, 400)
        self.assertEqual(self.client.post("/posts/new", data={"csrf": "বাংলা"}).status_code, 400)
        self.assertEqual(self.stored_posts(), [])

    def test_wrong_password_logout_and_password_reset(self):
        response = self.client.post("/owner/login", data={"csrf": self.token(), "password": "wrong"})
        self.assertEqual(response.status_code, 401)
        self.login()
        token = self.token("/posts/new")
        self.assertEqual(self.client.post("/owner/logout", data={"csrf": token}).status_code, 302)
        self.assertEqual(self.client.get("/posts/new").status_code, 403)
        self.login()
        changed = "another-password-for-tests"
        self.app.test_cli_runner().invoke(args=["set-password"], input=f"{changed}\n{changed}\n")
        self.assertEqual(self.client.get("/posts/new").status_code, 403)

    def test_publish_edit_and_delete_text(self):
        self.login()
        text = '<script>alert("x")</script>\nhello বাংলা'
        self.assertEqual(self.publish(text).status_code, 302)
        post = self.stored_posts()[0]
        public = self.app.test_client().get("/posts.html")
        self.assertIn(b"&lt;script&gt;", public.data)
        self.assertNotIn(b"<script>alert", public.data)
        self.assertNotIn(b">Edit</a>", public.data)
        edit_path = f'/posts/{post["id"]}/edit'
        response = self.client.post(edit_path, data={"csrf": self.token(edit_path), "text": "changed"})
        self.assertEqual(response.status_code, 302)
        edited = self.stored_posts()[0]
        self.assertEqual(edited["text"], "changed")
        self.assertEqual(edited["created_at"], post["created_at"])
        self.assertGreaterEqual(edited["updated_at"], post["updated_at"])
        delete_path = f'/posts/{post["id"]}/delete'
        self.assertIn(b"can't undo", self.client.get(delete_path).data)
        self.assertEqual(len(self.stored_posts()), 1)  # GET never deletes.
        self.assertEqual(self.client.post(delete_path, data={"csrf": self.token(delete_path)}).status_code, 302)
        self.assertEqual(self.stored_posts(), [])

    def test_four_images_replacement_and_file_cleanup(self):
        self.login()
        self.assertEqual(self.publish("", [self.image(filename=f"{i}.png") for i in range(4)]).status_code, 302)
        post = self.stored_posts()[0]
        images = self.stored_images()
        self.assertEqual(len(images), 4)
        image_url = "/uploads/" + images[0]["filename"]
        response = self.app.test_client().get(image_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "image/jpeg")
        response.close()
        edit_path = f'/posts/{post["id"]}/edit'
        response = self.client.post(edit_path, data={
            "csrf": self.token(edit_path), "text": "", "images": [self.image()],
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.stored_images(), images)
        response = self.client.post(edit_path, data={
            "csrf": self.token(edit_path), "text": "", "remove": str(images[0]["id"]),
            "images": [self.image("blue", "../../replace.png")],
        })
        self.assertEqual(response.status_code, 302)
        replaced = self.stored_images()
        self.assertEqual([row["filename"] for row in replaced[:3]], [row["filename"] for row in images[1:]])
        self.assertEqual(self.client.get(image_url).status_code, 404)
        self.assertFalse((Path(self.storage.name) / "uploads" / images[0]["filename"]).exists())
        self.assertNotIn("replace", replaced[-1]["filename"])
        delete_path = f'/posts/{post["id"]}/delete'
        self.client.post(delete_path, data={"csrf": self.token(delete_path)})
        self.assertEqual(self.stored_images(), [])
        self.assertEqual(list((Path(self.storage.name) / "uploads").iterdir()), [])

    def test_bad_posts_leave_no_data_or_files(self):
        self.login()
        cases = [
            {"text": "   "},
            {"text": "x" * 10001},
            {"images": [self.image() for _ in range(5)]},
            {"images": [self.image(), (io.BytesIO(b"not a picture"), "fake.jpg")]},
            {"images": [(io.BytesIO(b"x" * (5 * 1024 * 1024 + 1)), "big.jpg")]},
        ]
        for data in cases:
            data["csrf"] = self.token("/posts/new")
            self.assertEqual(self.client.post("/posts/new", data=data).status_code, 400)
            self.assertEqual(self.stored_posts(), [])
            self.assertEqual(list((Path(self.storage.name) / "uploads").iterdir()), [])
        with patch("posts.Path.write_bytes", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                self.publish(images=[self.image()])
        self.assertEqual(self.stored_posts(), [])

    def test_oversized_request_and_empty_image_edit(self):
        self.login()
        self.app.config["MAX_CONTENT_LENGTH"] = 100
        response = self.client.post("/posts/new", data={"text": "x" * 200})
        self.assertEqual(response.status_code, 413)
        self.app.config["MAX_CONTENT_LENGTH"] = 22 * 1024 * 1024
        self.publish("", [self.image()])
        post_id = self.stored_posts()[0]["id"]
        image_id = self.stored_images()[0]["id"]
        path = f"/posts/{post_id}/edit"
        response = self.client.post(path, data={"csrf": self.token(path), "text": "", "remove": str(image_id)})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(len(self.stored_images()), 1)

    def test_newest_first_and_older_posts(self):
        with self.app.app_context():
            db = get_db()
            db.executemany("INSERT INTO posts (text) VALUES (?)", [(f"entry-{i}",) for i in range(21)])
            db.commit()
        newest = self.client.get("/posts.html").data
        self.assertLess(newest.index(b"entry-20"), newest.index(b"entry-19"))
        self.assertIn(b"Older posts", newest)
        self.assertNotIn(b">entry-0<", newest)
        older = self.client.get("/posts.html?before=2").data
        self.assertIn(b">entry-0<", older)
        self.assertNotIn(b"Older posts", older)
        self.assertEqual(self.client.get("/posts.html?before=not-a-number").status_code, 400)


if __name__ == "__main__":
    unittest.main()
