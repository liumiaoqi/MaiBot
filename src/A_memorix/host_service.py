from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import tomlkit

from src.common.logger import get_logger
from src.webui.utils.toml_utils import save_toml_with_format

from .core.runtime.sdk_memory_kernel import KernelSearchRequest, SDKMemoryKernel
from .paths import config_path, repo_root, schema_path
from .runtime_registry import set_runtime_kernel

logger = get_logger("a_memorix.host_service")


def _to_builtin_data(obj: Any) -> Any:
    if hasattr(obj, "unwrap"):
        try:
            obj = obj.unwrap()
        except Exception:
            pass

    if isinstance(obj, dict):
        return {str(key): _to_builtin_data(value) for key, value in obj.items()}
    if isinstance(obj, list):
        return [_to_builtin_data(value) for value in obj]
    return obj


def _backup_config_file(path: Path) -> Optional[Path]:
    if not path.exists():
        return None
    backup_name = f"{path.name}.backup.{datetime.now().strftime('%Y%m%d%H%M%S')}"
    backup_path = path.parent / backup_name
    backup_path.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    return backup_path


class AMemorixHostService:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._kernel: Optional[SDKMemoryKernel] = None
        self._config_cache: Dict[str, Any] | None = None

    async def start(self) -> None:
        await self._ensure_kernel()

    async def stop(self) -> None:
        async with self._lock:
            await self._shutdown_locked()

    async def reload(self) -> None:
        async with self._lock:
            await self._shutdown_locked()
            self._config_cache = self._read_config()

        await self._ensure_kernel()

    def get_config_path(self) -> Path:
        return config_path()

    def get_schema_path(self) -> Path:
        return schema_path()

    def get_config_schema(self) -> Dict[str, Any]:
        path = self.get_schema_path()
        if not path.exists():
            return {
                "plugin_id": "a_memorix",
                "plugin_info": {
                    "name": "A_Memorix",
                    "version": "",
                    "description": "A_Memorix 配置结构",
                    "author": "A_Dawn",
                },
                "sections": {},
                "layout": {"type": "auto", "tabs": []},
            }

        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def get_config(self) -> Dict[str, Any]:
        return dict(self._read_config())

    def _build_default_config(self) -> Dict[str, Any]:
        schema = self.get_config_schema()
        sections = schema.get("sections") if isinstance(schema, dict) else None
        if not isinstance(sections, dict):
            return {}

        defaults: Dict[str, Any] = {}
        for section_name, section_payload in sections.items():
            if not isinstance(section_payload, dict):
                continue
            fields = section_payload.get("fields")
            if not isinstance(fields, dict):
                continue

            section_parts = [part for part in str(section_name or "").split(".") if part]
            if not section_parts:
                continue

            section_target: Dict[str, Any] = defaults
            for part in section_parts:
                nested = section_target.get(part)
                if not isinstance(nested, dict):
                    nested = {}
                    section_target[part] = nested
                section_target = nested

            for field_name, field_payload in fields.items():
                if not isinstance(field_payload, dict) or "default" not in field_payload:
                    continue
                section_target[str(field_name)] = _to_builtin_data(field_payload.get("default"))

        return defaults

    def get_raw_config_with_meta(self) -> Dict[str, Any]:
        path = self.get_config_path()
        if path.exists():
            return {
                "config": path.read_text(encoding="utf-8"),
                "exists": True,
                "using_default": False,
            }

        default_config = self._build_default_config()
        default_raw = tomlkit.dumps(default_config) if default_config else ""
        return {
            "config": default_raw,
            "exists": False,
            "using_default": True,
        }

    def get_raw_config(self) -> str:
        payload = self.get_raw_config_with_meta()
        return str(payload.get("config", "") or "")

    async def update_raw_config(self, raw_config: str) -> Dict[str, Any]:
        tomlkit.loads(raw_config)
        path = self.get_config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        backup_path = _backup_config_file(path)
        path.write_text(raw_config, encoding="utf-8")
        await self.reload()
        return {
            "success": True,
            "message": "配置已保存",
            "backup_path": str(backup_path) if backup_path is not None else "",
            "config_path": str(path),
        }

    async def update_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        path = self.get_config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        backup_path = _backup_config_file(path)
        save_toml_with_format(config, str(path), preserve_comments=True)
        await self.reload()
        return {
            "success": True,
            "message": "配置已保存",
            "backup_path": str(backup_path) if backup_path is not None else "",
            "config_path": str(path),
        }

    async def invoke(self, component_name: str, args: Dict[str, Any] | None = None, *, timeout_ms: int = 30000) -> Any:
        del timeout_ms
        payload = args or {}
        kernel = await self._ensure_kernel()

        if component_name == "search_memory":
            return await kernel.search_memory(
                KernelSearchRequest(
                    query=str(payload.get("query", "") or ""),
                    limit=int(payload.get("limit", 5) or 5),
                    mode=str(payload.get("mode", "search") or "search"),
                    chat_id=str(payload.get("chat_id", "") or ""),
                    person_id=str(payload.get("person_id", "") or ""),
                    time_start=payload.get("time_start"),
                    time_end=payload.get("time_end"),
                    respect_filter=bool(payload.get("respect_filter", True)),
                    user_id=str(payload.get("user_id", "") or "").strip(),
                    group_id=str(payload.get("group_id", "") or "").strip(),
                )
            )

        if component_name == "enqueue_feedback_task":
            return await kernel.enqueue_feedback_task(
                query_tool_id=str(payload.get("query_tool_id", "") or ""),
                session_id=str(payload.get("session_id", "") or ""),
                query_timestamp=payload.get("query_timestamp"),
                structured_content=payload.get("structured_content")
                if isinstance(payload.get("structured_content"), dict)
                else {},
            )

        if component_name == "ingest_summary":
            return await kernel.ingest_summary(
                external_id=str(payload.get("external_id", "") or ""),
                chat_id=str(payload.get("chat_id", "") or ""),
                text=str(payload.get("text", "") or ""),
                participants=list(payload.get("participants") or []),
                time_start=payload.get("time_start"),
                time_end=payload.get("time_end"),
                tags=list(payload.get("tags") or []),
                metadata=payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
                respect_filter=bool(payload.get("respect_filter", True)),
                user_id=str(payload.get("user_id", "") or "").strip(),
                group_id=str(payload.get("group_id", "") or "").strip(),
            )

        if component_name == "ingest_text":
            relations = payload.get("relations") if isinstance(payload.get("relations"), list) else []
            entities = payload.get("entities") if isinstance(payload.get("entities"), list) else []
            return await kernel.ingest_text(
                external_id=str(payload.get("external_id", "") or ""),
                source_type=str(payload.get("source_type", "") or ""),
                text=str(payload.get("text", "") or ""),
                chat_id=str(payload.get("chat_id", "") or ""),
                person_ids=list(payload.get("person_ids") or []),
                participants=list(payload.get("participants") or []),
                timestamp=payload.get("timestamp"),
                time_start=payload.get("time_start"),
                time_end=payload.get("time_end"),
                tags=list(payload.get("tags") or []),
                metadata=payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
                entities=entities,
                relations=relations,
                respect_filter=bool(payload.get("respect_filter", True)),
                user_id=str(payload.get("user_id", "") or "").strip(),
                group_id=str(payload.get("group_id", "") or "").strip(),
            )

        if component_name == "get_person_profile":
            return await kernel.get_person_profile(
                person_id=str(payload.get("person_id", "") or ""),
                chat_id=str(payload.get("chat_id", "") or ""),
                limit=max(1, int(payload.get("limit", 10) or 10)),
            )

        if component_name == "maintain_memory":
            return await kernel.maintain_memory(
                action=str(payload.get("action", "") or ""),
                target=str(payload.get("target", "") or ""),
                hours=payload.get("hours"),
                reason=str(payload.get("reason", "") or ""),
                limit=max(1, int(payload.get("limit", 50) or 50)),
            )

        if component_name == "memory_stats":
            return kernel.memory_stats()

        admin_actions = {
            "memory_graph_admin": kernel.memory_graph_admin,
            "memory_source_admin": kernel.memory_source_admin,
            "memory_episode_admin": kernel.memory_episode_admin,
            "memory_profile_admin": kernel.memory_profile_admin,
            "memory_feedback_admin": kernel.memory_feedback_admin,
            "memory_runtime_admin": kernel.memory_runtime_admin,
            "memory_import_admin": kernel.memory_import_admin,
            "memory_tuning_admin": kernel.memory_tuning_admin,
            "memory_v5_admin": kernel.memory_v5_admin,
            "memory_delete_admin": kernel.memory_delete_admin,
        }
        if component_name in admin_actions:
            kwargs = dict(payload)
            action = str(kwargs.pop("action", "") or "")
            return await admin_actions[component_name](action=action, **kwargs)

        raise RuntimeError(f"不支持的 A_Memorix 调用: {component_name}")

    async def _ensure_kernel(self) -> SDKMemoryKernel:
        async with self._lock:
            if self._kernel is None:
                config = self._read_config()
                kernel = SDKMemoryKernel(plugin_root=repo_root(), config=config)
                try:
                    await kernel.initialize()
                except Exception:
                    kernel.close()
                    raise
                self._kernel = kernel
                set_runtime_kernel(kernel)
            return self._kernel

    def _read_config(self) -> Dict[str, Any]:
        if self._config_cache is not None:
            return dict(self._config_cache)

        path = self.get_config_path()
        if not path.exists():
            defaults = self._build_default_config()
            self._config_cache = defaults
            return dict(defaults)

        try:
            with path.open("r", encoding="utf-8") as handle:
                loaded = tomlkit.load(handle)
        except Exception as exc:
            logger.warning("读取 A_Memorix 配置失败 %s: %s", path, exc)
            defaults = self._build_default_config()
            self._config_cache = defaults
            return dict(defaults)

        self._config_cache = _to_builtin_data(loaded) if isinstance(loaded, dict) else {}
        return dict(self._config_cache)

    async def _shutdown_locked(self) -> None:
        if self._kernel is None:
            return
        shutdown = getattr(self._kernel, "shutdown", None)
        if callable(shutdown):
            await shutdown()
        else:
            self._kernel.close()
        self._kernel = None
        set_runtime_kernel(None)


a_memorix_host_service = AMemorixHostService()
