"""Dependency wiring. One place decides memory-vs-Postgres, fake-vs-Voyage, etc."""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from marginalia.agents.orchestrator import EventSink, Orchestrator
from marginalia.agents.roster import build_roster
from marginalia.agents.runtime import AgentRuntime, AnthropicRuntime
from marginalia.agents.toolkits import CriticToolkit, FilingsToolkit, QuantToolkit
from marginalia.config import Settings, get_settings
from marginalia.ingestion.edgar import EdgarClient
from marginalia.knowledge.embeddings import Embedder, HashingEmbedder, VoyageEmbedder
from marginalia.knowledge.retrieval import HybridRetriever
from marginalia.knowledge.store import ChunkStore, InMemoryStore
from marginalia.tools.finance import default_registry
from marginalia.tools.provenance import ToolRegistry


@dataclass
class Container:
    settings: Settings
    store: ChunkStore
    embedder: Embedder
    registry: ToolRegistry
    runtime: AgentRuntime | None
    edgar: EdgarClient
    load_fundamentals: Callable[[str, int], Mapping[str, float]]

    def orchestrator(self, effort: str, on_event: EventSink) -> Orchestrator:
        if self.runtime is None:
            raise RuntimeError("No LLM runtime configured (set ANTHROPIC_API_KEY)")
        retriever = HybridRetriever(store=self.store, embedder=self.embedder)
        filings = FilingsToolkit(store=self.store, retriever=retriever)
        quant = QuantToolkit(registry=self.registry, load_fundamentals=self.load_fundamentals)
        critic = CriticToolkit(filings=filings, registry=self.registry)
        return Orchestrator(
            runtime=self.runtime,
            roster=build_roster(self.settings, effort=effort),
            filings=filings,
            quant=quant,
            critic=critic,
            coverage=self.store.coverage,
            on_event=on_event,
        )


def _no_fundamentals(ticker: str, fiscal_year: int) -> Mapping[str, float]:
    raise LookupError(f"No fundamentals loaded for {ticker} FY{fiscal_year}")


def build_container(settings: Settings | None = None) -> Container:
    settings = settings or get_settings()
    backend = os.environ.get("STORE_BACKEND", "memory")
    store: ChunkStore
    if backend == "postgres":
        from marginalia.knowledge.store import PostgresStore

        store = PostgresStore(settings.database_url)
    else:
        store = InMemoryStore()

    embedder: Embedder = (
        VoyageEmbedder(settings.voyage_api_key, settings.embedding_model, settings.embedding_dim)
        if settings.voyage_api_key
        else HashingEmbedder(dim=settings.embedding_dim)
    )
    runtime = AnthropicRuntime() if settings.anthropic_api_key else None
    return Container(
        settings=settings,
        store=store,
        embedder=embedder,
        registry=default_registry(),
        runtime=runtime,
        edgar=EdgarClient(user_agent=settings.sec_user_agent),
        load_fundamentals=_no_fundamentals,
    )
