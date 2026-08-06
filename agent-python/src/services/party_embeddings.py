"""Optional embedding provider for party-knowledge hybrid retrieval."""
from __future__ import annotations

import os
import hashlib
import logging
import math
from functools import lru_cache


logger = logging.getLogger(__name__)
QWEN_VL_EMBEDDING_DIMENSIONS = 4096
PROJECTED_EMBEDDING_DIMENSIONS = 1536


@lru_cache(maxsize=1)
def _client():
    from openai import OpenAI
    provider = os.getenv("OA_AGENT_EMBEDDING_PROVIDER", "siliconflow").lower()
    if provider != "siliconflow":
        raise RuntimeError("PARTY_EMBEDDING_PROVIDER_NOT_ALLOWED: 党务向量检索只允许使用 SiliconFlow")
    api_key = os.getenv("OA_AGENT_EMBEDDING_API_KEY")
    base_url = os.getenv("OA_AGENT_EMBEDDING_BASE_URL") or "https://api.siliconflow.cn/v1"
    if not api_key or "siliconflow" not in base_url.lower():
        raise RuntimeError("PARTY_EMBEDDING_CONFIG_INVALID: 缺少 SiliconFlow embedding 配置")
    return OpenAI(
        api_key=api_key,
        base_url=base_url.rstrip("/"),
    )


def local_hash_embedding(text: str, dimensions: int = QWEN_VL_EMBEDDING_DIMENSIONS) -> list[float]:
    """Deterministic emergency vector; replace with a semantic provider in production."""
    vector = [0.0] * dimensions
    normalized = text.lower().strip()
    grams = [normalized[i:i + 3] for i in range(max(1, len(normalized) - 2))]
    for gram in grams:
        digest = hashlib.sha256(gram.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % dimensions
        vector[index] += 1.0 if digest[4] & 1 else -1.0
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / norm for value in vector]


def project_embedding(vector: list[float], dimensions: int = PROJECTED_EMBEDDING_DIMENSIONS) -> list[float]:
    """Stable feature-hash projection shared by indexing and query paths."""
    projected = [0.0] * dimensions
    for index, value in enumerate(vector):
        digest = hashlib.sha256(f"party-projection:{index}".encode("ascii")).digest()
        bucket = int.from_bytes(digest[:4], "big") % dimensions
        projected[bucket] += value if digest[4] & 1 else -value
    norm = math.sqrt(sum(value * value for value in projected)) or 1.0
    return [value / norm for value in projected]


def embed_text(text: str) -> list[float] | None:
    provider = os.getenv("OA_AGENT_EMBEDDING_PROVIDER", "siliconflow").lower()
    if provider == "local_hash":
        return local_hash_embedding(text)
    if provider != "siliconflow":
        logger.warning("party knowledge embedding provider is not allowed: %s", provider)
        return None
    if not os.getenv("OA_AGENT_EMBEDDING_API_KEY"):
        return None
    model = os.getenv(
        "OA_AGENT_EMBEDDING_MODEL",
        "Qwen/Qwen3-VL-Embedding-8B" if provider == "siliconflow" else "text-embedding-3-small",
    )
    try:
        response = _client().embeddings.create(model=model, input=text)
        vector = list(response.data[0].embedding)
        # Qwen3-VL-Embedding-8B returns a 4096-dimensional vector. Do not
        # silently write a different model's vector into the fixed pgvector
        # column: that would turn a provider/configuration mistake into a
        # delayed database failure during ingestion.
        expected_dimensions = int(os.getenv("OA_AGENT_EMBEDDING_DIMENSIONS", str(QWEN_VL_EMBEDDING_DIMENSIONS)))
        if len(vector) != expected_dimensions:
            logger.warning(
                "party knowledge embedding dimension mismatch: provider=%s model=%s expected=%s actual=%s",
                provider,
                model,
                expected_dimensions,
                len(vector),
            )
            return None
        return vector
    except Exception as exc:
        # Retrieval intentionally degrades to the Java keyword path.  Do not
        # replace a failed semantic model with a hash embedding in production:
        # it looks valid but has no semantic meaning and corrupts ranking.
        logger.warning("party knowledge embedding request failed: %s", exc.__class__.__name__)
        return None


def embed_query(text: str) -> list[float] | None:
    if os.getenv("OA_AGENT_KNOWLEDGE_EMBEDDING", "false").lower() != "true":
        return None
    return embed_text(text)
