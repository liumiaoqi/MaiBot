"""ZG16-5: ScopeVocabulary Tier 1 扩展测试。

验证 6 个新增 Tier 1 scope 的合法性、风险等级、审批要求、三段式命名，
以及原有 57 个 scope 不变、总数 63、is_tier1 判定、版本号 1.1.0。
"""

import pytest

from src.plugin_runtime_v2.scope.vocabulary import ScopeVocabulary


# 6 个新增 Tier 1 scope
TIER1_SCOPES = [
    "system:execute:cli",
    "system:read:screenshot",
    "system:read:location",
    "account:execute:operation",
    "finance:read:qr_code",
    "network:fetch:url",
]


class TestNewScopeValidity:
    """新增 scope 合法性。"""

    @pytest.mark.parametrize("scope", TIER1_SCOPES)
    def test_new_scope_valid(self, scope):
        assert ScopeVocabulary.validate(scope) is True

    def test_new_scope_valid_cli(self):
        assert ScopeVocabulary.validate("system:execute:cli") is True

    def test_new_scope_valid_screenshot(self):
        assert ScopeVocabulary.validate("system:read:screenshot") is True

    def test_new_scope_valid_location(self):
        assert ScopeVocabulary.validate("system:read:location") is True

    def test_new_scope_valid_account(self):
        assert ScopeVocabulary.validate("account:execute:operation") is True

    def test_new_scope_valid_finance(self):
        assert ScopeVocabulary.validate("finance:read:qr_code") is True

    def test_new_scope_valid_network(self):
        assert ScopeVocabulary.validate("network:fetch:url") is True


class TestNewScopeRiskLevel:
    """新增 scope 风险等级 = high。"""

    @pytest.mark.parametrize("scope", TIER1_SCOPES)
    def test_risk_level_high(self, scope):
        entry = ScopeVocabulary.lookup(scope)
        assert entry.risk_level == "high"

    @pytest.mark.parametrize("scope", TIER1_SCOPES)
    def test_approval_required_true(self, scope):
        entry = ScopeVocabulary.lookup(scope)
        assert entry.approval_required is True


class TestThreePartNaming:
    """三段式命名 domain:action:resource。"""

    @pytest.mark.parametrize("scope", TIER1_SCOPES)
    def test_three_part_naming(self, scope):
        parts = scope.split(":")
        assert len(parts) == 3
        # 各段非空
        assert all(p for p in parts)


class TestExistingScopesUnchanged:
    """原有 57 个 scope 不变。"""

    # 原 57 个 scope 中采样验证（覆盖各资源域）
    EXISTING_SCOPES_SAMPLE = [
        "message:send:text",
        "message:send:image",
        "message:read:recent",
        "message:write:context",
        "database:read:session_message",
        "database:write:session_message",
        "database:delete:plugin_data",
        "session:read:list",
        "session:write:create",
        "memory:read:search",
        "memory:write:observe",
        "config:read:self",
        "config:read:all",
        "agent:read:emotion",
        "agent:execute:proactive",
        "person:read:id",
        "llm:execute:generate",
        "llm:read:models",
        "emoji:read:random",
        "emoji:write:delete",
        "plugin:read:list",
        "plugin:execute:load",
        "system:read:statistics",
        "system:execute:command",
        "system:execute:knowledge",
    ]

    @pytest.mark.parametrize("scope", EXISTING_SCOPES_SAMPLE)
    def test_existing_scope_still_valid(self, scope):
        assert ScopeVocabulary.validate(scope) is True

    def test_existing_risk_level_unchanged(self):
        """message:send:text 风险等级不变。"""
        entry = ScopeVocabulary.lookup("message:send:text")
        assert entry.risk_level == "low"
        assert entry.approval_required is False

    def test_existing_high_risk_unchanged(self):
        """database:write:session_message 风险等级不变。"""
        entry = ScopeVocabulary.lookup("database:write:session_message")
        assert entry.risk_level == "high"
        assert entry.approval_required is True


class TestTotalCount:
    """总 scope 数 = 63。"""

    def test_total_count_63(self):
        assert len(ScopeVocabulary.scopes) == 63

    def test_no_four_part_naming(self):
        """所有 scope 均为三段式。"""
        for entry in ScopeVocabulary.scopes:
            parts = entry.scope.split(":")
            assert len(parts) == 3, f"scope {entry.scope} 不是三段式"


class TestIsTier1:
    """is_tier1 判定。"""

    def test_is_tier1_cli(self):
        assert ScopeVocabulary.is_tier1("system:execute:cli") is True

    def test_is_tier1_screenshot(self):
        assert ScopeVocabulary.is_tier1("system:read:screenshot") is True

    def test_is_tier1_non_tier1_low_risk(self):
        """message:send:text 是 low risk → 非 Tier 1。"""
        assert ScopeVocabulary.is_tier1("message:send:text") is False

    def test_is_tier1_nonexistent(self):
        """不存在的 scope → False（不抛异常）。"""
        assert ScopeVocabulary.is_tier1("foo:bar:baz") is False

    def test_is_tier1_existing_high_risk(self):
        """既有 high risk scope 也是 Tier 1（复用 risk_level 判定）。"""
        assert ScopeVocabulary.is_tier1("database:write:session_message") is True

    def test_is_tier1_existing_medium_risk(self):
        """medium risk scope 非 Tier 1。"""
        assert ScopeVocabulary.is_tier1("message:send:image") is False


class TestVersion:
    """版本号 = 1.1.0。"""

    def test_version_is_1_1_0(self):
        assert ScopeVocabulary.version == "1.1.0"