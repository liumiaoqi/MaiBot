"""Phoenix-3 OAuth Scope 授权端到端测试。"""

from __future__ import annotations

from src.plugin_runtime_v2.scope.approval_store import ScopeApprovalStore
from src.plugin_runtime_v2.scope.token_service import TokenService


class TestTokenService:
    def test_issue_and_validate(self):
        svc = TokenService(ttl_seconds=300)
        token = svc.issue("test.plugin")
        assert len(token) == 43  # 32 bytes urlsafe base64 without padding

        valid, plugin_id = svc.validate(token)
        assert valid
        assert plugin_id == "test.plugin"

    def test_validate_twice_fails(self):
        svc = TokenService()
        token = svc.issue("test.plugin")
        svc.validate(token)
        valid, _ = svc.validate(token)
        assert not valid

    def test_validate_unknown_token(self):
        svc = TokenService()
        valid, _ = svc.validate("nonexistent-token")
        assert not valid

    def test_cleanup_expired(self):
        svc = TokenService(ttl_seconds=0)  # 立即过期
        svc.issue("test.plugin")
        count = svc.cleanup_expired()
        assert count == 1
        assert len(svc._tokens) == 0


class TestScopeApprovalStore:
    def test_approve_and_revoke(self, tmp_path):
        store = ScopeApprovalStore(str(tmp_path / "approvals.json"))
        store.approve_scope("test.plugin", "message:send:text")
        assert "message:send:text" in store.get_granted_scopes("test.plugin")

        store.revoke_scope("test.plugin", "message:send:text")
        assert "message:send:text" not in store.get_granted_scopes("test.plugin")

    def test_approve_all_pending_auto_approves_low_risk(self, tmp_path):
        store = ScopeApprovalStore(str(tmp_path / "approvals.json"))
        count = store.approve_all_pending("test.plugin", [
            "message:send:text",      # low, approval_required=False
            "message:send:image",     # medium, approval_required=True
        ])
        assert count >= 1  # message:send:text 应被自动批准
        granted = store.get_granted_scopes("test.plugin")
        assert "message:send:text" in granted

    def test_invalid_scope_not_approved(self, tmp_path):
        store = ScopeApprovalStore(str(tmp_path / "approvals.json"))
        store.approve_scope("test.plugin", "invalid:scope:xyz")
        assert "invalid:scope:xyz" not in store.get_granted_scopes("test.plugin")

    def test_save_and_load(self, tmp_path):
        path = tmp_path / "approvals.json"
        store1 = ScopeApprovalStore(str(path))
        store1.approve_scope("test.plugin", "message:send:text")
        store1.save()

        store2 = ScopeApprovalStore(str(path))
        store2.load()
        assert "message:send:text" in store2.get_granted_scopes("test.plugin")

    def test_get_all_approvals(self, tmp_path):
        store = ScopeApprovalStore(str(tmp_path / "approvals.json"))
        store.approve_scope("plugin_a", "message:send:text")
        store.approve_scope("plugin_b", "database:read:self")
        all_approved = store.get_all_approvals()
        assert "plugin_a" in all_approved
        assert "plugin_b" in all_approved
