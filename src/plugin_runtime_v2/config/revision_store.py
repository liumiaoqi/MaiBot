"""ZG16-6a: 每插件配置 revision 持久化——单调递增 + 乐观并发检查。

设计参考：dsh bumpRevision `index.ts:719-723` + SettingsConflictError `index.ts:164-183`。
"""

import json
from pathlib import Path

from src.common.logger import get_logger

logger = get_logger("plugin_runtime_v2.config.revision_store")


class ConfigConflictError(Exception):
    """配置乐观并发冲突错误。设计参考 dsh SettingsConflictError `index.ts:164-183`。"""

    def __init__(self, plugin_id: str, expected: int, actual: int) -> None:
        self.plugin_id = plugin_id
        self.expected = expected
        self.actual = actual
        super().__init__(
            f"插件 {plugin_id} 配置已变更（期望 revision {expected}, 实际 {actual}）"
        )


class RevisionStore:
    """每插件配置 revision 持久化——单调递增 + 乐观并发检查。"""

    def __init__(self, path: str) -> None:
        """加载磁盘 revision 文件到内存 dict。"""
        self._path = Path(path)
        self._revisions: dict[str, int] = self._load()

    def _load(self) -> dict[str, int]:
        """从磁盘加载 revision（文件不存在/损坏时返回空 dict + warning）。"""
        if not self._path.exists():
            return {}
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"revision 文件损坏，回退到空: {e}")
            return {}

    def get(self, plugin_id: str) -> int:
        """返回插件当前 revision（内存读取，O(1)）。"""
        return self._revisions.get(plugin_id, 0)

    def bump(self, plugin_id: str) -> int:
        """revision += 1 → 持久化 → 返回新值。

        设计参考 dsh bumpRevision `index.ts:719-723`。
        spec 5.4.1 规则 1：任意变更（含 resolved value 不变）触发 += 1。
        """
        self._revisions[plugin_id] = self._revisions.get(plugin_id, 0) + 1
        self._persist()
        return self._revisions[plugin_id]

    def check(self, plugin_id: str, expected: int | None) -> None:
        """乐观并发检查。expected is None → 通过；expected != actual → 抛 ConfigConflictError。

        设计参考 dsh 队列内 revision 检查 `index.ts:622-627`。
        """
        if expected is None:
            return  # 未携带 expected，跳过检查（FileWatcher 触发）
        actual = self._revisions.get(plugin_id, 0)
        if expected != actual:
            raise ConfigConflictError(plugin_id, expected, actual)

    def _persist(self) -> None:
        """原子写入 revision 文件（writeFileAtomic + withFileLock）。

        设计参考 dsh `settings-file/src/index.ts:215,227`。
        持久化失败时内存 revision 仍递增 + warning（spec 5.4.3 场景 1）。
        """
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._revisions), encoding="utf-8")
            tmp.replace(self._path)  # 原子 rename
        except OSError as e:
            logger.warning(f"revision 持久化失败，内存 revision 仍递增: {e}")