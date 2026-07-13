from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Optional, Sequence

import tomlkit

from src.common.logger import get_logger
from src.common.utils.utils_config import AMemorixConfigUtils
from src.config.official_configs import AMemorixConfig
from src.webui.utils.toml_utils import _update_toml_doc

from .paths import repo_root, schema_path
from .runtime_registry import set_runtime_kernel

if TYPE_CHECKING:
    from .core.runtime.sdk_memory_kernel import SDKMemoryKernel

logger = get_logger("a_memorix.host_service")

_INTERNAL_CONFIG_FIELDS = {"field_docs", "_validate_any", "suppress_any_warning"}


def _get_config_manager():
    from src.config.config import config_manager

    return config_manager


def _get_bot_config_path() -> Path:
    from src.config.config import BOT_CONFIG_PATH

    return BOT_CONFIG_PATH


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


def _strip_internal_config_fields(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {
            str(key): _strip_internal_config_fields(value)
            for key, value in obj.items()
            if str(key) not in _INTERNAL_CONFIG_FIELDS
        }
    if isinstance(obj, list):
        return [_strip_internal_config_fields(value) for value in obj]
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
        self._reload_callback_registered = False

    async def start(self) -> None:
        if not self.is_enabled():
            logger.info("A_Memorix 未启用，跳过长期记忆运行时初始化")
            return
        await self._ensure_kernel()

    async def stop(self) -> None:
        async with self._lock:
            await self._shutdown_locked()

    async def reload(self) -> None:
        async with self._lock:
            await self._shutdown_locked()
            self._config_cache = None
            config = self._read_config()

        if self._is_enabled_config(config):
            await self._ensure_kernel()
        else:
            logger.info("A_Memorix 配置为未启用，运行时保持关闭")

    def get_config_path(self) -> Path:
        return _get_bot_config_path()

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

    def is_enabled(self) -> bool:
        return self._is_enabled_config(self._read_config())

    @staticmethod
    def _is_enabled_config(config: Dict[str, Any]) -> bool:
        plugin_config = config.get("plugin") if isinstance(config, dict) else None
        if not isinstance(plugin_config, dict):
            return True
        return bool(plugin_config.get("enabled", True))

    def _build_default_config(self) -> Dict[str, Any]:
        return self._config_model_to_runtime_dict(AMemorixConfig())

    def get_raw_config_with_meta(self) -> Dict[str, Any]:
        config = self.get_config()
        default_config = self._build_default_config()
        raw_doc = tomlkit.document()
        raw_doc.add("a_memorix", config)
        return {
            "config": tomlkit.dumps(raw_doc),
            "exists": self.get_config_path().exists(),
            "using_default": config == default_config,
        }

    def get_raw_config(self) -> str:
        payload = self.get_raw_config_with_meta()
        return payload.get("config", "")

    async def update_raw_config(self, raw_config: str) -> Dict[str, Any]:
        loaded = tomlkit.loads(raw_config)
        raw_payload = _to_builtin_data(loaded) if isinstance(loaded, dict) else {}
        config_payload = raw_payload.get("a_memorix") if isinstance(raw_payload.get("a_memorix"), dict) else raw_payload
        path, backup_path = await self._write_config_to_bot_config(config_payload)
        return {
            "success": True,
            "message": "配置已保存",
            "backup_path": str(backup_path) if backup_path is not None else "",
            "config_path": str(path),
        }

    async def update_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        path, backup_path = await self._write_config_to_bot_config(config)
        return {
            "success": True,
            "message": "配置已保存",
            "backup_path": str(backup_path) if backup_path is not None else "",
            "config_path": str(path),
        }

    async def invoke(self, component_name: str, args: Dict[str, Any] | None = None, *, timeout_ms: int = 30000) -> Any:
        del timeout_ms
        payload = args or {}
        if not self.is_enabled():
            return self._disabled_response(component_name)
        kernel = await self._ensure_kernel()

        if component_name == "search_memory":
            from .core.runtime.sdk_memory_kernel import KernelSearchRequest

            chat_id = payload.get("chat_id", "").strip()
            config = self._read_config()
            global_memory_sharing_enabled = bool(config.get("global_memory_sharing_enabled", False))
            search_chat_id = "" if global_memory_sharing_enabled else chat_id
            shared_chat_ids = ()
            if not global_memory_sharing_enabled:
                shared_chat_ids = tuple(AMemorixConfigUtils.get_shared_memory_session_ids(chat_id))

            return await kernel.search_memory(
                KernelSearchRequest(
                    query=payload.get("query", ""),
                    limit=int(payload.get("limit", 5) or 5),
                    mode=str(payload.get("mode", "search") or "search"),
                    chat_id=search_chat_id,
                    shared_chat_ids=shared_chat_ids,
                    person_id=payload.get("person_id", ""),
                    time_start=payload.get("time_start"),
                    time_end=payload.get("time_end"),
                    respect_filter=bool(payload.get("respect_filter", True)),
                    user_id=payload.get("user_id", "").strip(),
                    group_id=payload.get("group_id", "").strip(),
                )
            )

        if component_name == "enqueue_feedback_task":
            return await kernel._feedback_correction_service.enqueue_feedback_task(
                query_tool_id=payload.get("query_tool_id", ""),
                session_id=payload.get("session_id", ""),
                query_timestamp=payload.get("query_timestamp"),
                structured_content=payload.get("structured_content")
                if isinstance(payload.get("structured_content"), dict)
                else {},
            )

        if component_name == "ingest_summary":
            return await kernel.ingest_summary(
                external_id=payload.get("external_id", ""),
                chat_id=payload.get("chat_id", ""),
                text=payload.get("text", ""),
                participants=list(payload.get("participants") or []),
                time_start=payload.get("time_start"),
                time_end=payload.get("time_end"),
                tags=list(payload.get("tags") or []),
                metadata=payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
                respect_filter=bool(payload.get("respect_filter", True)),
                user_id=payload.get("user_id", "").strip(),
                group_id=payload.get("group_id", "").strip(),
            )

        if component_name == "ingest_text":
            relations = payload.get("relations") if isinstance(payload.get("relations"), list) else []
            entities = payload.get("entities") if isinstance(payload.get("entities"), list) else []
            return await kernel.ingest_text(
                external_id=payload.get("external_id", ""),
                source_type=payload.get("source_type", ""),
                text=payload.get("text", ""),
                chat_id=payload.get("chat_id", ""),
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
                user_id=payload.get("user_id", "").strip(),
                group_id=payload.get("group_id", "").strip(),
            )

        if component_name == "get_person_profile":
            return await kernel.get_person_profile(
                person_id=payload.get("person_id", ""),
                chat_id=payload.get("chat_id", ""),
                limit=max(1, int(payload.get("limit", 10) or 10)),
            )

        if component_name == "maintain_memory":
            result = await kernel.maintain_memory(
                action=payload.get("action", ""),
                target=payload.get("target", ""),
                hours=payload.get("hours"),
                reason=payload.get("reason", ""),
                limit=max(1, int(payload.get("limit", 50) or 50)),
            )
            action = payload.get("action", "")
            migration_adapter = kernel._migration_adapter
            if action == "decay" and migration_adapter and migration_adapter.should_observe():
                hours = float(payload.get("hours") or 1.0) if payload.get("hours") else 1.0
                decay_result = await kernel._memory_field.granular_decay(elapsed_hours=hours)
                result["connectionist_decay"] = {
                    "traces_processed": decay_result.traces_processed,
                    "traces_consolidated": decay_result.traces_consolidated,
                }
            return result

        if component_name == "memory_stats":
            return kernel.memory_stats()

        if component_name == "observe":
            migration_adapter = kernel._migration_adapter
            if migration_adapter and not migration_adapter.should_observe():
                from .core.connectionist.models import ObserveResult
                return ObserveResult(text=payload.get("text", ""))
            from .core.connectionist.enums import Valence

            valence = Valence.NEUTRAL
            valence_str = payload.get("valence", "").strip()
            if valence_str:
                try:
                    valence = Valence(valence_str)
                except ValueError:
                    pass
            return await kernel._memory_field.observe(
                text=payload.get("text", ""),
                valence=valence,
                timestamp=payload.get("timestamp"),
                source_id=payload.get("source_id", ""),
                session_id=payload.get("session_id", ""),
            )

        if component_name == "recall":
            migration_adapter = kernel._migration_adapter
            if migration_adapter and not migration_adapter.should_recall():
                return []
            seeds = payload.get("seeds") if isinstance(payload.get("seeds"), list) else []
            return kernel._memory_field.recall(
                seeds=[str(s) for s in seeds],
                agent_id=payload.get("agent_id", ""),
                min_weight=float(payload.get("min_weight", 0.05) or 0.05),
                max_results=int(payload.get("max_results", 20) or 20),
            )

        if component_name == "derive_profile":
            migration_adapter = kernel._migration_adapter
            if migration_adapter and not migration_adapter.should_recall():
                from .core.connectionist.models import ProfileView
                return ProfileView(subject=payload.get("subject", ""))
            return await kernel._memory_field.derive_profile(
                subject=payload.get("subject", ""),
                observer=payload.get("observer", ""),
                now=payload.get("now"),
            )

        if component_name == "reflect":
            migration_adapter = kernel._migration_adapter
            if migration_adapter and not migration_adapter.should_recall():
                from .core.connectionist.models import ReflectResult
                return ReflectResult()
            return await kernel._memory_field.reflect(
                subject=payload.get("subject", ""),
                agent_id=payload.get("agent_id", ""),
            )

        if component_name == "register_agent":
            from .core.connectionist.enums import VoiceStyle
            from .core.connectionist.models import InnerVoice, MemoryPersonalityV2

            personality = MemoryPersonalityV2(
                decay_rate=float(payload.get("decay_rate", 1.0) or 1.0),
                emotional_sensitivity=float(payload.get("emotional_sensitivity", 1.0) or 1.0),
                association_depth=int(payload.get("association_depth", 2) or 2),
                reinforcement_boost=float(payload.get("reinforcement_boost", 0.3) or 0.3),
                attention_tags=frozenset(payload.get("attention_tags") if isinstance(payload.get("attention_tags"), list) else []),
                positive_affinity=float(payload.get("positive_affinity", 1.0) or 1.0),
                negative_affinity=float(payload.get("negative_affinity", 1.0) or 1.0),
                curiosity=float(payload.get("curiosity", 1.0) or 1.0),
            )
            voices_data = payload.get("voices") if isinstance(payload.get("voices"), list) else []
            voices = []
            for v in voices_data:
                if isinstance(v, dict):
                    style_str = str(v.get("style", "preserve") or "preserve")
                    try:
                        style = VoiceStyle(style_str)
                    except ValueError:
                        style = VoiceStyle.PRESERVE
                    voices.append(
                        InnerVoice(
                            name=v.get("name", ""),
                            style=style,
                            focus_concepts=frozenset(v.get("focus_concepts") if isinstance(v.get("focus_concepts"), list) else []),
                            weight_multiplier=float(v.get("weight_multiplier", 1.0) or 1.0),
                            description=v.get("description", ""),
                        )
                    )
            kernel._memory_field.register_agent(
                agent_id=payload.get("agent_id", ""),
                personality=personality,
                voices=voices,
            )
            return {"success": True}

        if component_name == "connectionist_stats":
            return kernel._memory_field.memory_stats()

        # ── 叙事原型 API ──────────────────────────────────

        if component_name == "narrative_weave":
            return await kernel._memory_field.weave_narrative(
                agent_id=payload.get("agent_id", ""),
            )

        if component_name == "narrative_stats":
            stats = kernel._memory_field.memory_stats()
            return {
                "fragment_count": stats.get("fragment_count", 0),
                "episode_count": stats.get("episode_count", 0),
                "saga_count": stats.get("saga_count", 0),
            }

        if component_name == "cognitive_query":
            return kernel._memory_field.get_cognitive_entries(
                agent_id=payload.get("agent_id", ""),
                concept=payload.get("concept", ""),
            )

        if component_name == "cognitive_evidence":
            kernel._memory_field.add_cognitive_evidence(
                entry_id=int(payload.get("entry_id", 0)),
                observation_id=payload.get("observation_id", ""),
                is_confirm=bool(payload.get("is_confirm", True)),
            )
            return {"success": True}

        if component_name == "intuition_trigger":
            return kernel._memory_field.get_intuition(
                context_text=payload.get("context_text", ""),
                agent_id=payload.get("agent_id", ""),
                max_tokens=int(payload.get("max_tokens", 800) or 800),
            )

        if component_name == "lifecycle_advance":
            return kernel._memory_field.advance_lifecycle(
                agent_id=payload.get("agent_id", ""),
            )

        if component_name == "lifecycle_stats":
            stats = kernel._memory_field.memory_stats()
            return {
                "fragment_count": stats.get("fragment_count", 0),
                "episode_count": stats.get("episode_count", 0),
                "saga_count": stats.get("saga_count", 0),
                "cognitive_entry_count": stats.get("cognitive_entry_count", 0),
            }

        if component_name == "migration_status":
            migration_adapter = kernel._migration_adapter
            if migration_adapter is None:
                return {"phase": "unknown", "can_advance": False}
            return {
                "phase": migration_adapter.phase.value,
                "can_advance": migration_adapter.can_advance(),
            }

        if component_name == "migration_search":
            return await kernel._migration_router.search(
                query=payload.get("query", ""),
                agent_id=payload.get("agent_id", ""),
                **{k: v for k, v in payload.items() if k not in {"query", "agent_id"}},
            )

        if component_name == "migration_get_person_profile":
            return await kernel._migration_router.get_person_profile(
                person_id=payload.get("person_id", ""),
                agent_id=payload.get("agent_id", ""),
                limit=int(payload.get("limit", 4) or 4),
            )

        if component_name == "migration_ingest_text":
            return await kernel._migration_router.ingest_text(
                text=payload.get("text", ""),
                **{k: v for k, v in payload.items() if k != "text"},
            )

        if component_name == "migration_build_profile_injection_text":
            return await kernel._migration_router.build_profile_injection_text(
                raw_text=payload.get("raw_text", ""),
                agent_id=payload.get("agent_id", ""),
            )

        if component_name == "metadata_get_paragraphs_by_source":
            source = payload.get("source", "")
            if not source:
                return []
            metadata_store = kernel.metadata_store
            if metadata_store is None:
                return []
            paragraphs = metadata_store.get_paragraphs_by_source(source)
            if not paragraphs:
                return []
            return [
                {
                    "hash": p.get("hash", ""),
                    "source": p.get("source", ""),
                    "content": p.get("content", ""),
                    "metadata": p.get("metadata", {}),
                    "created_at": str(p.get("created_at", "")),
                }
                for p in paragraphs
            ]

        if component_name == "metadata_query":
            sql = payload.get("sql", "").strip()
            params = payload.get("params", ())
            if not sql:
                return []
            if not sql.upper().startswith("SELECT"):
                raise ValueError("metadata_query 仅支持只读查询")
            metadata_store = kernel.metadata_store
            if metadata_store is None:
                return []
            rows = metadata_store.query(sql, tuple(params) if not isinstance(params, tuple) else params)
            return [dict(row) for row in rows] if rows else []

        _ADMIN_HANDLER_MAP = {
            "memory_graph_admin": "graph",
            "memory_source_admin": "source",
            "memory_episode_admin": "episode",
            "memory_profile_admin": "profile",
            "memory_feedback_admin": "feedback",
            "memory_runtime_admin": "runtime",
            "memory_import_admin": "import",
            "memory_tuning_admin": "tuning",
            "memory_v5_admin": "v5",
            "memory_delete_admin": "delete",
            "memory_correction_admin": "correction",
            "memory_fuzzy_modify_admin": "correction",
        }
        handler_key = _ADMIN_HANDLER_MAP.get(component_name)
        if handler_key is not None:
            kwargs = dict(payload)
            action = kwargs.pop("action", "")
            return await kernel._admin_handlers[handler_key].handle(action, **kwargs)

        raise RuntimeError(f"不支持的 A_Memorix 调用: {component_name}")

    async def _ensure_kernel(self) -> SDKMemoryKernel:
        async with self._lock:
            if self._kernel is None:
                from .core.runtime.sdk_memory_kernel import SDKMemoryKernel

                config = self._read_config()
                if not self._is_enabled_config(config):
                    raise RuntimeError("A_memorix 未启用")
                ports = self._build_service_ports()
                kernel = SDKMemoryKernel(plugin_root=repo_root(), config=config, ports=ports)
                try:
                    await kernel.initialize()
                except Exception:
                    kernel.close()
                    raise
                self._kernel = kernel
                set_runtime_kernel(kernel)
                self._inject_session_info_port(kernel)
                self._register_agents_from_config(kernel)
            return self._kernel

    def _register_agents_from_config(self, kernel: SDKMemoryKernel) -> None:
        from .core.connectionist.enums import VoiceStyle
        from .core.connectionist.models import InnerVoice, MemoryPersonalityV2

        config = self._read_config()
        connectionist_config = config.get("connectionist", {})
        personality_config = connectionist_config.get("personality", {})
        inner_voices_config = connectionist_config.get("inner_voices", {})

        # 迁移阶段设置 — 无论是否配置 personality 都需要执行
        phase_str = connectionist_config.get("phase", "legacy_only")
        if kernel._migration_adapter is not None:
            from .core.migration.migration_adapter import MigrationPhase
            try:
                phase = MigrationPhase(phase_str)
            except ValueError:
                logger.warning(f"无效的迁移阶段配置: {phase_str}，使用默认 LEGACY_ONLY")
                phase = MigrationPhase.LEGACY_ONLY
            kernel._migration_adapter.set_phase(phase)
            logger.info(f"迁移阶段已设置: {phase.value}")

        if not personality_config:
            logger.info("未配置连接主义记忆性格，所有智能体将使用默认性格")
            return

        for agent_id, p_cfg in personality_config.items():
            if not isinstance(p_cfg, dict):
                continue
            try:
                personality = MemoryPersonalityV2(
                    decay_rate=float(p_cfg.get("decay_rate", 1.0)),
                    emotional_sensitivity=float(p_cfg.get("emotional_sensitivity", 1.0)),
                    association_depth=int(p_cfg.get("association_depth", 2)),
                    reinforcement_boost=float(p_cfg.get("reinforcement_boost", 0.3)),
                    attention_tags=frozenset(p_cfg.get("attention_tags", [])),
                    positive_affinity=float(p_cfg.get("positive_affinity", 1.0)),
                    negative_affinity=float(p_cfg.get("negative_affinity", 1.0)),
                    curiosity=float(p_cfg.get("curiosity", 1.0)),
                )
            except Exception as exc:
                raise ValueError(f"智能体 {agent_id} 的记忆性格配置无效: {exc}") from exc

            voices: list[InnerVoice] = []
            voice_list = inner_voices_config.get(agent_id, [])
            if isinstance(voice_list, list):
                for v_cfg in voice_list:
                    if not isinstance(v_cfg, dict):
                        continue
                    style_str = str(v_cfg.get("style", "preserve")).strip()
                    try:
                        style = VoiceStyle(style_str)
                    except ValueError:
                        style = VoiceStyle.PRESERVE
                    voices.append(InnerVoice(
                        name=str(v_cfg.get("name", "")),
                        style=style,
                        focus_concepts=frozenset(v_cfg.get("focus_concepts", [])),
                        weight_multiplier=float(v_cfg.get("weight_multiplier", 1.0)),
                        description=str(v_cfg.get("description", "")),
                    ))

            kernel._memory_field.register_agent(agent_id, personality, voices)
            logger.info(f"已注册智能体记忆性格: {agent_id} (voices={len(voices)})")


    @staticmethod
    def _inject_session_info_port(kernel: SDKMemoryKernel) -> None:
        """注入 SessionInfoPort，从全局注册点获取，不再延迟导入适配器。"""
        from src.core.session_port_registry import get_session_info_port

        port = get_session_info_port()
        if port is not None:
            kernel._session_info_port = port

    @staticmethod
    def _build_service_ports() -> Any:
        """构建 AMemorixServicePorts，注入 MaiBot 服务层依赖。"""
        from .core.ports import AMemorixServicePorts

        from src.common.database.database import get_db_session
        from src.common.database.database_model import PersonInfo
        from src.common.data_models.llm_service_data_models import LLMServiceResult
        from src.config.config import config_manager
        from src.llm_models.exceptions import NetworkConnectionError
        from src.llm_models.model_client.base_client import EmbeddingRequest, client_registry
        from src.services import llm_service as llm_api
        from src.services import message_service as message_api

        return AMemorixServicePorts(
            llm_service=llm_api,
            message_service=message_api,
            config_manager=config_manager,
            db_session_factory=get_db_session,
            db_person_info_model=PersonInfo,
            llm_models_client_registry=client_registry,
            llm_models_exceptions=NetworkConnectionError,
            llm_models_base_client=EmbeddingRequest,
            llm_data_models=LLMServiceResult,
            build_profile_injection_text=AMemorixHostService.build_profile_injection_text,
        )

    def _read_config(self) -> Dict[str, Any]:
        if self._config_cache is not None:
            return dict(self._config_cache)

        try:
            config_model = _get_config_manager().get_global_config().a_memorix
        except Exception as exc:
            logger.warning(f"读取 A_Memorix 主配置失败，使用默认值: {exc}")
            defaults = self._build_default_config()
            self._config_cache = defaults
            return dict(defaults)

        self._config_cache = self._config_model_to_runtime_dict(config_model)
        return dict(self._config_cache)

    @staticmethod
    def _config_model_to_runtime_dict(config_model: AMemorixConfig) -> Dict[str, Any]:
        payload = config_model.model_dump(mode="json")
        web_config = payload.get("web")
        if isinstance(web_config, dict) and "import_config" in web_config:
            web_config["import"] = web_config.pop("import_config")
        payload = _to_builtin_data(payload) if isinstance(payload, dict) else {}
        return _strip_internal_config_fields(payload) if isinstance(payload, dict) else {}

    @staticmethod
    def _runtime_dict_to_bot_config_dict(config: Dict[str, Any]) -> Dict[str, Any]:
        payload = _to_builtin_data(config)
        if not isinstance(payload, dict):
            return {}
        payload = _strip_internal_config_fields(payload)
        web_config = payload.get("web")
        if isinstance(web_config, dict) and "import_config" in web_config and "import" not in web_config:
            web_config["import"] = web_config.pop("import_config")
        return payload

    async def _write_config_to_bot_config(self, config: Dict[str, Any]) -> tuple[Path, Optional[Path]]:
        path = self.get_config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        backup_path = _backup_config_file(path)
        if path.exists():
            with path.open("r", encoding="utf-8") as handle:
                doc = tomlkit.load(handle)
        else:
            doc = tomlkit.document()

        bot_config_payload = self._runtime_dict_to_bot_config_dict(config)
        current = doc.get("a_memorix")
        if isinstance(current, dict):
            _update_toml_doc(current, bot_config_payload)
        else:
            doc["a_memorix"] = bot_config_payload

        with path.open("w", encoding="utf-8") as handle:
            tomlkit.dump(doc, handle)

        await _get_config_manager().reload_config(changed_scopes=("bot",))
        if not self._reload_callback_registered:
            await self.reload()
        return path, backup_path

    def register_config_reload_callback(self) -> None:
        if self._reload_callback_registered:
            return
        _get_config_manager().register_reload_callback(self.on_config_reload)
        self._reload_callback_registered = True

    async def on_config_reload(self, changed_scopes: Sequence[str] | None = None) -> None:
        normalized = {str(scope or "").strip().lower() for scope in (changed_scopes or [])}
        if normalized and "bot" not in normalized:
            return
        await self.reload()

    @staticmethod
    def _disabled_response(component_name: str) -> Dict[str, Any]:
        reason = "a_memorix_disabled"
        message = "A_Memorix 未启用，请在长期记忆配置中开启后再使用。"

        if component_name == "search_memory":
            return {
                "success": True,
                "disabled": True,
                "reason": reason,
                "summary": "",
                "hits": [],
                "filtered": False,
            }

        if component_name in {"ingest_summary", "ingest_text"}:
            return {
                "success": True,
                "disabled": True,
                "reason": reason,
                "stored_ids": [],
                "skipped_ids": [reason],
                "detail": reason,
            }

        if component_name == "get_person_profile":
            return {
                "success": True,
                "disabled": True,
                "reason": reason,
                "summary": "",
                "traits": [],
                "evidence": [],
            }

        if component_name == "memory_stats":
            return {
                "success": True,
                "enabled": False,
                "disabled": True,
                "reason": reason,
                "message": message,
                "paragraph_count": 0,
                "relation_count": 0,
                "episode_count": 0,
            }

        if component_name == "memory_runtime_admin":
            return {
                "success": True,
                "enabled": False,
                "disabled": True,
                "reason": reason,
                "message": message,
                "runtime_ready": False,
                "embedding_degraded": False,
                "embedding_dimension": 0,
                "auto_save": False,
                "data_dir": "",
            }

        if component_name == "enqueue_feedback_task":
            return {
                "success": True,
                "queued": False,
                "disabled": True,
                "reason": reason,
            }

        if component_name == "metadata_get_paragraphs_by_source":
            return []

        if component_name == "metadata_query":
            return []

        if component_name in {"observe", "recall", "derive_profile", "reflect",
                               "register_agent", "connectionist_stats", "migration_status",
                               "migration_search", "migration_get_person_profile",
                               "migration_ingest_text", "migration_build_profile_injection_text"}:
            return {
                "success": False,
                "disabled": True,
                "reason": reason,
                "error": message,
            }

        return {
            "success": False,
            "enabled": False,
            "disabled": True,
            "reason": reason,
            "error": message,
        }

    async def _shutdown_locked(self) -> None:
        if self._kernel is None:
            return
        try:
            await self._kernel.shutdown()
        except Exception:
            self._kernel.close()
        self._kernel = None
        set_runtime_kernel(None)

    @staticmethod
    def build_profile_injection_text(raw_text: str) -> str:
        """公共 API — 从结构化画像段落构建紧凑注入文本。

        适配器层应通过此方法调用，而非直接导入 A_memorix.core.utils 内部模块。
        """
        from src.A_memorix.core.utils.profile_text import build_profile_injection_text

        return build_profile_injection_text(raw_text)


a_memorix_host_service = AMemorixHostService()
