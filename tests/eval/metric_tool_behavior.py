"""Did the agent call the right tools (and avoid the wrong ones)?  Deterministic, no LLM.

Reads the case's `expect` field:
  must_call:     [{"name": "star_item", "args": {"item_id": 3}, "args_contain": {"note": "text"}}]
  must_not_call: ["mark_item", "refresh_feed"]
"""


def _calls(instance):
    out = []
    for turn in (instance.get("agent_data") or {}).get("turns", []):
        for event in turn.get("events", []):
            for part in (event.get("content") or {}).get("parts", []):
                fc = part.get("function_call")
                if fc:
                    out.append((fc.get("name"), fc.get("args") or {}))
    return out


def evaluate(instance):
    expect = instance.get("expect") or {}
    calls = _calls(instance)
    problems = []

    for want in expect.get("must_call", []):
        matched = False
        for name, args in calls:
            if name != want["name"]:
                continue
            if any(args.get(k) != v for k, v in (want.get("args") or {}).items()):
                continue
            if any(
                str(v).lower() not in str(args.get(k, "")).lower()
                for k, v in (want.get("args_contain") or {}).items()
            ):
                continue
            matched = True
            break
        if not matched:
            problems.append(f"missing call {want} (saw {[c[0] for c in calls]})")

    for name in expect.get("must_not_call", []):
        if any(c[0] == name for c in calls):
            problems.append(f"must not call {name}")

    return {
        "score": 0 if problems else 1,
        "explanation": "; ".join(problems) or "tool calls as expected",
    }
