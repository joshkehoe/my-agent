"""Simple text expectations on the final answer.  Deterministic, no LLM.

Reads the case's `expect` field:
  response_contains:     ["onboarding"]            (all must appear, case-insensitive)
  response_contains_any: ["no items", "nothing"]   (at least one must appear)
  response_not_contains: ["added to your favorites"]
"""


def _final_text(instance):
    text = ""
    for turn in (instance.get("agent_data") or {}).get("turns", []):
        for event in turn.get("events", []):
            for part in (event.get("content") or {}).get("parts", []):
                if part.get("text") and event.get("author") not in ("user", "tool"):
                    text = part["text"]
    return text.lower()


def evaluate(instance):
    expect = instance.get("expect") or {}
    text = _final_text(instance)
    problems = []
    for s in expect.get("response_contains", []):
        if s.lower() not in text:
            problems.append(f"answer should mention {s!r}")
    any_of = expect.get("response_contains_any", [])
    if any_of and not any(s.lower() in text for s in any_of):
        problems.append(f"answer should mention one of {any_of}")
    for s in expect.get("response_not_contains", []):
        if s.lower() in text:
            problems.append(f"answer must not say {s!r}")
    return {
        "score": 0 if problems else 1,
        "explanation": "; ".join(problems) or "answer checks passed",
    }
