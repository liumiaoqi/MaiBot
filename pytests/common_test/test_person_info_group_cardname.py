"""人物信息群名片字段兼容测试。"""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import json
import sys

import pytest

from src.common.data_models.person_info_data_model import dump_group_cardname_records, parse_group_cardname_json


class _DummyLogger:
    """模拟日志记录器。"""

    def debug(self, message: str) -> None:
        """记录调试日志。

        Args:
            message: 日志内容。
        """
        del message

    def info(self, message: str) -> None:
        """记录信息日志。

        Args:
            message: 日志内容。
        """
        del message

    def warning(self, message: str) -> None:
        """记录警告日志。

        Args:
            message: 日志内容。
        """
        del message

    def error(self, message: str) -> None:
        """记录错误日志。

        Args:
            message: 日志内容。
        """
        del message


class _DummyStatement:
    """模拟 SQL 查询语句对象。"""

    def where(self, condition: Any) -> "_DummyStatement":
        """附加过滤条件。

        Args:
            condition: 过滤条件。

        Returns:
            _DummyStatement: 当前语句对象。
        """
        del condition
        return self

    def limit(self, value: int) -> "_DummyStatement":
        """限制返回条数。

        Args:
            value: 条数限制。

        Returns:
            _DummyStatement: 当前语句对象。
        """
        del value
        return self


class _DummyColumn:
    """模拟 SQLModel 列对象。"""

    def is_not(self, value: Any) -> "_DummyColumn":
        """模拟 `IS NOT` 条件构造。

        Args:
            value: 比较值。

        Returns:
            _DummyColumn: 当前列对象。
        """
        del value
        return self

    def __eq__(self, other: Any) -> "_DummyColumn":
        """模拟等值条件构造。

        Args:
            other: 比较值。

        Returns:
            _DummyColumn: 当前列对象。
        """
        del other
        return self


class _DummyResult:
    """模拟数据库查询结果。"""

    def __init__(self, record: Any) -> None:
        """初始化查询结果。

        Args:
            record: 待返回的首条记录。
        """
        self._record = record

    def first(self) -> Any:
        """返回第一条记录。

        Returns:
            Any: 首条记录。
        """
        return self._record

    def all(self) -> list[Any]:
        """返回全部结果。

        Returns:
            list[Any]: 结果列表。
        """
        if self._record is None:
            return []
        return self._record if isinstance(self._record, list) else [self._record]


class _DummySession:
    """模拟数据库 Session。"""

    def __init__(self, record: Any) -> None:
        """初始化 Session。

        Args:
            record: `first()` 应返回的记录。
        """
        self.record = record
        self.added_records: list[Any] = []

    def __enter__(self) -> "_DummySession":
        """进入上下文管理器。

        Returns:
            _DummySession: 当前 Session。
        """
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """退出上下文管理器。

        Args:
            exc_type: 异常类型。
            exc_val: 异常值。
            exc_tb: 异常回溯。
        """
        del exc_type
        del exc_val
        del exc_tb

    def exec(self, statement: Any) -> _DummyResult:
        """执行查询。

        Args:
            statement: 查询语句。

        Returns:
            _DummyResult: 模拟结果对象。
        """
        del statement
        return _DummyResult(self.record)

    def add(self, record: Any) -> None:
        """记录被添加的对象。

        Args:
            record: 被写入 Session 的对象。
        """
        self.added_records.append(record)


class _DummyPersonInfoRecord:
    """模拟 `PersonInfo` ORM 模型。"""

    person_id = "person_id"
    person_name = "person_name"

    def __init__(self, **kwargs: Any) -> None:
        """使用关键字参数初始化记录对象。

        Args:
            **kwargs: 字段值。
        """
        for key, value in kwargs.items():
            setattr(self, key, value)


def _load_person_module(monkeypatch: pytest.MonkeyPatch, session: _DummySession) -> ModuleType:
    """加载带依赖桩的 `person_info` 模块。

    Args:
        monkeypatch: Pytest monkeypatch 工具。
        session: 提供给模块使用的假数据库 Session。

    Returns:
        ModuleType: 加载后的模块对象。
    """
    logger_module = ModuleType("src.common.logger")
    logger_module.get_logger = lambda name: _DummyLogger()
    monkeypatch.setitem(sys.modules, "src.common.logger", logger_module)

    database_module = ModuleType("src.common.database.database")
    database_module.get_db_session = lambda: session
    monkeypatch.setitem(sys.modules, "src.common.database.database", database_module)

    database_model_module = ModuleType("src.common.database.database_model")
    database_model_module.PersonInfo = _DummyPersonInfoRecord
    monkeypatch.setitem(sys.modules, "src.common.database.database_model", database_model_module)

    llm_module = ModuleType("src.llm_models.utils_model")

    class _DummyLLMRequest:
        """模拟 LLMRequest。"""

        def __init__(self, model_set: Any, request_type: str) -> None:
            """初始化假请求对象。

            Args:
                model_set: 模型配置。
                request_type: 请求类型。
            """
            del model_set
            del request_type

    llm_module.LLMRequest = _DummyLLMRequest
    monkeypatch.setitem(sys.modules, "src.llm_models.utils_model", llm_module)

    config_module = ModuleType("src.config.config")
    config_module.global_config = SimpleNamespace(bot=SimpleNamespace(nickname="MaiBot"))
    config_module.model_config = SimpleNamespace(model_task_config=SimpleNamespace(tool_use="tool_use", utils="utils"))
    monkeypatch.setitem(sys.modules, "src.config.config", config_module)

    chat_manager_module = ModuleType("src.chat.message_receive.chat_manager")
    chat_manager_module.chat_manager = SimpleNamespace()
    monkeypatch.setitem(sys.modules, "src.chat.message_receive.chat_manager", chat_manager_module)

    module_path = Path(__file__).resolve().parents[2] / "src" / "person_info" / "person_info.py"
    spec = spec_from_file_location("person_info_group_cardname_test_module", module_path)
    assert spec is not None and spec.loader is not None

    module = module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)

    monkeypatch.setattr(module, "select", lambda *args: _DummyStatement())
    monkeypatch.setattr(module, "col", lambda field: _DummyColumn())
    return module


def test_parse_group_cardname_json_uses_canonical_key() -> None:
    """群名片 JSON 解析应只使用 `group_cardname` 键名。"""
    parsed = parse_group_cardname_json(
        json.dumps(
            [
                {"group_id": "1001", "group_cardname": "现行字段"},
            ],
            ensure_ascii=False,
        )
    )

    assert parsed is not None
    assert [(item.group_id, item.group_cardname) for item in parsed] == [
        ("1001", "现行字段"),
    ]


def test_dump_group_cardname_records_uses_canonical_key() -> None:
    """群名片序列化应输出 `group_cardname` 键名。"""
    dumped = dump_group_cardname_records(
        [
            {"group_id": "1001", "group_cardname": "群昵称"},
        ]
    )

    assert json.loads(dumped) == [{"group_id": "1001", "group_cardname": "群昵称"}]


def test_person_sync_to_database_uses_group_cardname_field(monkeypatch: pytest.MonkeyPatch) -> None:
    """同步人物信息时应写入数据库模型的 `group_cardname` 字段。"""
    record = _DummyPersonInfoRecord()
    session = _DummySession(record)
    module = _load_person_module(monkeypatch, session)

    person = module.Person.__new__(module.Person)
    person.is_known = True
    person.person_id = "person-1"
    person.platform = "qq"
    person.user_id = "10001"
    person.nickname = "看番的龙"
    person.person_name = "看番的龙"
    person.name_reason = "测试"
    person.know_times = 1
    person.know_since = 1700000000.0
    person.last_know = 1700000100.0
    person.memory_points = ["喜好:番剧:0.8"]
    person.group_cardname_list = [{"group_id": "20001", "group_cardname": "白泽大人"}]

    person.sync_to_database()

    assert record.group_cardname == '[{"group_id": "20001", "group_cardname": "白泽大人"}]'
    assert not hasattr(record, "group_nickname")


def test_person_load_from_database_normalizes_group_cardname_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    """从数据库加载人物信息时应读取标准 `group_cardname` 结构。"""
    record = _DummyPersonInfoRecord(
        user_id="10001",
        platform="qq",
        is_known=True,
        user_nickname="看番的龙",
        person_name="看番的龙",
        name_reason=None,
        know_counts=2,
        memory_points='["喜好:番剧:0.8"]',
        group_cardname=json.dumps(
            [
                {"group_id": "20001", "group_cardname": "白泽大人"},
            ],
            ensure_ascii=False,
        ),
    )
    session = _DummySession(record)
    module = _load_person_module(monkeypatch, session)

    person = module.Person.__new__(module.Person)
    person.person_id = "person-1"
    person.memory_points = []
    person.group_cardname_list = []

    person.load_from_database()

    assert person.group_cardname_list == [
        {"group_id": "20001", "group_cardname": "白泽大人"},
    ]
