"""砦（Toride-06）tools / agent のユニットテスト"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.toride_06.tools import (
    analyze_critical,
    escalate_incident,
    save_critique_memory,
)
from shared.models import Memory, MemoryType


# ── analyze_critical ──────────────────────────────────────────────────────────


def test_analyze_critical_clean_actions():
    result = analyze_critical(["公式コメントを準備する", "関係部署に連絡する"], risk_score=50.0)
    assert result["passed"] is True
    assert result["objections"] == []
    assert result["blind_spots"] == []


def test_analyze_critical_detects_optimistic_phrase():
    result = analyze_critical(["問題ないので様子を見る"], risk_score=30.0)
    assert result["passed"] is False
    assert any("問題ない" in obj for obj in result["objections"])


def test_analyze_critical_detects_blind_spot():
    result = analyze_critical(["様子を見る"], risk_score=40.0)
    assert result["passed"] is False
    assert len(result["blind_spots"]) >= 1


def test_analyze_critical_high_risk_few_actions():
    result = analyze_critical(["様子を見る"], risk_score=75.0)
    assert result["passed"] is False
    assert any("不足" in obj for obj in result["objections"])


def test_analyze_critical_multiple_optimistic():
    result = analyze_critical(["大丈夫です", "問題なし"], risk_score=20.0)
    assert result["critique_count"] >= 2


def test_analyze_critical_passed_flag_false_on_objection():
    result = analyze_critical(["想定内の対応"], risk_score=50.0)
    assert result["passed"] is False


# ── escalate_incident ─────────────────────────────────────────────────────────


def test_escalate_incident_returns_record():
    mock_repo = MagicMock()
    mock_repo.upsert.return_value = {}
    record = escalate_incident(mock_repo, "incident_abc", "対応案が不十分")
    assert record["incident_id"] == "incident_abc"
    assert record["agent_id"] == "Toride-06"
    assert record["container_type"] == "escalation"
    mock_repo.upsert.assert_called_once()


# ── save_critique_memory ──────────────────────────────────────────────────────


def test_save_critique_memory_returns_model():
    mock_repo = MagicMock()
    mock_repo.upsert.return_value = {}
    memory = save_critique_memory(mock_repo, "incident_xyz", "批評サマリーテスト")
    assert isinstance(memory, Memory)
    assert memory.agent_id == "Toride-06"
    assert memory.memory_type == MemoryType.EPISODE
    assert "incident_xyz" in memory.source_incident_ids
    mock_repo.upsert.assert_called_once()


# ── critique_actions (agent fallback) ────────────────────────────────────────


@pytest.mark.asyncio
async def test_critique_actions_fallback_on_error():
    """LLM 接続失敗時にルールベース結果を返すことを検証。"""
    import agents.toride_06.agent as toride_agent_module
    with patch.object(toride_agent_module, "get_toride_agent", side_effect=Exception("no LLM")):
        result = await toride_agent_module.critique_actions(
            actions=["問題ないので様子を見る"],
            risk_score=80.0,
            incident_id="incident_test",
        )
    assert "objections" in result
    assert "blind_spots" in result
    assert "escalation_required" in result
    assert isinstance(result["escalation_required"], bool)


@pytest.mark.asyncio
async def test_critique_actions_escalation_high_risk():
    """リスクスコア高 + ルールベースで問題検出 → escalation_required=True を検証。"""
    import agents.toride_06.agent as toride_agent_module
    with patch.object(toride_agent_module, "get_toride_agent", side_effect=Exception("no LLM")):
        result = await toride_agent_module.critique_actions(
            actions=["問題ない"],
            risk_score=75.0,
            incident_id="incident_high",
        )
    assert result["escalation_required"] is True
