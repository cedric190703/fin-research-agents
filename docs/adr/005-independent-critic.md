# ADR-005 — Independent critic agent over self-verification

**Status:** Accepted · 2026-09-12

## Context
Asking a model "are you sure?" in the same context mostly yields "yes". The reasoning that produced a claim is still visible, and the model anchors on it.

## Decision
A separate Critic agent (Opus 5, effort `high`) receives only the memo and has only read tools (`search_filings`, `read_section`, `recompute`). It must locate independent support for every claim and returns a per-claim verdict. The orchestrator owns the revision loop (max 2 rounds). Unsupported claims that survive are shown flagged, never removed silently.

## Consequences
+ Real independence: the critic cannot see how the claim was derived.
+ Verdicts are structured, so faithfulness can be measured over time.
− Roughly doubles the cost of a `deep` run; `brief` depth skips the critic and says so.
− A strict critic can flag true claims whose support is in a document not yet ingested — surfaced as `needs_update`, not `unsupported`.

## Alternatives rejected
- Self-check in the writer prompt — cheap, weak.
- Human review only — does not scale and gives no metric.
