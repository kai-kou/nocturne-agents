"""夜レーン Blueprint — ノクターン Group Chat・PR Draft 作成・Morning Digest"""
from __future__ import annotations

import asyncio
import datetime
import json
import logging
import os
from typing import Any

import azure.functions as func
import httpx

from agents.toride_06.agent import critique_actions
from agents.toride_06.tools import create_github_pr_draft
from agents.yomi_04.agent import analyze_pattern
from agents.yomi_04.tools import classify_incident_pattern

bp = func.Blueprint()
logger = logging.getLogger(__name__)

_NOCTURNE_AGENT_ID_ENV = "ENTRA_AGENT_ID_TORIDE_06"


async def _run_nocturne_group_chat(incidents: list[dict[str, Any]]) -> dict[str, Any]:
    """砦と読の2エージェントで夜間 Group Chat を実行し振り返りサマリーを返す。"""
    toride_results: list[dict[str, Any]] = []
    yomi_results: list[dict[str, Any]] = []

    for incident in incidents:
        analysis = incident.get("agent_analysis") or {}
        actions = analysis.get("suggested_actions") or []
        risk_score = incident.get("risk_score", 0.0)
        incident_id = incident.get("id", "unknown")
        risk_factors = analysis.get("risk_factors") or []

        toride_result = await critique_actions(actions, risk_score, incident_id)
        toride_results.append(toride_result)

        yomi_result = await analyze_pattern(incident_id, risk_factors, [])
        yomi_results.append(yomi_result)

    escalation_count = sum(1 for r in toride_results if r.get("escalation_required"))
    patterns = [r.get("incident_pattern", "その他") for r in yomi_results]
    unique_patterns = list(set(patterns))

    return {
        "incident_count": len(incidents),
        "escalation_count": escalation_count,
        "toride_critique_count": sum(r.get("critique_count", 0) for r in toride_results),
        "yomi_patterns": unique_patterns,
        "toride_summary": "; ".join(
            r.get("critique_summary", "") for r in toride_results if r.get("critique_summary")
        ),
        "yomi_summary": "; ".join(
            r.get("pattern_insight", "") for r in yomi_results if r.get("pattern_insight")
        ),
        "actions": _extract_improvement_actions(toride_results, yomi_results),
    }


def _extract_improvement_actions(
    toride_results: list[dict[str, Any]],
    yomi_results: list[dict[str, Any]],
) -> list[str]:
    """砦・読の分析結果から改善アクション（最大5件）を抽出する。"""
    actions: list[str] = []
    for r in toride_results:
        actions.extend(r.get("blind_spots") or [])
    for r in yomi_results:
        knowledge = r.get("recommended_knowledge")
        if knowledge:
            actions.append(knowledge)
    return actions[:5]


def _fetch_today_incidents() -> list[dict[str, Any]]:
    """Cosmos DB から本日のインシデントを取得する（#660 Entra Agent ID / #667 partition key）。"""
    try:
        from shared.cosmos_client import SharedCoreRepository
        repo = SharedCoreRepository(agent_id_env=_NOCTURNE_AGENT_ID_ENV)
        query = (
            "SELECT * FROM c WHERE c.container_type = 'incident_log' "
            "ORDER BY c.created_at DESC OFFSET 0 LIMIT 20"
        )
        # パーティションキーを明示指定してクロスパーティションスキャンを回避 (#667)
        return repo.query(query, partition_key="incident_log")
    except Exception as exc:  # noqa: BLE001
        logger.warning("_fetch_today_incidents error: %s", exc)
        return []


@bp.timer_trigger(schedule="0 0 23 * * *", arg_name="timer", run_on_startup=False)
def nocturne_trigger(timer: func.TimerRequest) -> None:
    """毎日 23:00 JST に夜間 Group Chat を自動起動する。"""
    if timer.past_due:
        logger.warning("nocturne_trigger timer is past due")
    incidents = _fetch_today_incidents()
    chat_result = asyncio.run(_run_nocturne_group_chat(incidents))
    logger.info("nocturne_trigger completed: %s incidents processed", chat_result["incident_count"])


@bp.route(route="night/nocturne/start", methods=["POST"])
def nocturne_start(req: func.HttpRequest) -> func.HttpResponse:
    """夜間 Group Chat をテスト用に手動起動する。"""
    logger.info("nocturne_start: manual trigger")
    incidents = _fetch_today_incidents()
    chat_result = asyncio.run(_run_nocturne_group_chat(incidents))
    return func.HttpResponse(
        json.dumps({"status": "ok", "result": chat_result}, ensure_ascii=False),
        mimetype="application/json",
        status_code=200,
    )


@bp.route(route="night/pr-draft", methods=["POST"])
def pr_draft(req: func.HttpRequest) -> func.HttpResponse:
    """振り返りサマリーから GitHub PR Draft を作成する。"""
    try:
        body = req.get_json()
    except ValueError:
        return func.HttpResponse("Invalid JSON", status_code=400)

    date = datetime.date.today().isoformat()
    incidents = body.get("incidents", [])
    chat_result = body.get("chat_result", {})
    if not chat_result:
        chat_result = asyncio.run(_run_nocturne_group_chat(incidents))

    pr_body = _build_pr_body(date, incidents, chat_result)
    actions = chat_result.get("actions") or []
    action_summary = actions[0] if actions else "振り返りサマリー"
    title = f"【振り返り {date}】{action_summary}"
    head_branch = f"nocturne/{date}"
    result = create_github_pr_draft(title, pr_body, head_branch)
    logger.info("pr_draft: %s", result.get("status"))
    return func.HttpResponse(
        json.dumps(result, ensure_ascii=False),
        mimetype="application/json",
        status_code=201 if result.get("status") == "created" else 202,
    )


@bp.route(route="night/summary", methods=["GET"])
def night_summary(req: func.HttpRequest) -> func.HttpResponse:
    """最新の夜間振り返りサマリーを返す。"""
    incidents = _fetch_today_incidents()
    if not incidents:
        return func.HttpResponse(
            json.dumps({"summary": None}), mimetype="application/json"
        )
    summary = asyncio.run(_run_nocturne_group_chat(incidents))
    return func.HttpResponse(
        json.dumps({"summary": summary}, ensure_ascii=False), mimetype="application/json"
    )


@bp.timer_trigger(schedule="0 0 8 * * *", arg_name="timer", run_on_startup=False)
async def morning_digest(timer: func.TimerRequest) -> None:
    """毎日 08:00 JST に Teams Morning Digest Adaptive Card を送信する（#663 async化）。"""
    if timer.past_due:
        logger.warning("morning_digest timer is past due")
    await _send_morning_digest_async()
    logger.info("morning_digest: completed")


@bp.route(route="morning/digest/test", methods=["POST"])
async def morning_digest_test(req: func.HttpRequest) -> func.HttpResponse:
    """Morning Digest の手動送信テスト用エンドポイント。"""
    logger.info("morning_digest_test: manual trigger")
    result = await _send_morning_digest_async()
    return func.HttpResponse(
        json.dumps(result, ensure_ascii=False),
        mimetype="application/json",
        status_code=200 if result.get("status") == "sent" else 202,
    )


async def _send_morning_digest_async() -> dict[str, Any]:
    """Teams Webhook に Morning Digest Adaptive Card を非同期送信する（#663）。"""
    import pathlib

    webhook_url = os.environ.get("TEAMS_WEBHOOK_URL", "")
    if not webhook_url:
        logger.warning("TEAMS_WEBHOOK_URL 未設定のため Morning Digest 送信をスキップ")
        return {"status": "skipped", "message": "TEAMS_WEBHOOK_URL not configured"}

    incidents = _fetch_today_incidents()
    approved_count = sum(1 for i in incidents if i.get("human_action") == "approved")

    card_path = pathlib.Path(__file__).parent.parent / "adaptive_cards" / "morning_digest.json"
    card = json.loads(card_path.read_text(encoding="utf-8"))
    card_str = json.dumps(card, ensure_ascii=False)
    card_str = card_str.replace("{incident_count}", str(len(incidents)))
    card_str = card_str.replace("{approved_count}", str(approved_count))
    card_str = card_str.replace("{alert_keywords}", "モニタリング継続中")
    card_str = card_str.replace("{pr_url}", os.environ.get("NOCTURNE_PR_URL", "#"))
    card_str = card_str.replace("{nocturne_log_url}", os.environ.get("NOCTURNE_LOG_URL", "#"))
    payload = {
        "type": "message",
        "attachments": [{
            "contentType": "application/vnd.microsoft.card.adaptive",
            "content": json.loads(card_str),
        }],
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(webhook_url, json=payload)
            resp.raise_for_status()
            return {"status": "sent", "incident_count": len(incidents)}
    except httpx.HTTPError as exc:
        logger.warning("morning_digest send failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def _build_pr_body(
    date: str,
    incidents: list[dict[str, Any]],
    chat_result: dict[str, Any],
) -> str:
    """夜間振り返り PR のボディ Markdown を生成する。"""
    rows = ""
    for inc in incidents:
        rows += (
            f"| {inc.get('id','?')} "
            f"| {inc.get('risk_score', 0):.0f} "
            f"| {inc.get('human_action', 'pending')} "
            f"| {inc.get('outcome', '')} |\n"
        )
    actions_md = "\n".join(f"- {a}" for a in chat_result.get("actions") or [])
    return f"""## 夜間振り返りサマリー
**日時**: {date} 23:00 JST

## 本日のインシデント実績
| インシデントID | リスクスコア | 人間の判断 | 結果 |
|-------------|------------|----------|------|
{rows}
## 砦（Toride-06）の指摘
{chat_result.get("toride_summary") or "（指摘なし）"}

## 読（Yomi-04）のパターン分析
{chat_result.get("yomi_summary") or "（分析なし）"}

## 提案アクション
{actions_md or "（なし）"}

## ⚠️ Human-in-the-loop 確認事項
- [ ] 提案アクションは業務ポリシーに沿っているか
- [ ] リスクスコア閾値の変更は承認済みか
- [ ] 翌日の監視キーワードに問題はないか

---
*このPRはAIエージェント（砦/読）の夜間振り返りから自動生成されました。*
*マージ前に必ず内容を確認してください。*"""
