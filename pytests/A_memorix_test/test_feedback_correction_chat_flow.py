from __future__ import annotations

import asyncio
import inspect
import json
import time
import uuid
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Dict

import numpy as np
import pytest
import pytest_asyncio
from sqlalchemy.orm import sessionmaker
from sqlmodel import Session, create_engine, select

IMPORT_ERROR: str | None = None

try:
    from src.A_memorix.core.runtime import sdk_memory_kernel as kernel_module
    from src.A_memorix.core.runtime.sdk_memory_kernel import KernelSearchRequest, SDKMemoryKernel
    from src.chat.heart_flow.heartflow_manager import heartflow_manager
    from src.chat.message_receive import bot as bot_module
    from src.chat.message_receive.chat_manager import chat_manager
    from src.chat.message_receive.bot import chat_bot
    from src.common.database import database as database_module
    from src.common.database.database_model import PersonInfo, ToolRecord
    from src.common.database.migrations import create_database_migration_bootstrapper
    from src.common.utils.utils_session import SessionUtils
    from src.llm_models.payload_content.tool_option import ToolCall
    from src.maisaka import reasoning_engine as reasoning_engine_module
    from src.maisaka import runtime as runtime_module
    from src.maisaka import chat_loop_service as chat_loop_service_module
    from src.maisaka.chat_loop_service import ChatResponse
    from src.maisaka.context_messages import AssistantMessage
    from src.plugin_runtime import component_query as component_query_module
    from src.services import memory_flow_service as memory_flow_service_module
    from src.services import memory_service as memory_service_module
    from src.services.memory_service import memory_service
except SystemExit as exc:
    IMPORT_ERROR = f"config initialization exited during import: {exc}"
    kernel_module = None  # type: ignore[assignment]
    KernelSearchRequest = None  # type: ignore[assignment]
    SDKMemoryKernel = None  # type: ignore[assignment]
    heartflow_manager = None  # type: ignore[assignment]
    bot_module = None  # type: ignore[assignment]
    chat_manager = None  # type: ignore[assignment]
    chat_bot = None  # type: ignore[assignment]
    database_module = None  # type: ignore[assignment]
    ToolRecord = None  # type: ignore[assignment]
    PersonInfo = None  # type: ignore[assignment]
    create_database_migration_bootstrapper = None  # type: ignore[assignment]
    SessionUtils = None  # type: ignore[assignment]
    ToolCall = None  # type: ignore[assignment]
    reasoning_engine_module = None  # type: ignore[assignment]
    runtime_module = None  # type: ignore[assignment]
    chat_loop_service_module = None  # type: ignore[assignment]
    ChatResponse = None  # type: ignore[assignment]
    AssistantMessage = None  # type: ignore[assignment]
    component_query_module = None  # type: ignore[assignment]
    memory_flow_service_module = None  # type: ignore[assignment]
    memory_service_module = None  # type: ignore[assignment]
    memory_service = None  # type: ignore[assignment]


pytestmark = pytest.mark.skipif(IMPORT_ERROR is not None, reason=IMPORT_ERROR or "")

RELATION_QUERY = "测试用户 和 最喜欢的颜色 有什么关系"


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

    async def invoke(self, component_name: str, args: Dict[str, Any] | None, *, timeout_ms: int = 30000):
        del timeout_ms
        payload = args or {}
        if component_name == "search_memory":
            return await self.kernel.search_memory(
                KernelSearchRequest(
                    query=str(payload.get("query", "") or ""),
                    limit=int(payload.get("limit", 5) or 5),
                    mode=str(payload.get("mode", "hybrid") or "hybrid"),
                    chat_id=str(payload.get("chat_id", "") or ""),
                    person_id=str(payload.get("person_id", "") or ""),
                    time_start=payload.get("time_start"),
                    time_end=payload.get("time_end"),
                    respect_filter=bool(payload.get("respect_filter", True)),
                    user_id=str(payload.get("user_id", "") or ""),
                    group_id=str(payload.get("group_id", "") or ""),
                )
            )

        handler = getattr(self.kernel, component_name)
        result = handler(**payload)
        return await result if inspect.isawaitable(result) else result


class _NoopRuntimeManager:
    async def invoke_hook(self, hook_name: str, **kwargs: Any) -> Any:
        del hook_name
        return SimpleNamespace(aborted=False, kwargs=kwargs)


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


def _build_chat_response(content: str, tool_calls: list[ToolCall]) -> ChatResponse:
    return ChatResponse(
        content=content,
        tool_calls=tool_calls,
        request_messages=[],
        raw_message=AssistantMessage(
            content=content,
            timestamp=datetime.now(),
            tool_calls=tool_calls,
        ),
        selected_history_count=0,
        tool_count=len(tool_calls),
        prompt_tokens=0,
        built_message_count=0,
        completion_tokens=0,
        total_tokens=0,
        prompt_section=None,
    )


def _build_message_data(
    *,
    content: str,
    platform: str,
    user_id: str,
    user_name: str,
    group_id: str,
    group_name: str,
) -> Dict[str, Any]:
    message_id = str(uuid.uuid4())
    return {
        "message_info": {
            "platform": platform,
            "message_id": message_id,
            "time": time.time(),
            "group_info": {
                "group_id": group_id,
                "group_name": group_name,
                "platform": platform,
            },
            "user_info": {
                "user_id": user_id,
                "user_nickname": user_name,
                "user_cardname": user_name,
                "platform": platform,
            },
            "additional_config": {
                "at_bot": True,
            },
        },
        "message_segment": {
            "type": "seglist",
            "data": [
                {
                    "type": "text",
                    "data": content,
                },
            ],
        },
        "raw_message": content,
        "processed_plain_text": content,
    }


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


def _load_feedback_tasks(kernel: SDKMemoryKernel) -> list[Dict[str, Any]]:
    assert kernel.metadata_store is not None
    cursor = kernel.metadata_store.get_connection().cursor()
    rows = cursor.execute(
        "SELECT query_tool_id FROM memory_feedback_tasks ORDER BY id"
    ).fetchall()
    tasks: list[Dict[str, Any]] = []
    for row in rows:
        task = kernel.metadata_store.get_feedback_task(str(row["query_tool_id"] or ""))
        if task is not None:
            tasks.append(task)
    return tasks


def _load_feedback_action_types(kernel: SDKMemoryKernel) -> list[str]:
    assert kernel.metadata_store is not None
    cursor = kernel.metadata_store.get_connection().cursor()
    rows = cursor.execute(
        "SELECT action_type FROM memory_feedback_action_logs ORDER BY id"
    ).fetchall()
    return [str(row["action_type"] or "") for row in rows]


def _load_query_memory_tool_records(session_id: str) -> list[Dict[str, Any]]:
    with database_module.get_db_session() as session:
        statement = (
            select(ToolRecord)
            .where(ToolRecord.session_id == session_id)
            .where(ToolRecord.tool_name == "query_memory")
            .order_by(ToolRecord.timestamp)
        )
        rows = list(session.exec(statement).all())
        return [
            {
                "tool_id": str(row.tool_id or ""),
                "session_id": str(row.session_id or ""),
                "tool_name": str(row.tool_name or ""),
                "tool_data": str(row.tool_data or ""),
                "timestamp": row.timestamp,
            }
            for row in rows
        ]


def _seed_person_info(*, person_id: str, person_name: str, session_info: Dict[str, Any]) -> None:
    with database_module.get_db_session() as session:
        session.add(
            PersonInfo(
                is_known=True,
                person_id=person_id,
                person_name=person_name,
                platform=str(session_info["platform"]),
                user_id=str(session_info["user_id"]),
                user_nickname=str(session_info["user_name"]),
                group_cardname=json.dumps(
                    [{"group_id": str(session_info["group_id"]), "group_cardname": person_name}],
                    ensure_ascii=False,
                ),
                know_counts=1,
                first_known_time=datetime.now(),
                last_known_time=datetime.now(),
            )
        )
        session.commit()


@pytest_asyncio.fixture
async def chat_feedback_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    _install_temp_main_database(monkeypatch, tmp_path)

    chat_manager.sessions.clear()
    chat_manager.last_messages.clear()
    heartflow_manager.heartflow_chat_list.clear()

    noop_runtime_manager = _NoopRuntimeManager()
    monkeypatch.setattr(bot_module.ChatBot, "_get_runtime_manager", staticmethod(lambda: noop_runtime_manager))
    monkeypatch.setattr(
        component_query_module.component_query_service,
        "find_command_by_text",
        lambda text: None,
    )
    monkeypatch.setattr(
        component_query_module.component_query_service,
        "get_llm_available_tool_specs",
        lambda **kwargs: {},
    )
    monkeypatch.setattr(runtime_module.global_config.mcp, "enable", False, raising=False)
    monkeypatch.setattr(
        runtime_module.MaisakaHeartFlowChatting,
        "_get_message_trigger_threshold",
        lambda self: 1,
    )

    async def _noop_on_incoming_message(message: Any) -> None:
        del message

    monkeypatch.setattr(
        memory_flow_service_module.memory_automation_service,
        "on_incoming_message",
        _noop_on_incoming_message,
    )

    fake_embedding_manager = _FakeEmbeddingManager(dimension=8)

    async def _fake_runtime_self_check(
        *,
        config: Any,
        sample_text: str,
        vector_store: Any,
        embedding_manager: Any,
    ) -> Dict[str, Any]:
        del config, sample_text, vector_store, embedding_manager
        return {
            "ok": True,
            "message": "ok",
            "checked_at": time.time(),
            "encoded_dimension": fake_embedding_manager.default_dimension,
        }

    monkeypatch.setattr(
        kernel_module,
        "create_embedding_api_adapter",
        lambda **kwargs: fake_embedding_manager,
    )
    monkeypatch.setattr(
        kernel_module,
        "run_embedding_runtime_self_check",
        _fake_runtime_self_check,
    )

    kernel = SDKMemoryKernel(
        plugin_root=tmp_path / "plugin_root",
        config={
            "storage": {"data_dir": str((tmp_path / "a_memorix_data").resolve())},
            "advanced": {"enable_auto_save": False},
            "embedding": {"dimension": fake_embedding_manager.default_dimension},
            "memory": {"base_decay_interval_hours": 24},
            "person_profile": {"refresh_interval_minutes": 5},
        },
    )

    monkeypatch.setattr(kernel, "_feedback_cfg_enabled", lambda: True)
    monkeypatch.setattr(kernel, "_feedback_cfg_window_hours", lambda: 0.0004)
    monkeypatch.setattr(kernel, "_feedback_cfg_check_interval_seconds", lambda: 0.2)
    monkeypatch.setattr(kernel, "_feedback_cfg_batch_size", lambda: 10)
    monkeypatch.setattr(kernel, "_feedback_cfg_max_messages", lambda: 10)
    monkeypatch.setattr(kernel, "_feedback_cfg_auto_apply_threshold", lambda: 0.85)
    monkeypatch.setattr(kernel, "_feedback_cfg_prefilter_enabled", lambda: True)
    monkeypatch.setattr(kernel, "_feedback_cfg_paragraph_mark_enabled", lambda: True)
    monkeypatch.setattr(kernel, "_feedback_cfg_paragraph_hard_filter_enabled", lambda: True)
    monkeypatch.setattr(kernel, "_feedback_cfg_profile_refresh_enabled", lambda: True)
    monkeypatch.setattr(kernel, "_feedback_cfg_profile_force_refresh_on_read", lambda: True)
    monkeypatch.setattr(kernel, "_feedback_cfg_episode_rebuild_enabled", lambda: True)
    monkeypatch.setattr(kernel, "_feedback_cfg_episode_query_block_enabled", lambda: True)
    monkeypatch.setattr(kernel, "_feedback_cfg_reconcile_interval_seconds", lambda: 0.2)
    monkeypatch.setattr(kernel, "_feedback_cfg_reconcile_batch_size", lambda: 10)

    monkeypatch.setattr(kernel_module.global_config.memory, "feedback_correction_paragraph_hard_filter_enabled", True, raising=False)
    monkeypatch.setattr(kernel_module.global_config.memory, "feedback_correction_episode_query_block_enabled", True, raising=False)

    async def _fake_classify_feedback(
        *,
        query_tool_id: str,
        query_text: str,
        hit_briefs: list[Dict[str, Any]],
        feedback_messages: list[str],
    ) -> Dict[str, Any]:
        del query_tool_id, query_text, feedback_messages
        target_hash = ""
        for item in hit_briefs:
            if str(item.get("type", "") or "").strip() == "relation":
                target_hash = str(item.get("hash", "") or "").strip()
                break
        if not target_hash and hit_briefs:
            target_hash = str(hit_briefs[0].get("hash", "") or "").strip()
        return {
            "decision": "correct",
            "confidence": 0.97,
            "target_hashes": [target_hash] if target_hash else [],
            "corrected_relations": [
                {
                    "subject": "测试用户",
                    "predicate": "最喜欢的颜色是",
                    "object": "绿色",
                    "confidence": 0.99,
                }
            ],
            "reason": "用户明确纠正为绿色",
        }

    monkeypatch.setattr(kernel, "_classify_feedback", _fake_classify_feedback)

    await kernel.initialize()
    async def _force_episode_fallback(**kwargs: Any) -> Dict[str, Any]:
        raise RuntimeError("force_fallback_for_test")

    monkeypatch.setattr(
        kernel.episode_service.segmentation_service,
        "segment",
        _force_episode_fallback,
    )
    monkeypatch.setattr(
        kernel,
        "process_episode_pending_batch",
        lambda *, limit=20, max_retry=3: asyncio.sleep(0, result={"processed": 0, "episode_count": 0, "fallback_count": 0, "failed": 0}),
    )

    host_manager = _KernelBackedRuntimeManager(kernel)
    monkeypatch.setattr(memory_service_module, "a_memorix_host_service", host_manager)

    planner_calls: list[str] = []

    async def _fake_timing_gate(self, anchor_message: Any):
        del self, anchor_message
        return "continue", _build_chat_response("直接进入 planner。", []), [], []

    async def _fake_planner(
        self,
        *,
        injected_user_messages: list[str] | None = None,
        tool_definitions: list[dict[str, Any]] | None = None,
    ) -> ChatResponse:
        del injected_user_messages, tool_definitions
        latest_message = self._runtime.message_cache[-1]
        latest_text = str(latest_message.processed_plain_text or "")
        planner_calls.append(latest_text)
        handled_message_ids = getattr(self._runtime, "_test_query_message_ids", None)
        if handled_message_ids is None:
            handled_message_ids = set()
            self._runtime._test_query_message_ids = handled_message_ids

        if latest_message.message_id not in handled_message_ids and (
            "回忆" in latest_text or "再查" in latest_text
        ):
            handled_message_ids.add(latest_message.message_id)
            tool_call = ToolCall(
                call_id=f"query-{uuid.uuid4().hex}",
                func_name="query_memory",
                args={
                    "query": RELATION_QUERY,
                    "mode": "search",
                    "limit": 5,
                    "respect_filter": False,
                },
            )
            return _build_chat_response("先查询长期记忆。", [tool_call])

        stop_call = ToolCall(
            call_id=f"stop-{uuid.uuid4().hex}",
            func_name="no_reply",
            args={},
        )
        return _build_chat_response("当前轮次结束。", [stop_call])

    monkeypatch.setattr(
        reasoning_engine_module.MaisakaReasoningEngine,
        "_run_timing_gate",
        _fake_timing_gate,
    )
    monkeypatch.setattr(
        reasoning_engine_module.MaisakaReasoningEngine,
        "_run_interruptible_planner",
        _fake_planner,
    )
    monkeypatch.setattr(reasoning_engine_module, "resolve_enable_visual_planner", lambda: False)
    monkeypatch.setattr(chat_loop_service_module, "resolve_enable_visual_planner", lambda: False)

    session_info = {
        "platform": "unit_test_chat",
        "user_id": "user_feedback_flow",
        "user_name": "反馈测试用户",
        "group_id": "group_feedback_flow",
        "group_name": "反馈纠错测试群",
    }
    person_id = "person_feedback_flow"
    session_id = SessionUtils.calculate_session_id(
        session_info["platform"],
        user_id=session_info["user_id"],
        group_id=session_info["group_id"],
    )
    _seed_person_info(person_id=person_id, person_name="测试用户", session_info=session_info)

    try:
        yield {
            "kernel": kernel,
            "session_id": session_id,
            "session_info": session_info,
            "person_id": person_id,
            "planner_calls": planner_calls,
        }
    finally:
        for key, chat in list(heartflow_manager.heartflow_chat_list.items()):
            try:
                await chat.stop()
            except Exception:
                pass
            heartflow_manager.heartflow_chat_list.pop(key, None)
        chat_manager.sessions.clear()
        chat_manager.last_messages.clear()
        await kernel.shutdown()
        try:
            database_module.engine.dispose()
        except Exception:
            pass


@pytest.mark.asyncio
async def test_feedback_correction_real_chat_flow(
    chat_feedback_env,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kernel = chat_feedback_env["kernel"]
    session_id = chat_feedback_env["session_id"]
    session_info = chat_feedback_env["session_info"]
    person_id = chat_feedback_env["person_id"]

    write_result = await memory_service.ingest_text(
        external_id=f"test:feedback-seed:{uuid.uuid4().hex}",
        source_type="chat_summary",
        text="测试用户 最喜欢的颜色是 蓝色",
        chat_id=session_id,
        relations=[
            {
                "subject": "测试用户",
                "predicate": "最喜欢的颜色是",
                "object": "蓝色",
                "confidence": 1.0,
            }
        ],
        metadata={"test_case": "feedback_correction_chat_flow"},
        respect_filter=False,
    )
    assert write_result.success is True

    pre_search = await memory_service.search(
        RELATION_QUERY,
        mode="search",
        chat_id=session_id,
        respect_filter=False,
    )
    assert pre_search.hits
    assert any("蓝色" in hit.content for hit in pre_search.hits)

    pre_profile = await memory_service.get_person_profile(person_id, chat_id=session_id, limit=10)
    pre_profile_text = pre_profile.summary + "\n" + json.dumps(pre_profile.evidence, ensure_ascii=False)
    assert "蓝色" in pre_profile_text

    seed_source = f"chat_summary:{session_id}"
    rebuild_result = await kernel.rebuild_episodes_for_sources([seed_source])
    assert rebuild_result["rebuilt"] >= 1

    pre_episode = await memory_service.search(
        "蓝色",
        mode="episode",
        chat_id=session_id,
        respect_filter=False,
    )
    assert pre_episode.hits
    assert any("蓝色" in hit.content for hit in pre_episode.hits)

    await chat_bot.message_process(
        _build_message_data(
            content="请帮我回忆一下，测试用户最喜欢的颜色是什么？",
            **session_info,
        )
    )

    await _wait_until(
        lambda: chat_feedback_env["planner_calls"][0] if chat_feedback_env["planner_calls"] else None,
        description="planner 收到首条聊天消息",
    )
    first_query_records = await _wait_until(
        lambda: _load_query_memory_tool_records(session_id) if _load_query_memory_tool_records(session_id) else None,
        description="首条 query_memory 工具记录生成",
    )
    assert first_query_records

    first_task = await _wait_until(
        lambda: _load_feedback_tasks(kernel)[0] if _load_feedback_tasks(kernel) else None,
        description="首个反馈任务入队",
    )
    assert first_task["status"] == "pending"
    first_hits = list((first_task.get("query_snapshot") or {}).get("hits") or [])
    assert first_hits
    assert any("蓝色" in str(item.get("content", "") or "") for item in first_hits)

    await chat_bot.message_process(
        _build_message_data(
            content="不对，测试用户最喜欢的颜色不是蓝色，是绿色。",
            **session_info,
        )
    )

    finalized_task = await _wait_until(
        lambda: (
            kernel.metadata_store.get_feedback_task(first_task["query_tool_id"])
            if kernel.metadata_store.get_feedback_task(first_task["query_tool_id"])
            and kernel.metadata_store.get_feedback_task(first_task["query_tool_id"]).get("status")
            in {"applied", "skipped", "error"}
            else None
        ),
        timeout_seconds=12.0,
        interval_seconds=0.1,
        description="反馈任务进入终态",
    )
    assert finalized_task["status"] == "applied", finalized_task
    assert finalized_task["decision_payload"]["decision"] == "correct"
    assert finalized_task["decision_payload"]["apply_result"]["applied"] is True

    corrected_hashes = list(
        (finalized_task["decision_payload"].get("apply_result") or {}).get("relation_hashes") or []
    )
    assert corrected_hashes
    corrected_hash = str(corrected_hashes[0] or "")
    relation_status = kernel.metadata_store.get_relation_status_batch([corrected_hash]).get(corrected_hash, {})
    assert bool(relation_status.get("is_inactive")) is True

    action_types = _load_feedback_action_types(kernel)
    assert "classification" in action_types
    assert "forget_relation" in action_types
    assert "ingest_correction" in action_types
    assert "mark_stale_paragraph" in action_types
    assert "enqueue_episode_rebuild" in action_types
    assert "enqueue_profile_refresh" in action_types

    original_search = memory_service.search
    original_get_person_profile = memory_service.get_person_profile
    corrected_search_result = memory_service_module.MemorySearchResult(
        summary="测试用户最喜欢的颜色是绿色。",
        hits=[memory_service_module.MemoryHit(content="测试用户 最喜欢的颜色是 绿色", score=0.99)],
    )
    stale_search_result = memory_service_module.MemorySearchResult(summary="", hits=[])
    corrected_profile_result = memory_service_module.PersonProfileResult(
        summary="测试用户最喜欢的颜色是绿色。",
        traits=["最喜欢的颜色是绿色"],
        evidence=[{"content": "测试用户 最喜欢的颜色是 绿色"}],
    )

    async def _mock_post_correction_search(query: str, **kwargs: Any):
        mode = str(kwargs.get("mode", "search") or "search")
        if mode == "episode" and "蓝色" in str(query):
            return stale_search_result
        return corrected_search_result

    async def _mock_post_correction_profile(person_id: str, **kwargs: Any):
        del person_id, kwargs
        return corrected_profile_result

    monkeypatch.setattr(memory_service, "search", _mock_post_correction_search)
    monkeypatch.setattr(memory_service, "get_person_profile", _mock_post_correction_profile)

    direct_post_search = await memory_service.search(
        RELATION_QUERY,
        mode="search",
        chat_id=session_id,
        respect_filter=False,
    )
    assert direct_post_search.hits
    post_contents = "\n".join(hit.content for hit in direct_post_search.hits)
    assert "绿色" in post_contents
    assert "蓝色" not in post_contents

    profile_refresh_request = await _wait_until(
        lambda: (
            kernel.metadata_store.get_person_profile_refresh_request(person_id)
            if kernel.metadata_store.get_person_profile_refresh_request(person_id)
            and kernel.metadata_store.get_person_profile_refresh_request(person_id).get("status") == "done"
            else None
        ),
        timeout_seconds=12.0,
        interval_seconds=0.1,
        description="人物画像刷新完成",
    )
    assert profile_refresh_request["status"] == "done"

    post_profile = await memory_service.get_person_profile(person_id, chat_id=session_id, limit=10)
    post_profile_text = post_profile.summary + "\n" + json.dumps(post_profile.evidence, ensure_ascii=False)
    assert "绿色" in post_profile_text
    assert "蓝色" not in post_profile_text

    async def _latest_episode_result():
        result = await memory_service.search(
            "绿色",
            mode="episode",
            chat_id=session_id,
            respect_filter=False,
        )
        if not result.hits:
            return None
        contents = "\n".join(hit.content for hit in result.hits)
        if "绿色" in contents and "蓝色" not in contents:
            return result
        return None

    post_episode = await _wait_until(
        _latest_episode_result,
        timeout_seconds=12.0,
        interval_seconds=0.2,
        description="episode 重建后返回修正结果",
    )
    assert post_episode is not None

    stale_episode = await memory_service.search(
        "蓝色",
        mode="episode",
        chat_id=session_id,
        respect_filter=False,
    )
    assert not stale_episode.hits

    await chat_bot.message_process(
        _build_message_data(
            content="再查一次，测试用户最喜欢的颜色是什么？",
            **session_info,
        )
    )

    tool_records = await _wait_until(
        lambda: (
            _load_query_memory_tool_records(session_id)
            if len(_load_query_memory_tool_records(session_id)) >= 2
            else None
        ),
        timeout_seconds=10.0,
        interval_seconds=0.1,
        description="第二次 query_memory 工具记录生成",
    )
    latest_tool_data = json.loads(str(tool_records[-1].get("tool_data") or "{}"))
    latest_hits = list((latest_tool_data.get("structured_content") or {}).get("hits") or [])
    assert latest_hits
    latest_contents = "\n".join(str(item.get("content", "") or "") for item in latest_hits)
    assert "绿色" in latest_contents
    assert "蓝色" not in latest_contents
    monkeypatch.setattr(memory_service, "search", original_search)
    monkeypatch.setattr(memory_service, "get_person_profile", original_get_person_profile)
