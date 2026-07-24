"""Runner 连接注册表 — 管理所有活跃 Runner 连接的增删改查。"""

from __future__ import annotations

from src.plugin_runtime_v2.host.connection import RunnerConnection, RunnerConnectionSnapshot


class RunnerRegistry:
    """Runner 连接注册表，线程安全的字典封装。"""

    def __init__(self) -> None:
        self._connections: dict[str, RunnerConnection] = {}

    def register(self, conn: RunnerConnection) -> None:
        """注册连接。runner_id 已存在时抛出 ValueError。"""
        if conn.runner_id in self._connections:
            raise ValueError("RUNNER_ALREADY_CONNECTED")
        self._connections[conn.runner_id] = conn

    def unregister(self, runner_id: str) -> None:
        """移除连接，不存在时静默忽略。"""
        self._connections.pop(runner_id, None)

    def get(self, runner_id: str) -> RunnerConnection | None:
        """按 runner_id 查找连接。"""
        return self._connections.get(runner_id)

    def get_all(self) -> dict[str, RunnerConnection]:
        """返回全部连接的浅拷贝。"""
        return dict(self._connections)

    def has(self, runner_id: str) -> bool:
        """判断 runner_id 是否存在。"""
        return runner_id in self._connections

    def get_snapshot(self, runner_id: str) -> RunnerConnectionSnapshot | None:
        """返回指定 Runner 的不可变快照。"""
        conn = self._connections.get(runner_id)
        if conn is None:
            return None
        return conn.to_snapshot()

    def get_all_snapshots(self) -> dict[str, RunnerConnectionSnapshot]:
        """返回所有 Runner 的快照字典。"""
        return {rid: conn.to_snapshot() for rid, conn in self._connections.items()}
