import importlib.util
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parents[1] / "eval"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, EVAL_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.evaluate


def _trace(calls=(), results=(), final="", **extra):
    events = [{"author": "user", "content": {"parts": [{"text": "hi"}]}}]
    events += [
        {
            "author": "my_agent",
            "content": {"parts": [{"function_call": {"name": n, "args": a}}]},
        }
        for n, a in calls
    ]
    events += [
        {
            "author": "my_agent",
            "content": {"parts": [{"function_response": {"name": "t", "response": r}}]},
        }
        for r in results
    ]
    events.append({"author": "my_agent", "content": {"parts": [{"text": final}]}})
    return {"agent_data": {"turns": [{"turn_index": 0, "events": events}]}, **extra}


def test_tool_behavior_matches_subset_of_args_and_forbids_calls():
    check = _load("metric_tool_behavior")
    expect = {
        "must_call": [{"name": "star_item", "args": {"item_id": 3}}],
        "must_not_call": ["mark_item"],
    }
    ok = _trace(calls=[("star_item", {"item_id": 3, "starred": True})], expect=expect)
    assert check(ok)["score"] == 1
    wrong_id = _trace(calls=[("star_item", {"item_id": 4})], expect=expect)
    assert check(wrong_id)["score"] == 0
    forbidden = _trace(
        calls=[("star_item", {"item_id": 3}), ("mark_item", {"item_id": 1})],
        expect=expect,
    )
    assert check(forbidden)["score"] == 0
    assert check(_trace(expect={}))["score"] == 1


def test_tool_behavior_args_contain_is_case_insensitive():
    check = _load("metric_tool_behavior")
    expect = {
        "must_call": [
            {"name": "save_note", "args_contain": {"note": "share with priya"}}
        ]
    }
    assert (
        check(
            _trace(
                calls=[
                    (
                        "save_note",
                        {"item_id": 5, "note": "Share with Priya before Friday"},
                    )
                ],
                expect=expect,
            )
        )["score"]
        == 1
    )
    assert (
        check(
            _trace(
                calls=[("save_note", {"item_id": 5, "note": "something else"})],
                expect=expect,
            )
        )["score"]
        == 0
    )


def test_response_checks():
    check = _load("metric_response_checks")
    expect = {
        "response_contains": ["Onboarding"],
        "response_not_contains": ["done!"],
        "response_contains_any": ["star", "favorite"],
    }
    assert (
        check(_trace(final="Your onboarding idea: star it first", expect=expect))[
            "score"
        ]
        == 1
    )
    assert (
        check(_trace(final="Your onboarding idea. done!", expect=expect))["score"] == 0
    )
    assert check(_trace(final="nothing relevant", expect=expect))["score"] == 0


def test_no_invented_links():
    check = _load("metric_no_invented_links")
    known = {"items": [{"url": "https://example.com/a"}]}
    good = _trace(results=[known], final="Read [A](https://example.com/a).")
    assert check(good)["score"] == 1
    bad = _trace(
        results=[known],
        final="Try https://made-up.example/post and https://example.com/a",
    )
    result = check(bad)
    assert result["score"] == 0 and "made-up.example" in result["explanation"]
    assert check(_trace(final="No links here."))["score"] == 1
