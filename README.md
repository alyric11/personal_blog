###### first try at a personal blog :p (p.s. very likely to fail)

### Run locally

From this project folder (Python 3.9 or newer):

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m flask --app app run --port 5500
```

Open http://127.0.0.1:5500. Use Flask instead of Live Server for this project.
Stop Live Server first if it is already using port 5500.

The existing HTML pages and CSS are served as they are. On startup, Flask
creates `instance/posts.sqlite3` and `instance/uploads/` if needed. Existing
posts are preserved when the app restarts. These local files are ignored by Git;
back up the whole `instance/` folder together once it contains real posts.

The database holds post text, creation/edit timestamps, and up to four ordered
image filenames per post. Actual image files will go in the uploads folder.
Publishing, login, editing, and deleting will be added in the next steps; this
version only prepares storage and serves the existing site. The edit timestamp
will be updated by the editing code when that is added.

Flask's built-in server is for local development. Public hosting comes later.

### Check the foundation

```sh
python -m unittest discover -s tests
```
