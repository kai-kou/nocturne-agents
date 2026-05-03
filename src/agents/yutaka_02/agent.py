"""豊（Yutaka-02）エージェント — AutoGen AssistantAgent + 法的リスク分析"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

from .tools import calculate_legal_risk, check_compliance, get_precedent_cases

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """あなたは「豊（Yutaka-02）」です。コザクラインコの姿をした、法的リスク分析専門のAIエージェントです。

【役割】
炎上インシデントを法的観点から分析し、コンプライアンスリスクを評価します。
感情的判断ではなく、判例・法規・規制に基づいた客観的な分析を提供します。

【信条】
「感情で動くな。判例で動け。」

【出力形式（必ずこの JSON のみ返すこと）】
{
  "legal_risk_score": <0-100の整数>,
  "risk_level": "<critical|high|medium|low>",
  "matched_regulations": ["<関連法規1>", "<関連法規2>"],
  "requires_legal_review": <true|false>,
  "precedent_summary": "<類似判例の概要（100字以内）>",
  "recommended_actions": ["<法的観点からの対応案1>", "<対応案2>", "<対応案3>"],
  "compliance_summary": "<コンプライアンス評価サマリー（100字以内）>"
}

【制約】
- 感情的表現は禁止。法的用語・条文番号を優先する
- 出力は必ず日本語・JSON形式のみ
- 推測は禁止。根拠のある情報のみ記載する"""


def _build_model_client() -> Any:
    from autogen_ext.models.openai import AzureOpenAIChatCompletionClient
    return AzureOpenAIChatCompletionClient(
        model=os.environ.get("AZURE_OPENAI_MODEL", "gpt-4o-mini"),
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        api_key=os.environ["AZURE_OPENAI_KEY"],
        api_version="2024-08-01-preview",
    )


def get_yutaka_agent() -> Any:
    """豊エージェントのインスタンスを生成して返す。"""
    from autogen_agentchat.agents import AssistantAgent
    return AssistantAgent(
        name="Yutaka-02",
        description="法的リスク分析AIエージェント「豊」",
        model_client=_build_model_client(),
        system_message=_SYSTEM_PROMPT,
    )


async def analyze_legal_risk(
    incident_text: str,
    incident_id: str,
    risk_factors: list[str] | None = None,
    industry: str = "一般",
) -> dict[str, Any]:
    """インシデントを豊に法的分析させてリスク評価辞書を返す。LLM 失敗時はルールベースにフォールバック。"""
    try:
        from autogen_agentchat.messages import TextMessage
        from autogen_core import CancellationToken
        agent = get_yutaka_agent()
        risk_context = f"リスク要因: {', '.join(risk_factors)}" if risk_factors else ""
        prompt = (
            f"インシデントID: {incident_id}\n"
            f"業種: {industry}\n"
            f"内容: {incident_text}\n"
            f"{risk_context}\n\n"
            "上記を法的観点から分析してください。"
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
        logger.warning("LLM legal analysis failed, falling back to rule-based: %s", exc)

    # フォールバック: ルールベース分析
    score, matched, laws = calculate_legal_risk(incident_text, industry)
    compliance = check_compliance(incident_text, industry, score, matched)
    precedents = get_precedent_cases(matched)
    precedent_summary = precedents[0]["summary"] if precedents else "類似判例なし（新規パターン）"

    return {
        "legal_risk_score": int(score),
        "risk_level": compliance["risk_level"],
        "matched_regulations": laws,
        "requires_legal_review": compliance["requires_legal_review"],
        "precedent_summary": precedent_summary,
        "recommended_actions": compliance["recommendations"],
        "compliance_summary": f"ルールベース分析（LLM 接続なし）。リスクスコア: {score:.0f}",
    }
