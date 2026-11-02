###### first try at a personal blog :p (p.s. very likely to fail)





### Run locally

From this project folder (Python 3.11 or newer):

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m flask --app app run --port 5500
```

Open http://127.0.0.1:5500. Use Flask instead of Live Server for this project.
Stop Live Server first if it is already using port 5500.

The existing HTML pages and CSS are served as they are, except Posts is now
rendered from `templates/posts.html`. On startup, Flask
creates `instance/posts.sqlite3` and `instance/uploads/` if needed. Existing
posts are preserved when the app restarts. These local files are ignored by Git;
back up the whole `instance/` folder together once it contains real posts.

### Posting

Set your owner password once (with the virtual environment active):

```sh
python -m flask --app app set-password
```

The command prompts privately twice. Use at least 12 characters. You can run
the same command to reset the password; doing so expires existing logins.
There is one owner account and no signup. Only a password hash is saved.

Open `/posts.html`, choose **Owner login**, and sign in. **Write a post** lets
you publish text, up to four images, or both. You can edit text, remove images,
add replacements, or delete a post after confirming. Visitors only see the feed
and can open its images. Older posts are available in batches of 20.

Images must be still JPG, PNG, or WebP files, up to 5 MB and 20 megapixels each.
The server checks the actual image contents, corrects orientation, resizes to a
maximum of 2400 pixels per side, and saves a fresh image without metadata.
Text is plain text, up to 10,000 characters. Previewing uploads uses a small
JavaScript file; posting also works without JavaScript.

`app.py` starts Flask and the database. `posts.py` handles login and post actions.
The posting templates, `posts.css`, and `posts.js` provide the forms and feed;
the original `style.css` and other pages are unchanged. Private password and
session-key files also live in the ignored `instance/` folder. Keep that folder
when restarting or moving to another server.

Flask's built-in server is for local development. Public hosting comes later:
use HTTPS, a production server, persistent storage, and login rate limiting.
Set `FLASK_SESSION_COOKIE_SECURE=true` in the hosting environment for HTTPS.

### Check the foundation

```sh
python -m unittest discover -s tests
```
