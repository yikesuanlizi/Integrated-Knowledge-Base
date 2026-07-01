"""Open Knowledge Format import/export helpers."""
from __future__ import annotations

import json
from datetime import datetime


OKF_VERSION = "akos-okf-v1"


def export_okf(cards: list[dict], *, project: str = "Agentic Knowledge OS") -> str:
    payload = {
        "format": OKF_VERSION,
        "project": project,
        "exported_at": datetime.utcnow().isoformat(),
        "cards": cards,
        "total": len(cards),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def import_okf(text: str) -> list[dict]:
    payload = json.loads(text)
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        raise ValueError("OKF payload must be a JSON object")
    if payload.get("format") not in (OKF_VERSION, None):
        raise ValueError(f"Unsupported OKF format: {payload.get('format')}")
    cards = payload.get("cards", [])
    if not isinstance(cards, list):
        raise ValueError("OKF cards must be a list")
    return [item for item in cards if isinstance(item, dict)]
