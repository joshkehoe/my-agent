import pytest

from app import agent
from app.feed import db


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setenv("FEED_DB_PATH", str(tmp_path / "feed.db"))
    db.add_item(
        url="https://example.com/a",
        title="T",
        source="S",
        topic="AI Evals",
        bullets=["b"],
    )


def _id():
    return db.list_items()[0]["id"]


def test_notes_require_a_favorite():
    assert agent.save_note(_id(), "x")["ok"] is False
    assert agent.star_item(_id())["ok"] is True
    assert agent.save_note(_id(), "first")["ok"] is True
    assert agent.save_note(_id(), "second", append=True)["ok"] is True
    assert db.get_item(_id())["notes"] == "first\n\nsecond"


def test_search_favorites_returns_notes():
    agent.star_item(_id())
    agent.save_note(_id(), "my take")
    result = agent.search_feed(favorites_only=True)
    assert result["count"] == 1 and result["items"][0]["notes"] == "my take"
    assert agent.star_item(9999)["ok"] is False
