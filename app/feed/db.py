"""SQLite storage for feed items and the user's read/bookmark/dismiss state."""

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

STATUSES = ("new", "read", "bookmarked", "dismissed")

_DEFAULT_PATH = Path(__file__).resolve().parents[2] / "data" / "feed.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    source TEXT NOT NULL,
    author TEXT NOT NULL DEFAULT '',
    topic TEXT NOT NULL,
    bullets TEXT NOT NULL,
    published TEXT NOT NULL DEFAULT '',
    found_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'new' CHECK (status IN ('new','read','bookmarked','dismissed')),
    status_updated_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_items_status ON items(status);
CREATE INDEX IF NOT EXISTS idx_items_topic ON items(topic);
"""


def db_path() -> Path:
    return Path(os.environ.get("FEED_DB_PATH", _DEFAULT_PATH))


@contextmanager
def connect():
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _row_to_item(row: sqlite3.Row) -> dict:
    item = dict(row)
    item["bullets"] = json.loads(item["bullets"])
    return item


def url_known(url: str) -> bool:
    with connect() as conn:
        return (
            conn.execute("SELECT 1 FROM items WHERE url = ?", (url,)).fetchone()
            is not None
        )


def add_item(
    *,
    url: str,
    title: str,
    source: str,
    topic: str,
    bullets: list[str],
    author: str = "",
    published: str = "",
) -> bool:
    """Insert a new item. Returns False if the URL already exists (state is kept)."""
    with connect() as conn:
        cur = conn.execute(
            "INSERT OR IGNORE INTO items (url, title, source, author, topic, bullets, published, found_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (url, title, source, author, topic, json.dumps(bullets), published, _now()),
        )
        return cur.rowcount == 1


def get_item(item_id: int) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    return _row_to_item(row) if row else None


def set_status(item_id: int, status: str) -> bool:
    if status not in STATUSES:
        raise ValueError(f"status must be one of {STATUSES}")
    with connect() as conn:
        cur = conn.execute(
            "UPDATE items SET status = ?, status_updated_at = ? WHERE id = ?",
            (status, _now(), item_id),
        )
        return cur.rowcount == 1


def list_items(
    *,
    status: str | None = None,
    topic: str | None = None,
    query: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """List items, newest first. Dismissed items only appear when asked for explicitly."""
    clauses, params = [], []
    if status:
        clauses.append("status = ?")
        params.append(status)
    else:
        clauses.append("status != 'dismissed'")
    if topic:
        clauses.append("topic = ?")
        params.append(topic)
    if query:
        clauses.append("(title LIKE ? OR bullets LIKE ? OR author LIKE ?)")
        params.extend([f"%{query}%"] * 3)
    sql = (
        "SELECT * FROM items WHERE "
        + " AND ".join(clauses)
        + " ORDER BY found_at DESC, id DESC LIMIT ?"
    )
    params.append(max(1, min(limit, 200)))
    with connect() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_row_to_item(r) for r in rows]


def counts() -> dict:
    with connect() as conn:
        rows = conn.execute(
            "SELECT status, COUNT(*) AS n FROM items GROUP BY status"
        ).fetchall()
        topics = conn.execute(
            "SELECT topic, COUNT(*) AS n FROM items WHERE status != 'dismissed' GROUP BY topic ORDER BY n DESC"
        ).fetchall()
    by_status = dict.fromkeys(STATUSES, 0)
    by_status.update({r["status"]: r["n"] for r in rows})
    return {"status": by_status, "topics": {r["topic"]: r["n"] for r in topics}}
