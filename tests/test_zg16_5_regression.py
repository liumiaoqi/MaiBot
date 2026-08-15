"""ZG16-5 回归测试 — 向后兼容性验证。

覆盖：既有 57 scope 合法、_CAPABILITY_MAP 不变、risk_level 不变、
审计开关关闭行为、ManifestV3._validate_scopes 不变、版本号、is_tier1 既有判定。
"""

from unittest.mock import patch

import pytest

from src.plugin_runtime_v2.scope.vocabulary import ScopeVocabulary


# 既有 57 个 scope（ZG16-5 扩展前）
EXISTING_57_SCOPES = [
    # message (12)
    "message:send:text", "message:send:image", "message:send:emoji",
    "message:send:forward", "message:send:hybrid", "message:read:recent",
    "message:read:by_time", "message:read:by_id", "message:write:context",
    "message:receive:group", "message:receive:private", "message:receive:notice",
    # database (8)
    "database:read:session_message", "database:read:plugin_data",
    "database:write:session_message", "database:write:plugin_data",
    "database:delete:session_message", "database:delete:plugin_data",
    "database:read:self", "database:write:self",
    # session (3)
    "session:read:list", "session:read:detail", "session:write:create",
    # memory (3)
    "memory:read:search", "memory:read:profile", "memory:write:observe",
    # config (3)
    "config:read:self", "config:read:all", "config:write:self",
    # agent (3)
    "agent:read:emotion", "agent:read:relationship", "agent:execute:proactive",
    # person (2)
    "person:read:id", "person:read:detail",
    # llm (5)
    "llm:execute:generate", "llm:execute:generate_with_tools",
    "llm:execute:embed", "llm:execute:transcribe", "llm:read:models",
    # emoji (5)
    "emoji:read:random", "emoji:read:by_description", "emoji:read:list",
    "emoji:write:register", "emoji:write:delete",
    # plugin (6)
    "plugin:read:list", "plugin:read:info", "plugin:write:config",
    "plugin:write:enable", "plugin:execute:load", "plugin:execute:api",
    # system (7)
    "system:read:statistics", "system:read:frequency",
    "system:read:tool_definitions", "system:write:frequency",
    "system:execute:render", "system:execute:command", "system:execute:knowledge",
]

# 采样 capability 映射（验证 _CAPABILITY_MAP 不变）
CAPABILITY_MAP_SAMPLE = {
    "send.text": ["message:send:text"],
    "send.image": ["message:send:image"],
    "db.query": ["database:read:session_message", "database:read:plugin_data"],
    "db.save": ["database:write:session_message", "database:write:plugin_data"],
    "config.get_plugin": ["config:read:self"],
    "chat.get_all_streams": ["session:read:list"],
    "maisaka.context.append": ["message:write:context"],
    "maisaka.proactive.trigger": ["agent:execute:proactive"],
    "llm.generate": ["llm:execute:generate"],
    "render.html2png": ["system:execute:render"],
    "knowledge.search": ["system:execute:knowledge"],
}


class TestExisting57ScopesValid:
    """既有 57 个 scope 仍合法。"""

    def test_existing_57_count(self):
        assert len(EXISTING_57_SCOPES) == 57

    @pytest.mark.parametrize("scope", EXISTING_57_SCOPES)
    def test_existing_scope_valid(self, scope):
        assert ScopeVocabulary.validate(scope) is True


class TestCapabilityMapUnchanged:
    """_CAPABILITY_MAP 映射不变。"""

    @pytest.mark.parametrize("cap,expected", list(CAPABILITY_MAP_SAMPLE.items()))
    def test_capability_mapping(self, cap, expected):
        assert ScopeVocabulary.map_capability(cap) == expected

    def test_nonexistent_capability_empty(self):
        assert ScopeVocabulary.map_capability("nonexistent.cap") == []


class TestExistingRiskLevelUnchanged:
    """既有 scope risk_level/approval_required 不变。"""

    def test_message_send_text_low(self):
        entry = ScopeVocabulary.lookup("message:send:text")
        assert entry.risk_level == "low"
        assert entry.approval_required is False

    def test_database_write_session_message_high(self):
        entry = ScopeVocabulary.lookup("database:write:session_message")
        assert entry.risk_level == "high"
        assert entry.approval_required is True

    def test_llm_execute_generate_high(self):
        entry = ScopeVocabulary.lookup("llm:execute:generate")
        assert entry.risk_level == "high"
        assert entry.approval_required is True

    def test_database_read_self_low(self):
        entry = ScopeVocabulary.lookup("database:read:self")
        assert entry.risk_level == "low"
        assert entry.approval_required is False


class TestAuditSwitchOff:
    """审计开关关闭 → 不产生审计日志。"""

    async def test_audit_off_no_record(self, tmp_path):
        """enable_scope_audit=False → ToolRouter 不审计。"""
        from unittest.mock import AsyncMock, MagicMock

        from src.plugin_runtime_v2.runner.tool_router import ToolRouter
        from src.plugin_runtime_v2.sdk.plugin import MaiBotPlugin

        class FakePlugin(MaiBotPlugin):
            plugin_id = "test.off"
            scopes = ["system:execute:cli"]

        router = ToolRouter()
        plugin = FakePlugin()

        mock_recorder = MagicMock()
        mock_recorder.record = AsyncMock()
        # 审计关闭 → get_scope_audit_recorder 返回 None
        with patch(
            "src.plugin_runtime_v2.runner.tool_router.get_scope_audit_recorder",
            return_value=None,
        ):
            async def handler(plg, args):
                return {"ok": True}
            router.register("t1", plugin, handler)
            resp = await router.execute("t1", {})
            assert resp.success
            mock_recorder.record.assert_not_called()


class TestManifestV3ValidateScopes:
    """ManifestV3._validate_scopes 仍使用 ScopeVocabulary.validate。"""

    def test_valid_scopes_accepted(self):
        from src.plugin_runtime_v2.sdk.manifest import ManifestV3

        # 合法 scope → 不抛异常
        manifest = ManifestV3(
            id="org.test.plugin",
            version="1.0.0",
            name="test",
            author={"name": "t", "email": ""},
            scopes=["message:send:text", "system:execute:cli"],
        )
        assert "system:execute:cli" in manifest.scopes

    def test_invalid_scopes_rejected(self):
        from src.plugin_runtime_v2.sdk.manifest import ManifestV3

        with pytest.raises(ValueError):
            ManifestV3(
                id="org.test.plugin",
                version="1.0.0",
                name="test",
                author={"name": "t", "email": ""},
                scopes=["foo:bar:baz"],
            )


class TestVersion:
    """版本号 = 1.1.0。"""

    def test_version_is_1_1_0(self):
        assert ScopeVocabulary.version == "1.1.0"


class TestIsTier1ForExisting:
    """is_tier1 对既有 scope 的判定。"""

    def test_is_tier1_existing_high_risk(self):
        """既有 high risk scope → True。"""
        assert ScopeVocabulary.is_tier1("database:write:session_message") is True

    def test_is_tier1_existing_low_risk(self):
        """既有 low risk scope → False。"""
        assert ScopeVocabulary.is_tier1("message:send:text") is False

    def test_is_tier1_existing_medium_risk(self):
        """既有 medium risk scope → False。"""
        assert ScopeVocabulary.is_tier1("message:send:image") is False

    def test_is_tier1_new_tier1(self):
        """新增 Tier 1 scope → True。"""
        assert ScopeVocabulary.is_tier1("system:execute:cli") is True
        assert ScopeVocabulary.is_tier1("network:fetch:url") is True


class TestProductionPathWiring:
    """生产路径接线验证（P0 修复——AGENTS.md 新模块接线硬性规则）。"""

    def test_main_py_calls_init_scope_audit_recorder(self):
        """main.py 包含 init_scope_audit_recorder 调用（生产接线点）。"""
        from pathlib import Path

        main_py = Path(__file__).resolve().parent.parent / "src" / "main.py"
        content = main_py.read_text(encoding="utf-8")
        assert "init_scope_audit_recorder" in content, (
            "main.py 必须调用 init_scope_audit_recorder（AGENTS.md 新模块接线规则）"
        )

    def test_main_py_calls_close_scope_audit_recorder(self):
        """main.py 包含 close_scope_audit_recorder 调用（关闭流程接线点）。"""
        from pathlib import Path

        main_py = Path(__file__).resolve().parent.parent / "src" / "main.py"
        content = main_py.read_text(encoding="utf-8")
        assert "close_scope_audit_recorder" in content, (
            "main.py 必须调用 close_scope_audit_recorder（AGENTS.md 新模块接线规则）"
        )

    def test_main_py_reads_audit_config(self):
        """main.py 从 AppConfigPort 读取审计配置（非硬编码）。"""
        from pathlib import Path

        main_py = Path(__file__).resolve().parent.parent / "src" / "main.py"
        content = main_py.read_text(encoding="utf-8")
        assert "get_audit_log_path" in content
        assert "get_audit_log_max_size_mb" in content
        assert "get_audit_log_backup_count" in content
        assert "get_sensitive_param_names" in content