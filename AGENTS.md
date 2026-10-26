# AGENTS.md

## Repo Shape
- Python 3.12 repo managed with `uv`.
- Importable package code lives in `src/rer_api_client/`; the public client is `RERClient` and the thin service facade is `RERService`.
- Response contracts are Pydantic dataclasses in `src/rer_client/models.py`; prefer attributes over dict subscripting in new code.
- `test/rer-python/` is live integration coverage against `rer.ofgem.gov.uk`, not offline unit tests.
- `test/rer-html/` are helper scripts that fetch and save HTML fixtures; they write `*.html` files that are ignored.

## Commands
- Install deps: `uv sync`
- Run all tests: `uv run pytest`
- Run one test file: `uv run pytest test/rer-python/test_user.py`
- Type-check with the repo venv: `.venv/bin/python -m mypy src test/rer-python test/rer-html`
- Regenerate cookies: `uv run python test/bootstrap_rer_cookies.py`

## Live Test Rules
- `test/rer-python/conftest.py` skips the suite if `rer_cookies.json` is missing or invalid.
- Keep `rer_cookies.json` and `.env` out of git; they are already ignored.
- Run repo-root-relative scripts from the repository root so cookie and token paths resolve correctly.

## Cookie Bootstrap
- `test/bootstrap_rer_cookies.py` needs `RER_EMAIL` and `RER_PASSWORD` from `.env` or flags.
- Saved cookies strip `ai_` tracking cookies before writing `rer_cookies.json`.

## Notes
- The package is installable from Git via `pyproject.toml`; keep import paths under `rer_client` and avoid test-only `sys.path` hacks.
- Parser field names are the JSON API contract; preserve them when editing models or parsers.
