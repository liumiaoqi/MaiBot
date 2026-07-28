"""日志管理 API — 动态级别调整、日志搜索、ThinkCycleLog 查询。"""


import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Query

router = APIRouter(prefix="/api/webui/log", tags=["log"])

_LOG_DIR = Path("logs")
_LEVEL_NAMES = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}


def _level_to_name(level: int) -> str:
    for name, val in _LEVEL_NAMES.items():
        if val == level:
            return name
    return str(level)


# ── T1: 动态级别调整 ──────────────────────────────────────────


@router.get("/levels")
async def get_log_levels() -> list[dict[str, Any]]:
    """返回所有模块的当前日志级别。"""
    result: list[dict[str, Any]] = []
    for name, logger in sorted(logging.getLogger().manager.loggerDict.items()):
        if isinstance(logger, logging.Logger):
            result.append({
                "module": name,
                "level": _level_to_name(logger.level),
                "effective_level": _level_to_name(logger.getEffectiveLevel()),
            })
    return result


@router.patch("/levels")
async def set_log_levels(payload: dict[str, Any]) -> dict[str, Any]:
    """修改模块日志级别。支持 prefix 批量调整。

    Body: {"prefix": "maisaka", "level": "DEBUG"}
    或: {"module": "maisaka.runtime", "level": "WARNING"}
    """
    prefix = payload.get("prefix", "")
    module = payload.get("module", "")
    level_name = payload.get("level", "INFO").upper()
    level = _LEVEL_NAMES.get(level_name, 20)
    count = 0

    if module:
        logger = logging.getLogger(module)
        logger.setLevel(level)
        count = 1
    elif prefix:
        for name, logger in logging.getLogger().manager.loggerDict.items():
            if isinstance(logger, logging.Logger) and name.startswith(prefix):
                logger.setLevel(level)
                count += 1

    return {"changed": count, "level": level_name}


# ── T2: 日志搜索 ─────────────────────────────────────────────

def _parse_log_level(level_str: str) -> int:
    return _LEVEL_NAMES.get(level_str.upper(), 0)


def _match_log_entry(entry: dict, module_prefix: str, min_level: int,
                     keyword: str, since_ts: float, until_ts: float) -> bool:
    if module_prefix and not str(entry.get("module", "")).startswith(module_prefix):
        return False
    if min_level:
        entry_level = _parse_log_level(str(entry.get("level", "")))
        if entry_level < min_level:
            return False
    if keyword and keyword.lower() not in str(entry.get("event", "")).lower():
        return False
    ts = entry.get("timestamp")
    if ts and since_ts:
        try:
            entry_dt = datetime.fromisoformat(str(ts))
            if entry_dt.timestamp() < since_ts:
                return False
        except (ValueError, OSError):
            pass
    if ts and until_ts:
        try:
            entry_dt = datetime.fromisoformat(str(ts))
            if entry_dt.timestamp() > until_ts:
                return False
        except (ValueError, OSError):
            pass
    return True


def _read_jsonl_reverse(filepath: Path, limit: int) -> list[dict]:
    """倒序读取 JSONL 文件末尾 N 条。"""
    if not filepath.exists():
        return []
    results: list[dict] = []
    with open(filepath, "rb") as f:
        f.seek(0, os.SEEK_END)
        pos = f.tell()
        buf = b""
        while pos > 0 and len(results) < limit:
            chunk_size = min(4096, pos)
            pos -= chunk_size
            f.seek(pos)
            chunk = f.read(chunk_size)
            buf = chunk + buf
            lines = buf.split(b"\n")
            buf = lines.pop(0)
            for line in reversed(lines):
                if not line.strip():
                    continue
                try:
                    results.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
                if len(results) >= limit:
                    break
    return results


@router.get("/search")
async def search_logs(
    module: str = Query(""),
    level: str = Query(""),
    keyword: str = Query(""),
    since: str = Query(""),
    until: str = Query(""),
    limit: int = Query(100, ge=1, le=500),
) -> dict[str, Any]:
    """从 JSONL 日志文件倒序搜索。

    - module: 模块名前缀匹配
    - level: 最低日志级别 (DEBUG/INFO/WARNING/ERROR/CRITICAL)
    - keyword: event 字段包含的关键词
    - since/until: ISO 时间范围
    - limit: 返回最大条数 (默认 100, 最大 500)
    """
    min_level = _parse_log_level(level)
    since_ts = 0.0
    until_ts = 0.0
    try:
        if since:
            since_ts = datetime.fromisoformat(since).timestamp()
        if until:
            until_ts = datetime.fromisoformat(until).timestamp()
    except ValueError:
        pass

    log_files = sorted(
        _LOG_DIR.glob("maibot_*.log.jsonl"), key=os.path.getmtime, reverse=True,
    )
    results: list[dict] = []
    for fp in log_files:
        if len(results) >= limit:
            break
        entries = _read_jsonl_reverse(fp, limit * 2)
        for entry in entries:
            if _match_log_entry(entry, module, min_level, keyword, since_ts, until_ts):
                results.append(entry)
                if len(results) >= limit:
                    break

    return {"count": len(results), "results": results}


# ── T4: ThinkCycleLog 查询 ────────────────────────────────────


@router.get("/think-cycles")
async def get_think_cycles(
    agent_id: str = Query(""),
    action: str = Query(""),
    since: str = Query(""),
    until: str = Query(""),
    limit: int = Query(50, ge=1, le=200),
) -> dict[str, Any]:
    """查询 ThinkCycleLog 记录。

    - agent_id: 按智能体 ID 过滤
    - action: 按 ThinkAction 过滤
    - since/until: ISO 时间范围
    - limit: 返回最大条数
    """
    tc_files = sorted(
        _LOG_DIR.glob("think_cycles_*.log.jsonl"), key=os.path.getmtime, reverse=True,
    )
    results: list[dict] = []
    for fp in tc_files:
        if len(results) >= limit:
            break
        entries = _read_jsonl_reverse(fp, limit * 2)
        for entry in entries:
            if agent_id and entry.get("agent_id") != agent_id:
                continue
            if action and entry.get("action") != action:
                continue
            results.append(entry)
            if len(results) >= limit:
                break

    return {"count": len(results), "results": results}
