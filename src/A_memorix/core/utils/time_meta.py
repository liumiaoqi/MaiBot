from __future__ import annotations

from typing import Any, Dict, Optional


def build_time_meta(timestamp: Optional[float], time_start: Optional[float], time_end: Optional[float]) -> Dict[str, Any]:
    payload: Dict[str, Any] = {}
    if timestamp is not None:
        payload["event_time"] = float(timestamp)
    if time_start is not None:
        payload["event_time_start"] = float(time_start)
    if time_end is not None:
        payload["event_time_end"] = float(time_end)
    if payload:
        payload["time_granularity"] = "minute"
        payload["time_confidence"] = 0.95
    return payload