import pytest

from app.feed import db
from app.feed.ingest import parse_page


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setenv("FEED_DB_PATH", str(tmp_path / "feed.db"))


def _add(url="https://example.com/a", topic="AI Evals", **kw):
    return db.add_item(
        url=url, title="T", source="S", topic=topic, bullets=["one", "two"], **kw
    )


def test_add_item_is_idempotent_and_keeps_user_state():
    assert _add() is True
    item = db.list_items()[0]
    db.set_status(item["id"], "bookmarked")
    assert _add() is False  # same URL on a later refresh
    assert db.get_item(item["id"])["status"] == "bookmarked"


def test_dismissed_items_hidden_by_default_but_listable():
    _add()
    item_id = db.list_items()[0]["id"]
    db.set_status(item_id, "dismissed")
    assert db.list_items() == []
    assert [i["id"] for i in db.list_items(status="dismissed")] == [item_id]


def test_status_transitions_and_counts():
    _add("https://example.com/a")
    _add("https://example.com/b", topic="Career & Interviews")
    a, b = (i["id"] for i in db.list_items())
    db.set_status(a, "read")
    db.set_status(b, "bookmarked")
    counts = db.counts()
    assert counts["status"] == {"new": 0, "read": 1, "bookmarked": 1, "dismissed": 0}
    assert set(counts["topics"]) == {"AI Evals", "Career & Interviews"}


def test_invalid_status_rejected():
    _add()
    with pytest.raises(ValueError):
        db.set_status(db.list_items()[0]["id"], "archived")
    assert db.set_status(9999, "read") is False


def test_filter_by_topic_and_query():
    _add("https://example.com/a", topic="AI Evals")
    _add("https://example.com/b", topic="Career & Interviews")
    assert len(db.list_items(topic="AI Evals")) == 1
    assert len(db.list_items(query="one")) == 2
    assert db.list_items(query="nomatch") == []


def test_parse_page_extracts_text_and_ignores_chrome():
    html = """<html><head><title>My Post</title>
    <meta name="description" content="About evals">
    <meta property="article:published_time" content="2026-03-01T10:00:00Z"></head>
    <body><nav><p>Menu junk</p></nav><h1>Heading</h1><p>Real paragraph.</p>
    <script>var x = 1;</script><footer><li>Footer junk</li></footer></body></html>"""
    page = parse_page(html)
    assert page["title"] == "My Post"
    assert page["description"] == "About evals"
    assert page["published"] == "2026-03-01"
    assert "Real paragraph." in page["text"] and "Heading" in page["text"]
    assert "junk" not in page["text"] and "var x" not in page["text"]


def test_star_and_notes_roundtrip():
    _add()
    item_id = db.list_items()[0]["id"]
    assert db.get_item(item_id)["starred"] is False
    assert db.set_star(item_id, True) is True
    assert db.set_notes(item_id, "  Great framework for evals  ") is True
    item = db.get_item(item_id)
    assert item["starred"] is True and item["notes"] == "Great framework for evals"
    assert db.set_star(9999, True) is False and db.set_notes(9999, "x") is False


def test_favorites_filter_ignores_status_and_searches_notes():
    _add("https://example.com/a")
    _add("https://example.com/b")
    a, b = (i["id"] for i in db.list_items())
    db.set_star(a, True)
    db.set_status(a, "read")
    db.set_notes(a, "apply to roadmap review")
    assert [i["id"] for i in db.list_items(starred=True)] == [a]
    assert [i["id"] for i in db.list_items(query="roadmap")] == [a]
    assert db.counts()["starred"] == 1
    assert b not in [i["id"] for i in db.list_items(starred=True)]


def test_notes_survive_unstar_and_refresh():
    _add()
    item_id = db.list_items()[0]["id"]
    db.set_star(item_id, True)
    db.set_notes(item_id, "keep me")
    db.set_star(item_id, False)
    assert _add() is False  # re-ingested on a later refresh
    assert db.get_item(item_id)["notes"] == "keep me"


def test_notes_are_length_capped():
    _add()
    item_id = db.list_items()[0]["id"]
    db.set_notes(item_id, "x" * (db.MAX_NOTES_CHARS + 500))
    assert len(db.get_item(item_id)["notes"]) == db.MAX_NOTES_CHARS


def test_existing_database_is_migrated_without_data_loss(tmp_path, monkeypatch):
    import sqlite3

    old = tmp_path / "old.db"
    conn = sqlite3.connect(old)
    conn.executescript(
        """CREATE TABLE items (id INTEGER PRIMARY KEY AUTOINCREMENT, url TEXT NOT NULL UNIQUE,
        title TEXT NOT NULL, source TEXT NOT NULL, author TEXT NOT NULL DEFAULT '', topic TEXT NOT NULL,
        bullets TEXT NOT NULL, published TEXT NOT NULL DEFAULT '', found_at TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'new', status_updated_at TEXT);
        INSERT INTO items (url,title,source,topic,bullets,found_at,status)
        VALUES ('https://example.com/old','Old','S','AI Evals','["b"]','2026-01-01','read');"""
    )
    conn.commit()
    conn.close()
    monkeypatch.setenv("FEED_DB_PATH", str(old))
    item = db.list_items(status="read")[0]
    assert item["title"] == "Old" and item["starred"] is False and item["notes"] == ""
    assert db.set_star(item["id"], True)
