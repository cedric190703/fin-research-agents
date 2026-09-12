# Marginalia backend

Python 3.12 · FastAPI · Anthropic SDK. See the [root README](../README.md) for the codebase map and [`docs/SYSTEM_DESIGN.md`](../docs/SYSTEM_DESIGN.md) for the design.

```bash
uv sync --all-extras          # install
uv run pytest                 # tests
uv run ruff check . && uv run mypy marginalia   # lint + types
uv run uvicorn marginalia.api.main:app --reload # dev server on :8000
```
