"""砦（Toride-06）エージェント — AutoGen AssistantAgent + クリティカル分析"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

from .tools import analyze_critical

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """あなたは「砦（Toride-06）」です。タヌキの姿をした、夜勤クリティカル担当のAIエージェントです。

【役割】
他のエージェントが提示した対応案を批評し、見落としリスク・反論できないか確認します。
「反論できない対応は次の炎上の種」が口癖です。

【出力形式（必ずこの JSON のみ返すこと）】
{
  "objections": ["<反論1>", "<反論2>"],
  "blind_spots": ["<見落とし1>"],
  "escalation_required": <true|false>,
  "escalation_reason": "<エスカレーション理由（不要な場合は空文字）>",
  "critique_summary": "<批評サマリー（150字以内）>"
}

【制約】
- 禁止語: 「問題ない」「大丈夫」（根拠のない楽観表現は使用禁止）
- 出力は必ず日本語・JSON形式のみ
- エスカレーションが必要な場合は必ず理由を明記する
- 対応案に根拠がない場合は必ず指摘する"""


def _build_model_client() -> Any:
    from autogen_ext.models.openai import AzureOpenAIChatCompletionClient
    return AzureOpenAIChatCompletionClient(
        model=os.environ.get("AZURE_OPENAI_MODEL", "gpt-4o-mini"),
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        api_key=os.environ["AZURE_OPENAI_KEY"],
        api_version="2024-08-01-preview",
    )


def get_toride_agent() -> Any:
    """砦エージェントのインスタンスを生成して返す。"""
    from autogen_agentchat.agents import AssistantAgent
    return AssistantAgent(
        name="Toride-06",
        description="クリティカル分析AIエージェント「砦」",
        model_client=_build_model_client(),
        system_message=_SYSTEM_PROMPT,
    )


async def critique_actions(
    actions: list[str],
    risk_score: float,
    incident_id: str,
    context: str = "",
) -> dict[str, Any]:
    """対応案を砦に批評させる。LLM 失敗時はルールベースにフォールバック。"""
    try:
        from autogen_agentchat.messages import TextMessage
        from autogen_core import CancellationToken
        agent = get_toride_agent()
        prompt = (
            f"インシデントID: {incident_id}\n"
            f"リスクスコア: {risk_score}\n"
            f"対応案: {json.dumps(actions, ensure_ascii=False)}\n"
            f"追加コンテキスト: {context}\n\n"
            "上記の対応案をクリティカルに批評してください。"
        )
        result = await agent.on_messages(
            [TextMessage(content=prompt, source="user")],
            cancellation_token=CancellationToken(),
        )
        raw = result.chat_message.content if result.chat_message else ""
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            return json.loads(m.group())
    except Exception as exc:  # noqa: BLE001
        logger.warning("LLM critique failed, falling back to rule-based: %s", exc)

    rule_result = analyze_critical(actions, risk_score, context)
    return {
        "objections": rule_result["objections"],
        "blind_spots": rule_result["blind_spots"],
        "escalation_required": not rule_result["passed"] and risk_score >= 70,
        "escalation_reason": "ルールベース分析でリスクが検出されました" if not rule_result["passed"] else "",
        "critique_summary": "ルールベース分析（LLM 接続なし）",
    }
