"""WebUI API 路由"""

from fastapi import APIRouter, Depends, Request, Response

from src.common.logger import get_logger
from src.webui.core import (
    check_auth_rate_limit,
    clear_auth_cookie,
    get_rate_limiter,
    get_token_manager,
    set_auth_cookie,
)
from src.webui.dependencies import require_auth, verify_token_optional
from src.webui.errors import AppError
from src.webui.errors.codes import ErrorCode
from src.webui.routers.avatar import router as avatar_router
from src.webui.routers.agent import router as agent_router
from src.webui.routers.deepseek import router as deepseek_router
from src.webui.routers.behavior import router as behavior_router
from src.webui.routers.config import router as config_router
from src.webui.routers.emoji import router as emoji_router
from src.webui.routers.expression import router as expression_router
from src.webui.routers.jargon import router as jargon_router
from src.webui.routers.memory import router as memory_router
from src.webui.routers.model import router as model_router
from src.webui.routers.person import router as person_router
from src.webui.routers.plugin import router as plugin_router
from src.webui.routers.reasoning_process import router as reasoning_process_router
from src.webui.routers.statistics import router as statistics_router
from src.webui.routers.system import router as system_router
from src.webui.routers.websocket.auth import router as ws_auth_router
from src.webui.routers.websocket.unified import router as unified_ws_router
from src.webui.schemas.auth import (
    CompleteSetupResponse,
    FirstSetupStatusResponse,
    ResetSetupResponse,
    TokenRegenerateResponse,
    TokenUpdateRequest,
    TokenUpdateResponse,
    TokenVerifyRequest,
    TokenVerifyResponse,
)
from src.webui.schemas.base import ApiResponse

logger = get_logger("webui.api")

# 创建路由器
router = APIRouter(prefix="/api/webui", tags=["WebUI"])

# 注册智能体管理路由
router.include_router(agent_router)

# 注册 DeepSeek 优化面板路由
router.include_router(deepseek_router)
# 注册配置管理路由
router.include_router(config_router)
# 注册统计数据路由
router.include_router(statistics_router)
# 注册人物信息管理路由
router.include_router(person_router)
# 注册表达方式管理路由
router.include_router(expression_router)
# 注册黑话管理路由
router.include_router(jargon_router)
# 注册表情包管理路由
router.include_router(behavior_router)
router.include_router(emoji_router)
router.include_router(avatar_router)
# 注册插件管理路由
router.include_router(plugin_router)
# 注册系统控制路由
router.include_router(system_router)
router.include_router(reasoning_process_router)
# 注册模型列表获取路由
router.include_router(model_router)
# 注册长期记忆管理路由
router.include_router(memory_router)
# 注册 WebSocket 认证路由
router.include_router(ws_auth_router)
# 注册统一 WebSocket 路由
router.include_router(unified_ws_router)



@router.get("/health", response_model=ApiResponse[dict])
async def health_check():
    """健康检查"""
    return ApiResponse(data={"status": "healthy", "service": "MaiBot WebUI"})


@router.post("/auth/verify", response_model=ApiResponse[TokenVerifyResponse])
async def verify_token(
    request_body: TokenVerifyRequest,
    request: Request,
    response: Response,
    _rate_limit: None = Depends(check_auth_rate_limit),
):
    """验证访问令牌，验证成功后设置 HttpOnly Cookie"""
    token_manager = get_token_manager()
    rate_limiter = get_rate_limiter()

    is_valid = token_manager.verify_token(request_body.token)

    if is_valid:
        rate_limiter.reset_failures(request)
        set_auth_cookie(response, request_body.token, request)
        is_first_setup = token_manager.is_first_setup()
        return ApiResponse(data=TokenVerifyResponse(valid=True, message="Token 验证成功", is_first_setup=is_first_setup))

    blocked, remaining = rate_limiter.record_failed_attempt(
        request,
        max_failures=5,
        window_seconds=300,
        block_duration=600,
    )

    if blocked:
        raise AppError(ErrorCode.AUTH_RATE_LIMITED, "认证失败次数过多，您的 IP 已被临时封禁 10 分钟")

    message = "Token 无效或已过期"
    if remaining <= 2:
        message += f"（剩余 {remaining} 次尝试机会）"

    return ApiResponse(data=TokenVerifyResponse(valid=False, message=message))


@router.post("/auth/logout", response_model=ApiResponse[dict])
async def logout(response: Response):
    """登出并清除认证 Cookie"""
    clear_auth_cookie(response)
    return ApiResponse(data={"success": True}, message="已成功登出")


@router.get("/auth/check", response_model=ApiResponse[dict])
async def check_auth_status(
    authenticated: bool = Depends(verify_token_optional),
):
    """检查当前认证状态"""
    return ApiResponse(data={"authenticated": authenticated})


@router.post("/auth/update", response_model=ApiResponse[TokenUpdateResponse], dependencies=[Depends(require_auth)])
async def update_token(
    request: TokenUpdateRequest,
    response: Response,
):
    """更新访问令牌"""
    token_manager = get_token_manager()
    success, message = token_manager.update_token(request.new_token)
    if success:
        clear_auth_cookie(response)
    return ApiResponse(data=TokenUpdateResponse(success=success, message=message))


@router.post("/auth/regenerate", response_model=ApiResponse[TokenRegenerateResponse], dependencies=[Depends(require_auth)])
async def regenerate_token(
    response: Response,
):
    """重新生成访问令牌"""
    token_manager = get_token_manager()
    new_token = token_manager.regenerate_token()
    clear_auth_cookie(response)
    return ApiResponse(data=TokenRegenerateResponse(success=True, token=new_token, message="Token 已重新生成"))


@router.get("/setup/status", response_model=ApiResponse[FirstSetupStatusResponse], dependencies=[Depends(require_auth)])
async def get_setup_status():
    """获取首次配置状态"""
    token_manager = get_token_manager()
    is_first = token_manager.is_first_setup()
    return ApiResponse(data=FirstSetupStatusResponse(is_first_setup=is_first, message="首次配置" if is_first else "已完成配置"))


@router.post("/setup/complete", response_model=ApiResponse[CompleteSetupResponse], dependencies=[Depends(require_auth)])
async def complete_setup():
    """标记首次配置完成"""
    token_manager = get_token_manager()
    success = token_manager.mark_setup_completed()
    return ApiResponse(data=CompleteSetupResponse(success=success, message="配置已完成" if success else "标记失败"))


@router.post("/setup/reset", response_model=ApiResponse[ResetSetupResponse], dependencies=[Depends(require_auth)])
async def reset_setup():
    """重置首次配置状态"""
    token_manager = get_token_manager()
    success = token_manager.reset_setup_status()
    return ApiResponse(data=ResetSetupResponse(success=success, message="配置状态已重置" if success else "重置失败"))
