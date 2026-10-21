import pytest
from fastapi.testclient import TestClient

from app.feed import db
from app.feed.web import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("FEED_DB_PATH", str(tmp_path / "feed.db"))
    db.add_item(
        url="https://example.com/a",
        title="<b>Evals 101</b>",
        source="S",
        topic="AI Evals",
        bullets=["Measure first"],
    )
    return TestClient(app, base_url="http://127.0.0.1:8090")


def test_index_escapes_html_and_shows_item(client):
    page = client.get("/").text
    assert "&lt;b&gt;Evals 101&lt;/b&gt;" in page and "<b>Evals 101</b>" not in page
    assert "Measure first" in page


def test_status_buttons_move_items_between_tabs(client):
    item_id = db.list_items()[0]["id"]
    for status, tab in [
        ("bookmarked", "bookmarked"),
        ("read", "read"),
        ("dismissed", "dismissed"),
    ]:
        r = client.post(
            f"/items/{item_id}/status",
            data={"status": status, "tab": "new"},
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert "Evals 101" in client.get(f"/?tab={tab}").text
    assert "Evals 101" not in client.get("/?tab=new").text


def test_rejects_non_local_host_and_bad_status(client):
    assert TestClient(app, base_url="http://evil.example").get("/").status_code == 403
    assert client.post("/items/1/status", data={"status": "bogus"}).status_code == 400
    assert client.post("/items/999/status", data={"status": "read"}).status_code == 404
