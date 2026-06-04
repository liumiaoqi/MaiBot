"""Maisaka favourite pool storage helpers."""

from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any, Optional
from PIL import Image as PILImage

import base64
import hashlib
import json
import re
import uuid

from src.common.logger import get_logger

logger = get_logger("maisaka_favourite_storage")

FAVOURITE_ROOT = Path(__file__).parent.parent.parent / "data" / "favourite"
MANIFEST_FILENAME = "manifest.json"
MANIFEST_VERSION = 1
SHARED_POOL_KEY = "share"
POOL_SAFE_PATTERN = re.compile(r"[^0-9A-Za-z._-]+")
INVALID_FILENAME_CHARS = set('<>:"/\\|?*\0')
WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}
TEXT_MIME_TYPE = "text/plain; charset=utf-8"


class FavouriteStorageError(Exception):
    """收藏池操作失败。"""


@dataclass(frozen=True)
class FavouritePool:
    """收藏池路径信息。"""

    key: str
    chat_id: str
    directory: Path
    isolated_by_chat: bool


@dataclass(frozen=True)
class FavouriteSaveResult:
    """收藏内容写入结果。"""

    pool: FavouritePool
    item: dict[str, Any]
    file_path: Path


@dataclass(frozen=True)
class FavouriteResolvedItem:
    """已从收藏池解析出的内容。"""

    pool: FavouritePool
    item: dict[str, Any]
    file_path: Path


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _get_isolated_by_chat_config() -> bool:
    try:
        from src.config.config import global_config
    except Exception as exc:
        logger.warning(f"读取 favourite 配置失败，已使用共享收藏池: {exc}")
        return False

    favourite_config = getattr(global_config, "favourite", None)
    return bool(getattr(favourite_config, "isolate_by_chat", False))


def _normalize_pool_key(chat_id: str) -> str:
    normalized_chat_id = str(chat_id or "").strip()
    if not normalized_chat_id:
        raise FavouriteStorageError("当前聊天 ID 为空，无法使用按聊天隔离的收藏池。")

    safe_name = POOL_SAFE_PATTERN.sub("_", normalized_chat_id).strip("._")
    if not safe_name:
        safe_name = "unknown_chat"
    if safe_name == normalized_chat_id and len(safe_name) <= 80:
        return safe_name

    digest = hashlib.sha1(normalized_chat_id.encode("utf-8")).hexdigest()[:8]
    return f"{safe_name[:80].strip('._') or 'chat'}_{digest}"


def resolve_current_pool(chat_id: str) -> FavouritePool:
    """根据配置解析当前聊天应使用的收藏池。"""

    isolated_by_chat = _get_isolated_by_chat_config()
    normalized_chat_id = str(chat_id or "").strip()
    if isolated_by_chat:
        pool_key = _normalize_pool_key(normalized_chat_id)
        pool_chat_id = normalized_chat_id
    else:
        pool_key = SHARED_POOL_KEY
        pool_chat_id = ""
    return FavouritePool(
        key=pool_key,
        chat_id=pool_chat_id,
        directory=(FAVOURITE_ROOT / pool_key).resolve(),
        isolated_by_chat=isolated_by_chat,
    )


def _build_manifest(pool: FavouritePool, items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "version": MANIFEST_VERSION,
        "pool": pool.key,
        "chat_id": pool.chat_id,
        "isolated_by_chat": pool.isolated_by_chat,
        "updated_at": _now_iso(),
        "items": items,
    }


def _manifest_path(pool: FavouritePool) -> Path:
    return pool.directory / MANIFEST_FILENAME


def _load_manifest(pool: FavouritePool) -> dict[str, Any]:
    manifest_path = _manifest_path(pool)
    if not manifest_path.exists():
        return _build_manifest(pool, [])

    try:
        with manifest_path.open("r", encoding="utf-8") as handle:
            raw_manifest = json.load(handle)
    except Exception as exc:
        raise FavouriteStorageError(f"读取收藏索引失败：{manifest_path}，原因：{exc}") from exc

    if isinstance(raw_manifest, list):
        return _build_manifest(pool, [item for item in raw_manifest if isinstance(item, dict)])
    if not isinstance(raw_manifest, dict):
        raise FavouriteStorageError(f"收藏索引格式无效：{manifest_path}")

    raw_items = raw_manifest.get("items", [])
    items = [item for item in raw_items if isinstance(item, dict)] if isinstance(raw_items, list) else []
    manifest = _build_manifest(pool, items)
    if isinstance(raw_manifest.get("chat_id"), str):
        manifest["chat_id"] = raw_manifest["chat_id"]
    if isinstance(raw_manifest.get("isolated_by_chat"), bool):
        manifest["isolated_by_chat"] = raw_manifest["isolated_by_chat"]
    return manifest


def _write_manifest(pool: FavouritePool, manifest: dict[str, Any]) -> None:
    pool.directory.mkdir(parents=True, exist_ok=True)
    manifest_path = _manifest_path(pool)
    temp_path = manifest_path.with_suffix(f"{manifest_path.suffix}.tmp")
    try:
        with temp_path.open("w", encoding="utf-8") as handle:
            json.dump(manifest, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        temp_path.replace(manifest_path)
    except Exception as exc:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)
        raise FavouriteStorageError(f"写入收藏索引失败：{manifest_path}，原因：{exc}") from exc


def _validate_filename(filename: str, *, default_suffix: str) -> str:
    normalized_filename = str(filename or "").strip()
    if not normalized_filename:
        raise FavouriteStorageError("需要提供文件名。")
    if normalized_filename in {".", ".."}:
        raise FavouriteStorageError("文件名无效。")
    if normalized_filename.endswith((" ", ".")):
        raise FavouriteStorageError("文件名不能以空格或点号结尾。")
    if any(char in INVALID_FILENAME_CHARS for char in normalized_filename):
        raise FavouriteStorageError("文件名不能包含路径分隔符或 Windows 保留字符。")

    path = Path(normalized_filename)
    if path.name != normalized_filename:
        raise FavouriteStorageError("文件名不能包含路径。")

    stem_upper = path.stem.upper()
    if stem_upper in WINDOWS_RESERVED_NAMES:
        raise FavouriteStorageError(f"文件名使用了 Windows 保留名称：{path.stem}")
    if normalized_filename.casefold() == MANIFEST_FILENAME.casefold():
        raise FavouriteStorageError(f"{MANIFEST_FILENAME} 是收藏池索引文件，不能作为收藏内容文件名。")

    if not path.suffix and default_suffix:
        normalized_filename = f"{normalized_filename}{default_suffix}"
    return normalized_filename


def _ensure_unique_name(pool: FavouritePool, manifest: dict[str, Any], filename: str) -> Path:
    existing_names = {
        str(item.get("name") or "").casefold()
        for item in manifest.get("items", [])
        if isinstance(item, dict)
    }
    if filename.casefold() in existing_names:
        raise FavouriteStorageError(f"收藏内容重名：{filename}。请换一个文件名。")

    target_path = (pool.directory / filename).resolve()
    try:
        target_path.relative_to(pool.directory.resolve())
    except ValueError as exc:
        raise FavouriteStorageError("文件名解析到了收藏池之外，已拒绝保存。") from exc
    if target_path.exists():
        raise FavouriteStorageError(f"收藏文件已存在：{filename}。请换一个文件名。")
    return target_path


def _build_content_id(existing_items: list[dict[str, Any]]) -> str:
    existing_ids = {str(item.get("id") or "") for item in existing_items if isinstance(item, dict)}
    for _ in range(10):
        content_id = uuid.uuid4().hex[:12]
        if content_id not in existing_ids:
            return content_id
    raise FavouriteStorageError("生成收藏内容 ID 失败，请稍后重试。")


def _public_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(item.get("id") or ""),
        "name": str(item.get("name") or ""),
        "description": str(item.get("description") or ""),
        "format": str(item.get("format") or ""),
        "size": int(item.get("size") or 0),
        "content_type": str(item.get("content_type") or ""),
        "created_at": str(item.get("created_at") or ""),
    }


def _save_bytes(
    *,
    chat_id: str,
    filename: str,
    description: str,
    content_type: str,
    data: bytes,
    mime_type: str,
    default_suffix: str,
    source: Optional[dict[str, Any]] = None,
) -> FavouriteSaveResult:
    normalized_description = str(description or "").strip()
    if not normalized_description:
        raise FavouriteStorageError("需要提供简略描述。")
    if not data:
        raise FavouriteStorageError("收藏内容为空，无法保存。")

    pool = resolve_current_pool(chat_id)
    pool.directory.mkdir(parents=True, exist_ok=True)
    manifest = _load_manifest(pool)
    items = list(manifest.get("items", []))
    normalized_filename = _validate_filename(filename, default_suffix=default_suffix)
    target_path = _ensure_unique_name(pool, manifest, normalized_filename)

    content_id = _build_content_id(items)
    item = {
        "id": content_id,
        "name": normalized_filename,
        "description": normalized_description,
        "format": str(mime_type or "").strip() or "application/octet-stream",
        "size": len(data),
        "content_type": str(content_type or "").strip() or "binary",
        "file": normalized_filename,
        "created_at": _now_iso(),
        "source": dict(source or {}),
    }

    try:
        with target_path.open("xb") as handle:
            handle.write(data)
        items.append(item)
        manifest = _build_manifest(pool, items)
        _write_manifest(pool, manifest)
    except FavouriteStorageError:
        if target_path.exists():
            target_path.unlink(missing_ok=True)
        raise
    except FileExistsError as exc:
        raise FavouriteStorageError(f"收藏文件已存在：{normalized_filename}。请换一个文件名。") from exc
    except Exception as exc:
        if target_path.exists():
            target_path.unlink(missing_ok=True)
        raise FavouriteStorageError(f"保存收藏内容失败：{exc}") from exc

    return FavouriteSaveResult(pool=pool, item=_public_item(item), file_path=target_path)


def save_text_content(
    *,
    chat_id: str,
    filename: str,
    description: str,
    text: str,
) -> FavouriteSaveResult:
    """保存文本收藏内容。"""

    normalized_text = str(text or "")
    if not normalized_text.strip():
        raise FavouriteStorageError("需要提供要保存的文本内容。")
    return _save_bytes(
        chat_id=chat_id,
        filename=filename,
        description=description,
        content_type="text",
        data=normalized_text.encode("utf-8"),
        mime_type=TEXT_MIME_TYPE,
        default_suffix=".txt",
    )


def detect_image_mime_type(image_data: bytes, filename: str = "") -> tuple[str, str]:
    """识别图片格式，返回文件后缀和 MIME。"""

    try:
        with PILImage.open(BytesIO(image_data)) as image:
            image_format = (image.format or "").lower()
    except Exception:
        image_format = ""

    if image_format == "jpeg":
        image_format = "jpg"
    if not image_format:
        suffix = Path(str(filename or "")).suffix.lower().lstrip(".")
        image_format = suffix or "png"

    mime_suffix = "jpeg" if image_format == "jpg" else image_format
    return f".{image_format}", f"image/{mime_suffix}"


def save_image_content(
    *,
    chat_id: str,
    filename: str,
    description: str,
    image_data: bytes,
    source: Optional[dict[str, Any]] = None,
) -> FavouriteSaveResult:
    """保存图片收藏内容。"""

    default_suffix, mime_type = detect_image_mime_type(image_data, filename)
    return _save_bytes(
        chat_id=chat_id,
        filename=filename,
        description=description,
        content_type="image",
        data=image_data,
        mime_type=mime_type,
        default_suffix=default_suffix,
        source=source,
    )


def _match_item(item: dict[str, Any], query: str) -> bool:
    normalized_query = str(query or "").strip().casefold()
    if not normalized_query:
        return True
    name = str(item.get("name") or "").casefold()
    description = str(item.get("description") or "").casefold()
    return normalized_query in name or normalized_query in description


def browse_current_pool(*, chat_id: str, query: str = "", page: int = 1, page_size: int = 10) -> dict[str, Any]:
    """分页浏览当前配置对应的收藏池。"""

    pool = resolve_current_pool(chat_id)
    manifest = _load_manifest(pool)
    matched_items = [_public_item(item) for item in manifest.get("items", []) if _match_item(item, query)]
    matched_items.sort(key=lambda item: item.get("created_at") or "", reverse=True)

    safe_page_size = min(50, max(1, int(page_size)))
    safe_page = max(1, int(page))
    total = len(matched_items)
    total_pages = max(1, (total + safe_page_size - 1) // safe_page_size)
    start_index = (safe_page - 1) * safe_page_size
    end_index = start_index + safe_page_size
    page_items = matched_items[start_index:end_index]
    return {
        "pool": {
            "key": pool.key,
            "chat_id": pool.chat_id,
            "isolated_by_chat": pool.isolated_by_chat,
        },
        "query": str(query or "").strip(),
        "page": safe_page,
        "page_size": safe_page_size,
        "total": total,
        "total_pages": total_pages,
        "items": page_items,
    }


def _iter_existing_pools() -> list[FavouritePool]:
    if not FAVOURITE_ROOT.exists():
        return []

    pools: list[FavouritePool] = []
    for directory in FAVOURITE_ROOT.iterdir():
        if not directory.is_dir():
            continue
        pool_key = directory.name
        pool = FavouritePool(
            key=pool_key,
            chat_id="" if pool_key == SHARED_POOL_KEY else pool_key,
            directory=directory.resolve(),
            isolated_by_chat=pool_key != SHARED_POOL_KEY,
        )
        pools.append(pool)
    return sorted(pools, key=lambda pool: (pool.key != SHARED_POOL_KEY, pool.key))


def find_content_by_id(content_id: str, *, preferred_chat_id: str = "") -> FavouriteResolvedItem:
    """按 ID 从任意收藏池中查找内容。"""

    normalized_content_id = str(content_id or "").strip()
    if not normalized_content_id:
        raise FavouriteStorageError("需要提供收藏内容 ID。")

    pools = _iter_existing_pools()
    if preferred_chat_id:
        try:
            preferred_pool = resolve_current_pool(preferred_chat_id)
        except FavouriteStorageError:
            preferred_pool = None
        if preferred_pool is not None:
            pools = [preferred_pool, *[pool for pool in pools if pool.key != preferred_pool.key]]

    for pool in pools:
        manifest = _load_manifest(pool)
        for item in manifest.get("items", []):
            if str(item.get("id") or "").strip() != normalized_content_id:
                continue
            file_name = str(item.get("file") or item.get("name") or "").strip()
            if not file_name:
                raise FavouriteStorageError(f"收藏内容缺少文件名：id={normalized_content_id}")
            file_path = (pool.directory / file_name).resolve()
            try:
                file_path.relative_to(pool.directory.resolve())
            except ValueError as exc:
                raise FavouriteStorageError(f"收藏内容路径非法：id={normalized_content_id}") from exc
            if not file_path.exists():
                raise FavouriteStorageError(f"收藏文件不存在：id={normalized_content_id}，文件={file_name}")
            return FavouriteResolvedItem(pool=pool, item=_public_item(item), file_path=file_path)

    raise FavouriteStorageError(f"未找到收藏内容：id={normalized_content_id}")


def read_text_item(resolved_item: FavouriteResolvedItem) -> str:
    """读取文本收藏内容。"""

    try:
        return resolved_item.file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise FavouriteStorageError(f"收藏内容不是有效的 UTF-8 文本：id={resolved_item.item['id']}") from exc
    except Exception as exc:
        raise FavouriteStorageError(f"读取收藏文本失败：{exc}") from exc


def read_binary_item_base64(resolved_item: FavouriteResolvedItem) -> str:
    """读取二进制收藏内容并编码为 base64。"""

    try:
        return base64.b64encode(resolved_item.file_path.read_bytes()).decode("ascii")
    except Exception as exc:
        raise FavouriteStorageError(f"读取收藏文件失败：{exc}") from exc
