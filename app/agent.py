# ruff: noqa
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.models import Gemini
from google.genai import types

from app.feed import db, ingest
from app.feed.sources import TOPICS

MODEL = "gemini-3.8-flash"


def search_feed(
    topic: str = "", status: str = "new", query: str = "", limit: int = 10
) -> dict:
    """Look up items in the user's PM learning feed.

    Args:
        topic: Optional topic filter. One of the topics returned by get_feed_overview.
        status: One of "new", "read", "bookmarked" or "dismissed". Defaults to "new".
        query: Optional text to match against titles, summaries and authors.
        limit: Maximum number of items to return (1-25).

    Returns:
        A dict with a list of items, each with id, title, url, source, author, topic and bullets.
    """
    if status not in db.STATUSES:
        return {"error": f"status must be one of {list(db.STATUSES)}"}
    items = db.list_items(
        status=status,
        topic=topic or None,
        query=query or None,
        limit=min(max(limit, 1), 25),
    )
    return {
        "count": len(items),
        "items": [
            {
                k: i[k]
                for k in (
                    "id",
                    "title",
                    "url",
                    "source",
                    "author",
                    "topic",
                    "bullets",
                    "published",
                )
            }
            for i in items
        ],
    }


def get_feed_overview() -> dict:
    """Show how many feed items are in each state and each topic.

    Returns:
        A dict with counts by status (new/read/bookmarked/dismissed) and by topic, plus the full topic list.
    """
    return {**db.counts(), "all_topics": TOPICS}


def mark_item(item_id: int, status: str) -> dict:
    """Change an item's state in the feed.

    Args:
        item_id: The numeric id of the item, from search_feed.
        status: "read", "bookmarked" (save for later), "dismissed" (not interested) or "new" (undo).

    Returns:
        A dict saying whether the update succeeded.
    """
    if status not in db.STATUSES:
        return {"ok": False, "error": f"status must be one of {list(db.STATUSES)}"}
    item = db.get_item(item_id)
    if not item:
        return {"ok": False, "error": f"No item with id {item_id}"}
    db.set_status(item_id, status)
    return {"ok": True, "id": item_id, "title": item["title"], "status": status}


def refresh_feed(max_new_pages: int = 5) -> dict:
    """Check Product Faculty for new pages and add them to the feed. This can take a few minutes.

    Args:
        max_new_pages: Maximum number of new Product Faculty pages to add (1-15).

    Returns:
        A dict with how many new items were added.
    """
    return ingest.refresh(
        pf_limit=min(max(max_new_pages, 1), 15), per_person=0, people=[]
    )


INSTRUCTION = f"""You are a personal learning coach that helps the user become an AI-native product manager.
Your knowledge comes from a feed focused on Product Faculty (productfaculty.com) and its founder,
instructors and staff. The feed is organized by these topics: {", ".join(TOPICS)}.

How to work:
- Always use the tools to read the feed. Never invent articles, URLs or quotes.
- Show items grouped by topic. For each item give the title as a link, the source, and its short bullet
  summary (keep the bullets as stored, 3-5 of them). Include the item id so the user can refer to it.
- When the user says they read, want to save, or are not interested in an item, call mark_item
  ("read", "bookmarked", "dismissed"). Confirm what you changed. Never dismiss an item the user did not ask to dismiss.
- By default show "new" items. Offer to show saved ("bookmarked") items when relevant.
- Use refresh_feed only when the user asks for fresh content. Say it may take a few minutes.
- If the feed is empty or has nothing on a topic, say so and offer to refresh. Do not fill gaps from memory
  without clearly labelling it as general knowledge rather than feed content.
- Be concise and practical. When asked "what should I read next", pick 1-3 items and say why.
"""

root_agent = Agent(
    # Keep in sync with agents-cli-manifest.yaml: agents-cli derives this name
    # from the project `name:` recorded there, and telemetry reports it as
    # gen_ai.agent.name. Renaming the agent only here makes the two disagree,
    # and anything selecting traces by name stops finding this agent's.
    name="my_agent",
    model=Gemini(
        model=MODEL,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=INSTRUCTION,
    tools=[search_feed, get_feed_overview, mark_item, refresh_feed],
)

app = App(
    root_agent=root_agent,
    name="app",
)
