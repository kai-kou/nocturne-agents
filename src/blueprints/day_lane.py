"""昼レーン Blueprint — X API ポーリング・Adaptive Card 送信・インシデント取得"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import os
import secrets
import string
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import azure.functions as func
import httpx

from agents.mio_01.agent import analyze_tweet
from agents.mio_01.tools import (
    calculate_risk_score,
    create_incident,
    post_tweet,
    save_post_history,
    x_search,
)
from agents.yutaka_02.agent import analyze_legal_risk
from shared.cosmos_client import SharedCoreRepository
from shared.models import AgentAnalysis, HumanAction

bp = func.Blueprint()
logger = logging.getLogger(__name__)

_RISK_THRESHOLD = int(os.environ.get("RISK_SCORE_THRESHOLD", "70"))
_LEGAL_REVIEW_THRESHOLD = int(os.environ.get("LEGAL_REVIEW_THRESHOLD", "60"))
_MONITOR_KEYWORDS = json.loads(os.environ.get("MONITOR_KEYWORDS", '["炎上","不買運動","謝罪要求"]'))
_TEAMS_WEBHOOK_URL = os.environ.get("TEAMS_WEBHOOK_URL", "")
_COPILOT_WEBHOOK_SECRET = os.environ.get("COPILOT_WEBHOOK_SECRET", "")

_CARD_TEMPLATE_PATH = Path(__file__).parent.parent / "adaptive_cards" / "day_approval.json"


def _verify_copilot_hmac(req: func.HttpRequest) -> bool:
    """Copilot Studio Webhook の HMAC-SHA256 署名を検証する（#668）。

    Copilot Studio は X-Webhook-Signature: sha256=<hex> ヘッダーを付与する。
    COPILOT_WEBHOOK_SECRET 未設定かつ COPILOT_HMAC_REQUIRED=false の場合のみスキップ（開発用）。
    """
    secret = _COPILOT_WEBHOOK_SECRET
    if not secret:
        if os.environ.get("COPILOT_HMAC_REQUIRED", "true").lower() != "false":
            logger.warning("COPILOT_WEBHOOK_SECRET not configured; rejecting request (#668)")
            return False
        logger.warning("COPILOT_WEBHOOK_SECRET not set; HMAC check skipped (dev mode)")
        return True

    signature_header = req.headers.get("X-Webhook-Signature", "")
    if not signature_header.startswith("sha256="):
        logger.warning("X-Webhook-Signature header missing or invalid")
        return False

    expected_hex = signature_header[len("sha256="):]
    body = req.get_body()
    computed_hex = hmac.new(
        key=secret.encode("utf-8"), msg=body, digestmod=hashlib.sha256
    ).hexdigest()
    return secrets.compare_digest(computed_hex, expected_hex)


def _load_card_template() -> dict[str, Any]:
    with _CARD_TEMPLATE_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def _render_card(template: dict[str, Any], values: dict[str, str]) -> dict[str, Any]:
    """テンプレートの ${key} を values で安全に置換する（#669 JSON インジェクション対策）。

    value を json.dumps でエスケープしてから JSON 文字列内に埋め込むことで、
    ダブルクォートや改行を含む入力による構造破壊を防ぐ。
    """
    raw = json.dumps(template)
    for key, val in values.items():
        # json.dumps("v")[1:-1] → 引用符除去済みの JSON エスケープ済み文字列
        safe_val = json.dumps(str(val))[1:-1]
        raw = raw.replace(f"${{{key}}}", safe_val)
    return json.loads(raw)


def _send_teams_card(card: dict[str, Any]) -> bool:
    """Teams Webhook に Adaptive Card を送信して成功/失敗を返す。"""
    if not _TEAMS_WEBHOOK_URL:
        logger.warning("TEAMS_WEBHOOK_URL not set; skipping card send")
        return False
    payload = {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": card,
            }
        ],
    }
    try:
        resp = httpx.post(_TEAMS_WEBHOOK_URL, json=payload, timeout=10)
        resp.raise_for_status()
        return True
    except httpx.HTTPError as exc:
        logger.error("Teams webhook error: %s", exc)
        return False


@bp.timer_trigger(schedule="0 */5 * * * *", arg_name="timer", run_on_startup=False)
def x_poller(timer: func.TimerRequest) -> None:
    """X API を 5 分ごとにポーリングしてリスクスコアリング・インシデント登録を行う。"""
    if timer.past_due:
        logger.warning("x_poller timer is past due")

    logger.info("x_poller: keywords=%s", _MONITOR_KEYWORDS)
    tweets = x_search(_MONITOR_KEYWORDS, max_results=100)
    logger.info("x_poller: fetched %d tweets", len(tweets))

    repo = SharedCoreRepository()
    for tweet in tweets:
        tweet_id = tweet["tweet_id"]
        text = tweet["text"]
        author = tweet.get("author_id", "unknown")
        metrics = tweet.get("metrics", {})

        score, matched = calculate_risk_score(text, metrics)
        save_post_history(repo, tweet_id, text, author, score, matched)

        if score >= _RISK_THRESHOLD:
            logger.info("x_poller: high risk tweet %s (score=%.1f)", tweet_id, score)
            analysis_dict = asyncio.run(analyze_tweet(text, tweet_id))
            agent_analysis = AgentAnalysis(
                agent_id="Mio-01",
                summary=analysis_dict.get("summary", ""),
                risk_factors=analysis_dict.get("risk_factors", matched),
                suggested_actions=analysis_dict.get("suggested_actions", []),
            )
            incident = create_incident(repo, [tweet_id], score, agent_analysis)

            # 法的リスクが閾値を超える場合は豊（Yutaka-02）による法的分析を追加実行
            if score >= _LEGAL_REVIEW_THRESHOLD:
                logger.info(
                    "x_poller: requesting legal analysis from Yutaka-02 for tweet %s",
                    tweet_id,
                )
                legal_result = asyncio.run(
                    analyze_legal_risk(
                        incident_text=text,
                        incident_id=incident.id,
                        risk_factors=matched,
                    )
                )
                try:
                    incident_doc = repo.get(incident.id, partition_key="incident_log")
                    incident_doc["yutaka_legal_analysis"] = legal_result
                    repo.upsert(incident_doc)
                except Exception as get_exc:  # noqa: BLE001
                    logger.warning("x_poller: failed to persist legal analysis: %s", get_exc)
                logger.info(
                    "x_poller: legal analysis done: level=%s requires_review=%s",
                    legal_result.get("risk_level"),
                    legal_result.get("requires_legal_review"),
                )

    logger.info("x_poller: completed")


@bp.route(route="day/analyze", methods=["POST"])
def analyze(req: func.HttpRequest) -> func.HttpResponse:
    """澪による手動分析エンドポイント（デバッグ用）。"""
    try:
        body = req.get_json()
    except ValueError:
        return func.HttpResponse("Invalid JSON", status_code=400)

    tweet_text = body.get("tweet_text", "")
    tweet_id = body.get("tweet_id", "manual")
    if not tweet_text:
        return func.HttpResponse("tweet_text is required", status_code=400)

    result = asyncio.run(analyze_tweet(tweet_text, tweet_id))
    return func.HttpResponse(json.dumps(result, ensure_ascii=False), mimetype="application/json")


@bp.route(route="day/analyze-legal", methods=["POST"])
def analyze_legal(req: func.HttpRequest) -> func.HttpResponse:
    """豊による法的リスク分析エンドポイント（デバッグ用）。"""
    try:
        body = req.get_json()
    except ValueError:
        return func.HttpResponse("Invalid JSON", status_code=400)

    tweet_text = body.get("tweet_text", "")
    incident_id = body.get("incident_id", "manual")
    industry = body.get("industry", "一般")
    if not tweet_text:
        return func.HttpResponse("tweet_text is required", status_code=400)

    result = asyncio.run(
        analyze_legal_risk(
            incident_text=tweet_text,
            incident_id=incident_id,
            industry=industry,
        )
    )
    return func.HttpResponse(json.dumps(result, ensure_ascii=False), mimetype="application/json")


@bp.route(route="day/send-card", methods=["POST"])
def send_card(req: func.HttpRequest) -> func.HttpResponse:
    """Adaptive Card を Teams チャネルに送信して承認フローを開始する。"""
    try:
        body = req.get_json()
    except ValueError:
        return func.HttpResponse("Invalid JSON", status_code=400)

    incident_id = body.get("incident_id")
    if not incident_id:
        return func.HttpResponse("incident_id is required", status_code=400)

    repo = SharedCoreRepository()
    try:
        incident = repo.get(incident_id, partition_key="incident_log")
    except Exception:  # noqa: BLE001
        return func.HttpResponse(f"incident {incident_id} not found", status_code=404)

    analysis = incident.get("agent_analysis") or {}
    actions = analysis.get("suggested_actions", ["様子を見る", "コメント準備", "関係部署に連絡"])
    legal = incident.get("yutaka_legal_analysis") or {}

    template = _load_card_template()
    card = _render_card(template, {
        "incident_id": incident_id,
        "risk_score": str(incident.get("risk_score", 0)),
        "severity": incident.get("severity", ""),
        "predicted_escalation_hours": str(analysis.get("predicted_escalation_hours", 3)),
        "detected_at": incident.get("created_at", datetime.now(timezone.utc).isoformat()),
        "tweet_text": incident.get("tweet_ids", [""])[0],
        "risk_factors": "、".join(analysis.get("risk_factors", [])),
        "action_1": actions[0] if len(actions) > 0 else "",
        "action_2": actions[1] if len(actions) > 1 else "",
        "action_3": actions[2] if len(actions) > 2 else "",
        "legal_risk_level": legal.get("risk_level", "未分析"),
        "requires_legal_review": "要法務確認" if legal.get("requires_legal_review") else "法務確認不要",
    })

    sent = _send_teams_card(card)
    return func.HttpResponse(
        json.dumps({"status": "sent" if sent else "skipped", "incident_id": incident_id}),
        mimetype="application/json",
        status_code=202,
    )


@bp.route(route="day/approve", methods=["POST"])
def approve(req: func.HttpRequest) -> func.HttpResponse:
    """Copilot Studio からの承認 Webhook を受け取り、X API 投稿 or クローズ処理を行う。"""
    if not _verify_copilot_hmac(req):
        return func.HttpResponse(
            json.dumps({"error": "unauthorized: invalid or missing HMAC signature"}),
            mimetype="application/json",
            status_code=401,
        )

    try:
        body = req.get_json()
    except ValueError:
        return func.HttpResponse("Invalid JSON", status_code=400)

    incident_id = body.get("incident_id")
    action = body.get("action", "")
    modified_text = body.get("modified_text", "")

    if not incident_id or action not in ("approved", "modified", "cancelled"):
        return func.HttpResponse(
            json.dumps({"error": "incident_id and action (approved|modified|cancelled) are required"}),
            mimetype="application/json",
            status_code=400,
        )

    repo = SharedCoreRepository()
    try:
        incident = repo.get(incident_id, partition_key="incident_log")
    except Exception:  # noqa: BLE001
        return func.HttpResponse(
            json.dumps({"error": f"incident {incident_id} not found"}),
            mimetype="application/json",
            status_code=404,
        )

    tweet_result: dict[str, Any] = {}

    if action == "approved":
        analysis = incident.get("agent_analysis") or {}
        actions_list = analysis.get("suggested_actions") or []
        tweet_text = actions_list[0] if actions_list else "対応を実施しました。"
        tweet_result = post_tweet(tweet_text)
        outcome = f"承認投稿: {tweet_result.get('status', 'unknown')}"

    elif action == "modified":
        if not modified_text:
            return func.HttpResponse(
                json.dumps({"error": "modified_text is required for action=modified"}),
                mimetype="application/json",
                status_code=400,
            )
        tweet_result = post_tweet(modified_text)
        outcome = f"修正投稿: {tweet_result.get('status', 'unknown')}"

    else:  # cancelled
        tweet_result = {"status": "cancelled"}
        outcome = "キャンセル: 対応なし"

    incident["human_action"] = action
    incident["outcome"] = outcome
    repo.upsert(incident)
    logger.info("approve: incident=%s action=%s result=%s", incident_id, action, tweet_result.get("status"))

    return func.HttpResponse(
        json.dumps({
            "status": "ok",
            "incident_id": incident_id,
            "action": action,
            "tweet_result": tweet_result,
            "outcome": outcome,
        }, ensure_ascii=False),
        mimetype="application/json",
        status_code=200,
    )


@bp.route(route="day/incidents", methods=["GET"])
def list_incidents(req: func.HttpRequest) -> func.HttpResponse:
    """インシデント一覧を返す（クエリパラメータ: limit, severity）。"""
    limit = int(req.params.get("limit", "50"))
    severity = req.params.get("severity", "")

    repo = SharedCoreRepository()
    if severity:
        results = repo.query(
            "SELECT * FROM c WHERE c.container_type='incident_log' AND c.severity=@sev ORDER BY c.created_at DESC OFFSET 0 LIMIT @lim",
            [{"name": "@sev", "value": severity}, {"name": "@lim", "value": limit}],
        )
    else:
        results = repo.query(
            "SELECT * FROM c WHERE c.container_type='incident_log' ORDER BY c.created_at DESC OFFSET 0 LIMIT @lim",
            [{"name": "@lim", "value": limit}],
        )

    return func.HttpResponse(
        json.dumps({"incidents": results, "total": len(results)}, default=str),
        mimetype="application/json",
    )
