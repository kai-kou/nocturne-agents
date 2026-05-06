"""昼レーン E2E 統合テスト — x_poller フロー全体"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_tweet(tweet_id: str, text: str, retweet_count: int = 0) -> dict:
    return {
        "tweet_id": tweet_id,
        "text": text,
        "author_id": "@test_author",
        "metrics": {"retweet_count": retweet_count, "like_count": 0},
    }


def _make_mock_repo() -> MagicMock:
    repo = MagicMock()
    repo.query.return_value = []
    repo.upsert.return_value = {}
    repo.get.return_value = {}
    return repo


# ── x_poller フロー ───────────────────────────────────────────────────────────


def test_x_poller_low_risk_tweet_no_incident(monkeypatch):
    """リスクスコアが閾値未満の投稿はインシデントを生成しない。"""
    monkeypatch.setenv("RISK_SCORE_THRESHOLD", "70")
    tweets = [_make_tweet("t001", "今日はいい天気ですね")]

    with patch("blueprints.day_lane.x_search", return_value=tweets), \
         patch("blueprints.day_lane.SharedCoreRepository") as MockRepo, \
         patch("blueprints.day_lane.save_post_history"), \
         patch("blueprints.day_lane.calculate_risk_score", return_value=(10.0, [])):

        mock_repo = _make_mock_repo()
        MockRepo.return_value = mock_repo

        from blueprints.day_lane import x_poller
        timer = MagicMock(past_due=False)
        x_poller(timer)

    # create_incident は呼ばれない（低リスク）
    mock_repo.upsert.assert_not_called()


def test_x_poller_high_risk_creates_incident(monkeypatch):
    """リスクスコアが閾値以上の投稿はインシデントを生成する。"""
    monkeypatch.setenv("RISK_SCORE_THRESHOLD", "70")
    tweets = [_make_tweet("t002", "不買運動を呼びかけます 訴訟", retweet_count=1200)]

    mock_analysis = {
        "summary": "不買運動リスク",
        "risk_factors": ["不買運動", "訴訟"],
        "suggested_actions": ["公式声明を準備する"],
    }

    with patch("blueprints.day_lane.x_search", return_value=tweets), \
         patch("blueprints.day_lane.SharedCoreRepository") as MockRepo, \
         patch("blueprints.day_lane.save_post_history"), \
         patch("blueprints.day_lane.calculate_risk_score", return_value=(85.0, ["不買運動"])), \
         patch("blueprints.day_lane.analyze_tweet", new_callable=AsyncMock, return_value=mock_analysis), \
         patch("blueprints.day_lane.create_incident") as mock_create, \
         patch("blueprints.day_lane._send_teams_card", return_value=True), \
         patch("blueprints.day_lane.analyze_legal_risk", new_callable=AsyncMock,
               return_value={"risk_level": "LOW", "requires_legal_review": False}):

        mock_repo = _make_mock_repo()
        MockRepo.return_value = mock_repo
        incident_mock = MagicMock(id="INC-E2E-001")
        mock_create.return_value = incident_mock

        from blueprints.day_lane import x_poller
        timer = MagicMock(past_due=False)
        x_poller(timer)

    mock_create.assert_called_once()


def test_x_poller_past_due_still_runs():
    """past_due=True でも処理は継続する。"""
    tweets = [_make_tweet("t003", "テスト")]

    with patch("blueprints.day_lane.x_search", return_value=tweets), \
         patch("blueprints.day_lane.SharedCoreRepository") as MockRepo, \
         patch("blueprints.day_lane.save_post_history"), \
         patch("blueprints.day_lane.calculate_risk_score", return_value=(0.0, [])):

        MockRepo.return_value = _make_mock_repo()
        from blueprints.day_lane import x_poller
        timer = MagicMock(past_due=True)
        x_poller(timer)  # 例外が出なければ OK


# ── _render_card JSON インジェクション対策 ────────────────────────────────────


def test_render_card_safe_with_quotes():
    """値に引用符が含まれていても JSON 構造が壊れない（#669）。"""
    from blueprints.day_lane import _render_card
    template = {"title": "${title}", "body": "${body}"}
    values = {
        "title": 'テスト "タイトル"',
        "body": "改行\nあり",
    }
    result = _render_card(template, values)
    assert result["title"] == 'テスト "タイトル"'
    assert result["body"] == "改行\nあり"


def test_render_card_safe_with_backslash():
    """値にバックスラッシュが含まれていても JSON 構造が壊れない（#669）。"""
    from blueprints.day_lane import _render_card
    template = {"path": "${path}"}
    result = _render_card(template, {"path": "C:\\Users\\test"})
    assert result["path"] == "C:\\Users\\test"


def test_render_card_safe_with_json_injection():
    """値に JSON 構造を破壊する文字列を渡しても安全に処理される（#669）。"""
    from blueprints.day_lane import _render_card
    template = {"text": "${text}"}
    malicious = '"},"injected":{"evil":"payload'
    result = _render_card(template, {"text": malicious})
    assert result["text"] == malicious
    assert "injected" not in result


# ── HMAC 検証 ─────────────────────────────────────────────────────────────────


def test_verify_hmac_missing_secret_dev_mode(monkeypatch):
    """COPILOT_HMAC_REQUIRED=false かつ Secret 未設定時はスキップ。"""
    monkeypatch.setenv("COPILOT_HMAC_REQUIRED", "false")
    monkeypatch.delenv("COPILOT_WEBHOOK_SECRET", raising=False)

    import importlib
    import blueprints.day_lane as dl
    importlib.reload(dl)

    req = MagicMock()
    assert dl._verify_copilot_hmac(req) is True


def test_verify_hmac_valid_signature(monkeypatch):
    """正しい HMAC 署名で検証が通る（#668）。"""
    import hashlib
    import hmac as _hmac

    secret = "test-secret-key"
    monkeypatch.setenv("COPILOT_WEBHOOK_SECRET", secret)

    body = b'{"incident_id": "inc_001", "action": "approved"}'
    sig = "sha256=" + _hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

    import importlib
    import blueprints.day_lane as dl
    importlib.reload(dl)

    req = MagicMock()
    req.get_body.return_value = body
    req.headers.get.return_value = sig

    assert dl._verify_copilot_hmac(req) is True


def test_verify_hmac_invalid_signature(monkeypatch):
    """不正な HMAC 署名は拒否される（#668）。"""
    monkeypatch.setenv("COPILOT_WEBHOOK_SECRET", "correct-secret")

    body = b'{"incident_id": "inc_001", "action": "approved"}'
    wrong_sig = "sha256=0000000000000000000000000000000000000000000000000000000000000000"

    import importlib
    import blueprints.day_lane as dl
    importlib.reload(dl)

    req = MagicMock()
    req.get_body.return_value = body
    req.headers.get.return_value = wrong_sig

    assert dl._verify_copilot_hmac(req) is False
