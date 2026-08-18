"""ZG-27 Profile snapshot 过期 shrinker（测试专用，未在生产环境注册）。

spec 5.4.1 规则 3：count=过期 snapshot 数，scan=删过期，seeks=1，priority_score=600。

本 shrinker 未在 kernel_initializer.init_watermark_reclaim 中注册——快照由
metadata_store 按需构建，无内存 _snapshots dict 可回收。保留此文件仅用于测试
shrinker 接口契约（count_objects/scan_objects）。参见 kernel_initializer.py:667-671。
"""

import time

from src.A_memorix.core.runtime.shrinker import ShrinkControl


class ProfileSnapshotShrinker:
    """Profile snapshot 过期 shrinker。"""

    name = "profile_snapshot"
    batch = 0
    seeks = 1
    flags = 0

    def __init__(self, person_profile_service) -> None:
        self._service = person_profile_service

    def _get_snapshots(self) -> dict:
        """获取 snapshots dict（容错）。"""
        snapshots = getattr(self._service, "_snapshots", None)
        return snapshots if isinstance(snapshots, dict) else {}

    def _is_stale(self, snapshot, now: float) -> bool:
        """检查 snapshot 是否过期。"""
        is_stale_fn = getattr(self._service, "_is_snapshot_stale", None)
        if is_stale_fn is not None:
            try:
                return bool(is_stale_fn(snapshot))
            except Exception:
                pass
        expires_at = getattr(snapshot, "expires_at", None)
        return expires_at is not None and expires_at < now

    async def count_objects(self, sc: ShrinkControl) -> int:
        """相一：过期 snapshot 数。"""
        snapshots = self._get_snapshots()
        if not snapshots:
            return 0
        now = time.monotonic()
        count = 0
        for snapshot in snapshots.values():
            if self._is_stale(snapshot, now):
                count += 1
        return count

    async def scan_objects(self, sc: ShrinkControl) -> int:
        """相二：删过期 snapshot。"""
        snapshots = self._get_snapshots()
        if not snapshots:
            return 0
        now = time.monotonic()
        expired_keys = []
        for key, snapshot in snapshots.items():
            is_pinned = getattr(snapshot, "is_pinned", False)
            if is_pinned:
                continue
            if self._is_stale(snapshot, now):
                expired_keys.append(key)
        for key in expired_keys:
            snapshots.pop(key, None)
        sc.nr_scanned = len(expired_keys)
        return len(expired_keys)