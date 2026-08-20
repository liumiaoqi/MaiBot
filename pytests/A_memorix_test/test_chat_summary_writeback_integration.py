from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Dict, List

import asyncio
import inspect
import json
import pickle

from sqlalchemy.orm import sessionmaker
from sqlmodel import Session, create_engine
import numpy as np
import pytest

IMPORT_ERROR: str | None = None

try:
    from src.A_memorix.core.runtime import sdk_memory_kernel as kernel_module
    from src.A_memorix.core.runtime.sdk_memory_kernel import SDKMemoryKernel
    from src.A_memorix.core.utils import summary_importer as summary_importer_module
    from src.core.types import SessionInfo
    from src.chat.message_receive.message import SessionMessage
    from src.common.data_models.mai_message_data_model import MessageInfo, UserInfo
    from src.common.data_models.message_component_data_model import MessageSequence, TextComponent
    from src.common.database import database as database_module
    from src.common.database.migrations import create_database_migration_bootstrapper
    from src.common.message_repository import count_messages
    from src.config.model_configs import TaskConfig
    from src.services import memory_flow_service as memory_flow_service_module
    from src.services import memory_service as memory_service_module
    from src.services import message_service as message_service_module
    from src.services import send_service
except SystemExit as exc:
    IMPORT_ERROR = f"config initialization exited during import: {exc}"
    kernel_module = None  # type: ignore[assignment]
    SDKMemoryKernel = None  # type: ignore[assignment]
    summary_importer_module = None  # type: ignore[assignment]
    BotChatSession = None  # type: ignore[assignment]  # 保留变量名兼容
    SessionMessage = None  # type: ignore[assignment]
    MessageInfo = None  # type: ignore[assignment]
    UserInfo = None  # type: ignore[assignment]
    MessageSequence = None  # type: ignore[assignment]
    TextComponent = None  # type: ignore[assignment]
    database_module = None  # type: ignore[assignment]
    create_database_migration_bootstrapper = None  # type: ignore[assignment]
    count_messages = None  # type: ignore[assignment]
    TaskConfig = None  # type: ignore[assignment]
    memory_flow_service_module = None  # type: ignore[assignment]
    memory_service_module = None  # type: ignore[assignment]
    message_service_module = None  # type: ignore[assignment]
    send_service = None  # type: ignore[assignment]


pytestmark = pytest.mark.skipif(IMPORT_ERROR is not None, reason=IMPORT_ERROR or "")


class _FakeEmbeddingManager:
    def __init__(self, dimension: int = 8) -> None:
        self.default_dimension = dimension

    async def _detect_dimension(self) -> int:
        return self.default_dimension

    async def encode(self, text: Any) -> np.ndarray:
        def _encode_one(raw: Any) -> np.ndarray:
            content = str(raw or "")
            vector = np.zeros(self.default_dimension, dtype=np.float32)
            for index, byte in enumerate(content.encode("utf-8")):
                vector[index % self.default_dimension] += float((byte % 17) + 1)
            norm = float(np.linalg.norm(vector))
            if norm > 0:
                vector /= norm
            return vector

        if isinstance(text, (list, tuple)):
            return np.stack([_encode_one(item) for item in text]).astype(np.float32)
        return _encode_one(text).astype(np.float32)


class _KernelBackedRuntimeManager:
    def __init__(self, kernel: SDKMemoryKernel) -> None:
        self.kernel = kernel

    async def invoke(
        self,
        component_name: str,
        args: Dict[str, Any] | None,
        *,
        timeout_ms: int = 30000,
    ) -> Any:
        del timeout_ms
        payload = args or {}
        if component_name == "metadata_get_paragraphs_by_source":
            return self.kernel.metadata_store.get_paragraphs_by_source(str(payload.get("source", "")))
        if component_name == "metadata_query":
            return self.kernel.metadata_store.query(
                str(payload.get("sql", "")),
                tuple(payload.get("params") or []),
            )
        handler = getattr(self.kernel, component_name)
        result = handler(**payload)
        return await result if inspect.isawaitable(result) else result


class _NoopRuntimeManager:
    async def invoke_hook(self, hook_name: str, **kwargs: Any) -> Any:
        del hook_name
        return SimpleNamespace(aborted=False, kwargs=kwargs)


class _FakePlatformIOManager:
    def __init__(self) -> None:
        self.ensure_calls = 0

    async def ensure_send_pipeline_ready(self) -> None:
        self.ensure_calls += 1

    def build_route_key_from_message(self, message: Any) -> Any:
        del message
        return SimpleNamespace(platform="qq")

    async def send_message(self, message: Any, route_key: Any, metadata: Dict[str, Any]) -> Any:
        del message, metadata
        return SimpleNamespace(
            has_success=True,
            sent_receipts=[
                SimpleNamespace(
                    driver_id="plugin.qq.sender",
                    external_message_id="real-message-id",
                    metadata={},
                )
            ],
            failed_receipts=[],
            route_key=route_key,
        )


def _install_temp_main_database(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    db_dir = (tmp_path / "main_db").resolve()
    db_dir.mkdir(parents=True, exist_ok=True)
    db_file = db_dir / "MaiBot.db"
    database_url = f"sqlite:///{db_file}"

    try:
        database_module.engine.dispose()
    except Exception:
        pass

    engine = create_engine(
        database_url,
        echo=False,
        connect_args={"check_same_thread": False},
        pool_pre_ping=True,
    )
    session_local = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine,
        class_=Session,
    )
    bootstrapper = create_database_migration_bootstrapper(engine)

    monkeypatch.setattr(database_module, "_DB_DIR", db_dir, raising=False)
    monkeypatch.setattr(database_module, "_DB_FILE", db_file, raising=False)
    monkeypatch.setattr(database_module, "DATABASE_URL", database_url, raising=False)
    monkeypatch.setattr(database_module, "engine", engine, raising=False)
    monkeypatch.setattr(database_module, "SessionLocal", session_local, raising=False)
    monkeypatch.setattr(database_module, "_migration_bootstrapper", bootstrapper, raising=False)
    monkeypatch.setattr(database_module, "_db_initialized", False, raising=False)


def _build_incoming_message(
    *,
    session_id: str,
    user_id: str,
    text: str,
    timestamp: datetime | None = None,
) -> SessionMessage:
    message = SessionMessage(
        message_id="incoming-message-id",
        timestamp=timestamp or datetime.now(),
        platform="qq",
    )
    message.message_info = MessageInfo(
        user_info=UserInfo(
            user_id=user_id,
            user_nickname="测试用户",
            user_cardname="测试用户",
        ),
        additional_config={},
    )
    message.raw_message = MessageSequence(components=[TextComponent(text=text)])
    message.session_id = session_id
    message.reply_to = None
    message.is_mentioned = False
    message.is_at = False
    message.is_emoji = False
    message.is_picture = False
    message.is_command = False
    message.is_notify = False
    message.processed_plain_text = text
    message.initialized = True
    return message


async def _wait_until(
    predicate: Callable[[], Any],
    *,
    timeout_seconds: float = 10.0,
    interval_seconds: float = 0.05,
    description: str,
) -> Any:
    deadline = asyncio.get_running_loop().time() + max(0.5, float(timeout_seconds))
    while asyncio.get_running_loop().time() < deadline:
        value = predicate()
        if inspect.isawaitable(value):
            value = await value
        if value:
            return value
        await asyncio.sleep(interval_seconds)
    raise AssertionError(f"等待超时: {description}")


@pytest.mark.asyncio
async def test_text_to_stream_triggers_real_chat_summary_writeback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _install_temp_main_database(monkeypatch, tmp_path)

    fake_embedding_manager = _FakeEmbeddingManager()
    captured_prompts: List[str] = []
    fixed_send_timestamp = 1_777_000_000.0

    async def _fake_runtime_self_check(**kwargs: Any) -> Dict[str, Any]:
        del kwargs
        return {
            "ok": True,
            "message": "ok",
            "configured_dimension": fake_embedding_manager.default_dimension,
            "requested_dimension": fake_embedding_manager.default_dimension,
            "vector_store_dimension": fake_embedding_manager.default_dimension,
            "detected_dimension": fake_embedding_manager.default_dimension,
            "encoded_dimension": fake_embedding_manager.default_dimension,
            "elapsed_ms": 0.0,
            "sample_text": "test",
            "checked_at": datetime.now().timestamp(),
        }

    async def _fake_generate(request: Any) -> Any:
        captured_prompts.append(str(getattr(request, "prompt", "") or ""))
        return SimpleNamespace(
            success=True,
            completion=SimpleNamespace(
                response=json.dumps(
                    {
                        "summary": "这段对话记录了用户提到自己买了绿色围巾，机器人表示会记住这件事。",
                        "entities": ["绿色围巾"],
                        "relations": [],
                    },
                    ensure_ascii=False,
                )
            ),
        )

    monkeypatch.setattr(
        "src.A_memorix.core.embedding.create_embedding_api_adapter",
        lambda **kwargs: fake_embedding_manager,
    )
    monkeypatch.setattr(
        "src.A_memorix.core.utils.runtime_self_check.run_embedding_runtime_self_check",
        _fake_runtime_self_check,
    )
    monkeypatch.setattr(
        summary_importer_module,
        "run_embedding_runtime_self_check",
        _fake_runtime_self_check,
    )
    monkeypatch.setattr(send_service.time, "time", lambda: fixed_send_timestamp)
    monkeypatch.setattr(summary_importer_module.time, "time", lambda: fixed_send_timestamp)

    class _FakeLLMServiceRequest:
        def __init__(
            self,
            *,
            task_name: str,
            request_type: str,
            prompt: str,
            temperature: float | None = None,
            max_tokens: int | None = None,
        ) -> None:
            self.task_name = task_name
            self.request_type = request_type
            self.prompt = prompt
            self.temperature = temperature
            self.max_tokens = max_tokens

    class _FakeLLMService:
        LLMServiceRequest = _FakeLLMServiceRequest

        def get_available_models(self) -> Dict[str, Any]:
            return {"utils": TaskConfig(model_list=["fake-summary-model"])}

        def resolve_task_name_from_model_config(self, model_config: Any) -> str:
            del model_config
            return "utils"

        async def generate(self, request: Any) -> Any:
            return await _fake_generate(request)

    fake_llm_service = _FakeLLMService()

    kernel = SDKMemoryKernel(
        plugin_root=tmp_path / "plugin_root",
        config={
            "storage": {"data_dir": str((tmp_path / "a_memorix_data").resolve())},
            "advanced": {"enable_auto_save": False},
            "embedding": {"dimension": fake_embedding_manager.default_dimension},
            "memory": {"base_decay_interval_hours": 24},
            "person_profile": {"refresh_interval_minutes": 5},
            "summarization": {"model_name": ["utils"]},
        },
    )
    kernel._ports = SimpleNamespace(
        model_config_port=None,
        llm_models_client_registry=None,
        llm_models_base_client=None,
        llm_models_exceptions=None,
        session_info_port=None,
        config_manager=None,
        build_profile_injection_text=None,
        require_llm_service=lambda: fake_llm_service,
        require_message_service=lambda: SimpleNamespace(
            get_messages_by_time_in_chat=message_service_module.get_messages_by_time_in_chat,
            build_readable_messages=message_service_module.build_readable_messages,
        ),
        require_config_manager=lambda: None,
        llm_service=None,
        db_session_factory=None,
        db_person_info_model=None,
    )

    service = memory_flow_service_module.MemoryAutomationService()
    await service.start()
    fake_platform_io_manager = _FakePlatformIOManager()

    async def _fake_rebuild_episodes_for_sources(sources: List[str]) -> Dict[str, Any]:
        return {
            "rebuilt": 0,
            "items": [],
            "failures": [],
            "sources": list(sources),
        }

    monkeypatch.setattr(kernel, "rebuild_episodes_for_sources", _fake_rebuild_episodes_for_sources)
    kernel_backed_runtime_manager = _KernelBackedRuntimeManager(kernel)
    monkeypatch.setattr(
        "src.A_memorix.host_service.a_memorix_host_service",
        kernel_backed_runtime_manager,
    )
    real_memory_service = memory_service_module.memory_service
    monkeypatch.setattr(
        memory_flow_service_module,
        "get_memory_service_port",
        lambda: SimpleNamespace(
            ingest_summary=lambda **kwargs: real_memory_service.ingest_summary(**kwargs),
            get_paragraphs_by_source=lambda source: real_memory_service.get_paragraphs_by_source(source),
        ),
    )
    monkeypatch.setattr(memory_flow_service_module, "memory_automation_service", service)
    monkeypatch.setattr(
        message_service_module,
        "get_bot_config_port",
        lambda: SimpleNamespace(get_bot_nickname=lambda: "bot-qq"),
    )
    monkeypatch.setattr(send_service, "_get_runtime_manager", lambda: _NoopRuntimeManager())
    monkeypatch.setattr(send_service, "get_platform_io_manager", lambda: fake_platform_io_manager)
    monkeypatch.setattr(send_service, "get_bot_account", lambda platform: "bot-qq")
    from src.core.session_port_registry import register_session_info_port, register_session_query_port

    class _MockSessionInfoPort:
        def get_session_info(self, session_id: str):
            if session_id == "test-session":
                return SessionInfo(
                    session_id="test-session",
                    session_name="test-session",
                    platform="qq",
                    is_group_session=False,
                    user_id="target-user",
                )
            return None

        def get_existing_session_info(self, session_id: str):
            return self.get_session_info(session_id)

    class _MockSessionQueryPort:
        def get_last_message(self, session_id: str):
            return None

        def get_route_metadata(self, session_id: str):
            return {}

        def list_sessions(self):
            return []

    register_session_info_port(_MockSessionInfoPort())
    register_session_query_port(_MockSessionQueryPort())
    integration_config = SimpleNamespace()
    monkeypatch.setattr(memory_flow_service_module, "get_app_config_port", lambda: SimpleNamespace(
        get_a_memorix_integration_config=lambda: integration_config,
    ))
    monkeypatch.setattr(integration_config, "chat_summary_writeback_enabled", True, raising=False)
    monkeypatch.setattr(integration_config, "chat_summary_writeback_message_threshold", 2, raising=False)
    monkeypatch.setattr(integration_config, "chat_summary_writeback_context_length", 10, raising=False)
    monkeypatch.setattr(integration_config, "person_fact_writeback_enabled", False, raising=False)

    from src.core.model_config_port_registry import register_model_config_port, reset_model_config_port
    from src.llm_models.model_requirement import ResolvedModel

    class _FakeModelConfigPort:
        def resolve_by_capability(self, capabilities, *, agent_id="", options=None):
            return ResolvedModel(
                category="llm",
                name="fake-summary-model",
                model_identifier="fake-summary-model",
                api_provider="fake-provider",
                capabilities=frozenset(capabilities),
            )

        def get_model_config(self):
            return SimpleNamespace(models_dict={})

    register_model_config_port(_FakeModelConfigPort())

    await kernel.initialize()

    try:
        incoming_message = _build_incoming_message(
            session_id="test-session",
            user_id="target-user",
            text="我最近买了一条绿色围巾。",
            timestamp=datetime.fromtimestamp(fixed_send_timestamp) - timedelta(seconds=1),
        )
        with database_module.get_db_session() as session:
            session.add(incoming_message.to_db_instance())

        sent_message = _build_incoming_message(
            session_id="test-session",
            user_id="bot-qq",
            text="好的，我会记住你最近买了绿色围巾。",
            timestamp=datetime.fromtimestamp(fixed_send_timestamp),
        )
        sent_message.message_id = "sent-message-id"
        sent_message = await send_service.send_session_message_with_message(
            sent_message,
            storage_message=True,
        )

        assert sent_message is not None
        assert sent_message.message_id == "real-message-id"
        assert fake_platform_io_manager.ensure_calls == 1
        assert count_messages(session_id="test-session") == 2

        paragraphs = await _wait_until(
            lambda: kernel.metadata_store.get_paragraphs_by_source("chat_summary:test-session"),
            description="等待聊天摘要写回到 A_memorix",
        )

        assert captured_prompts
        assert "我最近买了一条绿色围巾。" in captured_prompts[-1]
        assert "好的，我会记住你最近买了绿色围巾。" in captured_prompts[-1]
        assert any("绿色围巾" in str(item.get("content", "") or "") for item in paragraphs)
        assert any(
            int(
                (
                    pickle.loads(item.get("metadata"))
                    if isinstance(item.get("metadata"), (bytes, bytearray))
                    else item.get("metadata")
                    or {}
                ).get("trigger_message_count", 0)
                or 0
            )
            == 2
            for item in paragraphs
        )
        assert service.chat_summary_writeback._states["test-session"].last_trigger_message_count == 2
    finally:
        await service.shutdown()
        await kernel.shutdown()
        reset_model_config_port()
        try:
            database_module.engine.dispose()
        except Exception:
            pass
