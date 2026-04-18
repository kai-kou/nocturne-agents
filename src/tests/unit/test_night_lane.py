"""夜レーン Blueprint のユニットテスト"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from blueprints.night_lane import (
    _build_pr_body,
    _extract_improvement_actions,
    _run_nocturne_group_chat,
)


_SAMPLE_INCIDENT = {
    "id": "incident_test_01",
    "risk_score": 75.0,
    "human_action": "approved",
    "outcome": "公式謝罪を実施",
    "agent_analysis": {
        "suggested_actions": ["公式コメントを準備する", "関係部署に連絡する"],
        "risk_factors": ["品質問題が発生"],
    },
}


# ── _extract_improvement_actions ─────────────────────────────────────────────


def test_extract_actions_empty():
    result = _extract_improvement_actions([], [])
    assert result == []


def test_extract_actions_from_toride_blind_spots():
    toride = [{"blind_spots": ["即時対応の遅れがリスク"], "critique_summary": "test"}]
    yomi = []
    result = _extract_improvement_actions(toride, yomi)
    assert "即時対応の遅れがリスク" in result


def test_extract_actions_capped_at_5():
    toride = [{"blind_spots": [f"blind_{i}" for i in range(10)]}]
    yomi = []
    result = _extract_improvement_actions(toride, yomi)
    assert len(result) <= 5


def test_extract_actions_from_yomi_knowledge():
    toride = []
    yomi = [{"recommended_knowledge": "品質パターンの監視強化を推奨"}]
    result = _extract_improvement_actions(toride, yomi)
    assert "品質パターンの監視強化を推奨" in result


# ── _build_pr_body ────────────────────────────────────────────────────────────


def test_build_pr_body_contains_date():
    chat_result = {"toride_summary": "test", "yomi_summary": "test", "actions": []}
    body = _build_pr_body("2026-04-17", [_SAMPLE_INCIDENT], chat_result)
    assert "2026-04-17" in body


def test_build_pr_body_contains_incident_id():
    chat_result = {"toride_summary": "", "yomi_summary": "", "actions": ["改善アクション1"]}
    body = _build_pr_body("2026-04-17", [_SAMPLE_INCIDENT], chat_result)
    assert "incident_test_01" in body


def test_build_pr_body_contains_checklist():
    chat_result = {"toride_summary": "", "yomi_summary": "", "actions": []}
    body = _build_pr_body("2026-04-17", [], chat_result)
    assert "Human-in-the-loop" in body
    assert "- [ ]" in body


# ── _run_nocturne_group_chat ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_nocturne_group_chat_empty_incidents():
    result = await _run_nocturne_group_chat([])
    assert result["incident_count"] == 0
    assert result["actions"] == []


@pytest.mark.asyncio
async def test_run_nocturne_group_chat_with_incident():
    import blueprints.night_lane as nl
    async def mock_critique(actions, risk_score, incident_id, context=""):
        return {"objections": [], "blind_spots": ["テスト指摘"], "escalation_required": False, "critique_summary": "ok", "critique_count": 1}
    async def mock_pattern(incident_id, risk_factors, similar):
        return {"incident_pattern": "品質問題", "recurrence_risk": 0.3, "pattern_insight": "テスト分析", "recommended_knowledge": "監視強化", "similar_case_count": 0}

    with patch.object(nl, "critique_actions", side_effect=mock_critique), \
         patch.object(nl, "analyze_pattern", side_effect=mock_pattern):
        result = await nl._run_nocturne_group_chat([_SAMPLE_INCIDENT])
    assert result["incident_count"] == 1
    assert "品質問題" in result["yomi_patterns"]
    assert len(result["actions"]) >= 1


# ── morning_digest.json ───────────────────────────────────────────────────────


def test_morning_digest_card_valid_json():
    card_path = Path(__file__).parent.parent.parent / "adaptive_cards" / "morning_digest.json"
    assert card_path.exists(), "morning_digest.json が存在しない"
    card = json.loads(card_path.read_text(encoding="utf-8"))
    assert card["type"] == "AdaptiveCard"
    assert card["version"] == "1.5"
    body_types = [b["type"] for b in card["body"]]
    assert "FactSet" in body_types
    assert "ActionSet" in body_types
