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
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port
        port = get_error_escalation_port()
        if port is not None:
            port.report(ErrorLevel.WARNING, "安全解析 JSON 失败", exception=exc)
        logger.warning("操作异常: %s", exc)
    return payload if isinstance(payload, dict) else {}
