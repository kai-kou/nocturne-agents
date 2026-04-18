"""澪（Mio-01）tools / agent のユニットテスト"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.mio_01.tools import (
    calculate_risk_score,
    create_incident,
    save_post_history,
)
from shared.models import AgentAnalysis, IncidentLog, PostHistory, Severity


# ── calculate_risk_score ──────────────────────────────────────────────────────


def test_risk_score_clean_text():
    score, matched = calculate_risk_score("今日もいい天気ですね")
    assert score == 0.0
    assert matched == []


def test_risk_score_single_keyword():
    score, matched = calculate_risk_score("謝罪を要求します")
    assert score == 20.0
    assert "謝罪" in matched


def test_risk_score_multiple_keywords():
    score, matched = calculate_risk_score("不正が発覚し不買運動が始まった")
    assert score >= 25
    assert "不正" in matched
    assert "不買運動" in matched


def test_risk_score_capped_at_100():
    text = "不買運動 訴訟 謝罪 差別 パワハラ セクハラ 詐欺 不正 虚偽 批判 最悪 怒り ありえない 問題"
    score, _ = calculate_risk_score(text)
    assert score == 100.0


def test_risk_score_engagement_boost():
    score_base, _ = calculate_risk_score("謝罪要求")
    score_rt, _ = calculate_risk_score("謝罪要求", {"retweet_count": 100, "like_count": 0})
    assert score_rt > score_base


def test_risk_score_engagement_max_30():
    _, _ = calculate_risk_score("test", {"retweet_count": 10000, "like_count": 10000})
    score, _ = calculate_risk_score("", {"retweet_count": 10000, "like_count": 10000})
    assert score <= 30.0


# ── save_post_history ─────────────────────────────────────────────────────────


def test_save_post_history_returns_model():
    mock_repo = MagicMock()
    mock_repo.upsert.return_value = {}
    result = save_post_history(mock_repo, "123", "test text", "user_a", 42.0, ["批判"])
    assert isinstance(result, PostHistory)
    assert result.tweet_id == "123"
    assert result.risk_score == 42.0
    mock_repo.upsert.assert_called_once()


# ── create_incident ───────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "score,expected_severity",
    [
        (95.0, Severity.CRITICAL),
        (75.0, Severity.HIGH),
        (55.0, Severity.MEDIUM),
        (30.0, Severity.LOW),
    ],
)
def test_create_incident_severity(score: float, expected_severity: Severity):
    mock_repo = MagicMock()
    mock_repo.upsert.return_value = {}
    analysis = AgentAnalysis(
        agent_id="Mio-01",
        summary="test",
        risk_factors=["批判"],
        suggested_actions=["様子を見る"],
    )
    incident = create_incident(mock_repo, ["tweet_1"], score, analysis)
    assert isinstance(incident, IncidentLog)
    assert incident.severity == expected_severity
    assert incident.risk_score == score
    mock_repo.upsert.assert_called_once()


# ── day_approval.json ─────────────────────────────────────────────────────────


def test_adaptive_card_template_valid_json():
    card_path = Path(__file__).parent.parent.parent / "adaptive_cards" / "day_approval.json"
    assert card_path.exists(), "day_approval.json が存在しない"
    card = json.loads(card_path.read_text(encoding="utf-8"))
    assert card["type"] == "AdaptiveCard"
    assert card["version"] == "1.5"
    assert len(card["actions"]) == 3


# ── analyze_tweet (agent fallback) ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_analyze_tweet_fallback_on_error():
    """LLM 接続失敗時にルールベース結果を返すことを検証。"""
    import agents.mio_01.agent as mio_agent_module
    with patch.object(mio_agent_module, "get_mio_agent", side_effect=Exception("no LLM")):
        result = await mio_agent_module.analyze_tweet("謝罪を要求します", "tweet_test")
    assert "risk_score" in result
    assert result["risk_score"] >= 0
    assert "suggested_actions" in result
