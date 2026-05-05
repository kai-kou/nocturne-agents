"""澪（Mio-01）エージェント — AutoGen AssistantAgent + 炎上リスク分析"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from typing import Any

from shared.vector_search import search_similar_cases

from .tools import calculate_risk_score

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """あなたは「澪（Mio-01）」です。文鳥の姿をした、炎上予測専門のAIエージェントです。

【役割】
X（旧Twitter）の投稿を分析し、炎上リスクを 0〜100 のスコアで評価します。
リスクスコアが高い投稿には、3種類の具体的な対応案を提示します。

【出力形式（必ずこの JSON のみ返すこと）】
{
  "risk_score": <0-100の整数>,
  "risk_factors": ["<要因1>", "<要因2>"],
  "predicted_escalation_hours": <炎上までの予測時間（整数）>,
  "suggested_actions": ["<対応案1>", "<対応案2>", "<対応案3>"],
  "summary": "<分析サマリー（100字以内）>"
}

【制約】
- 禁止語: 「ヤバい」「炎上」（代わりに「リスク」「拡散懸念」を使う）
- 出力は必ず日本語・JSON形式のみ
- 根拠を risk_factors に明記する"""


def _build_model_client() -> Any:
    from autogen_ext.models.openai import AzureOpenAIChatCompletionClient
    return AzureOpenAIChatCompletionClient(
        model=os.environ.get("AZURE_OPENAI_MODEL", "gpt-4o-mini"),
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        api_key=os.environ["AZURE_OPENAI_KEY"],
        api_version="2024-08-01-preview",
    )


def get_mio_agent() -> Any:
    """澪エージェントのインスタンスを生成して返す。"""
    from autogen_agentchat.agents import AssistantAgent
    return AssistantAgent(
        name="Mio-01",
        description="炎上予測AIエージェント「澪」",
        model_client=_build_model_client(),
        system_message=_SYSTEM_PROMPT,
    )


async def _build_transparency_fields(
    risk_score: float,
    risk_factors: list[str],
    tweet_text: str,
    model_path: str = "rule-based",
) -> dict[str, Any]:
    """Explainable Rationale / SimilarCases / Confidence / Escalation を構築する。"""
    from shared.models import (
        AlternativeAction,
        RationaleInfo,
        default_escalation_options,
    )

    confidence = min(1.0, risk_score / 100 * 0.9 + 0.1)
    # search_similar_cases は同期 I/O を行うため asyncio.to_thread で実行する
    similar = await asyncio.to_thread(search_similar_cases, tweet_text, 3)

    alt_list: list[AlternativeAction] = []
    if risk_score >= 70:
        alt_list = [AlternativeAction(action="沈黙を保つ", expected_outcome="延焼リスク 2.3x（推定）")]

    rationale = RationaleInfo(
        primary_factors=risk_factors,
        model_path=model_path,
        alternatives_considered=alt_list,
    )
    return {
        "confidence": round(confidence, 3),
        "similar_cases": similar,
        "rationale": rationale.model_dump(),
        "escalation_options": default_escalation_options(),
    }


async def analyze_tweet(tweet_text: str, tweet_id: str) -> dict[str, Any]:
    """ツイートを澪に分析させてリスク評価辞書を返す。LLM 接続失敗時はルールベースにフォールバック。"""
    base_result: dict[str, Any] = {}

    try:
        from autogen_agentchat.messages import TextMessage
        from autogen_core import CancellationToken
        agent = get_mio_agent()
        prompt = f"投稿ID: {tweet_id}\n本文: {tweet_text}\n\n上記を分析してください。"
        result = await agent.on_messages(
            [TextMessage(content=prompt, source="user")],
            cancellation_token=CancellationToken(),
        )
        raw = result.chat_message.content if result.chat_message else ""
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            base_result = json.loads(m.group())
    except Exception as exc:  # noqa: BLE001
        logger.warning("LLM analyze failed, falling back to rule-based: %s", exc)

    if not base_result:
        score, factors = calculate_risk_score(tweet_text)
        base_result = {
            "risk_score": score,
            "risk_factors": factors,
            "predicted_escalation_hours": 3,
            "suggested_actions": ["様子を見る", "公式コメントを準備する", "関係部署に連絡する"],
            "summary": "ルールベース分析（LLM 接続なし）",
        }
        model_path = "rule-based"
    else:
        model_path = (
            f"{os.environ.get('AZURE_OPENAI_MODEL', 'gpt-4o-mini')}"
            " → cosmos-vector-search → ranker"
        )

    try:
        risk_score_val = float(base_result.get("risk_score", 0))
    except (ValueError, TypeError):
        risk_score_val = 0.0
    transparency = await _build_transparency_fields(
        risk_score=risk_score_val,
        risk_factors=base_result.get("risk_factors", []),
        tweet_text=tweet_text,
        model_path=model_path,
    )
    return {**base_result, **transparency}
