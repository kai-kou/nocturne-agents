"""砦（Toride-06）カスタムツール — クリティカル分析・反論生成・GitHub PR Draft 作成"""
from __future__ import annotations

import logging
import os
import uuid
from typing import Any

import httpx

from shared.cosmos_client import SharedCoreRepository
from shared.models import Draft, DraftStatus, IncidentLog, Memory, MemoryType

logger = logging.getLogger(__name__)

# 反論トリガーキーワード（「問題ない」「大丈夫」系の楽観的表現）
_OPTIMISTIC_PATTERNS: list[str] = [
    "問題ない",
    "大丈夫",
    "心配ない",
    "支障なし",
    "問題なし",
    "影響なし",
]

# リスク見落としパターン（対応案に含まれていると危険なフレーズ）
_BLIND_SPOT_PATTERNS: dict[str, str] = {
    "様子を見る": "即時対応の遅れが拡散速度を上回るリスクがあります",
    "炎上": "「炎上」という表現は外部報告に不適切です。「情報拡散リスク」に言い換えてください",
    "一時的": "一時的と判断した根拠を明示しないと再発時に批判されます",
    "想定内": "想定内と断言することで、より大きなリスクを見逃す可能性があります",
}


def analyze_critical(
    actions: list[str],
    risk_score: float,
    context: str = "",
) -> dict[str, Any]:
    """対応案をクリティカル分析し、反論・見落としリスクを返す（ルールベース）。"""
    objections: list[str] = []
    blind_spots: list[str] = []

    for action in actions:
        # 楽観的表現チェック
        for pattern in _OPTIMISTIC_PATTERNS:
            if pattern in action:
                objections.append(
                    f"「{pattern}」は根拠のない楽観です。具体的な理由を示してください"
                )
        # 見落としパターンチェック
        for pattern, warning in _BLIND_SPOT_PATTERNS.items():
            if pattern in action:
                blind_spots.append(warning)

    # リスクスコアが高いのに対応案が少ない場合
    if risk_score >= 70 and len(actions) < 2:
        objections.append(
            f"リスクスコア {risk_score:.0f} に対して対応案が不足しています。最低3案を提示してください"
        )

    return {
        "objections": objections,
        "blind_spots": blind_spots,
        "critique_count": len(objections) + len(blind_spots),
        "passed": len(objections) == 0 and len(blind_spots) == 0,
    }


def escalate_incident(
    repo: SharedCoreRepository,
    incident_id: str,
    escalation_reason: str,
) -> dict[str, Any]:
    """インシデントのエスカレーション記録を Cosmos DB に保存する。"""
    record = {
        "id": f"escalation_{uuid.uuid4().hex[:12]}",
        "container_type": "escalation",
        "incident_id": incident_id,
        "reason": escalation_reason,
        "agent_id": "Toride-06",
    }
    repo.upsert(record)
    logger.info("escalation recorded for incident %s", incident_id)
    return record


def save_critique_memory(
    repo: SharedCoreRepository,
    incident_id: str,
    critique_summary: str,
) -> Memory:
    """砦の批評を Memory として保存し、次回の分析品質向上に活用する。"""
    memory = Memory(
        id=f"memory_toride_{uuid.uuid4().hex[:12]}",
        agent_id="Toride-06",
        memory_type=MemoryType.EPISODE,
        content=critique_summary,
        importance_score=0.8,
        source_incident_ids=[incident_id],
    )
    repo.upsert(memory.model_dump())
    return memory


def create_github_pr_draft(
    title: str,
    body: str,
    head_branch: str,
    base_branch: str = "main",
) -> dict[str, Any]:
    """GitHub API を呼び出して PR Draft を作成する。失敗時はスタブ結果を返す。"""
    token = os.environ.get("GITHUB_TOKEN", "")
    repo_full = os.environ.get("GITHUB_REPO", "")

    if not token or not repo_full:
        logger.warning("GITHUB_TOKEN / GITHUB_REPO 未設定のため PR Draft 作成をスキップ")
        return {
            "status": "skipped",
            "message": "GITHUB_TOKEN or GITHUB_REPO not configured",
            "draft_url": None,
        }

    url = f"https://api.github.com/repos/{repo_full}/pulls"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    payload = {
        "title": title,
        "body": body,
        "head": head_branch,
        "base": base_branch,
        "draft": True,
    }

    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            return {"status": "created", "draft_url": data.get("html_url"), "pr_number": data.get("number")}
    except httpx.HTTPError as exc:
        logger.warning("GitHub PR Draft 作成失敗: %s", exc)
        return {"status": "error", "message": str(exc), "draft_url": None}
