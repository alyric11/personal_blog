-- Startup creates missing tables without deleting existing posts.
CREATE TABLE IF NOT EXISTS posts (
    id INTEGER PRIMARY KEY,
    text TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

-- Four numbered slots preserve image order and enforce the limit per post.
-- Image files will live in instance/uploads; only their filenames go here.
CREATE TABLE IF NOT EXISTS post_images (
    id INTEGER PRIMARY KEY,
    post_id INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    filename TEXT NOT NULL UNIQUE,
    position INTEGER NOT NULL CHECK (position IN (0, 1, 2, 3)),
    UNIQUE (post_id, position)
);
