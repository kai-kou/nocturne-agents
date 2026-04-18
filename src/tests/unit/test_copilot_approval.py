"""Copilot Studio 承認フロー（/api/day/approve + post_tweet）のユニットテスト"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from agents.mio_01.tools import post_tweet


# ── post_tweet ────────────────────────────────────────────────────────────────


def test_post_tweet_missing_env_returns_skipped(monkeypatch):
    """X API 認証情報未設定時にグレースフルスキップを返すことを検証。"""
    for k in ["X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_SECRET"]:
        monkeypatch.delenv(k, raising=False)
    result = post_tweet("テスト投稿")
    assert result["status"] == "skipped"
    assert "missing env vars" in result["message"]


def test_post_tweet_success(monkeypatch):
    """X API 認証情報が揃っているときに投稿成功を返すことを検証。"""
    for k in ["X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_SECRET"]:
        monkeypatch.setenv(k, "dummy_value")

    mock_client = MagicMock()
    mock_client.create_tweet.return_value = MagicMock(data={"id": 123456})

    with patch("agents.mio_01.tools.get_x_write_client", return_value=mock_client):
        result = post_tweet("テスト投稿")

    assert result["status"] == "posted"
    assert result["tweet_id"] == "123456"
    mock_client.create_tweet.assert_called_once_with(text="テスト投稿")


def test_post_tweet_tweepy_error(monkeypatch):
    """Tweepy エラー時に error ステータスを返すことを検証。"""
    import tweepy
    for k in ["X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_SECRET"]:
        monkeypatch.setenv(k, "dummy_value")

    mock_client = MagicMock()
    mock_client.create_tweet.side_effect = tweepy.TweepyException("API error")

    with patch("agents.mio_01.tools.get_x_write_client", return_value=mock_client):
        result = post_tweet("テスト投稿")

    assert result["status"] == "error"
    assert "API error" in result["message"]


# ── /api/day/approve endpoint ─────────────────────────────────────────────────


def _make_http_request(body: dict) -> MagicMock:
    req = MagicMock()
    req.get_json.return_value = body
    return req


def _make_mock_repo(incident: dict) -> MagicMock:
    repo = MagicMock()
    repo.get.return_value = incident
    repo.upsert.return_value = {}
    return repo


def test_approve_missing_action():
    from blueprints.day_lane import approve
    req = _make_http_request({"incident_id": "inc_001", "action": "unknown"})
    resp = approve(req)
    assert resp.status_code == 400


def test_approve_missing_incident_id():
    from blueprints.day_lane import approve
    req = _make_http_request({"action": "approved"})
    resp = approve(req)
    assert resp.status_code == 400


def test_approve_approved_action(monkeypatch):
    from blueprints.day_lane import approve
    monkeypatch.delenv("X_API_KEY", raising=False)
    incident = {
        "id": "inc_001",
        "agent_analysis": {"suggested_actions": ["公式コメントを発表する"]},
        "risk_score": 80.0,
    }
    req = _make_http_request({"incident_id": "inc_001", "action": "approved"})

    with patch("blueprints.day_lane.SharedCoreRepository") as MockRepo, \
         patch("blueprints.day_lane.post_tweet", return_value={"status": "skipped"}):
        MockRepo.return_value = _make_mock_repo(incident)
        resp = approve(req)

    assert resp.status_code == 200
    import json
    data = json.loads(resp.get_body())
    assert data["action"] == "approved"
    assert data["incident_id"] == "inc_001"


def test_approve_modified_no_text():
    from blueprints.day_lane import approve
    req = _make_http_request({"incident_id": "inc_001", "action": "modified"})
    incident = {"id": "inc_001", "agent_analysis": {}}
    with patch("blueprints.day_lane.SharedCoreRepository") as MockRepo:
        MockRepo.return_value = _make_mock_repo(incident)
        resp = approve(req)
    assert resp.status_code == 400


def test_approve_modified_with_text(monkeypatch):
    from blueprints.day_lane import approve
    monkeypatch.delenv("X_API_KEY", raising=False)
    incident = {"id": "inc_001", "agent_analysis": {}}
    req = _make_http_request({
        "incident_id": "inc_001",
        "action": "modified",
        "modified_text": "修正済みの投稿テキスト",
    })
    with patch("blueprints.day_lane.SharedCoreRepository") as MockRepo, \
         patch("blueprints.day_lane.post_tweet", return_value={"status": "skipped"}):
        MockRepo.return_value = _make_mock_repo(incident)
        resp = approve(req)
    assert resp.status_code == 200
    import json
    data = json.loads(resp.get_body())
    assert data["action"] == "modified"


def test_approve_cancelled_updates_cosmos():
    from blueprints.day_lane import approve
    incident = {"id": "inc_001", "agent_analysis": {}}
    req = _make_http_request({"incident_id": "inc_001", "action": "cancelled"})
    with patch("blueprints.day_lane.SharedCoreRepository") as MockRepo:
        mock_repo = _make_mock_repo(incident)
        MockRepo.return_value = mock_repo
        resp = approve(req)
    assert resp.status_code == 200
    mock_repo.upsert.assert_called_once()
    updated = mock_repo.upsert.call_args[0][0]
    assert updated["human_action"] == "cancelled"


def test_approve_incident_not_found():
    from blueprints.day_lane import approve
    req = _make_http_request({"incident_id": "nonexistent", "action": "approved"})
    with patch("blueprints.day_lane.SharedCoreRepository") as MockRepo:
        repo = MagicMock()
        repo.get.side_effect = Exception("not found")
        MockRepo.return_value = repo
        resp = approve(req)
    assert resp.status_code == 404
