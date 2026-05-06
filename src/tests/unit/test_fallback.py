"""LLM フォールバック動作のユニットテスト + RoundRobinGroupChat テスト（#661, #662）"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── 澪 LLM フォールバック ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_analyze_tweet_llm_unavailable_uses_rule_base():
    """LLM（Azure OpenAI）が例外を投げた場合、ルールベース分析にフォールバックする。"""
    with patch("agents.mio_01.agent._build_model_client") as mock_client_builder:
        mock_client = MagicMock()
        mock_client_builder.return_value = mock_client

        with patch("agents.mio_01.agent.AssistantAgent") as MockAgent:
            instance = MagicMock()
            instance.on_messages = AsyncMock(side_effect=Exception("Service Unavailable"))
            MockAgent.return_value = instance

            from agents.mio_01.agent import analyze_tweet
            result = await analyze_tweet("不買運動 訴訟", "tweet-fallback-001")

    # ルールベースでもリスク情報が返る
    assert "risk_factors" in result or "summary" in result


@pytest.mark.asyncio
async def test_critique_actions_llm_unavailable_uses_rule_base():
    """砦の LLM が失敗した場合、ルールベース批評にフォールバックする。"""
    with patch("agents.toride_06.agent._build_model_client"), \
         patch("agents.toride_06.agent.AssistantAgent") as MockAgent:
        instance = MagicMock()
        instance.on_messages = AsyncMock(side_effect=Exception("LLM unavailable"))
        MockAgent.return_value = instance

        from agents.toride_06.agent import critique_actions
        result = await critique_actions(["様子を見る"], 85.0, "inc_fallback_001")

    assert "escalation_required" in result
    assert "critique_summary" in result
    assert isinstance(result["escalation_required"], bool)


@pytest.mark.asyncio
async def test_analyze_pattern_llm_unavailable_uses_rule_base():
    """読の LLM が失敗した場合、ルールベースパターン分析にフォールバックする。"""
    with patch("agents.yomi_04.agent._build_model_client"), \
         patch("agents.yomi_04.agent.AssistantAgent") as MockAgent:
        instance = MagicMock()
        instance.on_messages = AsyncMock(side_effect=Exception("Timeout"))
        MockAgent.return_value = instance

        from agents.yomi_04.agent import analyze_pattern
        result = await analyze_pattern("inc_fallback_002", ["品質問題"], [])

    assert "incident_pattern" in result
    assert "recurrence_risk" in result
    assert 0.0 <= result["recurrence_risk"] <= 1.0


# ── RoundRobinGroupChat フォールバック ────────────────────────────────────────


@pytest.mark.asyncio
async def test_group_chat_autogen_import_error_falls_back():
    """autogen_agentchat が利用不可の場合、sequential 実行にフォールバックする（#661）。"""
    incidents = [{
        "id": "inc_gc_001",
        "risk_score": 75.0,
        "agent_analysis": {
            "suggested_actions": ["対応A"],
            "risk_factors": ["品質問題"],
        },
    }]

    async def sequential_result(incs):
        return {
            "incident_count": len(incs),
            "escalation_count": 0,
            "toride_critique_count": 1,
            "yomi_patterns": ["品質問題"],
            "toride_summary": "ルールベース批評",
            "yomi_summary": "ルールベース分析",
            "actions": [],
        }

    with patch("blueprints.night_lane._run_group_chat_autogen",
               new_callable=AsyncMock, side_effect=ImportError("autogen not available")), \
         patch("blueprints.night_lane._run_group_chat_sequential",
               new_callable=AsyncMock, side_effect=sequential_result):

        from blueprints.night_lane import _run_nocturne_group_chat
        result = await _run_nocturne_group_chat(incidents)

    assert result["incident_count"] == 1
    assert result["yomi_patterns"] == ["品質問題"]


@pytest.mark.asyncio
async def test_group_chat_empty_incidents_returns_empty():
    """インシデントが 0 件の場合、空の結果を即返す（#661）。"""
    from blueprints.night_lane import _run_nocturne_group_chat
    result = await _run_nocturne_group_chat([])

    assert result["incident_count"] == 0
    assert result["escalation_count"] == 0
    assert result["actions"] == []


# ── _parse_group_chat_result ──────────────────────────────────────────────────


def test_parse_group_chat_extracts_toride_json():
    """RoundRobinGroupChat のメッセージから砦の JSON を正しく抽出する（#661）。"""
    import json
    from blueprints.night_lane import _parse_group_chat_result

    toride_msg = MagicMock(
        source="Toride_06",
        content=json.dumps({
            "objections": ["根拠が不明"],
            "blind_spots": ["再発リスクを考慮していない"],
            "escalation_required": True,
            "escalation_reason": "リスクスコア 85",
            "critique_summary": "楽観的すぎる対応",
        }),
    )
    yomi_msg = MagicMock(
        source="Yomi_04",
        content=json.dumps({
            "incident_pattern": "品質問題",
            "similar_case_count": 3,
            "recurrence_risk": 0.7,
            "pattern_insight": "過去 3 件同パターン",
            "recommended_knowledge": "監視強化を推奨",
        }),
    )

    incidents = [{"id": "inc_001"}]
    result = _parse_group_chat_result([toride_msg, yomi_msg], incidents)

    assert result["escalation_count"] == 1
    assert "品質問題" in result["yomi_patterns"]
    assert "楽観的すぎる対応" in result["toride_summary"]
    assert "過去 3 件同パターン" in result["yomi_summary"]
    assert "再発リスクを考慮していない" in result["actions"]


def test_parse_group_chat_invalid_json_ignored():
    """JSON でないメッセージは無視され、エラーにならない（#661）。"""
    from blueprints.night_lane import _parse_group_chat_result

    bad_msg = MagicMock(source="Toride_06", content="これは JSON じゃない")
    result = _parse_group_chat_result([bad_msg], [{"id": "inc_001"}])

    assert result["escalation_count"] == 0
    assert result["yomi_patterns"] == []
