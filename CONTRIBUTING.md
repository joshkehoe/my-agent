# Contributing

## Setup

```bash
agents-cli install
cp .env.example .env   # then fill in your own values; never commit .env
uvx pre-commit install
```

## Workflow

- `main` is protected: work on a branch (`feat/...`, `fix/...`, `chore/...`) and open a pull request.
- Use [Conventional Commits](https://www.conventionalcommits.org/) (`feat: ...`, `fix: ...`, `docs: ...`).
- Keep PRs small and focused; CI (lint + unit tests) must pass before merge.
- Run `uv run pytest tests/unit` and `uv run ruff check .` locally before pushing.

## Secrets

API keys and credentials belong in `.env` (git-ignored) or a secret manager, never in the repo.
