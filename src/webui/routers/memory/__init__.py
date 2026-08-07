"""memory 路由包。

将 7 个功能域子 router 聚合为 ``router``，同时导出 ``compat_router``。
聚合后主 router 保持 prefix="/memory" 不变。

兼容性导出：T5 拆分后，pytests/webui/test_memory_routes.py 仍通过
``memory_router_module.xxx`` 访问 12 个内部符号。此处 re-export 保持向后兼容，
pytests 迁移完成后应移除本块。
"""

from fastapi import APIRouter

from src.webui.routers.memory.delete import router as delete_router
from src.webui.routers.memory.episode import router as episode_router
from src.webui.routers.memory.graph import router as graph_router
from src.webui.routers.memory.import_ import router as import_router
from src.webui.routers.memory.maintenance import router as maintenance_router
from src.webui.routers.memory.profile import router as profile_router
from src.webui.routers.memory.tuning import router as tuning_router

# 聚合子 router：7 个功能域子 router，各子 router 已有 prefix="/memory"
router = APIRouter()
router.include_router(graph_router)
router.include_router(episode_router)
router.include_router(profile_router)
router.include_router(import_router)
router.include_router(tuning_router)
router.include_router(maintenance_router)
router.include_router(delete_router)

# compat_router 保留 /api 前缀兼容层
from src.webui.routers.memory.compat import compat_router  # noqa: E402

# ── pytests 向后兼容导出 ──────────────────────────────────────────────
# T5 拆分后符号分散到子 router / memory_helpers / memory_helper_service_web，
# pytests/webui/test_memory_routes.py 仍通过 memory_router_module.xxx 访问。
from pathlib import Path  # noqa: E402

from src.common.database.database import get_db_session  # noqa: E402
from src.person_info.person_info import resolve_person_id_for_memory  # noqa: E402
from src.services.memory_service import memory_service  # noqa: E402
from src.webui.routers.memory.import_ import STAGING_ROOT  # noqa: E402
from src.webui.routers.memory.profile import _profile_list  # noqa: E402
from src.webui.routers.memory_helpers import (  # noqa: E402
    _metadata_matches_chat,
    _query_memory_rows,
)
from src.webui.services.memory_helper_service_web import (  # noqa: E402
    _find_real_chat_session,
    _get_person_name_for_person_id,
    _get_session_name_via_port,
    _prefetch_latest_messages_by_session,
    get_existing_session_info,
)

__all__ = [
    "router",
    "compat_router",
    # pytests 兼容
    "Path",
    "STAGING_ROOT",
    "_find_real_chat_session",
    "_get_person_name_for_person_id",
    "_get_session_name_via_port",
    "_metadata_matches_chat",
    "_prefetch_latest_messages_by_session",
    "_profile_list",
    "_query_memory_rows",
    "get_db_session",
    "get_existing_session_info",
    "memory_service",
    "resolve_person_id_for_memory",
]
