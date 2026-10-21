"""Local web UI for the feed.  Run with:  uv run uvicorn app.feed.web:app --port 8090"""

import html
import threading

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.feed import db, ingest
from app.feed.sources import TOPICS

app = FastAPI(title="PM Learning Feed")

_ALLOWED_HOSTS = {"127.0.0.1", "localhost"}
_refresh_lock = threading.Lock()
_refresh_state = {"running": False, "last": ""}

_TABS = [
    ("new", "New"),
    ("bookmarked", "Saved for later"),
    ("read", "Read"),
    ("dismissed", "Dismissed"),
]

_CSS = """
:root{--bg:#fafaf9;--fg:#1c1917;--muted:#78716c;--card:#fff;--line:#e7e5e4;--accent:#4f46e5}
@media(prefers-color-scheme:dark){:root{--bg:#0c0a09;--fg:#f5f5f4;--muted:#a8a29e;--card:#1c1917;--line:#292524;--accent:#818cf8}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.5 system-ui,sans-serif}
main{max-width:820px;margin:0 auto;padding:24px 16px 64px}
h1{font-size:1.5rem;margin:0 0 4px}h2{font-size:1.05rem;margin:32px 0 8px;color:var(--muted);text-transform:uppercase;letter-spacing:.04em}
.top{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap}
nav{display:flex;gap:8px;flex-wrap:wrap;margin:16px 0}
nav a{padding:6px 12px;border:1px solid var(--line);border-radius:999px;color:var(--fg);text-decoration:none;font-size:.9rem}
nav a.on{background:var(--accent);color:#fff;border-color:var(--accent)}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;margin:10px 0}
.card h3{margin:0 0 2px;font-size:1.05rem}.card h3 a{color:var(--fg)}
.meta{color:var(--muted);font-size:.85rem;margin-bottom:8px}
ul{margin:8px 0;padding-left:20px}li{margin:3px 0}
.actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}
button{font:inherit;font-size:.85rem;padding:6px 12px;border-radius:8px;border:1px solid var(--line);background:var(--card);color:var(--fg);cursor:pointer}
button:hover{border-color:var(--accent)}button.primary{background:var(--accent);color:#fff;border-color:var(--accent)}
.empty{color:var(--muted);padding:32px 0;text-align:center}.note{color:var(--muted);font-size:.85rem}
"""


def _check_host(request: Request) -> None:
    host = (request.headers.get("host") or "").split(":")[0]
    if host not in _ALLOWED_HOSTS:
        raise HTTPException(status_code=403, detail="Local access only")


def _card(item: dict, tab: str) -> str:
    e = html.escape
    bullets = "".join(f"<li>{e(b)}</li>" for b in item["bullets"])
    by = f" · {e(item['author'])}" if item["author"] else ""
    when = f" · {e(item['published'])}" if item["published"] else ""
    buttons = []
    if item["status"] != "read":
        buttons.append(("read", "Mark read", "primary"))
    if item["status"] != "bookmarked":
        buttons.append(("bookmarked", "Save for later", ""))
    if item["status"] != "dismissed":
        buttons.append(("dismissed", "Dismiss", ""))
    if item["status"] != "new":
        buttons.append(("new", "Move to New", ""))
    forms = "".join(
        f'<form method="post" action="/items/{item["id"]}/status">'
        f'<input type="hidden" name="status" value="{s}"><input type="hidden" name="tab" value="{e(tab)}">'
        f'<button class="{cls}">{label}</button></form>'
        for s, label, cls in buttons
    )
    return (
        f'<article class="card"><h3><a href="{e(item["url"], quote=True)}" target="_blank" rel="noopener noreferrer">'
        f'{e(item["title"])}</a></h3><div class="meta">{e(item["source"])}{by}{when}</div>'
        f'<ul>{bullets}</ul><div class="actions">{forms}</div></article>'
    )


@app.get("/", response_class=HTMLResponse)
def index(request: Request, tab: str = "new", topic: str = "") -> str:
    _check_host(request)
    if tab not in dict(_TABS):
        tab = "new"
    counts = db.counts()
    items = db.list_items(status=tab, topic=topic or None, limit=200)
    nav = "".join(
        f'<a class="{"on" if t == tab else ""}" href="/?tab={t}">{label} ({counts["status"].get(t, 0)})</a>'
        for t, label in _TABS
    )
    topic_links = "".join(
        f'<a class="{"on" if topic == t else ""}" href="/?tab={tab}&topic={html.escape(t, quote=True)}">'
        f"{html.escape(t)} ({n})</a>"
        for t, n in counts["topics"].items()
    )
    sections = []
    for t in TOPICS:
        group = [i for i in items if i["topic"] == t]
        if group:
            sections.append(
                f"<h2>{html.escape(t)}</h2>" + "".join(_card(i, tab) for i in group)
            )
    body = (
        "".join(sections) or '<p class="empty">Nothing here yet. Try “Refresh now”.</p>'
    )
    state = "Refreshing…" if _refresh_state["running"] else _refresh_state["last"]
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>PM Learning Feed</title>
<style>{_CSS}</style></head><body><main>
<div class="top"><div><h1>AI-native PM feed</h1><div class="note">Product Faculty and its instructors · {html.escape(state)}</div></div>
<form method="post" action="/refresh"><button class="primary">Refresh now</button></form></div>
<nav>{nav}</nav><nav>{topic_links}</nav>{body}</main></body></html>"""


@app.post("/items/{item_id}/status")
def update_status(
    request: Request, item_id: int, status: str = Form(...), tab: str = Form("new")
):
    _check_host(request)
    if status not in db.STATUSES:
        raise HTTPException(status_code=400, detail="Invalid status")
    if not db.set_status(item_id, status):
        raise HTTPException(status_code=404, detail="Item not found")
    tab = tab if tab in dict(_TABS) else "new"
    return RedirectResponse(f"/?tab={tab}", status_code=303)


def _run_refresh() -> None:
    try:
        result = ingest.refresh(pf_limit=10, per_person=1)
        _refresh_state["last"] = f"Last refresh added {result['total_new']} items"
    except Exception as exc:
        _refresh_state["last"] = f"Last refresh failed: {type(exc).__name__}"
    finally:
        _refresh_state["running"] = False
        _refresh_lock.release()


@app.post("/refresh")
def refresh(request: Request):
    _check_host(request)
    if _refresh_lock.acquire(blocking=False):
        _refresh_state["running"] = True
        threading.Thread(target=_run_refresh, daemon=True).start()
    return RedirectResponse("/", status_code=303)
