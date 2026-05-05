"""類似炎上事例 Vector Search — Cosmos DB DiskANN + キーワードフォールバック"""
from __future__ import annotations

import json
import logging
import math
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_SEED_PATH = Path(__file__).parent.parent / "data" / "incident_corpus_seed.json"
_CORPUS_CONTAINER = "incident_corpus"

_seed_cache: list[dict[str, Any]] | None = None
_cosmos_client: Any | None = None
_httpx_client: Any | None = None


def _get_httpx_client() -> Any:
    global _httpx_client
    if _httpx_client is None:
        import httpx
        _httpx_client = httpx.Client(timeout=10)
    return _httpx_client


def _get_cosmos_client(endpoint: str, key: str) -> Any:
    global _cosmos_client
    if _cosmos_client is None:
        from azure.cosmos import CosmosClient
        _cosmos_client = CosmosClient(endpoint, credential=key)
    return _cosmos_client


def _load_seed() -> list[dict[str, Any]]:
    global _seed_cache
    if _seed_cache is None:
        try:
            _seed_cache = json.loads(_SEED_PATH.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("seed load failed: %s", exc)
            _seed_cache = []
    return _seed_cache


def _keyword_similarity(text: str, case: dict[str, Any]) -> float:
    """キーワードオーバーラップによる生スコアを返す（後段で 0〜1 に正規化される）。"""
    keywords: list[str] = case.get("keywords", [])
    if not keywords:
        return 0.0
    hits = sum(1 for kw in keywords if kw in text)
    return hits / math.sqrt(len(keywords))


def _normalize(scores: list[float]) -> list[float]:
    """スコアを 0〜1 に正規化する。"""
    max_s = max(scores) if scores else 1.0
    if max_s == 0:
        return scores
    return [s / max_s for s in scores]


def _search_keyword(query_text: str, top_k: int) -> list[dict[str, Any]]:
    """キーワードベースの類似事例検索（フォールバック）。"""
    from shared.models import SimilarCase

    corpus = _load_seed()
    scored = [(_keyword_similarity(query_text, c), c) for c in corpus]
    scored.sort(key=lambda x: x[0], reverse=True)
    # 相対正規化（最大値除算）は弱い単独マッチを 1.0 に見せる誤解を招くため
    # 絶対スコアを 1.0 でキャップする方式を採用する
    return [
        SimilarCase(
            case_id=c.get("case_id", ""),
            title=c.get("title", ""),
            similarity_score=round(min(s, 1.0), 3),
            outcome=c.get("outcome", ""),
            lessons_learned=c.get("lessons_learned", ""),
            applicable_actions=c.get("applicable_actions", []),
        ).model_dump()
        for s, c in scored[:top_k]
        if s > 0
    ]


def _search_cosmos_vector(query_text: str, top_k: int) -> list[dict[str, Any]] | None:
    """Cosmos DB Vector Search（Azure OpenAI embedding 使用）。失敗時は None を返す。"""
    endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT")
    key = os.environ.get("AZURE_OPENAI_KEY")
    cosmos_endpoint = os.environ.get("COSMOS_ENDPOINT")
    cosmos_key = os.environ.get("COSMOS_KEY")
    db_name = os.environ.get("COSMOS_DATABASE", "after-hours-agents")

    if not all([endpoint, key, cosmos_endpoint, cosmos_key]):
        return None

    # narrowing: all 4 values are truthy str at this point
    endpoint = str(endpoint)
    key = str(key)
    cosmos_endpoint = str(cosmos_endpoint)
    cosmos_key = str(cosmos_key)

    try:
        http = _get_httpx_client()
        deployment = os.environ.get("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "text-embedding-ada-002")
        embed_url = (
            f"{endpoint.rstrip('/')}/openai/deployments/"
            f"{deployment}/embeddings?api-version=2024-02-01"
        )
        resp = http.post(
            embed_url,
            headers={"api-key": key, "Content-Type": "application/json"},
            json={"input": query_text[:2000]},
        )
        resp.raise_for_status()
        vector = resp.json()["data"][0]["embedding"]

        client = _get_cosmos_client(cosmos_endpoint, cosmos_key)
        container = client.get_database_client(db_name).get_container_client(
            _CORPUS_CONTAINER
        )
        raw = list(
            container.query_items(
                query=(
                    "SELECT TOP @top_k c.case_id, c.title, c.outcome, "
                    "c.lessons_learned, c.applicable_actions, "
                    "VectorDistance(c.embedding, @vec) AS distance "
                    "FROM c ORDER BY VectorDistance(c.embedding, @vec)"
                ),
                parameters=[
                    {"name": "@top_k", "value": top_k},
                    {"name": "@vec", "value": vector},
                ],
                enable_cross_partition_query=True,
            )
        )
        # VectorDistance は距離（0=同一）を返すため similarity_score に変換する
        from shared.models import SimilarCase
        return [
            SimilarCase(
                case_id=item.get("case_id", ""),
                title=item.get("title", ""),
                similarity_score=round(max(0.0, 1.0 - item.pop("distance", 0.0)), 3),
                outcome=item.get("outcome", ""),
                lessons_learned=item.get("lessons_learned", ""),
                applicable_actions=item.get("applicable_actions", []),
            ).model_dump()
            for item in raw
        ]
    except Exception as exc:
        logger.warning("Cosmos vector search failed, falling back: %s", exc)
        return None


def search_similar_cases(query_text: str, top_k: int = 3) -> list[dict[str, Any]]:
    """類似炎上事例を最大 top_k 件返す。Cosmos Vector → キーワードの順でフォールバック。"""
    results = _search_cosmos_vector(query_text, top_k)
    if results is not None:
        return results
    return _search_keyword(query_text, top_k)
