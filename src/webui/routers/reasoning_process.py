"""推理过程日志浏览接口。"""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from src.webui.dependencies import require_auth

router = APIRouter(prefix="/reasoning-process", tags=["reasoning-process"], dependencies=[Depends(require_auth)])

PROJECT_ROOT = Path(__file__).resolve().parents[3]
PROMPT_LOG_ROOT = (PROJECT_ROOT / "logs" / "maisaka_prompt").resolve()
ALLOWED_SUFFIXES = {".txt", ".html"}


class ReasoningPromptFile(BaseModel):
    """推理过程日志条目。"""

    stage: str
    session_id: str
    stem: str
    timestamp: int | None = None
    text_path: str | None = None
    html_path: str | None = None
    size: int = 0
    modified_at: float = 0


class ReasoningPromptListResponse(BaseModel):
    """推理过程日志列表响应。"""

    items: list[ReasoningPromptFile]
    total: int
    page: int
    page_size: int
    stages: list[str] = Field(default_factory=list)
    sessions: list[str] = Field(default_factory=list)
    selected_session: str = ""


class ReasoningPromptContentResponse(BaseModel):
    """推理过程文本内容响应。"""

    path: str
    content: str
    size: int
    modified_at: float


def _to_safe_relative_path(relative_path: str) -> Path:
    safe_path = Path(relative_path)
    if safe_path.is_absolute() or ".." in safe_path.parts:
        raise HTTPException(status_code=400, detail="路径不合法")
    return safe_path


def _resolve_prompt_log_path(relative_path: str, allowed_suffixes: set[str]) -> Path:
    safe_path = _to_safe_relative_path(relative_path)
    resolved_path = (PROMPT_LOG_ROOT / safe_path).resolve()

    try:
        resolved_path.relative_to(PROMPT_LOG_ROOT)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="路径不合法") from exc

    if resolved_path.suffix.lower() not in allowed_suffixes:
        raise HTTPException(status_code=400, detail="不支持的文件类型")
    if not resolved_path.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")

    return resolved_path


def _relative_posix_path(path: Path) -> str:
    return path.relative_to(PROMPT_LOG_ROOT).as_posix()


def _is_safe_name(name: str) -> bool:
    path = Path(name)
    return bool(name) and not path.is_absolute() and ".." not in path.parts and len(path.parts) == 1


def _list_stage_names() -> list[str]:
    if not PROMPT_LOG_ROOT.is_dir():
        return []

    return sorted(path.name for path in PROMPT_LOG_ROOT.iterdir() if path.is_dir() and _is_safe_name(path.name))


def _resolve_stage_name(stage: str) -> str:
    normalized_stage = str(stage or "").strip()
    if not normalized_stage or normalized_stage == "all":
        return "planner"
    if not _is_safe_name(normalized_stage):
        raise HTTPException(status_code=400, detail="阶段名称不合法")
    return normalized_stage


def _list_session_names(stage: str) -> list[str]:
    stage_dir = PROMPT_LOG_ROOT / stage
    if not stage_dir.is_dir():
        return []

    session_dirs = [path for path in stage_dir.iterdir() if path.is_dir() and _is_safe_name(path.name)]
    session_dirs.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return [path.name for path in session_dirs]


def _resolve_session_name(session: str, sessions: list[str]) -> str:
    normalized_session = str(session or "").strip()
    if not normalized_session or normalized_session in {"all", "auto"}:
        return sessions[0] if sessions else ""
    if not _is_safe_name(normalized_session):
        raise HTTPException(status_code=400, detail="会话名称不合法")
    return normalized_session if normalized_session in sessions else ""


def _collect_prompt_files(stage: str, session: str) -> list[ReasoningPromptFile]:
    session_dir = PROMPT_LOG_ROOT / stage / session
    if not session or not session_dir.is_dir():
        return []

    records: dict[tuple[str, str, str], dict[str, object]] = {}

    for file_path in session_dir.iterdir():
        if not file_path.is_file() or file_path.suffix.lower() not in ALLOWED_SUFFIXES:
            continue

        try:
            relative_path = file_path.relative_to(PROMPT_LOG_ROOT)
        except ValueError:
            continue

        parts = relative_path.parts
        if len(parts) < 3:
            continue

        stage_name, session_id = parts[0], parts[1]
        stem = file_path.stem
        key = (stage_name, session_id, stem)
        stat = file_path.stat()

        record = records.setdefault(
            key,
            {
                "stage": stage_name,
                "session_id": session_id,
                "stem": stem,
                "timestamp": int(stem) if stem.isdigit() else None,
                "text_path": None,
                "html_path": None,
                "size": 0,
                "modified_at": 0.0,
            },
        )
        record["size"] = int(record["size"]) + stat.st_size
        record["modified_at"] = max(float(record["modified_at"]), stat.st_mtime)

        if file_path.suffix.lower() == ".txt":
            record["text_path"] = _relative_posix_path(file_path)
        elif file_path.suffix.lower() == ".html":
            record["html_path"] = _relative_posix_path(file_path)

    items = [ReasoningPromptFile(**record) for record in records.values()]
    items.sort(key=lambda item: (item.modified_at, item.timestamp or 0), reverse=True)
    return items


@router.get("/files", response_model=ReasoningPromptListResponse)
async def list_reasoning_prompt_files(
    stage: str = Query("planner"),
    session: str = Query("auto"),
    search: str = Query(""),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=10, le=200),
):
    """列出 logs/maisaka_prompt 下的推理过程日志。"""

    stages = _list_stage_names()
    selected_stage = _resolve_stage_name(stage)
    sessions = _list_session_names(selected_stage)
    selected_session = _resolve_session_name(session, sessions)
    items = _collect_prompt_files(selected_stage, selected_session)
    normalized_search = search.strip().lower()

    if normalized_search:
        items = [
            item
            for item in items
            if normalized_search in item.stage.lower()
            or normalized_search in item.session_id.lower()
            or normalized_search in item.stem.lower()
        ]

    total = len(items)
    start = (page - 1) * page_size
    end = start + page_size

    return ReasoningPromptListResponse(
        items=items[start:end],
        total=total,
        page=page,
        page_size=page_size,
        stages=stages,
        sessions=sessions,
        selected_session=selected_session,
    )


@router.get("/file", response_model=ReasoningPromptContentResponse)
async def get_reasoning_prompt_file(path: str = Query(...)):
    """读取推理过程 txt 日志内容。"""

    file_path = _resolve_prompt_log_path(path, {".txt"})
    stat = file_path.stat()

    return ReasoningPromptContentResponse(
        path=_relative_posix_path(file_path),
        content=file_path.read_text(encoding="utf-8", errors="replace"),
        size=stat.st_size,
        modified_at=stat.st_mtime,
    )


@router.get("/html")
async def get_reasoning_prompt_html(path: str = Query(...)):
    """预览推理过程 html 日志内容。"""

    file_path = _resolve_prompt_log_path(path, {".html"})
    return FileResponse(
        file_path,
        media_type="text/html; charset=utf-8",
        headers={"X-Robots-Tag": "noindex, nofollow"},
    )
