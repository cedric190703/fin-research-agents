CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS filings (
    id            TEXT PRIMARY KEY,           -- accession number
    cik           BIGINT NOT NULL,
    ticker        TEXT NOT NULL,
    form_type     TEXT NOT NULL,
    accession_no  TEXT NOT NULL UNIQUE,
    fiscal_year   INT  NOT NULL,
    fiscal_period TEXT NOT NULL,
    filed_at      DATE NOT NULL,
    source_url    TEXT NOT NULL,
    ingested_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS chunks (
    id            TEXT PRIMARY KEY,
    filing_id     TEXT NOT NULL REFERENCES filings(id) ON DELETE CASCADE,
    ticker        TEXT NOT NULL,
    form_type     TEXT NOT NULL,
    fiscal_year   INT  NOT NULL,
    fiscal_period TEXT NOT NULL,
    item          TEXT NOT NULL,
    level         TEXT NOT NULL CHECK (level IN ('parent', 'child')),
    parent_id     TEXT REFERENCES chunks(id) ON DELETE CASCADE,
    text          TEXT NOT NULL,
    char_start    INT  NOT NULL,
    char_end      INT  NOT NULL,
    tags          JSONB NOT NULL DEFAULT '{}'::jsonb,
    embedding     vector(1024),
    tsv           tsvector GENERATED ALWAYS AS (to_tsvector('english', text)) STORED
);
CREATE INDEX IF NOT EXISTS chunks_embedding_hnsw ON chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS chunks_tsv_gin        ON chunks USING gin (tsv);
CREATE INDEX IF NOT EXISTS chunks_tags_gin       ON chunks USING gin (tags);
CREATE INDEX IF NOT EXISTS chunks_filter         ON chunks (ticker, fiscal_year, item, level);

CREATE TABLE IF NOT EXISTS fundamentals (
    ticker           TEXT NOT NULL,
    fiscal_year      INT  NOT NULL,
    fiscal_period    TEXT NOT NULL,
    concept          TEXT NOT NULL,
    value            NUMERIC NOT NULL,
    unit             TEXT NOT NULL,
    source_accession TEXT NOT NULL,
    PRIMARY KEY (ticker, fiscal_year, fiscal_period, concept)
);

CREATE TABLE IF NOT EXISTS runs (
    id            TEXT PRIMARY KEY,
    ticker        TEXT NOT NULL,
    question      TEXT NOT NULL,
    depth         TEXT NOT NULL,
    status        TEXT NOT NULL,
    started_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at   TIMESTAMPTZ,
    cost_usd      NUMERIC(10,6),
    tokens_in     INT,
    tokens_out    INT
);

CREATE TABLE IF NOT EXISTS run_events (
    id       BIGSERIAL PRIMARY KEY,
    run_id   TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    agent    TEXT NOT NULL,
    type     TEXT NOT NULL,
    payload  JSONB NOT NULL DEFAULT '{}'::jsonb,
    ts       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS run_events_run ON run_events (run_id, id);

CREATE TABLE IF NOT EXISTS memos (
    run_id   TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    version  INT  NOT NULL,
    body     JSONB NOT NULL,
    verdict  JSONB,
    PRIMARY KEY (run_id, version)
);

CREATE TABLE IF NOT EXISTS eval_sets (
    id     TEXT PRIMARY KEY,
    name   TEXT NOT NULL,
    items  JSONB NOT NULL
);
