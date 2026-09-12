# ADR-004 — All numerics through deterministic tools

**Status:** Accepted · 2026-09-12

## Context
LLMs read tables unreliably and do arithmetic worse. A research memo whose EV/EBITDA is off by a factor of ten because a model misread "in thousands" is worse than no memo.

## Decision
Financial statements come from XBRL facts into a `fundamentals` table. All ratios, DCF and comps run in pandas/NumPy tools. Agents may *request* a computation and *interpret* the result; they never compute. Every result carries a `provenance` block (tool, args, data_as_of, hash) and the Critic can `recompute(metric_id)` to verify.

## Consequences
+ Numbers are exact and auditable; users can click through to the calculation.
+ Tools are unit-testable without any API calls.
− Every new metric needs code, not a prompt tweak.
− The Writer must be constrained (structured output) so it cannot "round" or restate a number.

## Alternatives rejected
- Embedding financial tables as text — known failure mode for retrieval and reading.
- Letting the model run code via code execution — flexible, but results are not replayable or unit-tested.
