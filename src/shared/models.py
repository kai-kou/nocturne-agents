from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class HumanAction(str, Enum):
    APPROVED = "approved"
    MODIFIED = "modified"
    CANCELLED = "cancelled"
    PENDING = "pending"


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class PostHistory(BaseModel):
    id: str = Field(alias="id")
    container_type: str = "post_history"
    tweet_id: str
    text: str
    author: str
    risk_score: float = Field(ge=0, le=100)
    keywords_matched: list[str] = Field(default_factory=list)
    retrieved_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {"populate_by_name": True}


class AgentAnalysis(BaseModel):
    agent_id: str
    summary: str
    risk_factors: list[str] = Field(default_factory=list)
    suggested_actions: list[str] = Field(default_factory=list)


class IncidentLog(BaseModel):
    id: str
    container_type: str = "incident_log"
    severity: Severity
    risk_score: float = Field(ge=0, le=100)
    tweet_ids: list[str] = Field(default_factory=list)
    agent_analysis: AgentAnalysis | None = None
    human_action: HumanAction = HumanAction.PENDING
    outcome: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)
    resolved_at: datetime | None = None

    model_config = {"populate_by_name": True}


class MemoryType(str, Enum):
    EPISODE = "episode"
    PATTERN = "pattern"
    KNOWLEDGE = "knowledge"


class Memory(BaseModel):
    id: str
    container_type: str = "memory"
    agent_id: str
    memory_type: MemoryType
    content: str
    emotional_valence: float = Field(default=0.0, ge=-1.0, le=1.0)
    importance_score: float = Field(default=0.5, ge=0.0, le=1.0)
    source_incident_ids: list[str] = Field(default_factory=list)
    expires_at: datetime | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {"populate_by_name": True}


class DraftStatus(str, Enum):
    WIP = "wip"
    READY = "ready"
    DISCARDED = "discarded"


class Draft(BaseModel):
    id: str
    container_type: str = "draft"
    agent_id: str
    draft_type: str
    content: str
    status: DraftStatus = DraftStatus.WIP
    created_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {"populate_by_name": True}


class MoodLog(BaseModel):
    id: str
    container_type: str = "mood_log"
    agent_id: str
    mood_score: float = Field(ge=-1.0, le=1.0)
    mood_label: str
    trigger_incident_id: str | None = None
    recorded_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {"populate_by_name": True}


class ShiftHandover(BaseModel):
    id: str
    container_type: str = "shift_handover"
    from_shift: str
    to_shift: str
    handover_at: datetime = Field(default_factory=datetime.utcnow)
    summary: str
    pending_incidents: list[str] = Field(default_factory=list)
    agent_notes: dict[str, Any] = Field(default_factory=dict)

    model_config = {"populate_by_name": True}


class AgentKnowledge(BaseModel):
    id: str
    container_type: str = "agent_knowledge"
    knowledge_type: str
    content: str
    confidence: float = Field(ge=0.0, le=1.0)
    source_incident_ids: list[str] = Field(default_factory=list)
    expires_at: datetime | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {"populate_by_name": True}


class SimilarCase(BaseModel):
    """過去の類似炎上事例（RAG 検索結果）。"""

    case_id: str
    title: str
    similarity_score: float = Field(ge=0.0, le=1.0)
    outcome: str = ""
    lessons_learned: str = ""
    applicable_actions: list[str] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class AlternativeAction(BaseModel):
    action: str
    expected_outcome: str


class RationaleInfo(BaseModel):
    """AI が判断に至った根拠（Explainable Rationale）。"""

    primary_factors: list[str] = Field(default_factory=list)
    model_path: str = ""
    alternatives_considered: list[AlternativeAction] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class EscalationOption(BaseModel):
    """ユーザーが選択できるエスカレーションアクション。"""

    action: str
    label: str

    model_config = {"populate_by_name": True}


_DEFAULT_ESCALATION_OPTIONS: list[dict[str, str]] = [
    {"action": "approve", "label": "提案通り対応する"},
    {"action": "escalate_pr", "label": "PR・広報部門に相談する"},
    {"action": "escalate_legal", "label": "法務部門に相談する"},
    {"action": "skip", "label": "対応を見送る"},
]


def default_escalation_options() -> list[dict[str, str]]:
    return [{**opt} for opt in _DEFAULT_ESCALATION_OPTIONS]
