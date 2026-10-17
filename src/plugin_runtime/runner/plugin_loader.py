"""插件加载器

在 Runner 进程中负责发现和加载插件。
插件通过 SDK 编写，不再 import src.*。
支持：manifest 校验、依赖解析（拓扑排序）、生命周期钩子。
兼容旧版 src.plugin_system 插件（通过导入钩子 + LegacyPluginAdapter）。
"""

from collections import deque
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Set, Tuple

import contextlib
import importlib
import importlib.util
import json
import os
import re
import sys

from src.common.logger import get_logger
from src.plugin_runtime.runner.manifest_validator import ManifestValidator, PluginManifest, is_reserved_plugin_directory

logger = get_logger("plugin_runtime.runner.plugin_loader")

PluginCandidate = Tuple[Path, PluginManifest, Path]


_LOCAL_FACE_MODULE: Optional[Any] = None


def _local_face_attr(name: str) -> Optional[Any]:
    """从桥接件**本地面**取一个属性；取不到 ⇒ 返回 None（调用方负责具名出声，不静默、不硬崩）。

    为什么按**路径**加载而不是 import：上游 `maibot_sdk.compat` 缺席时它连子模块都 import 不了
    （`sys.modules["maibot_sdk.compat"] = None` ⇒ `ModuleNotFoundError: … is not a package`），
    本地面也**没有**走 `maibot_sdk.compat` 命名空间（那是另一条被否掉的路：
    冒充上游命名空间会让 `upstream_available()` 这类探测**自己骗自己**）。
    ⇒ 与 `_install_local_legacy_face`（本文件 `:654`/`:659`）同法：按路径拿模块、取属性。

    模块对象**进程内缓存**（`_LOCAL_FACE_MODULE`）：`legacy_face` 一执行就读清单 JSON，
    老插件是**每个插件**走一次这条路，重复 exec 是白烧；缓存后 `_BasePlugin` 也恒为**同一个**
    类对象（自检与运行期看到的是同一个身份）。
    ⚠️ 本函数**只负责取**：取到空返回 None（**不**在这里出声）；"取不到"必须由调用方
    连同**具名原因**（plugin_id + 原始异常）一起记 warning —— 见两处调用点。
    """

    global _LOCAL_FACE_MODULE

    if _LOCAL_FACE_MODULE is not None:
        return getattr(_LOCAL_FACE_MODULE, name, None)

    face_path = Path(__file__).resolve().parents[3] / "plugins" / "maibot-team.v1-compat" / "legacy_face.py"
    if not face_path.is_file():
        return None
    try:
        spec = importlib.util.spec_from_file_location("_maibot_local_legacy_face_attrs", face_path)
        if spec is None or spec.loader is None:
            return None
        module = importlib.util.module_from_spec(spec)
        # ⭐ exec 前必须注册进 `sys.modules`（`component-bridge` 实测的加载器缺陷）：
        # 按路径 exec 的模块若不登记，**模块顶层用到的任何"回头查自己"的标准库机制都会崩** ——
        # 实测形态：`@dataclasses.dataclass` 抛
        #     `AttributeError: 'NoneType' object has no attribute '__dict__'`
        # （`dataclasses._is_type` → `sys.modules.get(cls.__module__)` 得 None）。
        # 症状最坏的地方在**它不像加载器的问题**：表现是"兜底面装载失败 ⇒ 老插件又变成
        # `No module named 'src.plugin_system'`"，与"兜底面压根没写"一模一样。
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
    except Exception:  # noqa: BLE001 - (丙)：出声交给调用方，不在这里吞
        return None
    _LOCAL_FACE_MODULE = module
    return getattr(module, name, None)


class PluginMeta:
    """加载后的插件元数据"""

    def __init__(
        self,
        plugin_id: str,
        plugin_dir: str,
        module_name: str,
        plugin_instance: Any,
        manifest: PluginManifest,
    ) -> None:
        """初始化插件元数据。

        Args:
            plugin_id: 插件 ID。
            plugin_dir: 插件目录绝对路径。
            module_name: 插件入口模块名。
            plugin_instance: 插件实例对象。
            manifest: 解析后的强类型 Manifest。
        """
        self.plugin_id = plugin_id
        self.plugin_dir = plugin_dir
        self.module_name = module_name
        self.instance = plugin_instance
        self.manifest = manifest
        self.version = manifest.version
        self.capabilities_required = list(manifest.capabilities)
        self.dependencies: List[str] = list(manifest.plugin_dependency_ids)
        self.component_handlers: Dict[str, str] = {}
        self.llm_provider_handlers: Dict[str, str] = {}


class PluginLoader:
    """插件加载器

    扫描插件目录，加载符合 SDK 规范的插件。
    每个插件目录须包含：
    - _manifest.json: 插件元数据
    - plugin.py: 插件入口模块（导出 create_plugin 工厂函数）
    """

    def __init__(self, host_version: str = "") -> None:
        """初始化插件加载器。

        Args:
            host_version: Host 版本号，用于 manifest 兼容性校验。
        """
        self._loaded_plugins: Dict[str, PluginMeta] = {}
        self._failed_plugins: Dict[str, str] = {}
        self._manifest_validator = ManifestValidator(host_version=host_version)
        self._compat_hook_installed = False
        # 兼容层来源：""（未装）/ "bridge-local"（上游缺席时改用桥接件自带的本地面）
        self._compat_source: str = ""
        self._blocked_plugin_reasons: Dict[str, str] = {}

    def set_blocked_plugin_reasons(self, blocked_plugin_reasons: Optional[Dict[str, str]] = None) -> None:
        """更新当前加载器持有的拒绝加载插件列表。

        Args:
            blocked_plugin_reasons: 需要拒绝加载的插件及原因映射。
        """

        self._blocked_plugin_reasons = {
            str(plugin_id or "").strip(): str(reason or "").strip()
            for plugin_id, reason in (blocked_plugin_reasons or {}).items()
            if str(plugin_id or "").strip() and str(reason or "").strip()
        }

    def get_blocked_plugin_reason(self, plugin_id: str) -> Optional[str]:
        """返回指定插件当前的拒绝加载原因。

        Args:
            plugin_id: 目标插件 ID。

        Returns:
            Optional[str]: 若插件被阻止加载则返回原因，否则返回 ``None``。
        """

        normalized_plugin_id = str(plugin_id or "").strip()
        if not normalized_plugin_id:
            return None
        return self._blocked_plugin_reasons.get(normalized_plugin_id)

    def discover_and_load(
        self,
        plugin_dirs: List[str],
        extra_available: Optional[Dict[str, str]] = None,
    ) -> List[PluginMeta]:
        """扫描多个目录并加载所有插件。

        Args:
            plugin_dirs: 插件目录列表。
            extra_available: 额外视为已满足的外部依赖插件版本映射。

        Returns:
            List[PluginMeta]: 成功加载的插件元数据列表，按依赖顺序排列。
        """
        candidates, duplicate_candidates = self._discover_candidates(plugin_dirs)
        self._record_duplicate_candidates(duplicate_candidates)

        # 第二阶段：依赖解析（拓扑排序）
        load_order, failed_deps = self._resolve_dependencies(candidates, extra_available=extra_available)
        self._record_failed_dependencies(failed_deps)

        # 第三阶段：按依赖顺序加载
        return self._load_plugins_in_order(load_order, candidates)

    def discover_candidates(self, plugin_dirs: List[str]) -> Tuple[Dict[str, PluginCandidate], Dict[str, List[Path]]]:
        """扫描插件目录并返回候选插件。

        Args:
            plugin_dirs: 需要扫描的插件根目录列表。

        Returns:
            Tuple[Dict[str, PluginCandidate], Dict[str, List[Path]]]:
                候选插件映射和重复插件 ID 冲突映射。
        """
        return self._discover_candidates(plugin_dirs)

    def _discover_candidates(self, plugin_dirs: List[str]) -> Tuple[Dict[str, PluginCandidate], Dict[str, List[Path]]]:
        """扫描插件目录并收集候选插件。"""
        candidates: Dict[str, PluginCandidate] = {}
        duplicate_candidates: Dict[str, List[Path]] = {}

        for base_dir_str in plugin_dirs:
            base_dir = Path(base_dir_str)
            if not base_dir.is_dir():
                logger.warning(f"插件目录不存在: {base_dir}")
                continue

            for plugin_dir in sorted(
                entry for entry in base_dir.iterdir() if entry.is_dir() and not is_reserved_plugin_directory(entry)
            ):
                discovered = self._discover_single_candidate(plugin_dir)
                if discovered is None:
                    continue

                plugin_id, candidate = discovered
                if plugin_id in duplicate_candidates:
                    duplicate_candidates[plugin_id].append(candidate[0])
                    continue

                previous = candidates.get(plugin_id)
                if previous is not None:
                    duplicate_candidates[plugin_id] = [previous[0], candidate[0]]
                    candidates.pop(plugin_id, None)
                    continue

                candidates[plugin_id] = candidate

        return candidates, duplicate_candidates

    def _discover_single_candidate(self, plugin_dir: Path) -> Optional[Tuple[str, PluginCandidate]]:
        """发现并校验单个插件目录。"""
        plugin_path = plugin_dir / "plugin.py"
        if not plugin_path.exists():
            return None

        manifest = self._manifest_validator.load_from_plugin_path(plugin_dir)
        if manifest is None:
            errors = "; ".join(self._manifest_validator.errors)
            plugin_id = self._read_manifest_id_for_failure(plugin_dir)
            if plugin_id is not None:
                self._failed_plugins[plugin_id] = f"manifest 校验失败: {errors}"
            else:
                logger.error(f"插件 {plugin_dir.name} manifest 校验失败，但 manifest 未声明 id，无法按插件 ID 上报: {errors}")
            return None

        plugin_id = manifest.id
        if blocked_reason := self.get_blocked_plugin_reason(plugin_id):
            self._failed_plugins[plugin_id] = blocked_reason
            logger.warning(f"插件 {plugin_id} 已被 Host 依赖流水线阻止加载: {blocked_reason}")
            return None

        return plugin_id, (plugin_dir, manifest, plugin_path)

    def _read_manifest_id_for_failure(self, plugin_dir: Path) -> Optional[str]:
        """manifest 校验失败时仍按原始插件 ID 记录失败原因。"""
        manifest_path = plugin_dir / "_manifest.json"
        try:
            with open(manifest_path, "r", encoding="utf-8") as file_obj:
                manifest_data = json.load(file_obj)
        except Exception as exc:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.WARNING, '读取插件失败', exception=exc)
            logger.warning(f"读取插件 {plugin_dir.name} manifest ID 失败，无法按插件 ID 上报失败原因: {exc}")
            return None

        if isinstance(manifest_data, dict):
            plugin_id = str(manifest_data.get("id")).strip()
            if plugin_id:
                return plugin_id

        return None

    def _record_duplicate_candidates(self, duplicate_candidates: Dict[str, List[Path]]) -> None:
        """记录重复插件 ID 错误。"""
        for plugin_id, conflict_dirs in duplicate_candidates.items():
            unique_dirs = sorted({str(path) for path in conflict_dirs})
            reason = f"检测到重复插件 ID: {plugin_id} -> {', '.join(unique_dirs)}"
            self._failed_plugins[plugin_id] = reason
            logger.error(reason)

    def _record_failed_dependencies(self, failed_deps: Dict[str, str]) -> None:
        """记录依赖解析失败信息。"""
        for plugin_id, reason in failed_deps.items():
            self._failed_plugins[plugin_id] = reason
            logger.error(f"插件 {plugin_id} 依赖解析失败: {reason}")

    def _load_plugins_in_order(
        self,
        load_order: List[str],
        candidates: Dict[str, PluginCandidate],
    ) -> List[PluginMeta]:
        """按依赖顺序加载插件。"""
        results: List[PluginMeta] = []
        for plugin_id in load_order:
            plugin_dir, manifest, plugin_path = candidates[plugin_id]
            try:
                if meta := self._load_single_plugin(plugin_id, plugin_dir, manifest, plugin_path):
                    results.append(meta)
            except Exception as e:
                from src.core.error_escalation.types import ErrorLevel
                from src.core.error_escalation_port_registry import get_error_escalation_port
                port = get_error_escalation_port()
                if port is not None:
                    port.report(ErrorLevel.ERROR, '加载插件失败', exception=e)
                self._failed_plugins[plugin_id] = str(e)
                logger.error(f"加载插件失败 [{plugin_id}]: {e}", exc_info=True)

        return results

    def get_plugin(self, plugin_id: str) -> Optional[PluginMeta]:
        """获取已加载的插件"""
        return self._loaded_plugins.get(plugin_id)

    def set_loaded_plugin(self, meta: PluginMeta) -> None:
        """登记一个已经完成初始化的插件。

        Args:
            meta: 待登记的插件元数据。
        """
        self._loaded_plugins[meta.plugin_id] = meta

    def remove_loaded_plugin(self, plugin_id: str) -> Optional[PluginMeta]:
        """移除一个已加载插件的元数据。

        Args:
            plugin_id: 待移除的插件 ID。

        Returns:
            Optional[PluginMeta]: 被移除的插件元数据；不存在时返回 ``None``。
        """
        return self._loaded_plugins.pop(plugin_id, None)

    def purge_plugin_modules(self, plugin_id: str, plugin_dir: str) -> List[str]:
        """清理指定插件目录下的模块缓存。

        Args:
            plugin_id: 插件 ID。
            plugin_dir: 插件目录绝对路径。

        Returns:
            List[str]: 已从 ``sys.modules`` 中移除的模块名列表。
        """
        removed_modules: List[str] = []
        plugin_path = Path(plugin_dir).resolve()
        synthetic_module_name = self._build_safe_module_name(plugin_id)

        for module_name, module in list(sys.modules.items()):
            if module_name == synthetic_module_name:
                removed_modules.append(module_name)
                sys.modules.pop(module_name, None)
                continue

            module_file = getattr(module, "__file__", None)
            if module_file is None:
                continue

            try:
                module_path = Path(module_file).resolve()
            except Exception as exc:
                from src.core.error_escalation.types import ErrorLevel
                from src.core.error_escalation_port_registry import get_error_escalation_port
                port = get_error_escalation_port()
                if port is not None:
                    port.report(ErrorLevel.WARNING, '模块路径解析失败', exception=exc)
                logger.warning("模块路径解析失败: %s", exc)
                continue

            if module_path.is_relative_to(plugin_path):
                removed_modules.append(module_name)
                sys.modules.pop(module_name, None)

        importlib.invalidate_caches()
        return removed_modules

    @staticmethod
    def _build_safe_module_name(plugin_id: str) -> str:
        """将插件 ID 转换为可用于动态导入的安全模块名。

        Args:
            plugin_id: 原始插件 ID。

        Returns:
            str: 仅包含字母、数字和下划线的合成模块名。
        """
        normalized_plugin_id = re.sub(r"[^0-9A-Za-z_]", "_", str(plugin_id or "").strip())
        if normalized_plugin_id and normalized_plugin_id[0].isdigit():
            normalized_plugin_id = f"_{normalized_plugin_id}"
        return f"_maibot_plugin_{normalized_plugin_id or 'plugin'}"

    def list_plugins(self) -> List[str]:
        """列出所有已加载的插件 ID"""
        return list(self._loaded_plugins.keys())

    @property
    def failed_plugins(self) -> Dict[str, str]:
        """返回当前记录的失败插件原因映射。"""
        return dict(self._failed_plugins)

    @property
    def manifest_validator(self) -> ManifestValidator:
        """返回当前加载器持有的 Manifest 校验器。

        Returns:
            ManifestValidator: 当前使用的 Manifest 校验器实例。
        """
        return self._manifest_validator

    # ──── 依赖解析 ────────────────────────────────────────────

    def resolve_dependencies(
        self,
        candidates: Dict[str, PluginCandidate],
        extra_available: Optional[Dict[str, str]] = None,
    ) -> Tuple[List[str], Dict[str, str]]:
        """解析候选插件的依赖顺序。

        Args:
            candidates: 待加载的候选插件集合。
            extra_available: 视为已满足的外部依赖插件版本映射。

        Returns:
            Tuple[List[str], Dict[str, str]]: 可加载顺序和失败原因映射。
        """
        return self._resolve_dependencies(candidates, extra_available=extra_available)

    def load_candidate(self, plugin_id: str, candidate: PluginCandidate) -> Optional[PluginMeta]:
        """加载单个候选插件模块。

        Args:
            plugin_id: 插件 ID。
            candidate: 候选插件三元组。

        Returns:
            Optional[PluginMeta]: 加载成功的插件元数据；失败时返回 ``None``。
        """
        plugin_dir, manifest, plugin_path = candidate
        return self._load_single_plugin(plugin_id, plugin_dir, manifest, plugin_path)

    def _resolve_dependencies(
        self,
        candidates: Dict[str, PluginCandidate],
        extra_available: Optional[Dict[str, str]] = None,
    ) -> Tuple[List[str], Dict[str, str]]:
        """拓扑排序解析加载顺序，返回 (有序列表, 失败项 {id: reason})。"""
        available = set(candidates.keys())
        satisfied_dependencies = {
            str(plugin_id or "").strip(): str(plugin_version or "").strip()
            for plugin_id, plugin_version in (extra_available or {}).items()
            if str(plugin_id or "").strip() and str(plugin_version or "").strip()
        }
        dep_graph: Dict[str, Set[str]] = {}
        failed: Dict[str, str] = {}

        for pid, (_, manifest, _) in candidates.items():
            resolved: Set[str] = set()
            missing_or_incompatible: List[str] = []

            for dependency in manifest.plugin_dependencies:
                dependency_id = dependency.id
                if dependency_id in available:
                    dependency_manifest = candidates[dependency_id][1]
                    if not self._manifest_validator.is_plugin_dependency_satisfied(
                        dependency,
                        dependency_manifest.version,
                    ):
                        missing_or_incompatible.append(
                            f"{dependency_id} (需要 {dependency.version_spec}，当前 {dependency_manifest.version})"
                        )
                        continue
                    resolved.add(dependency_id)
                    continue

                external_dependency_version = satisfied_dependencies.get(dependency_id)
                if external_dependency_version is None:
                    missing_or_incompatible.append(f"{dependency_id} (未找到依赖插件)")
                    continue

                if not self._manifest_validator.is_plugin_dependency_satisfied(
                    dependency,
                    external_dependency_version,
                ):
                    missing_or_incompatible.append(
                        f"{dependency_id} (需要 {dependency.version_spec}，当前 {external_dependency_version})"
                    )

            if missing_or_incompatible:
                failed[pid] = f"依赖未满足: {', '.join(missing_or_incompatible)}"
            dep_graph[pid] = resolved

        # 迭代传播“依赖自身加载失败”到上游依赖方，避免误报为循环依赖
        changed = True
        while changed:
            changed = False
            failed_plugin_ids = set(failed)
            for pid, dependencies in list(dep_graph.items()):
                if pid in failed:
                    dep_graph.pop(pid, None)
                    continue

                failed_dependencies = sorted(dependency for dependency in dependencies if dependency in failed_plugin_ids)
                if not failed_dependencies:
                    continue

                failed[pid] = f"依赖未满足: {', '.join(f'{dependency} (依赖插件加载失败)' for dependency in failed_dependencies)}"
                dep_graph.pop(pid, None)
                changed = True

        # Kahn 拓扑排序
        indegree = {pid: len(deps) for pid, deps in dep_graph.items()}
        reverse: Dict[str, Set[str]] = {pid: set() for pid in dep_graph}
        for pid, deps in dep_graph.items():
            for d in deps:
                if d in reverse:
                    reverse[d].add(pid)

        queue = deque(sorted(pid for pid, deg in indegree.items() if deg == 0))
        sorted_order: List[str] = []

        while queue:
            current = queue.popleft()
            sorted_order.append(current)
            for dependent in sorted(reverse.get(current, [])):
                indegree[dependent] -= 1
                if indegree[dependent] == 0:
                    queue.append(dependent)

        cycle_plugins = {pid for pid, deg in indegree.items() if deg > 0}
        for pid in cycle_plugins:
            failed[pid] = "检测到循环依赖"

        return sorted_order, failed

    # ──── 单个插件加载 ────────────────────────────────────────

    def _load_single_plugin(
        self,
        plugin_id: str,
        plugin_dir: Path,
        manifest: PluginManifest,
        plugin_path: Path,
    ) -> Optional[PluginMeta]:
        """加载单个插件"""
        # 确保兼容层导入钩子已安装（旧版插件可能 import src.plugin_system）
        self._ensure_compat_hook()

        # 动态导入插件模块
        module_name = self._build_safe_module_name(plugin_id)
        spec = importlib.util.spec_from_file_location(
            module_name,
            str(plugin_path),
            submodule_search_locations=[str(plugin_dir)],
        )
        if spec is None or spec.loader is None:
            logger.error(f"无法创建模块 spec: {plugin_path}")
            return None

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module

        plugin_parent_dir = plugin_dir.parent
        src_root = Path("src").resolve()
        try:
            with self._temporary_sys_path_entry(src_root):
                with self._temporary_sys_path_entry(plugin_parent_dir):
                    spec.loader.exec_module(module)

                    # 优先使用新版 create_plugin 工厂函数
                    create_plugin = getattr(module, "create_plugin", None)
                    if create_plugin is not None:
                        instance = create_plugin()
                        self._validate_sdk_plugin_contract(plugin_id, instance)
                        logger.info(f"插件 {plugin_id} v{manifest.version} 加载成功")
                        return PluginMeta(
                            plugin_id=plugin_id,
                            plugin_dir=str(plugin_dir),
                            module_name=module_name,
                            plugin_instance=instance,
                            manifest=manifest,
                        )

                    # 回退：检测旧版 @register_plugin 标记的 BasePlugin 子类
                    instance = self._try_load_legacy_plugin(module, plugin_id)
                    if instance is not None:
                        logger.info(
                            f"插件 {plugin_id} v{manifest.version} 通过旧版兼容层加载成功（请尽快迁移到 maibot_sdk）"
                        )
                        return PluginMeta(
                            plugin_id=plugin_id,
                            plugin_dir=str(plugin_dir),
                            module_name=module_name,
                            plugin_instance=instance,
                        manifest=manifest,
                    )
        except Exception as exc:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.WARNING, '插件加载失败', exception=exc)
            logger.warning("插件加载失败: %s", exc)
            sys.modules.pop(module_name, None)
            raise

        # ⭐ 静默收口（silence-first §3b）：这条兜底**也必须落进 `_failed_plugins`** —— 否则宿主三栏里
        # 既没有 loaded、也没有 failed，插件等于"凭空消失"（宿主看不到任何东西）。
        # ⚠️ 补丁件写的 `self._compat_hook_error` **本文件并不存在**（全树 grep 无命中）
        #    ⇒ 用本树**现有**信号 `_compat_source` 代替：空 ⇔ 本地兼容面没接上 ⇔ 无法用旧版面识别。
        if not self._compat_source:
            reason = (
                "无法判定是否为旧版插件：兼容层不可用"
                "（本地兼容面未接上）⇒ 该插件既没有 create_plugin 工厂函数，也无法用旧版面识别"
            )
            self._failed_plugins[plugin_id] = reason
            logger.warning("插件 %s %s", plugin_id, reason)
            return None
        self._failed_plugins[plugin_id] = "缺少 create_plugin 工厂函数且未检测到旧版 BasePlugin"
        logger.error(f"插件 {plugin_id} 缺少 create_plugin 工厂函数且未检测到旧版 BasePlugin")
        return None

    @staticmethod
    def _validate_sdk_plugin_contract(plugin_id: str, instance: Any) -> None:
        """校验 SDK 插件的基础契约。

        Args:
            plugin_id: 当前插件 ID。
            instance: ``create_plugin()`` 返回的插件实例。

        Raises:
            TypeError: 当插件未覆盖必需生命周期方法或订阅声明不合法时抛出。
        """

        try:
            from maibot_sdk.plugin import MaiBotPlugin
        except ImportError:
            return

        if not isinstance(instance, MaiBotPlugin):
            return

        if type(instance).on_load is MaiBotPlugin.on_load:
            raise TypeError(f"插件 {plugin_id} 必须实现 on_load()")
        if type(instance).on_unload is MaiBotPlugin.on_unload:
            raise TypeError(f"插件 {plugin_id} 必须实现 on_unload()")
        if type(instance).on_config_update is MaiBotPlugin.on_config_update:
            raise TypeError(f"插件 {plugin_id} 必须实现 on_config_update()")

        instance.get_config_reload_subscriptions()

    @staticmethod
    @contextlib.contextmanager
    def _temporary_sys_path_entry(path: Path) -> Iterator[None]:
        """临时将路径放入 sys.path 头部，并在离开作用域后恢复。"""
        normalized_path = os.path.normpath(str(path))
        existing_paths = {os.path.normpath(entry) for entry in sys.path}
        inserted = normalized_path not in existing_paths
        if inserted:
            sys.path.insert(0, normalized_path)

        try:
            yield
        finally:
            if inserted:
                with contextlib.suppress(ValueError):
                    sys.path.remove(normalized_path)

    # ──── 旧版插件兼容 ────────────────────────────────────────

    def _ensure_compat_hook(self) -> None:
        """安装旧版 src.plugin_system 导入钩子（幂等）。

        上游 `maibot_sdk.compat` 缺席时**不再直接放弃**：改试桥接件自带的本地面
        （`plugins/maibot-team.v1-compat/legacy_face.py`）⇒ 成功则记 `_compat_source = "bridge-local"`。
        """
        if self._compat_hook_installed:
            return
        try:
            from maibot_sdk.compat._import_hook import install_hook

            install_hook()
            self._compat_hook_installed = True
        except ImportError:
            self._compat_source = self._install_local_legacy_face()
            if self._compat_source:
                self._compat_hook_installed = True
                return
            logger.debug("maibot_sdk.compat 不可用，跳过导入钩子安装")

    @staticmethod
    def _install_local_legacy_face() -> str:
        """试装桥接件自带的本地兜底面；返回来源标记（`"bridge-local"`）或空串（没装成）。

        - **(丙) 不阻断**：面不在 / 装载失败 ⇒ 只记 `warning` 并返回空串 —— 老插件随后仍按原路径
          失败并**具名上报**（不静默、也不把主流程卡死）；
        - **(丁) 空壳要炸**：`install_local_face()` 内部先调 `assert_nonempty()` ⇒ "面是空的"当场抛，
          不会拿一个恒空 stub 冒充"兼容层可用"。

        Returns:
            str: 装成 = `"bridge-local"`；没装成 = `""`（调用方据此决定是否放弃）。
        """
        face_path = Path(__file__).resolve().parents[3] / "plugins" / "maibot-team.v1-compat" / "legacy_face.py"
        if not face_path.is_file():
            logger.warning("上游 maibot_sdk.compat 不可用，且本地兜底面缺失（老插件将按原路径失败）: %s", face_path)
            return ""
        try:
            spec = importlib.util.spec_from_file_location("_maibot_local_legacy_face", face_path)
            if spec is None or spec.loader is None:
                logger.warning("本地兜底面无法建立模块 spec（不阻断）: %s", face_path)
                return ""
            module = importlib.util.module_from_spec(spec)
            # ⭐ 同 `_local_face_attr`：exec 前注册进 `sys.modules`（按路径 exec 的模块若不登记，
            # 其顶层 `@dataclass` 会在装饰期崩 —— 实测 `AttributeError: 'NoneType' object has no
            # attribute '__dict__'`，而症状呈现为"兜底面装载失败"，看着像面写错了）。
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
            mode = module.install_local_face()
            counts = module.coverage()
            logger.warning(
                "上游 maibot_sdk.compat 不可用 ⇒ 已启用桥接件本地兜底面（%s / %s；覆盖=%s）",
                mode,
                face_path,
                counts,
            )
            return "bridge-local"
        except Exception as exc:  # noqa: BLE001 - 兜底面失败**不许阻断**加载，但必须出声
            logger.warning("本地兜底面装载失败（不阻断，老插件将按原路径失败）: %s", exc)
            return ""

    def _try_load_legacy_plugin(self, module: Any, plugin_id: str) -> Optional[Any]:
        """尝试从模块中发现旧版 BasePlugin 子类并包装为 LegacyPluginAdapter

        ⚠️ 本方法由 `@staticmethod` 改成实例方法（`adapter-hop`）："认子类"的退路需要读
        `self._compat_source`（本地面到底启用没启用）。两处调用点本来就走 `self.`（`:536`），
        故改签名不影响调用方。
        """
        # 方式 1: @register_plugin 装饰器设置的标记
        legacy_cls = getattr(module, "_legacy_plugin_class", None)

        # 方式 2: 扫描模块中所有 BasePlugin 子类
        if legacy_cls is None:
            # ── 第 1 跳（`adapter-hop`：上游优先、缺席取本地面）───────────────────
            try:
                from maibot_sdk.compat.base.base_plugin import BasePlugin as LegacyBasePlugin
            except ImportError as exc:
                LegacyBasePlugin = _local_face_attr("_BasePlugin")
                if LegacyBasePlugin is None:
                    # ⭐ 静默收口（silence-first §3a）：**拿不到基类**（上游缺席且兜底面没接上）必须**具名出声**，
                    # 否则这条路径会退化成"插件凭空消失"（宿主三栏全空）。
                    # ⚠️ 补丁件（silence-first.patch.md §3a）写的 `LegacyCompatUnavailableError` **本文件/本树并不存在**
                    #    （全树 grep 只命中那份补丁件自身）⇒ 按它"不新增类型"的约束，这里**复用原始异常类型**
                    #    `ImportError`、把具名原因放进消息；宿主侧由 `_load_plugins_in_order` 的
                    #    `_failed_plugins[plugin_id] = str(e)` 接住（本文件 `:253-259`）。
                    raise ImportError(
                        f"旧版插件 {plugin_id} 需要兼容层来识别，但兼容层不可用"
                        f"（{type(exc).__name__}: {exc}）"
                    ) from exc
                # ⭐ 中间证据（判据 (甲) 的可读性）：第一跳取到没、从哪儿取的。
                logger.warning(
                    "旧版插件 %s：上游 maibot_sdk.compat 不可用（%s）⇒ 第 1 跳改取桥接件本地面基类 %r（来源=bridge-local）",
                    plugin_id,
                    exc,
                    LegacyBasePlugin,
                )

            for attr_name in dir(module):
                obj = getattr(module, attr_name, None)
                if isinstance(obj, type) and issubclass(obj, LegacyBasePlugin) and obj is not LegacyBasePlugin:
                    legacy_cls = obj
                    break

        # ⭐ 上游缺席时的"认子类"退路（第一跳的**实测补丁**，见 `adapter-hop` 回执）：
        # 此刻 `maibot_sdk.compat` 不可 import ⇒ 上面那个 `isinstance/issubclass` 比对拿不到
        # 上游 `BasePlugin` 类对象；而插件模块里那个基类是**本地面**的 `_BasePlugin`
        # （`src.plugin_system` 的 import 由本地面接管）⇒ 比对基类上的**面标记**即可。
        # ⛔ 不挂命名空间、不冒充上游模块（路 B 的理由）；只在"上游真取不到"时生效。
        # ⚠️ 还要 `_compat_source == "bridge-local"` 这道门：标记只该在本地面**真被启用**时生效
        #    （否则"上游在场、这个插件恰好不是旧版"的情形也会去按标记扫一遍 —— 扫描本身无害，
        #    但"凭一个装饰性属性就认成旧插件"这件事必须有个前置条件兜着）。该属性在
        #    `_ensure_compat_hook` 里由本分支持有（`:681-690` / `:74`），故这里读到的不可能是过期值。
        if legacy_cls is None and self._compat_source == "bridge-local":
            for attr_name in dir(module):
                obj = getattr(module, attr_name, None)
                if not isinstance(obj, type) or not getattr(obj, "_local_legacy_face_base", False):
                    continue
                for candidate in module.__dict__.values():
                    if (
                        isinstance(candidate, type)
                        and candidate is not obj
                        and issubclass(candidate, obj)
                        and candidate.__module__ == module.__name__
                    ):
                        legacy_cls = candidate
                        logger.warning(
                            "旧版插件 %s：上游基类不可用 ⇒ 按本地面标记认出子类 %s（来源=bridge-local）",
                            plugin_id,
                            candidate.__name__,
                        )
                        break
                if legacy_cls is not None:
                    break

        if legacy_cls is None:
            return None

        try:
            # ── 第 2 跳（`adapter-hop`：上游优先、缺席取本地面）───────────────────
            try:
                from maibot_sdk.compat.legacy_adapter import LegacyPluginAdapter
            except ImportError:
                LegacyPluginAdapter = _local_face_attr("LocalLegacyPluginAdapter")
                if LegacyPluginAdapter is None:
                    # (丙)：具名出声 + 不阻断 —— 上游与兜底面**都不在**，这条插件按原路径失败。
                    logger.warning(
                        "旧版插件 %s 缺少 adapter（上游 maibot_sdk.compat.legacy_adapter 缺失 + "
                        "本地兜底面不可用：%s）⇒ 无法适配，按原路径失败",
                        plugin_id,
                        Path(__file__).resolve().parents[3] / "plugins" / "maibot-team.v1-compat" / "legacy_face.py",
                    )
                    return None

            legacy_instance = legacy_cls()
            adapter = LegacyPluginAdapter(legacy_instance)
            # ⭐ 中间证据（判据 (甲) 的可读性）：第二跳构造成功没。
            logger.warning(
                "旧版插件 %s：adapter 构造成功（%s ← %s；来源=%s）",
                plugin_id,
                type(adapter).__name__,
                type(legacy_instance).__name__,
                "bridge-local" if LegacyPluginAdapter.__module__ == "_maibot_local_legacy_face_attrs" else "upstream",
            )
            return adapter
        except Exception as e:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.ERROR, '旧版插件加载失败', exception=e)
            logger.error(f"旧版插件 {plugin_id} 适配失败: {e}", exc_info=True)
            return None
