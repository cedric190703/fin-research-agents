# ADR-001 — Orchestrator with typed sub-agents, not one flat agent

**Status:** Accepted · 2026-09-12

## Context
A single Claude agent with every tool (search, market data, DCF, write memo) can produce a memo. But retrieval dumps 30–50 chunks into context per question, the writer then reasons over raw text it should never see, and there is no independent check on the output.

## Decision
One orchestrator (Opus 5) plans and delegates. Sub-agents (Filings Analyst, Quant Analyst, Memo Writer, Critic) are exposed to it as tools (`delegate(agent, task)`). Each sub-agent runs in its own tool-runner with its own system prompt, tool set and model, and returns a Pydantic-validated result — never its transcript.

## Consequences
+ Orchestrator context stays small → high prompt-cache hit rate, cheaper turns.
+ Per-role model choice (Sonnet for reading, Opus for judging).
+ Parallel fan-out for independent sub-questions.
+ Critic runs in a clean context → real independence.
− More moving parts: five prompts to version, a delegation protocol to test.
− Latency: each delegation adds at least one round-trip; mitigated by parallelism.

## Alternatives rejected
- Flat single agent — simplest, but fails goals G3 (verification) and cache efficiency.
- Managed Agents multiagent roster — attractive for hosting, but the resume value is in owning the harness; revisit for deployment.
