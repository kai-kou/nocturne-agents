"""読（Yomi-04）tools / agent のユニットテスト"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from agents.yomi_04.tools import (
    classify_incident_pattern,
    generate_pattern_summary,
    record_incident_observation,
    save_pattern_knowledge,
)
from shared.models import AgentKnowledge, Memory, MemoryType


# ── classify_incident_pattern ─────────────────────────────────────────────────


def test_classify_detects_quality():
    result = classify_incident_pattern(["品質問題が発生", "不良品の報告多数"])
    assert result == "品質問題"


def test_classify_detects_harassment():
    result = classify_incident_pattern(["パワハラの告発", "差別的な発言"])
    assert result == "差別・ハラスメント"


def test_classify_detects_fraud():
    result = classify_incident_pattern(["詐欺行為が発覚"])
    assert result == "不正・詐欺"


def test_classify_detects_delay():
    result = classify_incident_pattern(["対応が遅い", "放置されている"])
    assert result == "対応遅延"


def test_classify_unknown_returns_other():
    result = classify_incident_pattern(["謎のクレーム"])
    assert result == "その他"


# ── generate_pattern_summary ──────────────────────────────────────────────────


def test_generate_summary_empty_incidents():
    summary = generate_pattern_summary([], "品質問題")
    assert "品質問題" in summary
    assert "記録されていません" in summary


def test_generate_summary_with_incidents():
    incidents = [
        {"severity": "high"},
        {"severity": "critical"},
        {"severity": "low"},
    ]
    summary = generate_pattern_summary(incidents, "品質問題")
    assert "3 件" in summary
    assert "2 件" in summary  # high + critical


def test_generate_summary_contains_catchphrase():
    summary = generate_pattern_summary([{"severity": "high"}], "不正・詐欺")
    assert "同じ火は" in summary


# ── save_pattern_knowledge ────────────────────────────────────────────────────


def test_save_pattern_knowledge_returns_model():
    mock_repo = MagicMock()
    mock_repo.upsert.return_value = {}
    knowledge = save_pattern_knowledge(
        mock_repo, "品質問題", "品質管理プロセスの見直しが必要", ["incident_1", "incident_2"]
    )
    assert isinstance(knowledge, AgentKnowledge)
    assert knowledge.knowledge_type == "pattern"
    assert "品質問題" in knowledge.content
    assert knowledge.source_incident_ids == ["incident_1", "incident_2"]
    mock_repo.upsert.assert_called_once()


# ── record_incident_observation ───────────────────────────────────────────────


def test_record_incident_observation_returns_memory():
    mock_repo = MagicMock()
    mock_repo.upsert.return_value = {}
    memory = record_incident_observation(mock_repo, "incident_abc", "観察メモのテスト")
    assert isinstance(memory, Memory)
    assert memory.agent_id == "Yomi-04"
    assert memory.memory_type == MemoryType.EPISODE
    assert "incident_abc" in memory.source_incident_ids
    mock_repo.upsert.assert_called_once()


# ── analyze_pattern (agent fallback) ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_analyze_pattern_fallback_on_error():
    """LLM 接続失敗時にルールベース結果を返すことを検証。"""
    import agents.yomi_04.agent as yomi_agent_module
    with patch.object(yomi_agent_module, "get_yomi_agent", side_effect=Exception("no LLM")):
        result = await yomi_agent_module.analyze_pattern(
            incident_id="incident_test",
            risk_factors=["品質問題が発生"],
            similar_incidents=[{"severity": "high"}],
        )
    assert "incident_pattern" in result
    assert "recurrence_risk" in result
    assert result["incident_pattern"] == "品質問題"
    assert result["similar_case_count"] == 1


@pytest.mark.asyncio
async def test_analyze_pattern_recurrence_capped_at_1():
    """再発リスクが 1.0 を超えないことを検証。"""
    import agents.yomi_04.agent as yomi_agent_module
    many_incidents = [{"severity": "high"}] * 10
    with patch.object(yomi_agent_module, "get_yomi_agent", side_effect=Exception("no LLM")):
        result = await yomi_agent_module.analyze_pattern(
            incident_id="incident_test",
            risk_factors=["詐欺行為"],
            similar_incidents=many_incidents,
        )
    assert result["recurrence_risk"] <= 1.0
