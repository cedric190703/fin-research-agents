import httpx
import respx

from marginalia.knowledge.embeddings import VOYAGE_URL, HashingEmbedder, VoyageEmbedder, cosine
from marginalia.knowledge.fusion import reciprocal_rank_fusion
from marginalia.knowledge.retrieval import HybridRetriever, citation_for, compare_sections
from marginalia.knowledge.store import Filters, InMemoryStore

# --- embeddings ---------------------------------------------------------------


def test_hashing_embedder_is_deterministic_and_normalised():
    e = HashingEmbedder(dim=64)
    a, b = e.embed(["revenue grew", "revenue grew"])
    assert a == b
    assert abs(sum(x * x for x in a) - 1.0) < 1e-9
    assert cosine(a, e.embed(["revenue fell"])[0]) > cosine(a, e.embed(["zebra"])[0])


@respx.mock
def test_voyage_embedder_batches_and_orders_results():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = request.read()
        import json

        payload = json.loads(body)
        calls.append(len(payload["input"]))
        data = [
            {"index": i, "embedding": [float(i)]} for i in reversed(range(len(payload["input"])))
        ]
        return httpx.Response(200, json={"data": data})

    respx.post(VOYAGE_URL).mock(side_effect=handler)
    e = VoyageEmbedder(api_key="k", dim=1)
    out = e.embed([f"t{i}" for i in range(130)])
    assert calls == [128, 2]
    assert out[0] == [0.0] and out[127] == [127.0] and out[129] == [1.0]


# --- fusion -------------------------------------------------------------------


def test_rrf_rewards_documents_present_in_both_lists():
    fused = reciprocal_rank_fusion([["a", "b", "c"], ["c", "d"]])
    ids = [i for i, _ in fused]
    assert ids[0] == "c"  # appears in both
    assert set(ids) == {"a", "b", "c", "d"}


def test_rrf_weights_shift_ranking():
    fused = reciprocal_rank_fusion([["a"], ["b"]], weights=[1.0, 3.0])
    assert fused[0][0] == "b"


# --- store --------------------------------------------------------------------


def test_filters_restrict_by_ticker_year_and_item(store: InMemoryStore):
    ids = [i for i, _ in store.sparse_search("advanced chips", Filters(ticker="AAPL"), 10)]
    assert set(ids) == {"c24b", "c23b"}
    ids = [i for i, _ in store.sparse_search("advanced chips", Filters(fiscal_years=(2024,)), 10)]
    assert ids == ["c24b"]
    ids = [i for i, _ in store.sparse_search("revenue", Filters(items=("7",)), 10)]
    assert set(ids) == {"c7a", "msft"}  # both Item 7, both tickers
    ids = [i for i, _ in store.sparse_search("revenue", Filters(ticker="AAPL", items=("7",)), 10)]
    assert ids == ["c7a"]


def test_sparse_search_exact_token_beats_paraphrase(store: InMemoryStore):
    ids = [i for i, _ in store.sparse_search("ASC 842", Filters(), 3)]
    assert ids[0] == "c7b"


def test_upsert_is_idempotent(store: InMemoryStore):
    before = store.coverage()["AAPL"]["chunks"]
    from tests.conftest import CORPUS

    store.upsert(CORPUS[:2], {})
    assert store.coverage()["AAPL"]["chunks"] == before


# --- retriever ----------------------------------------------------------------


def test_hybrid_search_returns_parents_deduped(store: InMemoryStore, embedder: HashingEmbedder):
    r = HybridRetriever(store=store, embedder=embedder, final_k=5)
    hits = r.search("Taiwan suppliers chips", Filters(ticker="AAPL"))
    assert hits[0].chunk.id == "p24"  # parent of the best child
    assert len({h.chunk.id for h in hits}) == len(hits)
    assert [h.rank for h in hits] == list(range(1, len(hits) + 1))


def test_reranker_is_applied(store: InMemoryStore, embedder: HashingEmbedder):
    def rerank(query: str, chunks):
        return [1.0 if c.id == "c7a" else 0.0 for c in chunks]

    r = HybridRetriever(store=store, embedder=embedder, reranker=rerank, final_k=2)
    hits = r.search("anything at all revenue", Filters(ticker="AAPL"))
    assert hits[0].chunk.id == "p7" and hits[0].score == 1.0


def test_citation_for_resolves_absolute_offsets(store: InMemoryStore):
    chunk = store.get("c24b")
    assert chunk is not None
    cit = citation_for(chunk, "Taiwan-based suppliers")
    assert cit is not None
    assert (cit.char_start, cit.char_end) == (50 + 13, 50 + 13 + len("Taiwan-based suppliers"))
    assert citation_for(chunk, "not in text") is None


def test_compare_sections_reports_added_and_removed_paragraphs(store: InMemoryStore):
    diff = compare_sections(store, "AAPL", "1A", (2023, 2024))
    assert diff.unchanged == 1
    assert diff.removed == ["We depend on suppliers for advanced chips."]
    assert diff.added == [
        "We depend on Taiwan-based suppliers for advanced chips.",
        "Foreign exchange headwinds reduced revenue.",
    ]
