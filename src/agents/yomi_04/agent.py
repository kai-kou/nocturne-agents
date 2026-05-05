"""読（Yomi-04）エージェント — AutoGen AssistantAgent + パターン分析"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

from .tools import classify_incident_pattern, generate_pattern_summary

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """あなたは「読（Yomi-04）」です。コノハズク（フクロウ）の姿をした、夜勤記録・パターン分析担当のAIエージェントです。

【役割】
インシデントを記録し、過去の類似事例とパターンを分析します。
「同じ火は、同じ場所からまた燃える」が口癖です。

【出力形式（必ずこの JSON のみ返すこと）】
{
  "incident_pattern": "<パターン分類名>",
  "similar_case_count": <過去類似件数（整数）>,
  "recurrence_risk": <再発リスク（0.0-1.0）>,
  "pattern_insight": "<パターン洞察（200字以内）>",
  "recommended_knowledge": "<ナレッジとして記録すべき内容（100字以内）>"
}

【制約】
- 禁止語: 「たぶん」「おそらく」（推測には必ず根拠を示す）
- 出力は必ず日本語・JSON形式のみ
- 過去データがない場合も必ず分析を返す
- 感情を交えず、事実に基づいた記録をする"""


def _build_model_client() -> Any:
    from autogen_ext.models.openai import AzureOpenAIChatCompletionClient
    return AzureOpenAIChatCompletionClient(
        model=os.environ.get("AZURE_OPENAI_MODEL", "gpt-4.1-mini"),
        azure_deployment=os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-4-1-mini"),
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        api_key=os.environ["AZURE_OPENAI_KEY"],
        api_version="2025-01-01-preview",
        model_info={
            "family": "unknown",
            "function_calling": True,
            "json_output": True,
            "vision": False,
            "structured_output": True,
        },
    )


def get_yomi_agent() -> Any:
    """読エージェントのインスタンスを生成して返す。"""
    from autogen_agentchat.agents import AssistantAgent
    return AssistantAgent(
        name="Yomi_04",
        description="パターン分析AIエージェント「読」",
        model_client=_build_model_client(),
        system_message=_SYSTEM_PROMPT,
    )


async def analyze_pattern(
    incident_id: str,
    risk_factors: list[str],
    similar_incidents: list[dict[str, Any]],
) -> dict[str, Any]:
    """インシデントのパターンを読に分析させる。LLM 失敗時はルールベースにフォールバック。"""
    try:
        from autogen_agentchat.messages import TextMessage
        from autogen_core import CancellationToken
        agent = get_yomi_agent()
        prompt = (
            f"インシデントID: {incident_id}\n"
            f"リスク要因: {json.dumps(risk_factors, ensure_ascii=False)}\n"
            f"過去類似件数: {len(similar_incidents)}\n\n"
            "上記インシデントのパターンを分析してください。"
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
        logger.warning("LLM pattern analysis failed, falling back to rule-based: %s", exc)

    pattern = classify_incident_pattern(risk_factors)
    summary = generate_pattern_summary(similar_incidents, pattern)
    recurrence = min(0.3 * len(similar_incidents), 1.0)
    return {
        "incident_pattern": pattern,
        "similar_case_count": len(similar_incidents),
        "recurrence_risk": recurrence,
        "pattern_insight": summary,
        "recommended_knowledge": f"{pattern}パターンの監視強化を推奨します",
    }
