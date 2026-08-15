"""ZG16-3 测试共享辅助 — manifest 工厂 + MockSupervisor。

供 7 个 ZG16-3 测试文件复用，避免重复的 manifest 构造与 supervisor mock。
"""

import json
from pathlib import Path
from typing import Any

from src.plugin_runtime_v2.host.runner_supervisor import SpawnResult
from src.plugin_runtime_v2.sdk.manifest import ManifestV3


def make_manifest_dict(
    plugin_id: str,
    dependencies: list[str] | None = None,
    name: str | None = None,
    version: str = "1.0.0",
    scopes: list[str] | None = None,
) -> dict[str, Any]:
    """构造 manifest v3 dict（供写文件或直接 model_validate）。"""
    return {
        "manifest_version": 3,
        "id": plugin_id,
        "version": version,
        "name": name or plugin_id.split(".")[-1],
        "author": {"name": "test", "url": ""},
        "scopes": scopes or ["message:send:text"],
        "dependencies": dependencies or [],
    }


def make_manifest(
    plugin_id: str,
    dependencies: list[str] | None = None,
    name: str | None = None,
) -> ManifestV3:
    """构造 ManifestV3 实例。"""
    return ManifestV3.model_validate(make_manifest_dict(plugin_id, dependencies, name))


def write_plugin_dir(
    base: Path,
    plugin_id: str,
    dependencies: list[str] | None = None,
    name: str | None = None,
    manifest_filename: str = "manifest.json",
    dir_name: str | None = None,
    raw_content: str | None = None,
) -> Path:
    """在 base 下创建插件目录 + manifest 文件，返回目录路径。

    Args:
        raw_content: 若提供则直接写入（用于测试非法 JSON），否则用 make_manifest_dict 构造
        dir_name: 目录名（默认用 plugin_id 的点替换为下划线）
    """
    d = dir_name or plugin_id.replace(".", "_")
    plugin_dir = base / d
    plugin_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = plugin_dir / manifest_filename
    if raw_content is not None:
        manifest_path.write_text(raw_content, encoding="utf-8")
    else:
        manifest_path.write_text(
            json.dumps(make_manifest_dict(plugin_id, dependencies, name), ensure_ascii=False),
            encoding="utf-8",
        )
    return plugin_dir


class MockSupervisor:
    """RunnerSupervisor 的异步 mock——记录 spawn 调用顺序，可配置失败插件。"""

    def __init__(
        self,
        success: bool = True,
        fail_ids: set[str] | None = None,
        reason: str = "mock fail",
    ) -> None:
        self._success = success
        self._fail_ids = fail_ids or set()
        self._reason = reason
        self.spawn_calls: list[tuple[str, str]] = []

    async def spawn_and_wait(self, plugin_id: str, plugin_dir: str) -> SpawnResult:
        self.spawn_calls.append((plugin_id, plugin_dir))
        if plugin_id in self._fail_ids:
            return SpawnResult(runner_id=plugin_id, success=False, reason=self._reason)
        return SpawnResult(runner_id=plugin_id, success=self._success)

    def set_servicer(self, servicer) -> None:
        """兼容 bootstrap 注入链。"""

    def start(self) -> None:
        """兼容 bootstrap 启动。"""

    async def stop(self) -> None:
        """兼容 bootstrap 关停。"""


class ExceptionSupervisor(MockSupervisor):
    """spawn_and_wait 对 fail_ids 抛异常（而非返回失败结果）。"""

    async def spawn_and_wait(self, plugin_id: str, plugin_dir: str) -> SpawnResult:
        self.spawn_calls.append((plugin_id, plugin_dir))
        if plugin_id in self._fail_ids:
            raise RuntimeError(f"spawn exception for {plugin_id}")
        return SpawnResult(runner_id=plugin_id, success=self._success)


class MockRunnerSupervisorFactory:
    """RunnerSupervisor 类的 mock 替换——供 bootstrap 集成测试用。

    用法：monkeypatch.setattr("...runner_supervisor.RunnerSupervisor", MockRunnerSupervisorFactory)
    每次实例化返回一个共享的 mock 实例（通过 .last_instance 访问）。
    """

    _instance: MockSupervisor | None = None

    def __new__(cls, *args, **kwargs) -> MockSupervisor:
        cls._instance = MockSupervisor()
        return cls._instance

    @classmethod
    def get_instance(cls) -> MockSupervisor | None:
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        cls._instance = None