from __future__ import annotations

from typing import Any, Dict

from json_repair import repair_json
import json


def safe_json_loads(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    text = str(raw or "").strip()
    if not text:
        return {}
    try:
        repaired = repair_json(text)
        payload = json.loads(repaired) if isinstance(repaired, str) else repaired
    except Exception:
        payload = None
    return payload if isinstance(payload, dict) else {}