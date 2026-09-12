FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
WORKDIR /app

# Install dependencies first so source edits don't bust the layer cache.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-install-project --no-dev

COPY fin_research ./fin_research
COPY sql ./sql
RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH" STORE_BACKEND=postgres
EXPOSE 8000
HEALTHCHECK CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health').status==200 else 1)"
CMD ["uvicorn", "fin_research.api.main:app_factory", "--factory", "--host", "0.0.0.0", "--port", "8000"]
