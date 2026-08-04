"""模型注册表 — 组件自治模型配置的核心查询基座（ZG-12）。

对标 Linux device model：设备（模型）由总线集中注册（build_index），
驱动（组件）声明需求（@model_requirement）后按能力查询（query_by_capability）。

三级索引：
- _provider_index: provider_name → APIProvider
- _model_index: (category, name) → ModelEntry
- _capability_index: capability → [ModelEntry]
"""

import random
from collections.abc import Sequence

from src.config.model_configs import APIProvider
from src.llm_models.model_requirement import (
    DEFAULT_SOURCE,
    OPTIONS_SOURCE,
    ComponentDeclaration,
    DeclarationError,
    ModelEntry,
    ResolutionOptions,
    ResolvedModel,
    get_all_declarations,
)

BALANCE_STRATEGY = "balance"
RANDOM_STRATEGY = "random"
SEQUENTIAL_STRATEGY = "sequential"


class ModelRegistry:
    """模型注册表单例 — 从配置构建三级索引并提供能力查询。

    线程安全说明：索引构建（build_index/refresh_index）与查询（query_by_capability）
    在单线程事件循环内调用（热重载在 reload 流程中串行），索引引用替换为原子操作。
    """

    def __init__(self) -> None:
        self._provider_index: dict[str, APIProvider] = {}
        self._model_index: dict[tuple[str, str], ModelEntry] = {}
        self._capability_index: dict[str, list[ModelEntry]] = {}

    # ── 索引构建 ────────────────────────────────────────────────

    def build_index(self, providers: list[APIProvider], models: list[ModelEntry]) -> None:
        """从配置构建三级索引（全量重建）。

        Args:
            providers: APIProvider 列表（来自 ModelConfig）
            models: 注册表模型条目列表（来自 ModelInfo 转换）
        """
        self._provider_index = {p.name: p for p in providers}
        self._model_index = {m.key: m for m in models}
        capability_index: dict[str, list[ModelEntry]] = {}
        for entry in models:
            for capability in entry.capabilities:
                capability_index.setdefault(capability, []).append(entry)
        self._capability_index = capability_index

    # ── 查询 ─────────────────────────────────────────────────────

    def query_by_capability(
        self,
        capabilities: Sequence[str],
        *,
        category: str | None = None,
        prefer: tuple[tuple[str, str], ...] = (),
        options: ResolutionOptions | None = None,
    ) -> ResolvedModel:
        """按能力需求解析模型 — 多能力交集 → category 过滤 → prefer 排序 → 选中。

        错误语义（错误码驱动验证的静态侧）：
        - prefer 模型不存在 → DeclarationError("prefer 指定模型 (X, Y) 在注册表中不存在")
        - prefer 模型缺能力 → DeclarationError("prefer 模型 (X, Y) 缺少 Z 能力")
        - 无任何候选 → DeclarationError（组件/能力/无匹配）

        Args:
            capabilities: 所需能力标签列表（多能力取交集）
            category: 能力域粗分过滤（llm/embedding/voice），None 不过滤
            prefer: 偏好模型列表（(category, name) 元组），按顺序优先
            options: 调用点解析选项（采样参数覆盖 + 选择策略）

        Returns:
            ResolvedModel：选中的模型 + 生效采样参数
        """
        required = frozenset(capabilities)
        if not required:
            raise DeclarationError(
                "能力需求为空", component_name="", required_capabilities=required,
            )

        # 多能力交集
        candidates = self._models_with_all_capabilities(required)
        # category 过滤
        if category is not None:
            candidates = [m for m in candidates if m.category == category]
        if not candidates:
            raise DeclarationError(
                f"无满足能力 {sorted(required)} 的模型",
                required_capabilities=required, category=category or "",
            )

        # prefer 校验与排序
        for prefer_category, prefer_name in prefer:
            pref_model = self._model_index.get((prefer_category, prefer_name))
            if pref_model is None:
                raise DeclarationError(
                    f"prefer 指定模型 ({prefer_category}, {prefer_name}) 在注册表中不存在",
                    category=prefer_category, name=prefer_name,
                    required_capabilities=required,
                )
            if not required.issubset(pref_model.capabilities):
                missing = sorted(required - pref_model.capabilities)
                raise DeclarationError(
                    f"prefer 模型 ({prefer_category}, {prefer_name}) 缺少能力 {missing}",
                    category=prefer_category, name=prefer_name,
                    required_capabilities=required,
                )
            if pref_model in candidates:
                return self._to_resolved(
                    pref_model, options, source=OPTIONS_SOURCE,
                    fallback=[m.name for m in candidates if m is not pref_model],
                )

        # 无 prefer 命中：按选择策略选
        active_options = options or ResolutionOptions()
        selected = self._select_by_strategy(candidates, active_options)
        return self._to_resolved(
            selected, active_options, source=DEFAULT_SOURCE,
            fallback=[m.name for m in candidates if m is not selected],
        )

    def get_fallback_chain(self, category: str, name: str, capability: str) -> list[str]:
        """同能力 fallback 链 — 排除当前模型，检测循环。

        对标 alternative framework：按优先级尝试，全失败才报错。

        Args:
            category: 当前模型 category
            name: 当前模型 name
            capability: 回退所需能力（同能力回退，不跨形态兜底）

        Returns:
            同能力候选模型 name 列表（排除当前模型）
        """
        candidates = [m.name for m in self._capability_index.get(capability, [])
                      if m.key != (category, name)]
        # 循环检测：A→B→A 的环在调用方 fallback 链声明中检测（T4 验收）
        if name in candidates:
            candidates.remove(name)
        return candidates

    # ── 热重载 diff ─────────────────────────────────────────────

    def refresh_index(self, providers: list[APIProvider], models: list[ModelEntry]) -> set[str]:
        """重建索引并返回受影响组件名集合（热重载 diff）。

        受影响判定（两个维度）：
        1. 能力候选集合变化：组件声明的每个能力在新索引中的候选集合
           ≠ 旧索引候选集合（新增模型 / 删除模型 → 组件需重新评估解析）
        2. provider 配置变化：某 provider 的 base_url/client_type 变更 →
           依赖该 provider 的模型所服务的组件需重启（client 实例重建）

        Args:
            providers: 新 APIProvider 列表
            models: 新 ModelEntry 列表

        Returns:
            受影响组件名集合（供 ServiceManager 精确重启）
        """
        old_provider_index = self._provider_index
        old_model_index = self._model_index
        self.build_index(providers, models)
        return self._diff_vs_old(old_provider_index, old_model_index)

    def diff_resolution(self, old_registry: "ModelRegistry") -> set[str]:
        """对比新旧注册表下各组件解析结果，返回受影响组件名集合。"""
        return self._diff_vs_old(old_registry._provider_index, old_registry._model_index)

    def _diff_vs_old(
        self,
        old_provider_index: dict[str, APIProvider],
        old_model_index: dict[tuple[str, str], ModelEntry],
    ) -> set[str]:
        """新旧索引对比：能力候选集合变化 ∪ provider 配置变化 → 受影响组件。"""
        # provider 配置变化：依赖该 provider 的模型 → 服务这些模型的组件
        changed_providers: set[str] = set()
        for name, provider in self._provider_index.items():
            old = old_provider_index.get(name)
            if old is None or (provider.base_url, provider.client_type) != (old.base_url, old.client_type):
                changed_providers.add(name)
        removed_providers = set(old_provider_index) - set(self._provider_index)

        affected: set[str] = set()
        for component_name, declaration in get_all_declarations().items():
            old_candidates = self._candidate_keys(old_model_index, declaration)
            new_candidates = self._candidate_keys(self._model_index, declaration)
            if old_candidates != new_candidates:
                affected.add(component_name)
                continue
            # provider 维度：组件**实际解析**的模型（prefer 优先，P1-1 修复）
            # 依赖变更的 provider → 受影响（候选集合不变但 prefer 模型所在 provider 变了）
            resolved = self._resolve_preferred(self._model_index, declaration)
            if resolved is not None and (
                resolved.api_provider in changed_providers
                or resolved.api_provider in removed_providers
            ):
                affected.add(component_name)
        return affected

    @staticmethod
    def _resolve_preferred(
        model_index: dict[tuple[str, str], ModelEntry],
        declaration: ComponentDeclaration,
    ) -> ModelEntry | None:
        """按声明 prefer 解析实际模型（prefer 命中优先，否则首个候选）。"""
        prefer = declaration.defaults.prefer if declaration.defaults else ()
        for prefer_category, prefer_name in prefer:
            entry = model_index.get((prefer_category, prefer_name))
            if entry is not None and declaration.capabilities.issubset(entry.capabilities):
                return entry
        for entry in model_index.values():
            if declaration.capabilities.issubset(entry.capabilities):
                return entry
        return None

    @staticmethod
    def _candidate_keys(
        model_index: dict[tuple[str, str], ModelEntry],
        declaration: ComponentDeclaration,
    ) -> set[tuple[str, str]]:
        """声明能力在新/旧索引下的候选模型 key 集合。"""
        return {
            key for key, entry in model_index.items()
            if declaration.capabilities.issubset(entry.capabilities)
        }

    @staticmethod
    def _first_candidate(
        model_index: dict[tuple[str, str], ModelEntry],
        declaration: ComponentDeclaration,
    ) -> ModelEntry | None:
        """声明能力下的首个候选模型（balance 语义）。"""
        for entry in model_index.values():
            if declaration.capabilities.issubset(entry.capabilities):
                return entry
        return None

    # ── 内部工具 ────────────────────────────────────────────────

    def _models_with_all_capabilities(self, required: frozenset[str]) -> list[ModelEntry]:
        """多能力交集：从第一个能力的候选集中过滤。"""
        result: list[ModelEntry] | None = None
        for capability in sorted(required):
            bucket = self._capability_index.get(capability, [])
            if result is None:
                result = list(bucket)
            else:
                result = [m for m in result if m in bucket]
            if not result:
                break
        return result or []

    @staticmethod
    def _select_by_strategy(
        candidates: list[ModelEntry],
        options: ResolutionOptions,
    ) -> ModelEntry:
        """按选择策略从候选中选模型（balance 取首个，random 随机，sequential 取首个）。"""
        strategy = options.selection_strategy or BALANCE_STRATEGY
        if strategy == RANDOM_STRATEGY and len(candidates) > 1:
            return random.choice(candidates)
        return candidates[0]

    def _to_resolved(
        self,
        entry: ModelEntry,
        options: ResolutionOptions | None,
        *,
        source: str,
        fallback: list[str],
    ) -> ResolvedModel:
        """ModelEntry → ResolvedModel（合并调用点 options 覆盖）。"""
        active = options or ResolutionOptions()
        return ResolvedModel(
            category=entry.category,
            name=entry.name,
            model_identifier=entry.model_identifier,
            api_provider=entry.api_provider,
            capabilities=entry.capabilities,
            temperature=active.temperature if active.temperature is not None else entry.temperature,
            max_tokens=active.max_tokens if active.max_tokens is not None else entry.max_tokens,
            selection_strategy=active.selection_strategy,
            hard_timeout=active.hard_timeout,
            slow_threshold=active.slow_threshold,
            source=source,
            fallback_candidates=tuple(fallback),
        )


_registry: ModelRegistry | None = None


def get_model_registry() -> ModelRegistry:
    """模型注册表单例（惰性创建）。"""
    global _registry
    if _registry is None:
        _registry = ModelRegistry()
    return _registry


def set_model_registry(registry: ModelRegistry) -> None:
    """注入注册表单例（测试/启动注入用）。"""
    global _registry
    _registry = registry
