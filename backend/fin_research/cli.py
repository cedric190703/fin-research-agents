"""Command line: ingest a ticker, run research, print coverage."""

from __future__ import annotations

import argparse
import json
import sys

from fin_research.api.deps import build_container
from fin_research.ingestion.pipeline import build_chunks
from fin_research.schemas import Depth


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="fin-research")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_ing = sub.add_parser("ingest", help="Fetch and index filings for a ticker")
    p_ing.add_argument("ticker")
    p_ing.add_argument("--limit", type=int, default=6)
    p_res = sub.add_parser("research", help="Run the agent team on a question")
    p_res.add_argument("ticker")
    p_res.add_argument("--question", default="Full research memo")
    p_res.add_argument("--depth", choices=[d.value for d in Depth], default="standard")
    sub.add_parser("coverage", help="Show what is ingested")
    args = parser.parse_args(argv)

    c = build_container()
    if args.cmd == "coverage":
        print(json.dumps(c.store.coverage(), indent=2))
        return 0
    if args.cmd == "ingest":
        cik = c.edgar.resolve_cik(args.ticker)
        total = 0
        for ref in c.edgar.list_filings(args.ticker, cik, limit=args.limit):
            chunks = build_chunks(ref, c.edgar.fetch_document(ref))
            kids = [ch for ch in chunks if ch.level == "child"]
            vecs = c.embedder.embed([k.text for k in kids])
            total += c.store.upsert(chunks, dict(zip([k.id for k in kids], vecs, strict=True)))
            print(f"indexed {ref.form_type} {ref.accession_no} ({len(chunks)} chunks)")
        print(f"total chunks: {total}")
        return 0
    if args.cmd == "research":
        depth = Depth(args.depth)
        orch = c.orchestrator(
            effort="medium", on_event=lambda e: print(f"[{e.agent}] {e.type}", file=sys.stderr)
        )
        result = orch.research(args.ticker, args.question, depth)
        print(result.model_dump_json(indent=2))
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
