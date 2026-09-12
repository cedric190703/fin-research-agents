"""HTTP API. See docs/API.md."""

from __future__ import annotations

import asyncio
import json
import queue
from collections.abc import AsyncIterator
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from fin_research import __version__
from fin_research.agents.orchestrator import DEPTH_POLICY
from fin_research.api.deps import Container, build_container
from fin_research.api.runs import RunRegistry, RunState
from fin_research.ingestion.pipeline import build_chunks
from fin_research.schemas import Depth, ResearchResult, RunEvent


class ResearchRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=10, pattern=r"^[A-Za-z.\-]+$")
    question: str = Field(default="Full research memo", min_length=1, max_length=2000)
    depth: Depth = Depth.STANDARD


class ResearchAccepted(BaseModel):
    run_id: str


class RunSummary(BaseModel):
    run_id: str
    ticker: str
    question: str
    depth: str
    status: str
    started_at: str
    error: str | None = None


class RunDetail(RunSummary):
    result: ResearchResult | None = None
    events: list[RunEvent]


class IngestRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=10)
    limit: int = Field(default=6, ge=1, le=40)


class IngestResult(BaseModel):
    ticker: str
    filings: int
    chunks: int


def _summary(s: RunState) -> RunSummary:
    return RunSummary(
        run_id=s.id,
        ticker=s.ticker,
        question=s.question,
        depth=s.depth,
        status=s.status,
        started_at=s.started_at.isoformat(),
        error=s.error,
    )


def create_app(container: Container | None = None) -> FastAPI:
    app = FastAPI(title="FinResearchAgents API", version=__version__)
    app.add_middleware(
        CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
    )
    c = container or build_container()
    runs = RunRegistry()
    app.state.container = c
    app.state.runs = runs

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "version": __version__,
            "llm": c.runtime is not None,
            "store": type(c.store).__name__,
            "embedder": type(c.embedder).__name__,
        }

    @app.get("/coverage")
    def coverage() -> dict[str, dict[str, int]]:
        return c.store.coverage()

    @app.post("/ingest", response_model=IngestResult)
    def ingest(req: IngestRequest) -> IngestResult:
        ticker = req.ticker.upper()
        try:
            cik = c.edgar.resolve_cik(ticker)
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        refs = c.edgar.list_filings(ticker, cik, limit=req.limit)
        total = 0
        for ref in refs:
            chunks = build_chunks(ref, c.edgar.fetch_document(ref))
            children = [ch for ch in chunks if ch.level == "child"]
            vecs = c.embedder.embed([ch.text for ch in children])
            total += c.store.upsert(
                chunks, dict(zip([ch.id for ch in children], vecs, strict=True))
            )
        return IngestResult(ticker=ticker, filings=len(refs), chunks=total)

    @app.post("/research", response_model=ResearchAccepted, status_code=202)
    def research(req: ResearchRequest) -> ResearchAccepted:
        if c.runtime is None:
            raise HTTPException(503, "LLM runtime not configured: set ANTHROPIC_API_KEY")
        ticker = req.ticker.upper()
        if ticker not in c.store.coverage():
            raise HTTPException(409, f"{ticker} is not ingested; POST /ingest first")
        state = runs.create(ticker, req.question, req.depth.value)
        effort = str(DEPTH_POLICY[req.depth]["effort"])

        def work(publish: Any) -> ResearchResult:
            return c.orchestrator(effort, publish).research(ticker, req.question, req.depth)

        runs.start(state, work)
        return ResearchAccepted(run_id=state.id)

    @app.get("/research", response_model=list[RunSummary])
    def list_runs() -> list[RunSummary]:
        return [_summary(s) for s in runs.list()]

    @app.get("/research/{run_id}", response_model=RunDetail)
    def get_run(run_id: str) -> RunDetail:
        s = runs.get(run_id)
        if s is None:
            raise HTTPException(404, "run not found")
        return RunDetail(**_summary(s).model_dump(), result=s.result, events=s.events)

    @app.get("/research/{run_id}/events")
    async def events(run_id: str) -> EventSourceResponse:
        s = runs.get(run_id)
        if s is None:
            raise HTTPException(404, "run not found")
        backlog, q = s.subscribe()

        async def gen() -> AsyncIterator[dict[str, str]]:
            for ev in backlog:
                yield {"event": ev.type, "data": ev.model_dump_json()}
            loop = asyncio.get_running_loop()
            while True:
                try:
                    item = await loop.run_in_executor(None, q.get, True, 15)
                except queue.Empty:
                    yield {"event": "ping", "data": "{}"}
                    continue
                if item is None:
                    yield {"event": "close", "data": json.dumps({"status": s.status})}
                    return
                yield {"event": item.type, "data": item.model_dump_json()}

        return EventSourceResponse(gen())

    return app


def app_factory() -> FastAPI:
    """Entry point for `uvicorn fin_research.api.main:app_factory --factory`."""
    return create_app()
