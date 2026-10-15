"""Phoenix-7 napcat-adapter v4 集成测试。"""

from __future__ import annotations

import hashlib

from tests._plugin_helpers import import_plugin_module

# 插件目录名含 '-'，经合成包机制导入（对齐 entrypoint._discover_plugin）
SessionIdMapper = import_plugin_module(
    "maibot-team.napcat-adapter", "session_mapper"
).SessionIdMapper


class TestSessionIdMapper:
    def test_algorithm_consistency_group(self):
        """群聊 session_id 算法与 SessionUtils 一致。"""
        sid = SessionIdMapper.calculate_session_id(
            "qq", group_id="123456",
            account_id="bot1", scope="main",
        )
        expected = hashlib.md5(
            "qq_account:bot1_scope:main_123456".encode()
        ).hexdigest()
        assert sid == expected

    def test_algorithm_consistency_private(self):
        """私聊 session_id 算法与 SessionUtils 一致。"""
        sid = SessionIdMapper.calculate_session_id(
            "qq", user_id="789",
        )
        expected = hashlib.md5(
            "qq_789_private".encode()
        ).hexdigest()
        assert sid == expected

    def test_register_and_resolve(self):
        mapper = SessionIdMapper()
        sid = mapper.calculate_private_session_id("user-1")
        mapper.register_session(sid, "user-1")
        assert mapper.get_qq_user_id(sid) == "user-1"
        assert mapper.get_qq_group_id(sid) == ""

    def test_register_group_session(self):
        mapper = SessionIdMapper()
        sid = mapper.calculate_group_session_id("group-1")
        mapper.register_session(sid, "user-1", "group-1")
        assert mapper.get_qq_user_id(sid) == "user-1"
        assert mapper.get_qq_group_id(sid) == "group-1"

    def test_resolve_unknown(self):
        mapper = SessionIdMapper()
        uid, gid = mapper.resolve_qq_ids("nonexistent")
        assert uid == ""
        assert gid == ""

    def test_serialize_roundtrip(self):
        mapper = SessionIdMapper()
        sid = mapper.calculate_private_session_id("user-1")
        mapper.register_session(sid, "user-1")
        data = mapper.to_dict()
        mapper2 = SessionIdMapper()
        mapper2.restore(data)
        assert mapper2.get_qq_user_id(sid) == "user-1"
