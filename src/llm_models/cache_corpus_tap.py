"""缓存语料**只读采集点**（cache-tap，2026-10-16）。

三条硬约束（挂/撤都靠它们）：

1. **默认关闭**：仅当环境变量 ``MAIBOT_CACHE_CORPUS_DIR`` 设成**绝对路径**时才落盘；
   不设 ⇒ 函数立即返回，**零副作用**（不建目录、不写文件）。⇒ 撤销 = 删本文件 +
   `adapter_base.py` 的两处（import 与调用）+ 重启，不必赶时间。
2. **只读**：把**已经渲染好的**请求原样落成段形状，**不改任何提示内容、顺序、字段**
   ——采到的必须是"现在真跑的东西"。
3. **落盘在仓外**：变量给什么路径就写哪里（约定 ``C:\\hub\\.scratch\\cache-corpus\\``）；
   ⛔ 不许落进仓内 ``logs/`` 或 ``data/``（那两个刚清干净）。

落盘形状 = ``tests/unit/prompt_cache/lcp_probe.py`` 的语料模式直接可读：
``{session_id, captured_at, system_prompt, tools, messages:[{role, content}]}``。
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from src.common.logger import get_logger

logger = get_logger("llm_models.cache_corpus_tap")

ENV_VAR = "MAIBOT_CACHE_CORPUS_DIR"
"""采集目录（绝对路径）。未设/非绝对路径 ⇒ 采集关闭。"""


def corpus_dir() -> Path | None:
    """返回采集目录；未开启返回 ``None``（非绝对路径也视为未开启，防止落进仓内相对目录）。"""
    raw = os.environ.get(ENV_VAR, "").strip()
    if not raw:
        return None
    path = Path(raw)
    return path if path.is_absolute() else None


def record_response_request(request: Any) -> None:
    """把一份**已渲染**的请求落盘；未开启采集时立即返回。

    :param request: ``ResponseRequest``（读 ``message_list`` / ``tool_options`` / ``extra_params``）。
    """
    directory = corpus_dir()
    if directory is None:
        return

    try:
        payload = _to_corpus_payload(request)
        directory.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        (directory / f"{stamp}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as exc:
        # 采集是旁路：失败绝不影响真实请求，但必须出声（logger + 上报，双通道）
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port

        port = get_error_escalation_port()
        if port is not None:
            port.report(ErrorLevel.WARNING, "缓存语料采集失败（不影响请求）", exception=exc)
        logger.warning("缓存语料采集失败（不影响请求）: %s", exc)


def _to_corpus_payload(request: Any) -> dict[str, Any]:
    """请求 → 段形状（system / tools / messages）。只读，不触碰原对象。"""
    messages = list(getattr(request, "message_list", None) or [])
    system_prompt = ""
    rest: list[dict[str, str]] = []
    for index, message in enumerate(messages):
        role = str(getattr(message, "role", "") or "")
        text = _message_text(message)
        # 首条 system 视作前缀段；其余按 msg[i] 顺次落
        if index == 0 and role == "system" and not system_prompt:
            system_prompt = text
            continue
        rest.append({"role": role, "content": text})

    extra_params = getattr(request, "extra_params", None) or {}
    session_id = ""
    if isinstance(extra_params, dict):
        session_id = str(extra_params.get("session_id") or extra_params.get("stream_id") or "")

    return {
        "session_id": session_id,
        "request_kind": _request_kind(request),
        "captured_at": datetime.now().isoformat(timespec="milliseconds"),
        "system_prompt": system_prompt,
        "tools": _tools_payload(getattr(request, "tool_options", None)),
        "messages": rest,
    }


def _request_kind(request: Any) -> str:
    """任务标识（探针按它分组——跨任务比 LCP 没有意义）。

    来源与仓内既有口径**同源**：`serialize_response_request_snapshot(request)['request_kind']`
    （失败快照就用这个名字，见 `src/llm_models/request_snapshot.py:457`）；取不到退回
    `request.extra_params['request_kind']`；再取不到就**空串**（宁可空，不编造）。
    """
    try:
        from src.llm_models.request_snapshot import serialize_response_request_snapshot

        return str(serialize_response_request_snapshot(request).get("request_kind") or "")
    except Exception:
        extra_params = getattr(request, "extra_params", None) or {}
        if isinstance(extra_params, dict):
            return str(extra_params.get("request_kind") or "")
        return ""


def _message_text(message: Any) -> str:
    """取消息文本（优先用仓内既有序列化器；失败退回 str，只读不改）。"""
    try:
        from src.llm_models.request_snapshot import serialize_message_snapshot

        serialized = serialize_message_snapshot(message)
        return json.dumps(serialized, ensure_ascii=False, default=str)
    except Exception:
        return str(message)


def _tools_payload(tool_options: Any) -> Any:
    """工具 schema（优先既有序列化器；失败退回字符串列表）。"""
    if not tool_options:
        return []
    try:
        from src.llm_models.request_snapshot import serialize_tool_options_snapshot

        return serialize_tool_options_snapshot(tool_options)
    except Exception:
        return [str(item) for item in tool_options]
