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
    """X API v2 クライアント。OAuth 1.0a User Context（kinako-mocchi 流用）。

    認証情報は kai-kou/kinako-mocchi の GitHub Variables から provision.sh が転記。
    OAuth 1.0a なら自分のアカウントの owned reads が $0.001/req（他者の 1/5）で
    取得できる。Bearer Token モードは X_BEARER_TOKEN がある時のみフォールバック。
    """
    if os.environ.get("X_BEARER_TOKEN"):
        return tweepy.Client(
            bearer_token=os.environ["X_BEARER_TOKEN"],
            wait_on_rate_limit=False,  # rate limit は呼び出し側でスキップ判断
        )
    return tweepy.Client(
        consumer_key=os.environ["X_API_KEY"],
        consumer_secret=os.environ["X_API_SECRET"],
        access_token=os.environ["X_ACCESS_TOKEN"],
        access_token_secret=os.environ["X_ACCESS_TOKEN_SECRET"],
        wait_on_rate_limit=False,
    )


def _tweet_to_dict(tweet: Any) -> dict[str, Any]:
    return {
        "tweet_id": str(tweet.id),
        "text": tweet.text,
        "author_id": str(tweet.author_id) if getattr(tweet, "author_id", None) else "",
        "created_at": tweet.created_at.isoformat() if tweet.created_at else None,
        "metrics": tweet.public_metrics or {},
    }


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
            tweets.append(_tweet_to_dict(tweet))
    except tweepy.TooManyRequests:
        logger.warning("x_search: rate limited, skipping this cycle")
    except tweepy.TweepyException as exc:
        logger.warning("x_search error: %s", exc)
    return tweets


def x_get_filtered_home_timeline(target_user_ids: list[str],
                                 max_results: int = 100) -> list[dict[str, Any]]:
    """認証アカウントのホームタイムラインから指定 user_id のオリジナル投稿のみ抽出。

    X API Free tier 制約により get_users_tweets / search_recent_tweets / get_user は
    401 Unauthorized となるが、get_home_timeline は通る。そのため認証アカウント
    （kinamocchi_tech）が監視対象（target_user_ids）をフォローしている前提で、
    home_timeline からフィルタ抽出する設計に変更した。

    フィルタ条件:
    - author_id が target_user_ids に含まれる
    - 投稿テキストが "RT @" で始まらない（手動 RT 除外・API の exclude が
      home_timeline では効かない場合のフォールバック）

    要件: 認証アカウントが監視対象ユーザーをフォローしていること。
    """
    if not target_user_ids:
        return []
    target_set = {str(uid) for uid in target_user_ids}
    client = get_x_client()
    tweets: list[dict[str, Any]] = []
    try:
        resp = client.get_home_timeline(
            max_results=min(max(max_results, 5), 100),
            exclude=["retweets", "replies"],
            tweet_fields=["created_at", "author_id", "text", "public_metrics"],
        )
        for tweet in resp.data or []:
            text = tweet.text or ""
            # RT 除外（API の exclude が home_timeline で効かないことへのフォールバック）
            if text.startswith("RT @"):
                continue
            if str(tweet.author_id) in target_set:
                tweets.append(_tweet_to_dict(tweet))
    except tweepy.TooManyRequests:
        logger.warning("x_get_filtered_home_timeline: rate limited, skipping")
    except tweepy.TweepyException as exc:
        logger.warning("x_get_filtered_home_timeline error: %s", exc)
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
    repo.upsert(post.model_dump(by_alias=True, mode="json"))
    return post


def get_x_write_client() -> tweepy.Client:
    return tweepy.Client(
        consumer_key=os.environ["X_API_KEY"],
        consumer_secret=os.environ["X_API_SECRET"],
        access_token=os.environ["X_ACCESS_TOKEN"],
        access_token_secret=os.environ["X_ACCESS_TOKEN_SECRET"],
    )


def post_tweet(text: str) -> dict[str, Any]:
    """X API v2 で投稿を実行する。認証情報未設定時はグレースフルエラーを返す。"""
    required_keys = ["X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_TOKEN_SECRET"]
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
    repo.upsert(incident.model_dump(mode="json"))
    return incident
