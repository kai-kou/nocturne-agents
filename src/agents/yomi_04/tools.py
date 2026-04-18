"""読（Yomi-04）カスタムツール — インシデント記録・パターン分析・Cosmos 読み書き"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from shared.cosmos_client import SharedCoreRepository
from shared.models import AgentKnowledge, IncidentLog, Memory, MemoryType

logger = logging.getLogger(__name__)

# パターン分析用キーワードカテゴリ
_PATTERN_CATEGORIES: dict[str, list[str]] = {
    "品質問題": ["不良品", "欠陥", "リコール", "品質"],
    "対応遅延": ["遅延", "対応が遅い", "放置", "無視"],
    "誤情報拡散": ["虚偽", "デマ", "誤報", "フェイク"],
    "差別・ハラスメント": ["差別", "パワハラ", "セクハラ", "ハラスメント"],
    "不正・詐欺": ["詐欺", "不正", "横領", "インサイダー"],
}


def classify_incident_pattern(risk_factors: list[str]) -> str:
    """リスク要因からインシデントパターンを分類して返す。"""
    for category, keywords in _PATTERN_CATEGORIES.items():
        for factor in risk_factors:
            if any(kw in factor for kw in keywords):
                return category
    return "その他"


def find_similar_incidents(
    repo: SharedCoreRepository,
    pattern: str,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """同じパターンの過去インシデントを Cosmos DB から取得する。"""
    try:
        query = (
            "SELECT TOP @limit * FROM c "
            "WHERE c.container_type = 'incident_log' "
            "ORDER BY c.created_at DESC"
        )
        items = list(repo.container.query_items(
            query=query,
            parameters=[{"name": "@limit", "value": limit}],
            enable_cross_partition_query=True,
        ))
        return [item for item in items if _matches_pattern(item, pattern)]
    except Exception as exc:  # noqa: BLE001
        logger.warning("find_similar_incidents error: %s", exc)
        return []


def _matches_pattern(incident: dict[str, Any], pattern: str) -> bool:
    """インシデントが指定パターンに合致するか判定する。"""
    analysis = incident.get("agent_analysis") or {}
    factors = analysis.get("risk_factors") or []
    combined = " ".join(factors)
    keywords = _PATTERN_CATEGORIES.get(pattern, [])
    return any(kw in combined for kw in keywords)


def save_pattern_knowledge(
    repo: SharedCoreRepository,
    pattern: str,
    insight: str,
    source_incident_ids: list[str],
) -> AgentKnowledge:
    """パターン分析結果を AgentKnowledge として Cosmos DB に保存する。"""
    knowledge = AgentKnowledge(
        id=f"knowledge_yomi_{uuid.uuid4().hex[:12]}",
        knowledge_type="pattern",
        content=f"[{pattern}] {insight}",
        confidence=0.7,
        source_incident_ids=source_incident_ids,
    )
    repo.upsert(knowledge.model_dump())
    logger.info("pattern knowledge saved: %s", pattern)
    return knowledge


def record_incident_observation(
    repo: SharedCoreRepository,
    incident_id: str,
    observation: str,
) -> Memory:
    """インシデント観察記録を Memory として保存する。"""
    memory = Memory(
        id=f"memory_yomi_{uuid.uuid4().hex[:12]}",
        agent_id="Yomi-04",
        memory_type=MemoryType.EPISODE,
        content=observation,
        importance_score=0.6,
        source_incident_ids=[incident_id],
    )
    repo.upsert(memory.model_dump())
    return memory


def generate_pattern_summary(
    incidents: list[dict[str, Any]],
    pattern: str,
) -> str:
    """過去インシデントリストからパターンサマリー文を生成する（ルールベース）。"""
    if not incidents:
        return f"「{pattern}」パターンの過去インシデントは記録されていません。"
    count = len(incidents)
    severities = [inc.get("severity", "unknown") for inc in incidents]
    high_count = sum(1 for s in severities if s in ("high", "critical"))
    return (
        f"「{pattern}」パターンの過去インシデント: {count} 件。"
        f"うち高リスク（high/critical）: {high_count} 件。"
        "同じ火は、同じ場所からまた燃える。"
    )
