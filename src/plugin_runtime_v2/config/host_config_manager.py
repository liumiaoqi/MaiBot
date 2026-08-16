"""ZG16-6a: Host 侧插件配置管理协调器——合并 + revision + 推送 + dump。

设计参考：dsh SettingsProvider.publish/commit `settings/src/index.ts:657-684,749-799`。
"""

import asyncio
import hashlib
import json
import tomllib

import grpc

from src.common.logger import get_logger
from src.core.protocols import AppConfigPort
from src.plugin_runtime_v2.config.merger import (
    merge_layers,
    merge_three_layers,
    merge_with_provenance,
    resolve_stream_override,
)
from src.plugin_runtime_v2.config.revision_store import RevisionStore
from src.plugin_runtime_v2.config.schema_drift import SchemaDriftDetector

logger = get_logger("plugin_runtime_v2.config.host_config_manager")


class RunnerConfigStub:
    """Host → Runner gRPC stub 包装——按 plugin_id 路由到对应 Runner。

    从 HostEndpoint.registry 查 runner_listen_address，动态创建 channel + stub。
    """

    def __init__(self, registry) -> None:
        self._registry = registry

    async def UpdatePluginConfig(self, request):
        """按 request.plugin_id 查 Runner 地址 → 创建 stub → 调用。"""
        from src.plugin_runtime_v2.proto.plugin_config_pb2_grpc import (
            PluginConfigServiceStub,
        )

        listen_address = self._find_runner_address(request.plugin_id)
        if listen_address is None:
            raise ConnectionError(
                f"插件 {request.plugin_id} 对应的 Runner 未连接"
            )
        channel = grpc.aio.insecure_channel(listen_address)
        stub = PluginConfigServiceStub(channel)
        try:
            resp = await stub.UpdatePluginConfig(request)
            return resp
        finally:
            await channel.close()

    def _find_runner_address(self, plugin_id: str) -> str | None:
        """从 registry 按 plugin_id 查 Runner 的 listen_address。"""
        for conn in self._registry.get_all().values():
            if conn.plugin_id == plugin_id and conn.runner_listen_address:
                return conn.runner_listen_address
        return None


class PluginConfigManager:
    """Host 侧插件配置管理协调器——合并 + revision + 推送 + dump。"""

    def __init__(
        self,
        app_config_port: AppConfigPort,
        revision_store: RevisionStore,
        grpc_stub,  # Host → Runner gRPC stub
        audit_log_path: str = "logs/config_audit.jsonl",
    ) -> None:
        self._port = app_config_port
        self._revision_store = revision_store
        self._grpc_stub = grpc_stub
        self._config_cache: dict[str, dict] = {}  # plugin_id → 合并后配置
        self._config_hashes: dict[str, str] = {}  # plugin_id → SHA-256 哈希
        self._schemas: dict[str, type | None] = {}  # plugin_id → pydantic schema
        self._plugin_base_paths: dict[str, str] = {}  # plugin_id → config.toml 路径
        self._audit_log_path = audit_log_path

    async def load_plugin_config(
        self,
        plugin_id: str,
        base_path: str,
        stream_id: str | None = None,
    ) -> dict:
        """加载插件配置：读取三层 → 合并 → schema 校验 → 缓存 → revision bump → 返回。"""
        self._plugin_base_paths[plugin_id] = base_path
        base, global_override, stream_override = await self._read_three_layers(
            plugin_id, base_path, stream_id
        )
        merged = merge_three_layers(base, global_override, stream_override)
        # schema 漂移检测
        if self._port.get_enable_schema_drift_detect():
            SchemaDriftDetector.detect(plugin_id, merged, self._schemas.get(plugin_id))
        # 缓存 + revision bump
        self._config_cache[plugin_id] = merged
        self._config_hashes[plugin_id] = self._hash(merged)
        self._revision_store.bump(plugin_id)
        return merged

    async def _read_three_layers(
        self,
        plugin_id: str,
        base_path: str,
        stream_id: str | None,
    ) -> tuple[dict, dict, dict]:
        """读取三层配置：base（插件 config.toml）+ 全局覆盖 + 聊天流覆盖。"""
        # base 层：插件 config.toml
        base = self._read_toml(base_path)  # 不存在返回 {}
        # 全局覆盖 + per_stream：通过 AppConfigPort 读取 bot_config [plugin_override] 节
        global_override, per_stream = self._read_plugin_override(plugin_id)
        stream_override = resolve_stream_override(plugin_id, stream_id, per_stream)
        return base, global_override, stream_override

    def _read_toml(self, path: str) -> dict:
        """读取 TOML 文件，不存在返回空 dict。"""
        try:
            with open(path, "rb") as f:
                return tomllib.load(f)
        except FileNotFoundError:
            logger.info(f"插件配置文件不存在，base 为空: {path}")
            return {}

    def _read_plugin_override(self, plugin_id: str) -> tuple[dict, dict]:
        """通过 AppConfigPort 读取 bot_config [plugin_override.{id}] 节。

        无该节时返回 ({}, {})（退化为仅 base 层，spec 5.6.1 规则 6）。
        """
        return self._port.get_plugin_override(plugin_id)

    async def handle_file_change(
        self,
        plugin_id: str,
        source: str,  # 'file_watcher' | 'webui' | 'sdk_update'
    ) -> None:
        """处理配置文件变更：磁盘对账 → 重新合并 → revision bump → gRPC 推送。

        设计参考 dsh reconcileFromDisk `settings-file/src/index.ts:321`。
        """
        # 磁盘对账：重新读盘合并 → 计算哈希 → 比对缓存哈希
        new_config = await self._reload_and_merge(plugin_id)
        new_hash = self._hash(new_config)
        cached_hash = self._config_hashes.get(plugin_id)
        if new_hash == cached_hash:
            return  # 深相等跳过（spec 5.3.1 规则 4a）
        # 磁盘内容变化 → 更新缓存 + revision bump + 推送
        self._config_cache[plugin_id] = new_config
        self._config_hashes[plugin_id] = new_hash
        new_revision = self._revision_store.bump(plugin_id)
        await self._push_to_runner(plugin_id, new_config, new_revision, source)

    async def _reload_and_merge(self, plugin_id: str) -> dict:
        """重新读盘 + 合并三层。"""
        base_path = self._plugin_base_paths.get(plugin_id, "")
        base, global_override, stream_override = await self._read_three_layers(
            plugin_id, base_path, stream_id=None
        )
        return merge_three_layers(base, global_override, stream_override)

    async def _push_to_runner(
        self,
        plugin_id: str,
        config: dict,
        revision: int,
        source: str,
    ) -> None:
        """gRPC UpdatePluginConfig 推送，失败重试 3 次指数退避（spec 5.3.3 场景 2）。"""
        from src.plugin_runtime_v2.proto import plugin_config_pb2

        request = plugin_config_pb2.UpdatePluginConfigRequest(
            plugin_id=plugin_id,
            config_json=json.dumps(config),
            revision=revision,
            source=source,
        )
        for attempt in range(3):
            try:
                await self._grpc_stub.UpdatePluginConfig(request)
                return
            except Exception as e:
                if attempt < 2:
                    await asyncio.sleep(2 ** attempt)  # 指数退避
                    continue
                logger.error(f"gRPC 推送失败（重试 3 次）: {e}")
                # 上报 error_escalation_port
                from src.core.error_escalation.types import ErrorLevel
                from src.core.error_escalation_port_registry import get_error_escalation_port
                port = get_error_escalation_port()
                if port is not None:
                    port.report(ErrorLevel.ERROR, f"插件 {plugin_id} 配置推送失败: {e}", component_id=plugin_id)

    @staticmethod
    def _hash(config: dict) -> str:
        """SHA-256 哈希（深相等跳过用）。"""
        return hashlib.sha256(
            json.dumps(config, sort_keys=True).encode()
        ).hexdigest()

    async def update_config(
        self,
        plugin_id: str,
        patch: dict,
        expected_revision: int | None,
        source: str,
        writer: str,
    ) -> dict:
        """配置更新：乐观并发检查 → 应用 patch → 合并 → revision bump → gRPC 推送 → 审计日志。"""
        # 乐观并发检查
        self._revision_store.check(plugin_id, expected_revision)
        # 应用 patch + 合并
        current = self._config_cache.get(plugin_id, {})
        new_config = merge_layers(current, patch)
        # schema 校验
        if self._port.get_enable_schema_drift_detect():
            drift = SchemaDriftDetector.detect(plugin_id, new_config, self._schemas.get(plugin_id))
            if drift and (drift.missing_keys or drift.type_mismatches):
                # schema 校验失败保留旧配置（spec 5.1.3 场景 4）
                logger.error(f"插件 {plugin_id} schema 校验失败，保留旧配置")
                return current
        # 缓存 + revision bump + 推送 + 审计
        self._config_cache[plugin_id] = new_config
        self._config_hashes[plugin_id] = self._hash(new_config)
        new_revision = self._revision_store.bump(plugin_id)
        await self._push_to_runner(plugin_id, new_config, new_revision, source)
        self._write_audit_log(plugin_id, new_revision, source, writer, current, new_config)
        return new_config

    def get_config(
        self,
        plugin_id: str,
        stream_id: str | None = None,
    ) -> dict:
        """返回缓存的合并后配置（内存读取，O(1)）。"""
        return self._config_cache.get(plugin_id, {})

    async def dump_config(
        self,
        plugin_id: str,
        stream_id: str | None = None,
        fmt: str = "human",  # 'human' | 'json'
    ) -> dict | str:
        """dump 配置快照 + provenance。用同一 mergeLayers 算法，与实际生效一致。"""
        base, global_override, stream_override = await self._read_three_layers(
            plugin_id, self._plugin_base_paths.get(plugin_id, ""), stream_id
        )
        merged, provenance = merge_with_provenance(
            base, global_override, stream_override,
            self._plugin_base_paths.get(plugin_id, ""), "config/bot_config.toml",
        )
        revision = self._revision_store.get(plugin_id)
        if fmt == "json":
            from src.plugin_runtime_v2.config.dump import render_config_dump_json
            return render_config_dump_json(merged, provenance, revision)
        from src.plugin_runtime_v2.config.dump import render_config_dump_human
        return render_config_dump_human(merged, provenance, revision)

    def _write_audit_log(self, plugin_id, revision, source, writer, prev, new) -> None:
        """审计日志（JSON Lines，禁止静默写入，spec 4.3.4）。

        每行一个 JSON 对象：{ts, plugin_id, revision, source, writer, prev, new}。
        """
        import time
        from pathlib import Path

        entry = {
            "ts": time.time(),
            "plugin_id": plugin_id,
            "revision": revision,
            "source": source,
            "writer": writer,
            "prev": prev,
            "new": new,
        }
        log_path = Path(self._audit_log_path)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        logger.info(f"配置变更审计已写入: plugin={plugin_id} rev={revision} source={source}")

    def register_schema(self, plugin_id: str, schema: type | None) -> None:
        """注册插件配置 schema（用于漂移检测）。"""
        self._schemas[plugin_id] = schema