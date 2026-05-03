"""豊（Yutaka-02）カスタムツール — 法的リスクスコアリング・コンプライアンス判定"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# 法的リスクキーワードと重み（判例ベース MVP 版）
_LEGAL_RISK_WEIGHTS: dict[str, float] = {
    "名誉毀損": 30,
    "侮辱": 25,
    "プライバシー侵害": 25,
    "個人情報": 20,
    "著作権": 20,
    "商標侵害": 20,
    "虚偽広告": 25,
    "景品表示法": 20,
    "独占禁止法": 20,
    "不正競争": 18,
    "誹謗中傷": 22,
    "差別": 20,
    "ハラスメント": 18,
    "違法": 15,
    "詐欺": 25,
    "消費者庁": 15,
    "行政処分": 20,
    "刑事告訴": 30,
    "損害賠償": 22,
    "訴訟": 25,
}

# 業界別コンプライアンス要件
_INDUSTRY_COMPLIANCE: dict[str, list[str]] = {
    "金融": ["金融商品取引法", "銀行法", "保険業法"],
    "医療": ["薬機法", "医療法", "個人情報保護法"],
    "食品": ["食品衛生法", "JAS法", "景品表示法"],
    "IT": ["個人情報保護法", "不正アクセス禁止法", "電子署名法"],
    "一般": ["消費者契約法", "特商法", "景品表示法"],
}


def calculate_legal_risk(
    text: str,
    industry: str = "一般",
) -> tuple[float, list[str], list[str]]:
    """法的リスクスコア（0-100）、マッチキーワード、関連法規を返す。"""
    score = 0.0
    matched: list[str] = []
    for keyword, weight in _LEGAL_RISK_WEIGHTS.items():
        if keyword in text:
            score += weight
            matched.append(keyword)
    applicable_laws = _INDUSTRY_COMPLIANCE.get(industry, _INDUSTRY_COMPLIANCE["一般"])
    return min(score, 100.0), matched, applicable_laws


def _score_to_risk_level(score: float) -> str:
    if score >= 80:
        return "critical"
    if score >= 60:
        return "high"
    if score >= 40:
        return "medium"
    return "low"


def check_compliance(
    text: str,
    industry: str = "一般",
    risk_score: float | None = None,
    matched_keywords: list[str] | None = None,
) -> dict[str, Any]:
    """コンプライアンスチェック結果を dict で返す。"""
    if risk_score is None or matched_keywords is None:
        risk_score, matched_keywords, _ = calculate_legal_risk(text, industry)

    risk_level = _score_to_risk_level(risk_score)
    applicable_laws = _INDUSTRY_COMPLIANCE.get(industry, _INDUSTRY_COMPLIANCE["一般"])

    recommendations: list[str] = []
    if risk_level in ("critical", "high"):
        recommendations.append("法務部門への即時エスカレーション")
        recommendations.append("外部弁護士への相談を検討")
    if "個人情報" in matched_keywords:
        recommendations.append("個人情報保護法に基づく対応確認")
    if "著作権" in matched_keywords:
        recommendations.append("著作権侵害リスクの法的評価を実施")
    if not recommendations:
        recommendations.append("通常の対応フローで処理可能")

    return {
        "risk_level": risk_level,
        "legal_risk_score": risk_score,
        "matched_keywords": matched_keywords,
        "applicable_laws": applicable_laws,
        "recommendations": recommendations,
        "requires_legal_review": risk_level in ("critical", "high"),
    }


def get_precedent_cases(keywords: list[str]) -> list[dict[str, Any]]:
    """キーワードに関連する過去の炎上判例を返す（MVP: ルールベース）。"""
    precedents: list[dict[str, Any]] = []
    keyword_set = set(keywords)

    if keyword_set & {"名誉毀損", "誹謗中傷", "侮辱"}:
        precedents.append({
            "case_id": "P-2022-001",
            "summary": "SNS 投稿による名誉毀損で企業が損害賠償命令を受けたケース",
            "outcome": "謝罪声明 + 損害賠償 500 万円",
            "lesson": "初動対応の速さが賠償額に影響した",
        })
    if keyword_set & {"個人情報", "プライバシー侵害"}:
        precedents.append({
            "case_id": "P-2023-002",
            "summary": "顧客個人情報漏洩で行政指導を受けたケース",
            "outcome": "個人情報保護委員会による勧告・公表",
            "lesson": "漏洩発覚から 72 時間以内の報告義務",
        })
    if keyword_set & {"虚偽広告", "景品表示法"}:
        precedents.append({
            "case_id": "P-2023-003",
            "summary": "誇大広告で消費者庁から措置命令を受けたケース",
            "outcome": "措置命令 + ブランドイメージ著しく低下",
            "lesson": "優良誤認表示は景表法違反になりうる",
        })

    return precedents
