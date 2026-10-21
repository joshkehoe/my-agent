# Eval datasets

- `agent-behavior.json`: the cases to iterate against while improving the agent.
- `holdout.json`: cases held back. Only run these when you think you are done, to check that fixes
  generalize and were not fitted to the cases above.

Each case has a `prompt` and an `expect` block read by the checks in `tests/eval/metric_*.py`:

| key | meaning |
|---|---|
| `must_call` | tool calls that must happen: `{"name", "args": {exact values}, "args_contain": {substrings}}` |
| `must_not_call` | tools that must not be called |
| `response_contains` | text the final answer must contain (all, case-insensitive) |
| `response_contains_any` | the answer must contain at least one of these |
| `response_not_contains` | text the answer must not contain |

The evals run against a fixed fixture database, never your real feed. See `tests/eval/README.md`.
