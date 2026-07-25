"""Scope 审批状态持久化。

管理每个 plugin_id 的已批准 scope 集合，持久化到 JSON 文件。
支持自动批准（approval_required=False 的 scope）和词汇表清理。
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from src.common.logger import get_logger
from src.plugin_runtime_v2.scope.vocabulary import ScopeVocabulary

logger = get_logger("plugin_runtime_v2.scope.approval_store")


class ScopeApprovalStore:
    """Scope 审批状态持久化管理。

    存储模型：{plugin_id: {granted_scopes: set[str], updated_at: float, updated_by: str}}
    """

    def __init__(self, file_path: str = "data/plugin_runtime_v2/scope_approvals.json") -> None:
        self._file_path = Path(file_path)
        self._approvals: dict[str, dict] = {}

    def load(self) -> None:
        """从 JSON 文件加载审批状态。"""
        if not self._file_path.exists():
            logger.info("审批状态文件不存在，使用空状态: %s", self._file_path)
            return

        try:
            data = json.loads(self._file_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("审批状态文件读取失败: %s", exc)
            return

        approvals = data.get("approvals", {})
        cleaned = 0
        for plugin_id, info in approvals.items():
            scopes = set(info.get("granted_scopes", []))
            valid = {s for s in scopes if ScopeVocabulary.validate(s)}
            if len(valid) < len(scopes):
                logger.warning(
                    "plugin %s 清理 %d 个无效 scope", plugin_id, len(scopes) - len(valid),
                )
                cleaned += len(scopes) - len(valid)
            if valid:
                self._approvals[plugin_id] = {
                    "granted_scopes": valid,
                    "updated_at": info.get("updated_at", time.time()),
                    "updated_by": info.get("updated_by", "system"),
                }
        logger.info(
            "审批状态已加载: plugins=%d cleaned=%d", len(self._approvals), cleaned,
        )

    def save(self) -> None:
        """持久化到 JSON 文件。"""
        self._file_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "updated_at": time.time(),
            "approvals": {
                pid: {
                    "granted_scopes": sorted(info["granted_scopes"]),
                    "updated_at": info["updated_at"],
                    "updated_by": info["updated_by"],
                }
                for pid, info in self._approvals.items()
            },
        }
        self._file_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8",
        )
        logger.debug("审批状态已保存: plugins=%d", len(self._approvals))

    def get_granted_scopes(self, plugin_id: str) -> set[str]:
        """获取已批准的 scope 集合。"""
        info = self._approvals.get(plugin_id)
        if info is None:
            return set()
        return info.get("granted_scopes", set()).copy()

    def approve_scope(self, plugin_id: str, scope: str, operator: str = "user") -> None:
        """批准单个 scope。"""
        if not ScopeVocabulary.validate(scope):
            logger.warning("拒绝批准无效 scope: %s", scope)
            return
        if plugin_id not in self._approvals:
            self._approvals[plugin_id] = {
                "granted_scopes": set(),
                "updated_at": time.time(),
                "updated_by": operator,
            }
        self._approvals[plugin_id]["granted_scopes"].add(scope)
        self._approvals[plugin_id]["updated_at"] = time.time()
        self._approvals[plugin_id]["updated_by"] = operator
        logger.info("scope 已批准: plugin=%s scope=%s by=%s", plugin_id, scope, operator)
        self.save()

    def revoke_scope(self, plugin_id: str, scope: str, operator: str = "user") -> None:
        """撤销单个 scope。"""
        info = self._approvals.get(plugin_id)
        if info is None:
            return
        info["granted_scopes"].discard(scope)
        info["updated_at"] = time.time()
        info["updated_by"] = operator
        logger.info("scope 已撤销: plugin=%s scope=%s by=%s", plugin_id, scope, operator)
        self.save()

    def approve_all_pending(self, plugin_id: str, requested_scopes: list[str]) -> int:
        """自动批准 approval_required=False 的 scope。

        Returns:
            新增批准的数量。
        """
        granted = self.get_granted_scopes(plugin_id)
        count = 0
        for scope in requested_scopes:
            if scope in granted:
                continue
            entry = None
            try:
                entry = ScopeVocabulary.lookup(scope)
            except KeyError:
                logger.warning("未知 scope: %s", scope)
                continue
            if not entry.approval_required:
                self.approve_scope(plugin_id, scope, operator="system")
                granted.add(scope)
                count += 1
        if count > 0:
            logger.info("自动批准 %d 个 scope: plugin=%s", count, plugin_id)
        return count

    def get_all_approvals(self) -> dict[str, set[str]]:
        """返回所有审批状态。"""
        return {
            pid: info["granted_scopes"].copy()
            for pid, info in self._approvals.items()
        }
