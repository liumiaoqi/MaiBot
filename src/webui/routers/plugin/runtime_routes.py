"""插件运行时相关 WebUI 路由。"""

from typing import Optional

from fastapi import APIRouter, Cookie

from src.plugin_runtime.component_query import component_query_service

from .schemas import HookSpecListResponse, HookSpecResponse
from .support import require_plugin_token

router = APIRouter()


@router.get("/runtime/hooks", response_model=HookSpecListResponse)
async def list_runtime_hook_specs(maibot_session: Optional[str] = Cookie(None)) -> HookSpecListResponse:
    """返回当前插件运行时公开的 Hook 规格清单。

    Args:
        maibot_session: 当前 WebUI 会话令牌。

    Returns:
        HookSpecListResponse: Hook 规格列表响应。
    """

    require_plugin_token(maibot_session)
    hooks = [HookSpecResponse(**hook_data) for hook_data in component_query_service.list_hook_specs()]
    return HookSpecListResponse(success=True, hooks=hooks)
