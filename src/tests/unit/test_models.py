from __future__ import annotations

from datetime import datetime

import pytest

from shared.models import (
    AgentAnalysis,
    Draft,
    DraftStatus,
    HumanAction,
    IncidentLog,
    Memory,
    MemoryType,
    MoodLog,
    PostHistory,
    Severity,
    ShiftHandover,
)


def test_post_history_risk_score_bounds() -> None:
    ph = PostHistory(id="t1", tweet_id="123", text="test", author="user", risk_score=75.0)
    assert ph.risk_score == 75.0


def test_post_history_invalid_risk_score() -> None:
    with pytest.raises(Exception):
        PostHistory(id="t1", tweet_id="123", text="test", author="user", risk_score=101.0)


def test_incident_log_default_action() -> None:
    incident = IncidentLog(id="i1", severity=Severity.HIGH, risk_score=80.0)
    assert incident.human_action == HumanAction.PENDING


def test_memory_emotional_valence_bounds() -> None:
    mem = Memory(id="m1", agent_id="Mio-01", memory_type=MemoryType.EPISODE, content="test")
    assert mem.emotional_valence == 0.0


def test_draft_default_status() -> None:
    draft = Draft(id="d1", agent_id="Toride-06", draft_type="nocturne", content="content")
    assert draft.status == DraftStatus.WIP


def test_mood_log_score_bounds() -> None:
    log = MoodLog(id="ml1", agent_id="Yomi-04", mood_score=0.5, mood_label="calm")
    assert log.mood_score == 0.5


def test_shift_handover_agent_notes() -> None:
    handover = ShiftHandover(
        id="sh1",
        from_shift="day",
        to_shift="night",
        summary="All clear",
        agent_notes={"Mio-01": "監視継続中"},
    )
    assert handover.agent_notes["Mio-01"] == "監視継続中"
