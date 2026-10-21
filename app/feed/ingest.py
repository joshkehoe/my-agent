"""Find, fetch and summarize content for the feed.

Run with:  uv run python -m app.feed.ingest --help
"""

import argparse
import json
import random
import re
import sys
import time
import urllib.robotparser
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path
from typing import ClassVar
from urllib.parse import urljoin, urlparse

import httpx
from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel

from app.feed import db
from app.feed.sources import CONTENT_PREFIXES, PEOPLE, SITE, SITEMAP_URL, TOPICS

MODEL = "gemini-3.8-flash"  # keep in sync with app/agent.py
USER_AGENT = "PMLearningFeed/0.1 (personal research tool)"
MAX_TEXT_CHARS = 8000
REQUEST_PAUSE_SECONDS = 1.0


class RateLimited(Exception):
    """The model kept returning 429/5xx after several retries; stop the run instead of hammering it."""


def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


class Summary(BaseModel):
    topic: str
    bullets: list[str]
    author: str = ""
    published: str = ""


# ---------------------------------------------------------------- fetching


class _PageParser(HTMLParser):
    _SKIP: ClassVar[set[str]] = {
        "script",
        "style",
        "nav",
        "footer",
        "header",
        "noscript",
        "svg",
        "form",
    }
    _KEEP: ClassVar[set[str]] = {"p", "li", "h1", "h2", "h3"}

    def __init__(self) -> None:
        super().__init__()
        self.title = ""
        self.description = ""
        self.published = ""
        self.chunks: list[str] = []
        self._skip_depth = 0
        self._in_title = False
        self._in_keep = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "meta":
            key = attrs.get("name") or attrs.get("property") or ""
            content = attrs.get("content") or ""
            if key in ("description", "og:description") and not self.description:
                self.description = content
            if key in ("article:published_time", "date") and not self.published:
                self.published = content[:10]
        elif tag == "title":
            self._in_title = True
        elif tag in self._SKIP:
            self._skip_depth += 1
        elif tag in self._KEEP:
            self._in_keep = True

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        elif tag in self._SKIP and self._skip_depth:
            self._skip_depth -= 1
        elif tag in self._KEEP:
            self._in_keep = False

    def handle_data(self, data):
        text = " ".join(data.split())
        if not text:
            return
        if self._in_title:
            self.title += text
        elif self._in_keep and not self._skip_depth:
            self.chunks.append(text)


def parse_page(html: str) -> dict:
    parser = _PageParser()
    parser.feed(html)
    text = "\n".join(parser.chunks)[:MAX_TEXT_CHARS]
    return {
        "title": parser.title.strip(),
        "description": parser.description.strip(),
        "published": parser.published,
        "text": text,
    }


def fetch(client: httpx.Client, url: str) -> str | None:
    try:
        resp = client.get(url, follow_redirects=True, timeout=20)
    except httpx.HTTPError:
        return None
    if resp.status_code >= 400 or "html" not in resp.headers.get("content-type", ""):
        return None
    return resp.text


def _robots_allowed(client: httpx.Client) -> urllib.robotparser.RobotFileParser:
    rp = urllib.robotparser.RobotFileParser()
    try:
        resp = client.get(urljoin(SITE, "/robots.txt"), timeout=20)
        rp.parse(resp.text.splitlines())
    except httpx.HTTPError:
        rp.parse(["User-agent: *", "Disallow: /"])  # fail closed
    return rp


# ------------------------------------------------------------ summarizing


def _generate(
    client: genai.Client,
    contents: str,
    config: types.GenerateContentConfig,
    tries: int = 7,
):
    for attempt in range(tries):
        try:
            return client.models.generate_content(
                model=MODEL, contents=contents, config=config
            )
        except Exception as exc:
            transient = any(code in str(exc) for code in ("429", "500", "503"))
            if not transient:
                raise
            if attempt == tries - 1:
                raise RateLimited(str(exc)[:120]) from exc
            time.sleep(min(2**attempt, 16) + random.random())


def summarize(client: genai.Client, *, url: str, page: dict) -> Summary | None:
    if len(page["text"]) < 200:
        return None
    prompt = f"""You curate learning material for a product manager who wants to become AI-native.
Summarize the page below.

Rules:
- Use ONLY information in the page text. Do not invent facts.
- 3 to 5 bullets, each under 20 words, concrete and useful (tips, frameworks, lessons).
- topic must be exactly one of: {json.dumps(TOPICS)}
- author: the writer or main guest if stated, else "".
- published: ISO date if stated, else "".

URL: {url}
Title: {page["title"]}
Description: {page["description"]}
Page text:
{page["text"]}"""
    resp = _generate(
        client,
        prompt,
        types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=Summary,
            temperature=0.2,
        ),
    )
    try:
        summary = Summary.model_validate_json(resp.text)
    except Exception:
        return None
    if summary.topic not in TOPICS:
        summary.topic = "Other"
    summary.bullets = [b.strip() for b in summary.bullets if b.strip()][:5]
    return summary if summary.bullets else None


# ----------------------------------------------------------------- sources


def _ingest_url(client, http, *, url: str, source: str, author_hint: str = "") -> bool:
    page_html = fetch(http, url)
    if not page_html:
        return False
    page = parse_page(page_html)
    summary = summarize(client, url=url, page=page)
    if not summary:
        return False
    return db.add_item(
        url=url,
        title=page["title"] or url,
        source=source,
        topic=summary.topic,
        bullets=summary.bullets,
        author=summary.author or author_hint,
        published=summary.published or page["published"],
    )


def ingest_product_faculty(client: genai.Client, http: httpx.Client, limit: int) -> int:
    """Add new pages listed in the Product Faculty sitemap."""
    robots = _robots_allowed(http)
    try:
        sitemap = http.get(SITEMAP_URL, timeout=20)
        sitemap.raise_for_status()
        locs = [
            e.text.strip()
            for e in ET.fromstring(sitemap.text).iter()
            if e.tag.endswith("loc") and e.text
        ]
    except (httpx.HTTPError, ET.ParseError):
        return 0
    added = 0
    for url in locs:
        if added >= limit:
            break
        path = urlparse(url).path
        source = next(
            (
                s
                for p, s in CONTENT_PREFIXES.items()
                if path.startswith(p) and path != p
            ),
            None,
        )
        if not source or db.url_known(url) or not robots.can_fetch(USER_AGENT, url):
            continue
        try:
            if _ingest_url(client, http, url=url, source=source):
                added += 1
                _log(f"added {url}")
        except RateLimited:
            _log(
                "model is rate limiting; stopping Product Faculty pass (progress is saved)"
            )
            break
        time.sleep(REQUEST_PAUSE_SECONDS)
    return added


def _find_candidates(client: genai.Client, person: dict) -> list[dict]:
    """Ask Google Search for recent public writing/talks; URLs are verified afterwards."""
    prompt = f"""Use Google Search to find up to 4 recent, publicly accessible articles, blog posts, newsletter
issues, GitHub repos, talks or podcast episodes by or featuring {person["name"]} ({person["role"]})
about AI, AI product management, or building with AI. Prefer the last 12 months.
Return ONLY a JSON array like [{{"title": "...", "url": "https://..."}}]. Do not include LinkedIn URLs."""
    resp = _generate(
        client,
        prompt,
        types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())]
        ),
    )
    match = re.search(r"\[.*\]", resp.text or "", re.S)
    if not match:
        return []
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return []
    return [
        d
        for d in data
        if isinstance(d, dict) and str(d.get("url", "")).startswith("https://")
    ]


def ingest_people(
    client: genai.Client, http: httpx.Client, per_person: int, people: list[dict]
) -> int:
    added = 0
    for person in people:
        try:
            candidates = _find_candidates(client, person)
        except Exception:
            continue
        taken = 0
        for cand in candidates:
            if taken >= per_person:
                break
            url = cand["url"]
            if "linkedin.com" in url or db.url_known(url):
                continue
            if _ingest_url(
                client,
                http,
                url=url,
                source=f"Web: {person['name']}",
                author_hint=person["name"],
            ):
                added += 1
                taken += 1
            time.sleep(REQUEST_PAUSE_SECONDS)
    return added


def refresh(
    pf_limit: int = 15, per_person: int = 2, people: list[dict] | None = None
) -> dict:
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
    client = genai.Client()
    with httpx.Client(headers={"User-Agent": USER_AGENT}) as http:
        pf = ingest_product_faculty(client, http, pf_limit)
        web = ingest_people(
            client, http, per_person, PEOPLE if people is None else people
        )
    return {"product_faculty": pf, "web": web, "total_new": pf + web}


def main() -> None:
    ap = argparse.ArgumentParser(description="Refresh the PM learning feed.")
    ap.add_argument(
        "--pf-limit", type=int, default=15, help="max new Product Faculty pages"
    )
    ap.add_argument(
        "--per-person", type=int, default=2, help="max new web items per instructor"
    )
    ap.add_argument("--no-web", action="store_true", help="skip instructor web search")
    args = ap.parse_args()
    result = refresh(args.pf_limit, args.per_person, [] if args.no_web else None)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
