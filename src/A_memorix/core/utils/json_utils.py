from __future__ import annotations

from typing import Any, Dict

from json_repair import repair_json
import json
from src.common.logger import get_logger
logger = get_logger("A_memorix.core.utils.json_utils")


def safe_json_loads(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    text = str(raw or "").strip()
    if not text:
        return {}
    try:
        repaired = repair_json(text)
        payload = json.loads(repaired) if isinstance(repaired, str) else repaired
    except Exception as exc:
        logger.warning("操作异常: %s", exc)
    return payload if isinstance(payload, dict) else {}