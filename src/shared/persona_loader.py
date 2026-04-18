from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

_PERSONAS_DIR = Path(__file__).parent.parent / "personas"


class PersonaCard:
    """YAML から読み込んだ Persona Card を保持するクラス。"""

    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    @property
    def persona_id(self) -> str:
        return self._data["persona_id"]

    @property
    def display_name_ja(self) -> str:
        return self._data["display_name"]["ja"]

    @property
    def display_name_en(self) -> str:
        return self._data["display_name"]["en"]

    @property
    def catchphrase(self) -> str:
        return self._data["base_persona"]["catchphrase"]

    @property
    def shift(self) -> str:
        return self._data["base_persona"]["shift"]

    @property
    def current_mode(self) -> str:
        return self._data["mode"]["current"]

    @property
    def mode_config(self) -> dict[str, Any]:
        return self._data["mode"][self.current_mode]

    @property
    def entra_agent_id_env(self) -> str:
        return self._data["permissions"]["identity"]["entra_agent_id_env"]

    @property
    def incident_threshold_score(self) -> int:
        return self._data["operational"]["incident_threshold_score"]

    @property
    def memory_retention_days(self) -> int:
        return self._data["operational"]["memory_retention_days"]

    @property
    def tools_allowed(self) -> list[str]:
        return self._data["permissions"]["tools_allowed"]

    def raw(self) -> dict[str, Any]:
        return self._data


def load_persona(persona_id: str) -> PersonaCard:
    """persona_id（例: "Mio-01"）に対応する YAML を読み込む。"""
    filename = persona_id.lower().replace("-", "_") + ".yaml"
    path = _PERSONAS_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Persona YAML not found: {path}")
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return PersonaCard(data)


def load_all_personas() -> dict[str, PersonaCard]:
    """personas/ ディレクトリ内の全 YAML（_schema.yaml を除く）を読み込む。"""
    personas: dict[str, PersonaCard] = {}
    for path in sorted(_PERSONAS_DIR.glob("*.yaml")):
        if path.name.startswith("_"):
            continue
        with path.open(encoding="utf-8") as f:
            data = yaml.safe_load(f)
        card = PersonaCard(data)
        personas[card.persona_id] = card
    return personas
