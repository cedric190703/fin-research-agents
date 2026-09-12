"""Runtime configuration, loaded from environment / .env."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # LLM
    anthropic_api_key: str | None = None
    orchestrator_model: str = "claude-opus-5"
    analyst_model: str = "claude-sonnet-5"
    writer_model: str = "claude-opus-5"
    critic_model: str = "claude-opus-5"
    tagger_model: str = "claude-haiku-4-5"

    # Embeddings
    voyage_api_key: str | None = None
    embedding_model: str = "voyage-finance-2"
    embedding_dim: int = 1024

    # Storage
    database_url: str = "postgresql://fin_research:fin_research@localhost:5432/fin_research"

    # External data
    sec_user_agent: str = Field(
        default="FinResearchAgents bot contact@example.com",
        description="SEC requires a descriptive User-Agent with contact details.",
    )
    fred_api_key: str | None = None

    # Chunking
    child_chunk_tokens: int = 512
    child_chunk_overlap: int = 64
    parent_chunk_tokens: int = 2000

    # Agent budgets
    max_revisions: int = 2
    subagent_max_turns: int = 12


@lru_cache
def get_settings() -> Settings:
    return Settings()
