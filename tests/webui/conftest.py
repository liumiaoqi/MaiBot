"""WebUI 测试基础设施 — conftest.py"""

import shutil
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlmodel import SQLModel, Session, create_engine
from starlette.testclient import TestClient

from src.webui.app import create_app
from src.webui.core import get_token_manager


@pytest.fixture(autouse=True)
def _register_webui_ports():
    """注册 WebUI 所需 Port（anti_crawler 模块 import 时即读配置；agent/auth 路由按需读取）。"""
    from src.core.adapters.agent_config_port import set_agent_config_provider
    from src.core.app_config_port_registry import (
        reset_app_config_port,
        set_app_config_port,
    )
    from src.core.bot_config_port_registry import (
        reset_bot_config_port,
        set_bot_config_port,
    )

    set_app_config_port(
        SimpleNamespace(
            get_webui_anti_crawler_mode=lambda: "off",
            get_webui_allowed_ips=lambda: [],
            get_webui_trusted_proxies=lambda: [],
            get_webui_trust_xff=lambda: False,
            get_webui_secure_cookie=lambda: False,
            get_webui_mode=lambda: "development",
            get_a_memorix_full_config=lambda: {},
        )
    )
    set_bot_config_port(
        SimpleNamespace(
            get_bot_platform=lambda: "aiocqhttp",
            get_bot_primary_account=lambda: "",
            get_bot_platforms=lambda: [],
            get_bot_nickname=lambda: "MaiBot",
            get_bot_qq_account=lambda platform: 0,
        )
    )
    set_agent_config_provider(
        SimpleNamespace(
            get_agent=lambda agent_id: None,
            list_agents=lambda: [],
            get_default_agent=lambda: None,
            has_agent=lambda agent_id: False,
            reload=lambda: None,
            reload_agent=lambda agent_id: False,
            load=lambda: None,
        )
    )
    yield
    reset_app_config_port()
    reset_bot_config_port()


@pytest.fixture
def app():
    return create_app(enable_static=False)


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


@pytest.fixture
def auth_client(client):
    token_manager = get_token_manager()
    token = token_manager.get_token()
    client.cookies.set("maibot_session", token)
    return client


def assert_api_success(response, expected_code: int = 200):
    assert response.status_code == expected_code, f"状态码 {response.status_code}: {response.text}"
    data = response.json()
    if "code" in data:
        assert data["code"] == 0, f"业务错误: {data}"
    if "error_code" in data:
        pytest.fail(f"错误响应: {data}")


def assert_api_error(response, expected_error_code: str, expected_status: int = None):
    if expected_status:
        assert response.status_code == expected_status, f"状态码 {response.status_code}: {response.text}"
    data = response.json()
    assert "error_code" in data, f"非错误响应: {data}"
    assert data["error_code"] == expected_error_code, f"错误码不匹配: {data}"


# ── T2.3 db_isolation fixture ──────────────────────────────────────

@pytest.fixture
def db_isolation():
    """方案 A：内存 SQLite，patch get_db_session 指向内存引擎。

    用于只读测试（快）和写测试（完全隔离，测试结束数据消失）。
    真实 DB + 事务回滚方案可用 db_isolation_real fixture。
    """
    import src.common.database.database as db_module
    import src.common.database.database_model  # noqa: F401 — 确保模型加载

    in_memory_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(in_memory_engine)

    from sqlalchemy.orm import sessionmaker

    in_memory_session_factory = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=in_memory_engine,
        class_=Session,
        expire_on_commit=False,
    )

    @contextmanager
    def _patched_get_db_session(auto_commit: bool = True):
        session = in_memory_session_factory()
        try:
            yield session
            if auto_commit:
                session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    with patch.object(db_module, "get_db_session", _patched_get_db_session), \
         patch.object(db_module, "initialize_database", lambda: None):
        yield in_memory_engine

    in_memory_engine.dispose()


@pytest.fixture
def db_isolation_real():
    """方案 B：真实 DB + 事务回滚。

    用于需要真实数据库 schema/数据的写操作测试。
    测试结束 rollback，真实数据库无残留。
    """
    import src.common.database.database as db_module

    db_module.initialize_database()
    real_engine = db_module.engine

    from sqlalchemy.orm import sessionmaker

    rollback_session_factory = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=real_engine,
        class_=Session,
        expire_on_commit=False,
    )

    _sessions = []

    @contextmanager
    def _patched_get_db_session(auto_commit: bool = True):
        session = rollback_session_factory()
        _sessions.append(session)
        try:
            yield session
            if auto_commit:
                session.flush()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    with patch.object(db_module, "get_db_session", _patched_get_db_session):
        yield real_engine

    for s in _sessions:
        try:
            s.rollback()
            s.close()
        except Exception:
            pass


# ── T2.4 config_file_isolation fixture ─────────────────────────────

@pytest.fixture
def config_file_isolation(tmp_path):
    """复制真实配置到 tmp_path，patch CONFIG_DIR 指向 tmp_path。

    测试结束后自动清理 tmp_path，真实 bot_config.toml 不受影响。
    """
    import src.config.config as config_module
    import src.config.startup_bindings as startup_module

    real_config_dir = Path(config_module.CONFIG_DIR)

    for config_file in ("bot_config.toml", "model_config.toml"):
        src_file = real_config_dir / config_file
        if src_file.exists():
            shutil.copy2(src_file, tmp_path / config_file)

    patches = [
        patch.object(config_module, "CONFIG_DIR", tmp_path),
        patch.object(config_module, "BOT_CONFIG_PATH", (tmp_path / "bot_config.toml").resolve()),
        patch.object(config_module, "MODEL_CONFIG_PATH", (tmp_path / "model_config.toml").resolve()),
        patch.object(startup_module, "CONFIG_DIR", tmp_path),
        patch.object(startup_module, "BOT_CONFIG_PATH", (tmp_path / "bot_config.toml").resolve()),
    ]

    for p in patches:
        p.start()

    try:
        yield tmp_path
    finally:
        for p in patches:
            p.stop()
