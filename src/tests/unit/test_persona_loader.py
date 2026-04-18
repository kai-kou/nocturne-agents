from __future__ import annotations

import pytest

from shared.persona_loader import load_all_personas, load_persona


def test_load_mio_01() -> None:
    card = load_persona("Mio-01")
    assert card.persona_id == "Mio-01"
    assert card.display_name_ja == "澪"
    assert card.shift == "day"
    assert card.incident_threshold_score == 70


def test_load_toride_06() -> None:
    card = load_persona("Toride-06")
    assert card.persona_id == "Toride-06"
    assert card.display_name_ja == "砦"
    assert card.shift == "night"


def test_load_yomi_04() -> None:
    card = load_persona("Yomi-04")
    assert card.persona_id == "Yomi-04"
    assert card.display_name_ja == "読"
    assert card.shift == "night"
    assert card.memory_retention_days == 90


def test_load_nonexistent_raises() -> None:
    with pytest.raises(FileNotFoundError):
        load_persona("Ghost-99")


def test_load_all_personas() -> None:
    personas = load_all_personas()
    assert "Mio-01" in personas
    assert "Toride-06" in personas
    assert "Yomi-04" in personas


def test_persona_tools_allowed() -> None:
    card = load_persona("Yomi-04")
    assert "cosmos_shared_read" in card.tools_allowed
    assert "twitter_search" not in card.tools_allowed
