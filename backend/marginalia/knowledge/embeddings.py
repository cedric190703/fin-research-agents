"""Embedding providers behind one interface.

Anthropic has no embeddings endpoint; Voyage AI is the recommended partner and
ships a finance-tuned model. `HashingEmbedder` is a deterministic stand-in for
tests and offline runs — not semantically meaningful, but stable.
"""

from __future__ import annotations

import hashlib
import math
import re
from typing import Protocol

import httpx

VOYAGE_URL = "https://api.voyageai.com/v1/embeddings"
_TOKEN = re.compile(r"[a-z0-9]+")


class Embedder(Protocol):
    dim: int

    def embed(self, texts: list[str], *, input_type: str = "document") -> list[list[float]]: ...


class VoyageEmbedder:
    def __init__(
        self,
        api_key: str,
        model: str = "voyage-finance-2",
        dim: int = 1024,
        client: httpx.Client | None = None,
    ) -> None:
        self.model = model
        self.dim = dim
        self._client = client or httpx.Client(
            headers={"Authorization": f"Bearer {api_key}"}, timeout=60.0
        )

    def embed(self, texts: list[str], *, input_type: str = "document") -> list[list[float]]:
        if not texts:
            return []
        out: list[list[float]] = []
        # Voyage accepts up to 128 inputs per call.
        for i in range(0, len(texts), 128):
            batch = texts[i : i + 128]
            resp = self._client.post(
                VOYAGE_URL, json={"input": batch, "model": self.model, "input_type": input_type}
            ).raise_for_status()
            data = sorted(resp.json()["data"], key=lambda d: d["index"])
            out.extend(d["embedding"] for d in data)
        return out


class HashingEmbedder:
    """Bag-of-hashed-tokens, L2-normalised. Deterministic; overlapping vocab → higher cosine."""

    def __init__(self, dim: int = 256) -> None:
        self.dim = dim

    def embed(self, texts: list[str], *, input_type: str = "document") -> list[list[float]]:
        return [self._one(t) for t in texts]

    def _one(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for tok in _TOKEN.findall(text.lower()):
            h = int(hashlib.md5(tok.encode(), usedforsecurity=False).hexdigest(), 16)
            vec[h % self.dim] += 1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(x * x for x in b)) or 1.0
    return dot / (na * nb)
