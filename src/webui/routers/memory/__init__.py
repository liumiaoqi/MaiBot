"""memory ??????

? 7 ????? router ????? `router`???? `compat_router`?
?????????? router ?? prefix="/memory"??
"""

from fastapi import APIRouter

from src.webui.routers.memory.delete import router as delete_router
from src.webui.routers.memory.episode import router as episode_router
from src.webui.routers.memory.graph import router as graph_router
from src.webui.routers.memory.import_ import router as import_router
from src.webui.routers.memory.maintenance import router as maintenance_router
from src.webui.routers.memory.profile import router as profile_router
from src.webui.routers.memory.tuning import router as tuning_router

# ? router??? 7 ????? router??? router ?? prefix="/memory"?
router = APIRouter()
router.include_router(graph_router)
router.include_router(episode_router)
router.include_router(profile_router)
router.include_router(import_router)
router.include_router(tuning_router)
router.include_router(maintenance_router)
router.include_router(delete_router)

# compat_router??? /api ??????
from src.webui.routers.memory.compat import compat_router  # noqa: E402

__all__ = ["router", "compat_router"]
