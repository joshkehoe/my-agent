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


def test_star_toggle_and_favorites_tab(client):
    item_id = db.list_items()[0]["id"]
    assert "No favorites yet" in client.get("/?tab=favorites").text
    r = client.post(
        f"/items/{item_id}/star",
        data={"starred": "1", "tab": "new", "topic": "AI Evals"},
        follow_redirects=False,
    )
    assert r.status_code == 303 and "topic=AI+Evals" in r.headers["location"]
    assert "Evals 101" in client.get("/?tab=favorites").text
    assert "★ Favorites (1)" in client.get("/").text
    client.post(f"/items/{item_id}/star", data={"starred": "0"})
    assert "No favorites yet" in client.get("/?tab=favorites").text


def test_notes_only_on_favorites_and_escaped(client):
    item_id = db.list_items()[0]["id"]
    assert (
        client.post(f"/items/{item_id}/notes", data={"notes": "hi"}).status_code == 400
    )
    assert "<textarea" not in client.get("/").text
    client.post(f"/items/{item_id}/star", data={"starred": "1"})
    assert "<textarea" in client.get("/?tab=favorites").text
    client.post(f"/items/{item_id}/notes", data={"notes": "<script>x</script> idea"})
    page = client.get("/?tab=favorites").text
    assert "&lt;script&gt;x&lt;/script&gt; idea" in page and "<script>x" not in page
    client.post(f"/items/{item_id}/star", data={"starred": "0"})
    assert "idea" in client.get("/").text  # notes are kept and shown read-only


def test_status_change_keeps_topic_filter(client):
    item_id = db.list_items()[0]["id"]
    r = client.post(
        f"/items/{item_id}/status",
        data={"status": "read", "tab": "new", "topic": "AI Evals"},
        follow_redirects=False,
    )
    assert "topic=AI+Evals" in r.headers["location"]
