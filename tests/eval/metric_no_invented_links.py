"""Every URL in the final answer must have come from a tool result (no invented links)."""

import re

_URL = re.compile(r"https?://[^\s)\]>\"']+")


def _walk(node, urls):
    if isinstance(node, dict):
        for v in node.values():
            _walk(v, urls)
    elif isinstance(node, list):
        for v in node:
            _walk(v, urls)
    elif isinstance(node, str):
        urls.update(u.rstrip(".,;*") for u in _URL.findall(node))


def evaluate(instance):
    allowed, final = set(), ""
    for turn in (instance.get("agent_data") or {}).get("turns", []):
        for event in turn.get("events", []):
            for part in (event.get("content") or {}).get("parts", []):
                if part.get("function_response"):
                    _walk(part["function_response"], allowed)
                elif part.get("text") and event.get("author") not in ("user", "tool"):
                    final = part["text"]
    shown = {u.rstrip(".,;*") for u in _URL.findall(final)}
    invented = sorted(shown - allowed)
    return {
        "score": 0 if invented else 1,
        "explanation": f"links not found in any tool result: {invented}"
        if invented
        else "all links came from tool results",
    }
