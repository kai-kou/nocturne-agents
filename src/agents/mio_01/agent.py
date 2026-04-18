"""澪（Mio-01）エージェント — AutoGen AssistantAgent + 炎上リスク分析"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from autogen_agentchat.agents import AssistantAgent

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


async def analyze_tweet(tweet_text: str, tweet_id: str) -> dict[str, Any]:
    """ツイートを澪に分析させてリスク評価辞書を返す。LLM 接続失敗時はルールベースにフォールバック。"""
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
            return json.loads(m.group())
    except Exception as exc:  # noqa: BLE001
        logger.warning("LLM analyze failed, falling back to rule-based: %s", exc)

    score, factors = calculate_risk_score(tweet_text)
    return {
        "risk_score": score,
        "risk_factors": factors,
        "predicted_escalation_hours": 3,
        "suggested_actions": ["様子を見る", "公式コメントを準備する", "関係部署に連絡する"],
        "summary": "ルールベース分析（LLM 接続なし）",
    }
