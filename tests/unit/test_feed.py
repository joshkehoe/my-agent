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
