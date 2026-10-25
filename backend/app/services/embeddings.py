"""
Embedding generation for semantic retrieval, using the configured Gemini embedding model.

The vector size is fixed at EMBEDDING_DIM so it matches the pgvector column. When no API key is
configured, or a call fails, callers get None/empty results and the document is indexed for
keyword search only (reported as PARTIALLY_INDEXED, never as a silent success).
"""
import json
import logging
import math
from typing import List, Optional, Sequence

from ..config import settings

logger = logging.getLogger(__name__)

EMBEDDING_DIM = 768
_BATCH_SIZE = 50
# Used when the configured model is retired (e.g. text-embedding-004 now returns 404 NOT_FOUND)
FALLBACK_MODELS = ("gemini-embedding-001", "gemini-embedding-2")


class EmbeddingService:
    def __init__(self):
        self.model = settings.GEMINI_EMBEDDING_MODEL
        self._fallbacks = [m for m in FALLBACK_MODELS if m != self.model]
        self._client = None
        self.last_error: Optional[str] = None  # short reason the last document embedding call failed
        key = settings.GEMINI_API_KEY
        if key and key != "YOUR_GEMINI_API_KEY_HERE":
            try:
                from google import genai
                from google.genai import types
                self._client = genai.Client(api_key=key, http_options=types.HttpOptions(timeout=30000))
            except Exception as e:  # pragma: no cover - depends on installed SDK
                logger.warning(f"Embedding client unavailable: {e}")

    def is_available(self) -> bool:
        return self._client is not None

    def _embed_batch(self, batch: List[str], task_type: str, max_rate_waits: int = 5):
        """
        Embed one batch. Switches to a fallback model if the configured one no longer exists, and
        waits out per-minute quota limits (HTTP 429). Daily-quota errors are raised to the caller.
        """
        import re
        import time
        from google.genai import types
        waits = 0
        while True:
            try:
                return self._client.models.embed_content(
                    model=self.model,
                    contents=batch,
                    config=types.EmbedContentConfig(task_type=task_type, output_dimensionality=EMBEDDING_DIM),
                )
            except Exception as e:
                msg = str(e)
                if ("NOT_FOUND" in msg or "404" in msg) and self._fallbacks:
                    retired, self.model = self.model, self._fallbacks.pop(0)
                    logger.warning(f"Embedding model '{retired}' is unavailable; using '{self.model}'. "
                                   f"Set GEMINI_EMBEDDING_MODEL={self.model} to silence this warning.")
                    continue
                per_minute = "RESOURCE_EXHAUSTED" in msg and "PerMinute" in msg and "PerDay" not in msg
                if per_minute and waits < max_rate_waits:
                    m = re.search(r"retry in ([\d.]+)s", msg)
                    delay = min(float(m.group(1)) + 1.0 if m else 30.0, 65.0)
                    waits += 1
                    logger.info(f"Embedding rate limit reached; waiting {delay:.0f}s (attempt {waits}/{max_rate_waits}).")
                    time.sleep(delay)
                    continue
                raise

    def _embed(self, texts: Sequence[str], task_type: str) -> List[List[float]]:
        vectors: List[List[float]] = []
        for i in range(0, len(texts), _BATCH_SIZE):
            batch = [t[:8000] for t in texts[i:i + _BATCH_SIZE]]
            resp = self._embed_batch(batch, task_type)
            for emb in resp.embeddings:
                values = list(emb.values)
                if len(values) != EMBEDDING_DIM:
                    raise ValueError(f"Embedding model returned {len(values)} dims, expected {EMBEDDING_DIM}")
                vectors.append(_normalise(values))
        return vectors

    def embed_documents(self, texts: Sequence[str]) -> Optional[List[List[float]]]:
        """Vectors for chunks, or None if embeddings are unavailable or the call failed."""
        if not self.is_available() or not texts:
            return None
        self.last_error = None
        try:
            return self._embed(texts, "RETRIEVAL_DOCUMENT")
        except Exception as e:
            logger.warning(f"Document embedding failed ({self.model}): {e}")
            self.last_error = describe_embedding_error(e, self.model)
            return None

    def embed_query(self, text: str) -> Optional[List[float]]:
        if not self.is_available() or not text.strip():
            return None
        try:
            return self._embed([text], "RETRIEVAL_QUERY")[0]
        except Exception as e:
            logger.warning(f"Query embedding failed ({self.model}): {e}")
            return None


def describe_embedding_error(e: Exception, model: str = "the embedding model") -> str:
    """A short, officer-readable reason for an embedding failure (no request details or keys)."""
    msg = str(e)
    if "RESOURCE_EXHAUSTED" in msg or "429" in msg:
        if "PerDay" in msg:
            return f"daily embedding quota exhausted for {model}; run backfill_embeddings.py after it resets"
        return "embedding rate limit reached; run backfill_embeddings.py later"
    if "DEADLINE_EXCEEDED" in msg or "timed out" in msg.lower():
        return "embedding request timed out"
    return f"{type(e).__name__}: {msg[:160]}"


def _normalise(v: List[float]) -> List[float]:
    norm = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / norm for x in v]


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    """Cosine similarity of two already-normalised vectors."""
    return sum(x * y for x, y in zip(a, b))


def to_json(v: Sequence[float]) -> str:
    return json.dumps([round(x, 6) for x in v])


def to_pgvector(v: Sequence[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in v) + "]"


embedding_service = EmbeddingService()
