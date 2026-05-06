"""
系统控制路由

提供系统重启、状态查询等功能
"""

from datetime import datetime
from importlib.metadata import PackageNotFoundError, version as get_package_version
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import httpx
import os
import time

from src.common.logger import get_logger
from src.config.config import MMC_VERSION
from src.webui.dependencies import require_auth

router = APIRouter(prefix="/system", tags=["system"], dependencies=[Depends(require_auth)])
logger = get_logger("webui_system")

# 记录启动时间
_start_time = time.time()
_DASHBOARD_PACKAGE_NAME = "maibot-dashboard"
_PYPI_JSON_URL = f"https://pypi.org/pypi/{_DASHBOARD_PACKAGE_NAME}/json"
_PYPI_CACHE_TTL_SECONDS = 60 * 60 * 6
_pypi_version_cache: Dict[str, Any] = {"checked_at": 0.0, "latest_version": None}


class RestartResponse(BaseModel):
    """重启响应"""

    success: bool
    message: str


class StatusResponse(BaseModel):
    """状态响应"""

    running: bool
    uptime: float
    version: str
    start_time: str


class DashboardVersionResponse(BaseModel):
    """WebUI 版本检查响应"""

    current_version: str
    latest_version: Optional[str] = None
    has_update: bool = False
    package_name: str = _DASHBOARD_PACKAGE_NAME
    pypi_url: str = f"https://pypi.org/project/{_DASHBOARD_PACKAGE_NAME}/"


def _get_installed_dashboard_version() -> str:
    try:
        return get_package_version(_DASHBOARD_PACKAGE_NAME)
    except PackageNotFoundError:
        return "unknown"


def _normalize_version(version: str) -> tuple[int, ...]:
    clean_version = version.strip().lower().removeprefix("v")
    numeric_part = clean_version.split("-", 1)[0].split("+", 1)[0]
    parts = []
    for item in numeric_part.split("."):
        number = ""
        for char in item:
            if not char.isdigit():
                break
            number += char
        parts.append(int(number) if number else 0)
    return tuple(parts)


def _is_newer_version(latest_version: Optional[str], current_version: str) -> bool:
    if not latest_version or not current_version or current_version == "unknown":
        return False

    latest_parts = _normalize_version(latest_version)
    current_parts = _normalize_version(current_version)
    width = max(len(latest_parts), len(current_parts))
    return latest_parts + (0,) * (width - len(latest_parts)) > current_parts + (0,) * (width - len(current_parts))


async def _get_latest_dashboard_version_from_pypi() -> Optional[str]:
    now = time.time()
    cached_version = _pypi_version_cache.get("latest_version")
    checked_at = float(_pypi_version_cache.get("checked_at", 0.0))
    if cached_version and now - checked_at < _PYPI_CACHE_TTL_SECONDS:
        return str(cached_version)

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(_PYPI_JSON_URL)
            response.raise_for_status()
            payload = response.json()
    except Exception as e:
        logger.debug(f"检查 WebUI PyPI 版本失败: {e}")
        return str(cached_version) if cached_version else None

    latest_version = payload.get("info", {}).get("version")
    if isinstance(latest_version, str) and latest_version.strip():
        _pypi_version_cache["checked_at"] = now
        _pypi_version_cache["latest_version"] = latest_version.strip()
        return latest_version.strip()

    return str(cached_version) if cached_version else None


@router.post("/restart", response_model=RestartResponse)
async def restart_maibot():
    """
    重启麦麦主程序

    请求重启当前进程，配置更改将在重启后生效。
    注意：此操作会使麦麦暂时离线。
    """
    import asyncio

    try:
        # 记录重启操作
        logger.info("WebUI 触发重启操作")

        # 定义延迟重启的异步任务
        async def delayed_restart():
            await asyncio.sleep(0.5)  # 延迟0.5秒，确保响应已发送
            # 使用 os._exit(42) 退出当前进程，配合外部 runner 脚本进行重启
            # 42 是约定的重启状态码
            logger.info("WebUI 请求重启，退出代码 42")
            os._exit(42)

        # 创建后台任务执行重启
        asyncio.create_task(delayed_restart())

        # 立即返回成功响应
        return RestartResponse(success=True, message="麦麦正在重启中...")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"重启失败: {str(e)}") from e


@router.get("/status", response_model=StatusResponse)
async def get_maibot_status():
    """
    获取麦麦运行状态

    返回麦麦的运行状态、运行时长和版本信息。
    """
    try:
        uptime = time.time() - _start_time

        # 尝试获取版本信息（需要根据实际情况调整）
        version = MMC_VERSION  # 可以从配置或常量中读取

        return StatusResponse(
            running=True, uptime=uptime, version=version, start_time=datetime.fromtimestamp(_start_time).isoformat()
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取状态失败: {str(e)}") from e


@router.get("/dashboard-version", response_model=DashboardVersionResponse)
async def get_dashboard_version(current_version: Optional[str] = None):
    """获取 WebUI 当前版本和 PyPI 最新版本。"""
    resolved_current_version = current_version or _get_installed_dashboard_version()
    latest_version = await _get_latest_dashboard_version_from_pypi()

    return DashboardVersionResponse(
        current_version=resolved_current_version,
        latest_version=latest_version,
        has_update=_is_newer_version(latest_version, resolved_current_version),
    )


# 可选：添加更多系统控制功能


@router.post("/reload-config")
async def reload_config():
    """
    热重载配置（不重启进程）

    仅重新加载配置文件，某些配置可能需要重启才能生效。
    此功能需要在主程序中实现配置热重载逻辑。
    """
    # 这里需要调用主程序的配置重载函数
    # 示例：await app_instance.reload_config()

    return {"success": True, "message": "配置重载功能待实现"}
