# Evals

The agent's tools change data (star, dismiss, notes), so evals run against a fixed fixture database built
by `fixtures/build_eval_db.py`, never your real feed (`data/feed.db`).

```bash
# 1. Rebuild the fixture database (do this before every run)
uv run python tests/eval/fixtures/build_eval_db.py

# 2. Run the agent over the cases and grade them. Results: artifacts/grade_results/results_<ts>.html
FEED_DB_PATH=artifacts/eval_feed.db agents-cli eval run \
  --dataset tests/eval/datasets/agent-behavior.json

# 3. Before calling it done, run the held-back cases (do not tune on these)
FEED_DB_PATH=artifacts/eval_feed.db agents-cli eval run \
  --dataset tests/eval/datasets/holdout.json

# Compare two runs after a change
agents-cli eval compare artifacts/grade_results/<before>.json artifacts/grade_results/<after>.json
```

Metrics: `tool_behavior`, `response_checks` and `no_invented_links` are deterministic code checks;
`answer_quality` is an LLM judge (1-5). Each run uses Gemini quota.
