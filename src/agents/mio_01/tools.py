"""澪（Mio-01）カスタムツール — X API 検索・リスクスコア計算・Cosmos 書き込み"""
from __future__ import annotations

import logging
import os
import uuid
from typing import Any

import tweepy

from shared.cosmos_client import SharedCoreRepository
from shared.models import AgentAnalysis, HumanAction, IncidentLog, PostHistory, Severity

logger = logging.getLogger(__name__)

# 炎上リスクキーワードと重みづけ（ルールベース MVP 版）
_RISK_WEIGHTS: dict[str, float] = {
    "不買運動": 25,
    "訴訟": 25,
    "謝罪": 20,
    "差別": 20,
    "パワハラ": 20,
    "セクハラ": 20,
    "詐欺": 20,
    "不正": 15,
    "虚偽": 15,
    "批判": 10,
    "最悪": 10,
    "怒り": 8,
    "ありえない": 8,
    "問題": 5,
}


def get_x_client() -> tweepy.Client:
    return tweepy.Client(
        bearer_token=os.environ["X_BEARER_TOKEN"],
        wait_on_rate_limit=True,
    )


def x_search(keywords: list[str], max_results: int = 100) -> list[dict[str, Any]]:
    """X API v2 でキーワード検索（RT 除外・日本語限定）。"""
    client = get_x_client()
    query = " OR ".join(f'"{kw}"' for kw in keywords) + " -is:retweet lang:ja"
    tweets: list[dict[str, Any]] = []
    try:
        resp = client.search_recent_tweets(
            query=query,
            max_results=min(max(max_results, 10), 100),
            tweet_fields=["created_at", "author_id", "text", "public_metrics"],
        )
        for tweet in resp.data or []:
            tweets.append({
                "tweet_id": str(tweet.id),
                "text": tweet.text,
                "author_id": str(tweet.author_id),
                "created_at": tweet.created_at.isoformat() if tweet.created_at else None,
                "metrics": tweet.public_metrics or {},
            })
    except tweepy.TweepyException as exc:
        logger.warning("x_search error: %s", exc)
    return tweets


def calculate_risk_score(
    text: str,
    engagement_metrics: dict[str, int] | None = None,
) -> tuple[float, list[str]]:
    """炎上リスクスコア（0-100）とマッチキーワードリストを返す。"""
    score = 0.0
    matched: list[str] = []
    for keyword, weight in _RISK_WEIGHTS.items():
        if keyword in text:
            score += weight
            matched.append(keyword)
    if engagement_metrics:
        rt = engagement_metrics.get("retweet_count", 0)
        like = engagement_metrics.get("like_count", 0)
        score += min(rt * 0.1 + like * 0.05, 30.0)
    return min(score, 100.0), matched


def save_post_history(
    repo: SharedCoreRepository,
    tweet_id: str,
    text: str,
    author: str,
    risk_score: float,
    keywords_matched: list[str],
) -> PostHistory:
    """投稿履歴を Cosmos DB shared_core に保存して返す。"""
    post = PostHistory(
        id=f"post_{tweet_id}",
        tweet_id=tweet_id,
        text=text,
        author=author,
        risk_score=risk_score,
        keywords_matched=keywords_matched,
    )
    repo.upsert(post.model_dump(by_alias=True))
    return post


def get_x_write_client() -> tweepy.Client:
    return tweepy.Client(
        consumer_key=os.environ["X_API_KEY"],
        consumer_secret=os.environ["X_API_SECRET"],
        access_token=os.environ["X_ACCESS_TOKEN"],
        access_token_secret=os.environ["X_ACCESS_SECRET"],
    )


def post_tweet(text: str) -> dict[str, Any]:
    """X API v2 で投稿を実行する。認証情報未設定時はグレースフルエラーを返す。"""
    required_keys = ["X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_SECRET"]
    missing = [k for k in required_keys if not os.environ.get(k)]
    if missing:
        logger.warning("post_tweet skipped: missing env vars %s", missing)
        return {"status": "skipped", "message": f"missing env vars: {missing}"}
    try:
        client = get_x_write_client()
        resp = client.create_tweet(text=text)
        tweet_id = str(resp.data["id"]) if resp.data else "unknown"
        logger.info("post_tweet succeeded: tweet_id=%s", tweet_id)
        return {"status": "posted", "tweet_id": tweet_id}
    except tweepy.TweepyException as exc:
        logger.error("post_tweet error: %s", exc)
        return {"status": "error", "message": str(exc)}


def create_incident(
    repo: SharedCoreRepository,
    tweet_ids: list[str],
    risk_score: float,
    agent_analysis: AgentAnalysis,
) -> IncidentLog:
    """インシデントレコードを生成して Cosmos DB に保存して返す。"""
    severity = (
        Severity.CRITICAL if risk_score >= 90
        else Severity.HIGH if risk_score >= 70
        else Severity.MEDIUM if risk_score >= 50
        else Severity.LOW
    )
    incident = IncidentLog(
        id=f"incident_{uuid.uuid4().hex[:12]}",
        severity=severity,
        risk_score=risk_score,
        tweet_ids=tweet_ids,
        agent_analysis=agent_analysis,
    )
    repo.upsert(incident.model_dump())
    return incident
