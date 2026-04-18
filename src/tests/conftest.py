from __future__ import annotations

import os

import pytest

os.environ.setdefault("COSMOS_ENDPOINT", "https://localhost:8081/")
os.environ.setdefault("COSMOS_KEY", "dummy-key-for-tests")
os.environ.setdefault("COSMOS_DATABASE", "after-hours-agents-test")
os.environ.setdefault("ENTRA_AGENT_ID_MIO_01", "")
os.environ.setdefault("ENTRA_AGENT_ID_TORIDE_06", "")
os.environ.setdefault("ENTRA_AGENT_ID_YOMI_04", "")
os.environ.setdefault("ENTRA_AGENT_ID_DIGEST", "")
