"""Reciprocal Rank Fusion for combining ranked lists from different retrievers."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence


def reciprocal_rank_fusion(
    rankings: Iterable[Sequence[str]], k: int = 60, weights: Sequence[float] | None = None
) -> list[tuple[str, float]]:
    """Fuse ranked id lists. Returns (id, score) sorted by descending score.

    RRF score = Σ weight_r / (k + rank_r). k=60 is the standard default; it
    dampens the advantage of being first in any single list.
    """
    rankings = list(rankings)
    weights = list(weights) if weights is not None else [1.0] * len(rankings)
    if len(weights) != len(rankings):
        raise ValueError("weights must match rankings")
    scores: dict[str, float] = defaultdict(float)
    for ranking, w in zip(rankings, weights, strict=True):
        for rank, doc_id in enumerate(ranking, start=1):
            scores[doc_id] += w / (k + rank)
    return sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
