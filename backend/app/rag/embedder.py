"""Text embedders — protocol + real (sentence-transformers) + fake (tests).

We use BAAI/bge-small-en-v1.5 by default. It's:
  - Open-source (MIT license)
  - Small: ~33M params, runs on CPU
  - Strong on retrieval benchmarks (top of MTEB for its size class)
  - No API costs, no rate limits, no per-token pricing

The Embedder protocol lets tests swap in a FakeEmbedder that returns
deterministic vectors from a hash, so we don't have to load a real model
in every test run.
"""
from __future__ import annotations

import hashlib
import math
from typing import Protocol, Sequence


class Embedder(Protocol):
    """Anything that turns text into a fixed-size vector."""

    @property
    def dimension(self) -> int: ...

    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class SentenceTransformerEmbedder:
    """Real embedder backed by sentence-transformers.

    Loads the model lazily on first use so importing the module is cheap.
    """

    def __init__(self, model_name: str = "BAAI/bge-small-en-v1.5"):
        self.model_name = model_name
        self._model = None
        self._dimension: int | None = None

    def _load(self) -> None:
        if self._model is None:
            # Deferred import — sentence-transformers pulls torch which is heavy.
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_name)
            self._dimension = int(self._model.get_sentence_embedding_dimension())

    @property
    def dimension(self) -> int:
        self._load()
        assert self._dimension is not None
        return self._dimension

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        self._load()
        if not texts:
            return []
        assert self._model is not None
        vectors = self._model.encode(
            list(texts),
            normalize_embeddings=True,  # bge models require L2 normalization
            convert_to_numpy=True,
        )
        return [v.tolist() for v in vectors]


class FakeEmbedder:
    """Deterministic hash-based embedder for tests. No ML dependencies.

    Same text -> same vector. Similar text (overlapping tokens) ends up in
    similar directions because we sum per-token contributions. Good enough
    to write meaningful retrieval tests without loading a real model.
    """

    def __init__(self, dimension: int = 32):
        self._dimension = dimension

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._embed_one(t) for t in texts]

    def _embed_one(self, text: str) -> list[float]:
        vec = [0.0] * self._dimension
        tokens = _tokenize(text)
        if not tokens:
            return _unit(vec) or [1.0 / math.sqrt(self._dimension)] * self._dimension
        for tok in tokens:
            digest = hashlib.sha256(tok.encode("utf-8")).digest()
            for i in range(self._dimension):
                # Map byte -> [-1, 1) then accumulate.
                byte = digest[i % len(digest)]
                vec[i] += (byte / 127.5) - 1.0
        return _unit(vec)


def _tokenize(text: str) -> list[str]:
    return [t for t in text.lower().replace("_", " ").split() if t]


def _unit(vec: list[float]) -> list[float]:
    n = math.sqrt(sum(v * v for v in vec))
    if n == 0:
        return vec
    return [v / n for v in vec]
