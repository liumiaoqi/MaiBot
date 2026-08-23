"""person_info 单元测试。

覆盖纯函数 get_person_id / calculate_string_similarity / levenshtein_distance /
_to_group_cardname_records 的行为，以及 Person 类的注册、参数校验与
bot_self 分支（数据库与 port 通过 monkeypatch 注入）。
"""

import hashlib
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.person_info.person_info import (
    Person,  # noqa: TID251
    calculate_string_similarity,
    get_person_id,
    levenshtein_distance,
)


class TestGetPersonId:
    """get_person_id 行为测试。"""

    def test_basic_id_generation(self):
        result = get_person_id("qq", "12345")
        expected = hashlib.md5("qq_12345".encode()).hexdigest()
        assert result == expected

    def test_platform_with_dash_strips_prefix(self):
        # platform 含 "-" → 取 split("-")[1]
        result = get_person_id("napcat-qq", "123")
        expected = hashlib.md5("qq_123".encode()).hexdigest()
        assert result == expected

    def test_user_id_int_converted_to_str(self):
        result = get_person_id("qq", 123)
        expected = hashlib.md5("qq_123".encode()).hexdigest()
        assert result == expected

    def test_deterministic(self):
        # 相同输入相同输出
        assert get_person_id("qq", "123") == get_person_id("qq", "123")

    def test_different_inputs_different_ids(self):
        assert get_person_id("qq", "123") != get_person_id("qq", "456")
        assert get_person_id("qq", "123") != get_person_id("tg", "123")

    def test_returns_hex_string(self):
        result = get_person_id("qq", "123")
        assert len(result) == 32
        assert all(c in "0123456789abcdef" for c in result)


class TestLevenshteinDistance:
    """levenshtein_distance 行为测试。"""

    def test_identical_strings(self):
        assert levenshtein_distance("abc", "abc") == 0

    def test_empty_to_string(self):
        assert levenshtein_distance("", "abc") == 3

    def test_string_to_empty(self):
        assert levenshtein_distance("abc", "") == 3

    def test_both_empty(self):
        assert levenshtein_distance("", "") == 0

    def test_single_substitution(self):
        assert levenshtein_distance("abc", "abd") == 1

    def test_single_insertion(self):
        assert levenshtein_distance("abc", "abxc") == 1

    def test_single_deletion(self):
        assert levenshtein_distance("abxc", "abc") == 1

    def test_kitten_sitting(self):
        # 经典案例：kitten → sitting = 3
        assert levenshtein_distance("kitten", "sitting") == 3

    def test_chinese_strings(self):
        assert levenshtein_distance("你好", "你好") == 0
        assert levenshtein_distance("你好", "世界") == 2

    def test_symmetric(self):
        # 编辑距离对称
        s1, s2 = "abcdef", "azcdef"
        assert levenshtein_distance(s1, s2) == levenshtein_distance(s2, s1)


class TestCalculateStringSimilarity:
    """calculate_string_similarity 行为测试。"""

    def test_identical_strings_return_one(self):
        assert calculate_string_similarity("abc", "abc") == 1.0

    def test_both_empty_return_one(self):
        # s1 == s2 短路返回 1.0
        assert calculate_string_similarity("", "") == 1.0

    def test_one_empty_return_zero(self):
        assert calculate_string_similarity("", "abc") == 0.0
        assert calculate_string_similarity("abc", "") == 0.0

    def test_single_substitution_similarity(self):
        # distance=1, max_len=3 → 1 - 1/3
        assert calculate_string_similarity("abc", "abd") == pytest.approx(2 / 3)

    def test_completely_different(self):
        assert calculate_string_similarity("abc", "xyz") == pytest.approx(0.0)

    def test_range_zero_to_one(self):
        # 相似度始终在 [0, 1]
        result = calculate_string_similarity("hello", "world")
        assert 0.0 <= result <= 1.0

    def test_chinese_similarity(self):
        result = calculate_string_similarity("你好世界", "你好朋友")
        # 2 字不同 / 4 字 → 0.5
        assert result == pytest.approx(0.5)


class TestPersonRegisterPerson:
    """Person.register_person 行为测试。"""

    def test_missing_platform_returns_none(self):
        result = Person.register_person(platform="", user_id="123", nickname="nick")
        assert result is None

    def test_missing_user_id_returns_none(self):
        result = Person.register_person(platform="qq", user_id="", nickname="nick")
        assert result is None

    def test_missing_nickname_returns_none(self):
        result = Person.register_person(platform="qq", user_id="123", nickname="")
        assert result is None

    def test_register_new_person(self, monkeypatch):
        # mock is_person_known 返回 False（新用户）
        monkeypatch.setattr("src.person_info.person_info.is_person_known", lambda **kw: False)
        # mock Person.sync_to_database 避免数据库写入
        monkeypatch.setattr(Person, "sync_to_database", lambda self: None)
        # mock is_bot_self 返回 False
        monkeypatch.setattr("src.core.identity.is_bot_self", lambda p, u: False)

        result = Person.register_person(platform="qq", user_id="123", nickname="测试用户")
        assert result is not None
        assert result.platform == "qq"
        assert result.user_id == "123"
        assert result.nickname == "测试用户"
        assert result.is_known is True
        assert result.person_name == "测试用户"

    def test_register_existing_person_returns_person(self, monkeypatch):
        # mock is_person_known 返回 True（已存在）
        monkeypatch.setattr("src.person_info.person_info.is_person_known", lambda **kw: True)
        # mock Person.__init__ 避免数据库加载
        original_init = Person.__init__

        def mock_init(self, *args, **kwargs):
            self.person_id = kwargs.get("person_id", "")
            self.group_cardname_list = []

        monkeypatch.setattr(Person, "__init__", mock_init)
        monkeypatch.setattr(Person, "add_group_nick_name", lambda self, gid, gn: None)

        result = Person.register_person(platform="qq", user_id="123", nickname="老用户")
        assert result is not None

        # 恢复
        monkeypatch.setattr(Person, "__init__", original_init)


class TestPersonInitBotSelf:
    """Person.__init__ bot_self 分支测试。"""

    def test_bot_self_init(self, monkeypatch):
        # mock is_bot_self 返回 True
        monkeypatch.setattr("src.core.identity.is_bot_self", lambda p, u: True)
        # mock bot_config_port
        mock_port = SimpleNamespace(
            get_bot_nickname=lambda: "MaiBot",
        )
        monkeypatch.setattr(
            "src.person_info.person_info.get_bot_config_port",
            lambda: mock_port,
        )

        person = Person(platform="qq", user_id="bot123")
        assert person.is_known is True
        assert person.nickname == "MaiBot"
        assert person.person_name == "MaiBot"
        assert person.platform == "qq"
        assert person.user_id == "bot123"

    def test_person_init_missing_params_raises(self, monkeypatch):
        # mock is_bot_self 返回 False
        monkeypatch.setattr("src.core.identity.is_bot_self", lambda p, u: False)
        # 缺少所有参数 → ValueError
        with pytest.raises(ValueError):
            Person()


class TestPersonDelMemory:
    """Person.del_memory 行为测试。"""

    def test_empty_memory_points_returns_zero(self, monkeypatch):
        monkeypatch.setattr("src.core.identity.is_bot_self", lambda p, u: False)
        # 构造 Person 实例绕过 __init__
        person = Person.__new__(Person)
        person.memory_points = []
        person.is_known = True
        person.person_id = "test"
        result = person.del_memory("category", "content")
        assert result == 0

    def test_delete_matching_memory(self, monkeypatch):
        monkeypatch.setattr("src.core.identity.is_bot_self", lambda p, u: False)
        monkeypatch.setattr(Person, "sync_to_database", lambda self: None)
        person = Person.__new__(Person)
        person.memory_points = ["分类:内容:权重", "其他:别的:权重"]
        person.is_known = True
        person.person_id = "test"
        # 相似度 1.0（完全匹配）→ 删除
        result = person.del_memory("分类", "内容", similarity_threshold=0.95)
        assert result == 1
        assert len(person.memory_points) == 1

    def test_no_match_returns_zero(self, monkeypatch):
        monkeypatch.setattr("src.core.identity.is_bot_self", lambda p, u: False)
        person = Person.__new__(Person)
        person.memory_points = ["分类:内容:权重"]
        person.is_known = True
        person.person_id = "test"
        result = person.del_memory("分类", "完全不同的内容", similarity_threshold=0.95)
        assert result == 0
        assert len(person.memory_points) == 1


class TestPersonAddGroupNickName:
    """Person.add_group_nick_name 行为测试。"""

    def test_add_new_group_nick_name(self, monkeypatch):
        monkeypatch.setattr(Person, "sync_to_database", lambda self: None)
        person = Person.__new__(Person)
        person.group_cardname_list = []
        person.person_id = "test"
        person.add_group_nick_name("group1", "名片1")
        assert person.group_cardname_list == [{"group_id": "group1", "group_cardname": "名片1"}]

    def test_update_existing_group_nick_name(self, monkeypatch):
        monkeypatch.setattr(Person, "sync_to_database", lambda self: None)
        person = Person.__new__(Person)
        person.group_cardname_list = [{"group_id": "group1", "group_cardname": "旧名片"}]
        person.person_id = "test"
        person.add_group_nick_name("group1", "新名片")
        assert person.group_cardname_list[0]["group_cardname"] == "新名片"
        assert len(person.group_cardname_list) == 1

    def test_empty_group_id_no_op(self, monkeypatch):
        person = Person.__new__(Person)
        person.group_cardname_list = []
        person.person_id = "test"
        person.add_group_nick_name("", "名片")
        assert person.group_cardname_list == []

    def test_empty_nick_name_no_op(self, monkeypatch):
        person = Person.__new__(Person)
        person.group_cardname_list = []
        person.person_id = "test"
        person.add_group_nick_name("group1", "")
        assert person.group_cardname_list == []


def _mock_db_session(person_record=None):
    """构造 mock get_db_session context manager。"""

    @contextmanager
    def _session(*args, **kwargs):
        sess = MagicMock()
        stmt = MagicMock()
        sess.exec.return_value = stmt
        stmt.first.return_value = person_record
        yield sess

    return _session


class TestGetPersonIdByName:
    """get_person_id_by_person_name 行为测试。"""

    def test_found_returns_id(self, monkeypatch):
        from src.person_info.person_info import get_person_id_by_person_name

        # get_person_id_by_person_name 查询 person_id 字段，first() 返回字段值
        monkeypatch.setattr(
            "src.person_info.person_info.get_db_session",
            lambda **kw: _mock_db_session("pid123")(),
        )
        result = get_person_id_by_person_name("Alice")
        assert result == "pid123"

    def test_not_found_returns_empty(self, monkeypatch):
        from src.person_info.person_info import get_person_id_by_person_name

        monkeypatch.setattr(
            "src.person_info.person_info.get_db_session",
            lambda **kw: _mock_db_session(None)(),
        )
        result = get_person_id_by_person_name("Unknown")
        assert result == ""

    def test_exception_returns_empty(self, monkeypatch):
        from src.person_info.person_info import get_person_id_by_person_name

        @contextmanager
        def _raising_session(*args, **kwargs):
            raise RuntimeError("db error")

        monkeypatch.setattr("src.person_info.person_info.get_db_session", lambda **kw: _raising_session())
        result = get_person_id_by_person_name("Alice")
        assert result == ""


class TestIsPersonKnown:
    """is_person_known 行为测试。"""

    def test_no_params_returns_false(self):
        from src.person_info.person_info import is_person_known

        assert is_person_known() is False

    def test_person_id_found_known(self, monkeypatch):
        from src.person_info.person_info import is_person_known

        mock_record = SimpleNamespace(is_known=True)
        monkeypatch.setattr(
            "src.person_info.person_info.get_db_session",
            lambda **kw: _mock_db_session(mock_record)(),
        )
        assert is_person_known(person_id="pid1") is True

    def test_person_id_found_unknown(self, monkeypatch):
        from src.person_info.person_info import is_person_known

        mock_record = SimpleNamespace(is_known=False)
        monkeypatch.setattr(
            "src.person_info.person_info.get_db_session",
            lambda **kw: _mock_db_session(mock_record)(),
        )
        assert is_person_known(person_id="pid1") is False

    def test_person_id_not_found_returns_false(self, monkeypatch):
        from src.person_info.person_info import is_person_known

        monkeypatch.setattr(
            "src.person_info.person_info.get_db_session",
            lambda **kw: _mock_db_session(None)(),
        )
        assert is_person_known(person_id="pid1") is False

    def test_user_id_and_platform_path(self, monkeypatch):
        from src.person_info.person_info import is_person_known

        mock_record = SimpleNamespace(is_known=True)
        monkeypatch.setattr(
            "src.person_info.person_info.get_db_session",
            lambda **kw: _mock_db_session(mock_record)(),
        )
        assert is_person_known(user_id="123", platform="qq") is True

    def test_person_name_path(self, monkeypatch):
        from src.person_info.person_info import is_person_known

        mock_record = SimpleNamespace(is_known=True, person_id="pid1")
        # person_name 路径先调 get_person_id_by_person_name 再查库
        monkeypatch.setattr(
            "src.person_info.person_info.get_db_session",
            lambda **kw: _mock_db_session(mock_record)(),
        )
        assert is_person_known(person_name="Alice") is True


class TestResolvePersonIdForMemory:
    """resolve_person_id_for_memory 行为测试。"""

    def test_empty_all_returns_empty(self, monkeypatch):
        from src.person_info.person_info import resolve_person_id_for_memory

        assert resolve_person_id_for_memory() == ""

    def test_person_name_resolves(self, monkeypatch):
        from src.person_info.person_info import resolve_person_id_for_memory

        monkeypatch.setattr(

            "src.person_info.person_info.get_person_id_by_person_name",
            lambda name: "pid_by_name",
        )
        result = resolve_person_id_for_memory(person_name="Alice")
        assert result == "pid_by_name"

    def test_platform_user_id_fallback(self, monkeypatch):
        from src.person_info.person_info import resolve_person_id_for_memory

        monkeypatch.setattr(
            "src.person_info.person_info.get_person_id_by_person_name",
            lambda name: "",
        )
        result = resolve_person_id_for_memory(platform="qq", user_id="123")
        expected = get_person_id("qq", "123")
        assert result == expected

    def test_strict_known_unknown_returns_empty(self, monkeypatch):
        from src.person_info.person_info import resolve_person_id_for_memory

        monkeypatch.setattr(
            "src.person_info.person_info.get_person_id_by_person_name",
            lambda name: "",
        )
        monkeypatch.setattr("src.person_info.person_info.is_person_known", lambda **kw: False)
        result = resolve_person_id_for_memory(
            platform="qq", user_id="123", strict_known=True
        )
        assert result == ""

    def test_strict_known_known_returns_id(self, monkeypatch):
        from src.person_info.person_info import resolve_person_id_for_memory

        monkeypatch.setattr(
            "src.person_info.person_info.get_person_id_by_person_name",
            lambda name: "",
        )
        monkeypatch.setattr("src.person_info.person_info.is_person_known", lambda **kw: True)
        result = resolve_person_id_for_memory(
            platform="qq", user_id="123", strict_known=True
        )
        assert result == get_person_id("qq", "123")


class TestToGroupCardnameRecords:
    """_to_group_cardname_records 行为测试。"""

    def test_none_returns_empty(self, monkeypatch):
        from src.person_info.person_info import _to_group_cardname_records

        monkeypatch.setattr(
            "src.person_info.person_info.parse_group_cardname_json",
            lambda x: [],
        )
        assert _to_group_cardname_records(None) == []

    def test_empty_list_returns_empty(self, monkeypatch):
        from src.person_info.person_info import _to_group_cardname_records

        monkeypatch.setattr(
            "src.person_info.person_info.parse_group_cardname_json",
            lambda x: [],
        )
        assert _to_group_cardname_records("[]") == []

    def test_valid_records_converted(self, monkeypatch):
        from src.person_info.person_info import _to_group_cardname_records

        mock_records = [
            SimpleNamespace(group_id="g1", group_cardname="名片1"),
            SimpleNamespace(group_id="g2", group_cardname="名片2"),
        ]
        monkeypatch.setattr(
            "src.person_info.person_info.parse_group_cardname_json",
            lambda x: mock_records,
        )
        result = _to_group_cardname_records('[{"group_id":"g1"}]')
        assert result == [
            {"group_id": "g1", "group_cardname": "名片1"},
            {"group_id": "g2", "group_cardname": "名片2"},
        ]


class TestPersonLoadFromDatabase:
    """Person.load_from_database 行为测试。"""

    def test_load_existing_record(self, monkeypatch):
        mock_record = SimpleNamespace(
            user_id="u123",
            platform="qq",
            is_known=True,
            user_nickname="昵称",
            person_name="真名",
            name_reason="理由",
            know_counts=5,
            memory_points='["cat:内容:1.0"]',
            group_cardname='[{"group_id":"g1","group_cardname":"名片"}]',
        )
        monkeypatch.setattr(
            "src.person_info.person_info.get_db_session",
            lambda **kw: _mock_db_session(mock_record)(),
        )
        monkeypatch.setattr(
            "src.person_info.person_info.parse_group_cardname_json",
            lambda x: [SimpleNamespace(group_id="g1", group_cardname="名片")],
        )
        person = Person.__new__(Person)
        person.person_id = "pid1"
        person.user_id = ""
        person.platform = ""
        person.is_known = False
        person.nickname = ""
        person.person_name = None
        person.name_reason = None
        person.know_times = 0
        person.memory_points = []
        person.group_cardname_list = []
        person.load_from_database()
        assert person.user_id == "u123"
        assert person.platform == "qq"
        assert person.is_known is True
        assert person.nickname == "昵称"
        assert person.know_times == 5
        assert person.memory_points == ["cat:内容:1.0"]

    def test_load_record_not_found_syncs_default(self, monkeypatch):
        # record 为 None → 调 sync_to_database 创建
        monkeypatch.setattr(
            "src.person_info.person_info.get_db_session",
            lambda **kw: _mock_db_session(None)(),
        )
        monkeypatch.setattr(Person, "sync_to_database", lambda self: None)
        person = Person.__new__(Person)
        person.person_id = "pid1"
        person.is_known = True
        person.load_from_database()
        # 不抛异常即通过

    def test_load_invalid_memory_points_falls_back(self, monkeypatch):
        mock_record = SimpleNamespace(
            user_id="u",
            platform="qq",
            is_known=True,
            user_nickname="n",
            person_name="p",
            name_reason=None,
            know_counts=1,
            memory_points="invalid json",
            group_cardname=None,
        )
        monkeypatch.setattr(
            "src.person_info.person_info.get_db_session",
            lambda **kw: _mock_db_session(mock_record)(),
        )
        person = Person.__new__(Person)
        person.person_id = "pid1"
        person.user_id = ""
        person.platform = ""
        person.is_known = False
        person.nickname = ""
        person.person_name = None
        person.name_reason = None
        person.know_times = 0
        person.memory_points = []
        person.group_cardname_list = []
        person.load_from_database()
        # 无效 JSON → 空列表
        assert person.memory_points == []

    def test_load_exception_preserves_defaults(self, monkeypatch):
        @contextmanager
        def _raising_session(*args, **kwargs):
            raise RuntimeError("db error")

        monkeypatch.setattr("src.person_info.person_info.get_db_session", lambda **kw: _raising_session())
        person = Person.__new__(Person)
        person.person_id = "pid1"
        person.is_known = True
        person.memory_points = ["existing"]
        person.load_from_database()
        # 异常时保持默认值
        assert person.memory_points == ["existing"]


class TestPersonSyncToDatabase:
    """Person.sync_to_database 行为测试。"""

    def test_not_known_skips_sync(self, monkeypatch):
        person = Person.__new__(Person)
        person.is_known = False
        person.person_id = "pid1"
        # 不应调 get_db_session
        called = []

        @contextmanager
        def _session(*args, **kwargs):
            called.append(True)
            yield MagicMock()

        monkeypatch.setattr("src.person_info.person_info.get_db_session", lambda **kw: _session())
        person.sync_to_database()
        assert called == []

    def test_sync_updates_existing_record(self, monkeypatch):
        mock_record = MagicMock()
        monkeypatch.setattr(
            "src.person_info.person_info.get_db_session",
            lambda **kw: _mock_db_session(mock_record)(),
        )
        monkeypatch.setattr(
            "src.person_info.person_info.dump_group_cardname_records",
            lambda x: "[]",
        )
        person = Person.__new__(Person)
        person.is_known = True
        person.person_id = "pid1"
        person.platform = "qq"
        person.user_id = "u1"
        person.nickname = "nick"
        person.person_name = "name"
        person.name_reason = "reason"
        person.know_times = 3
        person.know_since = None
        person.last_know = None
        person.memory_points = []
        person.group_cardname_list = []
        person.sync_to_database()
        # record 存在 → 更新字段
        assert mock_record.person_id == "pid1"

    def test_sync_creates_new_record(self, monkeypatch):
        # record 为 None → 创建新 PersonInfo
        monkeypatch.setattr(
            "src.person_info.person_info.get_db_session",
            lambda **kw: _mock_db_session(None)(),
        )
        monkeypatch.setattr(
            "src.person_info.person_info.dump_group_cardname_records",
            lambda x: "[]",
        )
        person = Person.__new__(Person)
        person.is_known = True
        person.person_id = "pid1"
        person.platform = "qq"
        person.user_id = "u1"
        person.nickname = "nick"
        person.person_name = "name"
        person.name_reason = None
        person.know_times = 1
        person.know_since = None
        person.last_know = None
        person.memory_points = []
        person.group_cardname_list = []
        # 不抛异常即通过（PersonInfo 构造在 mock session 中）
        person.sync_to_database()

    def test_sync_exception_does_not_raise(self, monkeypatch):
        @contextmanager
        def _raising_session(*args, **kwargs):
            raise RuntimeError("db error")

        monkeypatch.setattr("src.person_info.person_info.get_db_session", lambda **kw: _raising_session())
        person = Person.__new__(Person)
        person.is_known = True
        person.person_id = "pid1"
        person.memory_points = []
        person.group_cardname_list = []
        person.know_since = None
        person.last_know = None
        # 异常不抛出
        person.sync_to_database()


class TestStorePersonMemoryFromAnswer:
    """store_person_memory_from_answer 行为测试。"""

    def test_empty_content_skips(self):
        import asyncio

        from src.person_info.person_info import store_person_memory_from_answer

        async def _run():
            await store_person_memory_from_answer("Alice", "", "chat1")

        asyncio.run(_run())  # 不抛异常即通过

    def test_empty_chat_id_skips(self):
        import asyncio

        from src.person_info.person_info import store_person_memory_from_answer

        async def _run():
            await store_person_memory_from_answer("Alice", "内容", "")

        asyncio.run(_run())

    def test_no_session_skips(self, monkeypatch):
        import asyncio

        from src.person_info.person_info import store_person_memory_from_answer

        monkeypatch.setattr("src.person_info.person_info.get_session_info", lambda cid: None)
        async def _run():
            await store_person_memory_from_answer("Alice", "内容", "chat1")

        asyncio.run(_run())

    def test_successful_writeback(self, monkeypatch):
        import asyncio

        from src.person_info.person_info import store_person_memory_from_answer

        mock_session = SimpleNamespace(platform="qq", user_id="u1", group_id="g1")
        monkeypatch.setattr("src.person_info.person_info.get_session_info", lambda cid: mock_session)
        monkeypatch.setattr("src.person_info.person_info.resolve_person_id_for_memory", lambda **kw: "pid1")

        # mock Person 返回已知用户
        mock_person = SimpleNamespace(is_known=True, person_name="Alice", nickname="Alice")
        monkeypatch.setattr("src.person_info.person_info.Person", lambda **kw: mock_person)

        observe_result = SimpleNamespace(success=True, detail="")
        mock_memory_port = MagicMock()
        mock_memory_port.observe = MagicMock(return_value=observe_result)
        monkeypatch.setattr(
            "src.person_info.person_info.get_memory_service_port",
            lambda: mock_memory_port,
        )

        async def _run():
            await store_person_memory_from_answer("Alice", "事实内容", "chat1")

        asyncio.run(_run())
        mock_memory_port.observe.assert_called_once()

    def test_unknown_person_skips(self, monkeypatch):
        import asyncio

        from src.person_info.person_info import store_person_memory_from_answer

        mock_session = SimpleNamespace(platform="qq", user_id="u1", group_id="g1")
        monkeypatch.setattr("src.person_info.person_info.get_session_info", lambda cid: mock_session)
        monkeypatch.setattr("src.person_info.person_info.resolve_person_id_for_memory", lambda **kw: "pid1")

        mock_person = SimpleNamespace(is_known=False, person_name="", nickname="")
        monkeypatch.setattr("src.person_info.person_info.Person", lambda **kw: mock_person)

        async def _run():
            await store_person_memory_from_answer("Alice", "内容", "chat1")

        asyncio.run(_run())  # 未知用户跳过

    def test_exception_does_not_raise(self, monkeypatch):
        import asyncio

        from src.person_info.person_info import store_person_memory_from_answer

        monkeypatch.setattr(
            "src.person_info.person_info.get_session_info",
            lambda cid: (_ for _ in ()).throw(RuntimeError("boom")),
        )

        async def _run():
            await store_person_memory_from_answer("Alice", "内容", "chat1")

        asyncio.run(_run())  # 异常不抛出