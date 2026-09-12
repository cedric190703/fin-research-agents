import json

import httpx
import respx
from fastapi.testclient import TestClient

from marginalia.agents.runtime import FakeRuntime
from marginalia.api.deps import Container
from marginalia.api.main import create_app
from marginalia.config import Settings
from marginalia.ingestion.edgar import SUBMISSIONS_URL, TICKERS_URL, EdgarClient
from marginalia.knowledge.embeddings import HashingEmbedder
from marginalia.knowledge.store import InMemoryStore
from marginalia.tools.finance import default_registry
from tests.test_agents import FAIL, FINDINGS, MEMO, METRICS, PASS, PLAN
from tests.test_finance_tools import STATEMENT
from tests.test_ingestion import SUBMISSIONS, make_filing_text


def make_client(store: InMemoryStore, runtime: FakeRuntime | None) -> TestClient:
    container = Container(
        settings=Settings(),
        store=store,
        embedder=HashingEmbedder(dim=128),
        registry=default_registry(),
        runtime=runtime,
        edgar=EdgarClient(user_agent="test test@example.com"),
        load_fundamentals=lambda t, y: STATEMENT,
    )
    return TestClient(create_app(container))


def test_health_reports_wiring(store):
    client = make_client(store, None)
    body = client.get("/health").json()
    assert body["status"] == "ok" and body["llm"] is False
    assert body["store"] == "InMemoryStore" and body["embedder"] == "HashingEmbedder"


def test_coverage_endpoint(store):
    client = make_client(store, None)
    cov = client.get("/coverage").json()
    assert cov["AAPL"]["latest_fiscal_year"] == 2024


def test_research_requires_runtime_and_ingested_ticker(store):
    client = make_client(store, None)
    assert client.post("/research", json={"ticker": "AAPL"}).status_code == 503
    rt = FakeRuntime(scripts={})
    client = make_client(store, rt)
    assert client.post("/research", json={"ticker": "TSLA"}).status_code == 409
    assert client.post("/research", json={"ticker": "bad ticker!"}).status_code == 422


def test_research_run_lifecycle_and_sse_stream(store):
    rt = FakeRuntime(
        scripts={
            "planner": [PLAN],
            "filings_analyst": [FINDINGS] * 2,
            "quant_analyst": [METRICS],
            "memo_writer": [MEMO] * 2,
            "critic": [FAIL, PASS],
        }
    )
    client = make_client(store, rt)
    accepted = client.post("/research", json={"ticker": "aapl", "question": "q", "depth": "deep"})
    assert accepted.status_code == 202
    run_id = accepted.json()["run_id"]

    types = []
    with client.stream("GET", f"/research/{run_id}/events") as resp:
        assert resp.status_code == 200
        for line in resp.iter_lines():
            if line.startswith("event: "):
                types.append(line.split(": ", 1)[1])
            if line.startswith("event: close"):
                break
    assert types[0] == "run_started" and types[-1] == "close"
    assert types.count("verdict") == 2 and "memo" in types

    detail = client.get(f"/research/{run_id}").json()
    assert detail["status"] == "done"
    assert detail["result"]["revisions"] == 1
    assert detail["result"]["memo"]["ticker"] == "AAPL"
    assert detail["result"]["verdict"]["passed"] is True
    assert client.get("/research").json()[0]["run_id"] == run_id
    assert client.get("/research/nope").status_code == 404


def test_research_error_is_reported_not_swallowed(store):
    client = make_client(store, FakeRuntime(scripts={}))  # planner has no script → raises
    run_id = client.post("/research", json={"ticker": "AAPL"}).json()["run_id"]
    types = []
    with client.stream("GET", f"/research/{run_id}/events") as resp:
        for line in resp.iter_lines():
            if line.startswith("event: "):
                types.append(line.split(": ", 1)[1])
            if line.startswith("event: close"):
                break
    assert "error" in types
    detail = client.get(f"/research/{run_id}").json()
    assert detail["status"] == "error" and "FakeRuntime" in detail["error"]


@respx.mock
def test_ingest_endpoint_indexes_filings():
    respx.get(TICKERS_URL).mock(
        return_value=httpx.Response(
            200, json={"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple"}}
        )
    )
    respx.get(SUBMISSIONS_URL.format(cik=320193)).mock(
        return_value=httpx.Response(200, content=json.dumps(SUBMISSIONS))
    )
    html = "<html><body><p>" + make_filing_text().replace("\n", "</p><p>") + "</p></body></html>"
    respx.get(url__regex=r"https://www\.sec\.gov/Archives/.*").mock(
        return_value=httpx.Response(200, text=html)
    )

    store = InMemoryStore()
    client = make_client(store, None)
    res = client.post("/ingest", json={"ticker": "aapl", "limit": 2})
    assert res.status_code == 200
    body = res.json()
    assert body["ticker"] == "AAPL" and body["filings"] == 2 and body["chunks"] > 0
    assert client.get("/coverage").json()["AAPL"]["chunks"] == body["chunks"]
    assert (
        client.post("/ingest", json={"ticker": "aapl", "limit": 2}).json()["chunks"]
        == body["chunks"]
    )
    respx.get(TICKERS_URL).mock(return_value=httpx.Response(200, json={}))
    assert client.post("/ingest", json={"ticker": "ZZZZ"}).status_code == 404


def test_run_state_subscribe_after_close_replays_backlog_and_closes():
    from marginalia.api.runs import RunRegistry
    from marginalia.schemas import RunEvent

    reg = RunRegistry()
    st = reg.create("AAPL", "q", "brief")
    st.publish(RunEvent(run_id=st.id, agent="a", type="run_started"))
    backlog, q = st.subscribe()  # live subscriber
    st.publish(RunEvent(run_id=st.id, agent="a", type="done"))
    st.close()
    assert [e.type for e in backlog] == ["run_started"]
    assert q.get_nowait().type == "done" and q.get_nowait() is None
    backlog2, q2 = st.subscribe()  # late subscriber
    assert [e.type for e in backlog2] == ["run_started", "done"] and q2.get_nowait() is None
