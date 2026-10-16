import asyncio
import copy
import inspect
import os
from pathlib import Path
from typing import Any, Callable, Mapping, MutableMapping, Sequence, TypeVar, cast

import tomlkit

from src.common.i18n import t
from src.common.logger import get_logger
from src.common.runtime_paths import resolve_project_root
from src.common.version import read_project_version

from .config_base import AttributeData, ConfigBase, Field
from .config_lifecycle import check_field_lifecycle, collect_generated_paths
from .config_upgrade_hooks import (
    MIGRATIONS_COMMENT,
    MIGRATIONS_KEY,
    ConfigVersionChainError,
    ConfigVersionParseError,
    apply_config_upgrade_hooks,
    archive_config_file,
    plan_version_chain,
    read_migrations_from_file,
)
from .config_utils import output_config_changes, recursive_parse_item_to_table
from .default_model_config import create_default_model_config
from .file_watcher import FileChange, FileWatcher

from .model_configs import APIProvider, ModelInfo, ModelTaskConfig, preflight_provider_env_references
from .official_configs import (
    AMemorixConfig,
    AgentAutonomySectionConfig,
    AgentInteractionSectionConfig,
    AgentSectionConfig,
    BotConfig,
    ChatConfig,
    ChineseTypoConfig,
    ControlMessageSectionConfig,
    DebugConfig,
    EmojiConfig,
    ErrorEscalationSectionConfig,
    ExperimentalConfig,
    ExpressionConfig,
    JargonConfig,
    KeywordReactionConfig,
    LogConfig,
    MaimMessageConfig,
    MCPConfig,
    MessageReceiveConfig,
    PersonalityConfig,
    PluginConfig,
    PluginRuntimeConfig,
    PluginRuntimeV2Config,
    PythonRuntimeSectionConfig,
    EventBusConfig,
    ResponsePostProcessConfig,
    ResponseSplitterConfig,
    SystemStateSectionConfig,
    TaintedMaskSectionConfig,
    VisualConfig,
    VoiceConfig,
    WatchdogSectionConfig,
    WebUIConfig,
    CompactionSectionConfig,
    CachePrefixStabilityConfig,
)

"""
如果你想要修改配置文件，请递增version的值

版本格式：主版本号.次版本号.修订号，版本号递增规则如下：
    主版本号：MMC版本更新
    次版本号：配置文件内容大更新
    修订号：配置文件内容小更新
"""

PROJECT_ROOT: Path = resolve_project_root()  # 仓根：唯一来源（本文件不再自推，见 src/common/runtime_paths.py）
CONFIG_DIR: Path = PROJECT_ROOT / "config"
BOT_CONFIG_PATH: Path = (CONFIG_DIR / "bot_config.toml").resolve().absolute()
MODEL_CONFIG_PATH: Path = (CONFIG_DIR / "model_config.toml").resolve().absolute()


MMC_VERSION: str = read_project_version(PROJECT_ROOT)
CONFIG_VERSION: str = "8.29.1"
MODEL_CONFIG_VERSION: str = "1.17.6"

logger = get_logger("config")

T = TypeVar("T", bound="ConfigBase")
ConfigReloadCallback = Callable[[Sequence[str]], object] | Callable[[], object]


class Config(ConfigBase):
    """总配置类"""

    bot: BotConfig = Field(default_factory=BotConfig)
    """机器人配置类"""

    personality: PersonalityConfig = Field(default_factory=PersonalityConfig)
    """人格配置类"""

    chat: ChatConfig = Field(default_factory=ChatConfig)
    """聊天配置类"""

    experimental: ExperimentalConfig = Field(default_factory=ExperimentalConfig)
    """实验性功能配置类"""

    visual: VisualConfig = Field(default_factory=VisualConfig)
    """视觉配置类"""

    expression: ExpressionConfig = Field(default_factory=ExpressionConfig)
    """表达配置类"""

    jargon: JargonConfig = Field(default_factory=JargonConfig)
    """黑话配置类"""

    a_memorix: AMemorixConfig = Field(default_factory=AMemorixConfig)
    """A_Memorix 长期记忆子系统配置"""

    message_receive: MessageReceiveConfig = Field(default_factory=MessageReceiveConfig)
    """消息接收配置类"""

    voice: VoiceConfig = Field(default_factory=VoiceConfig)
    """语音配置类"""

    emoji: EmojiConfig = Field(default_factory=EmojiConfig)
    """表情包配置类"""

    keyword_reaction: KeywordReactionConfig = Field(default_factory=KeywordReactionConfig)
    """关键词反应配置类"""

    response_post_process: ResponsePostProcessConfig = Field(default_factory=ResponsePostProcessConfig)
    """回复后处理配置类"""

    chinese_typo: ChineseTypoConfig = Field(default_factory=ChineseTypoConfig)
    """中文错别字生成器配置类"""

    response_splitter: ResponseSplitterConfig = Field(default_factory=ResponseSplitterConfig)
    """回复分割器配置类"""

    log: LogConfig = Field(default_factory=LogConfig)
    """日志配置类"""

    debug: DebugConfig = Field(default_factory=DebugConfig)
    """调试配置类"""

    maim_message: MaimMessageConfig = Field(default_factory=MaimMessageConfig)
    """maim_message配置类"""

    webui: WebUIConfig = Field(default_factory=WebUIConfig)
    """WebUI配置类"""

    watchdog: WatchdogSectionConfig = Field(default_factory=WatchdogSectionConfig)
    """看门狗配置类"""

    control_message: ControlMessageSectionConfig = Field(default_factory=ControlMessageSectionConfig)
    """控制消息优先级配置类（ZG-8）"""

    tainted_mask: TaintedMaskSectionConfig = Field(default_factory=TaintedMaskSectionConfig)
    """污染标记配置类（ZG-7）"""

    error_escalation: ErrorEscalationSectionConfig = Field(default_factory=ErrorEscalationSectionConfig)
    """错误升级梯配置类（ZG-14）"""

    system_state: SystemStateSectionConfig = Field(default_factory=SystemStateSectionConfig)
    """系统生命周期状态机配置类（ZG-6）"""

    event_bus: EventBusConfig = Field(default_factory=EventBusConfig)
    """事件总线配置类（ZG-4）"""

    mcp: MCPConfig = Field(default_factory=MCPConfig)
    """MCP 配置类"""

    plugin: PluginConfig = Field(default_factory=PluginConfig)
    """插件管理配置类"""

    plugin_runtime: PluginRuntimeConfig = Field(default_factory=PluginRuntimeConfig)
    plugin_runtime_v2: PluginRuntimeV2Config = Field(default_factory=PluginRuntimeV2Config)
    """插件运行时配置类"""

    agent: AgentSectionConfig = Field(default_factory=AgentSectionConfig)
    """智能体配置类"""


    python_runtime: PythonRuntimeSectionConfig = Field(default_factory=PythonRuntimeSectionConfig)
    """Python运行时配置类"""

    agent_interaction: AgentInteractionSectionConfig = Field(default_factory=AgentInteractionSectionConfig)
    """智能体交互活化配置类"""

    agent_autonomy: AgentAutonomySectionConfig = Field(default_factory=AgentAutonomySectionConfig)
    """智能体自主性架构配置类"""

    compaction: CompactionSectionConfig = Field(default_factory=CompactionSectionConfig)
    """B 层替换式 compaction 配置类（ZG-25）"""

    cache_prefix_stability: CachePrefixStabilityConfig = Field(default_factory=CachePrefixStabilityConfig)
    """缓存前缀稳定化配置类（ZG-26）"""


class ModelConfig(ConfigBase):
    """模型配置类"""

    models: list[ModelInfo] = Field(default_factory=list)
    """模型配置列表"""

    model_task_config: ModelTaskConfig = Field(default_factory=ModelTaskConfig)
    """模型任务配置"""

    api_providers: list[APIProvider] = Field(default_factory=list)
    """API提供商列表"""

    def model_post_init(self, context: Any = None):
        if not self.models:
            raise ValueError(t("config.models_empty"))
        if not self.api_providers:
            raise ValueError(t("config.api_providers_empty"))

        # 检查API提供商名称是否重复
        provider_names = [provider.name for provider in self.api_providers]
        if len(provider_names) != len(set(provider_names)):
            raise ValueError(t("config.api_provider_name_duplicate"))

        # 检查 (category, name) 组合是否重复（ZG-12 组件自治寻址；
        # 组合唯一覆盖旧 name 唯一——不同 category 同名合法）
        model_keys = [(model.category, model.name) for model in self.models]
        if len(model_keys) != len(set(model_keys)):
            duplicate = next(key for key in model_keys if model_keys.count(key) > 1)
            raise ValueError(
                t("config.model_category_name_duplicate", category=duplicate[0], name=duplicate[1])
            )

        api_providers_dict = {provider.name: provider for provider in self.api_providers}

        for model in self.models:
            if not model.model_identifier:
                raise ValueError(t("config.model_identifier_empty", model_name=model.name))
            if not model.api_provider or model.api_provider not in api_providers_dict:
                raise ValueError(
                    t(
                        "config.model_api_provider_missing",
                        api_provider=model.api_provider,
                        model_name=model.name,
                    )
                )

        # 旧配置升级迁移（ZG-12）：embedding/voice 任务引用的模型 → category 推断。
        # 旧配置无 category/capabilities 字段，默认迁移会把 embedding 模型当文本模型——
        # 按 model_task_config 引用修正形态（embedding 模型不是文本模型）。
        embedding_names = {
            str(name).strip()
            for name in getattr(getattr(self.model_task_config, "embedding", None), "model_list", [])
            if str(name).strip()
        }
        voice_names = {
            str(name).strip()
            for name in getattr(getattr(self.model_task_config, "voice", None), "model_list", [])
            if str(name).strip()
        }
        for model in self.models:
            # P1-5 修复：仅"未显式声明"（category=llm 且 capabilities 恰为默认迁移集
            # 或空）才推断——用户显式配置的双用模型/自定义能力不被静默覆盖
            _default_llm_caps = {"text_generation", "tool_calling"}
            _is_default_migrated = (
                model.category in {"llm", ""}
                and (not model.capabilities or set(model.capabilities) == _default_llm_caps)
            )
            if _is_default_migrated:
                if model.name in embedding_names:
                    model.category = "embedding"
                    model.capabilities = {"embedding"}
                elif model.name in voice_names:
                    model.category = "voice"
                    model.capabilities = {"voice"}
        return super().model_post_init(context)


def _normalize_a_memorix_legacy_config(config_data: dict[str, Any]) -> dict[str, Any]:
    normalized = copy.deepcopy(config_data)
    web_config = normalized.get("web")
    if isinstance(web_config, dict) and "import" in web_config and "import_config" not in web_config:
        web_config["import_config"] = web_config.pop("import")
    return normalized



def _normalize_loaded_bot_config_dict(config_data: dict[str, Any]) -> dict[str, Any]:
    normalized = copy.deepcopy(config_data)
    a_memorix_config = normalized.get("a_memorix")
    if isinstance(a_memorix_config, dict):
        normalized["a_memorix"] = _normalize_a_memorix_legacy_config(a_memorix_config)
    return normalized


class ConfigFrozenError(RuntimeError):
    """配置冻结异常 — 启动完成后配置被冻结，运行时修改被拒绝（ZG-10 T19）。"""


class ConfigWriteRefusedError(RuntimeError):
    """配置写回被拒绝 — 盘上是密钥引用、但取不到原文，拒绝把解析后的明文写回文件。

    触发条件见 ``_restore_secret_references_before_write``：宁可这次升级不写，
    也不能把 ``api_key = "${VAR}"`` 换成明文（那等于把密钥外部化白做一遍）。
    """


class ConfigManager:
    """总配置管理类"""

    VLM_NOT_CONFIGURED_WARNING: str = "未配置视觉识图模型，部分图片理解可能受限，请在webui或model_config中配置"

    def __init__(self):
        self.bot_config_path: Path = BOT_CONFIG_PATH
        self.model_config_path: Path = MODEL_CONFIG_PATH
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        self.global_config: Config | None = None
        self.model_config: ModelConfig | None = None
        self._reload_lock: asyncio.Lock = asyncio.Lock()
        self._reload_callbacks: list[ConfigReloadCallback] = []
        self._file_watcher: FileWatcher | None = None
        self._file_watcher_subscription_id: str | None = None
        self._hot_reload_min_interval_s: float = 1.0
        self._hot_reload_timeout_s: float = 20.0
        self._last_hot_reload_monotonic: float = 0.0
        self.reload_revision: int = 0
        self._frozen: bool = False

    def freeze(self) -> None:
        """冻结配置（启动完成后调用，对标 Linux __init 内存回收前只读化）。

        冻结后 reload_config 抛 ConfigFrozenError。
        """
        self._frozen = True

    @property
    def frozen(self) -> bool:
        """配置是否已冻结。"""
        return self._frozen

    def initialize(self):
        """启动入口：读两份配置 + **启动期预校验**（缺变量当场拒绝启动）。

        预校验的位置有意放在两份配置都读完之后、`_warn_if_vlm_not_configured` 之前：
        它是"这份配置**能不能**跑起来"的问题，比"视觉模型配没配"这种告警更根本。

        ⚠️ 为什么启动期要单独校验一次（4 段归位的代价与补偿）：``${VAR}`` 的解析挪到
        "注入客户端之前"之后，"缺变量"不再是启动失败，而是**第一次建客户端**才炸 ⇒
        容器 `ready=True`、心跳正常，直到用户第一条消息进来才失败。启动期这一次**只读不写**
        （不构造客户端、不改文件，盘上仍是 ``${VAR}``），把"配置错误要响亮"这条拿回来。
        """
        logger.info(t("config.current_version", version=MMC_VERSION))
        logger.info(t("config.loading"))
        self.global_config, global_updated = load_config_from_file(Config, self.bot_config_path, CONFIG_VERSION)
        self.model_config, model_updated = load_config_from_file(
            ModelConfig,
            self.model_config_path,
            MODEL_CONFIG_VERSION,
            True,
        )
        if global_updated or model_updated:
            logger.info("配置已自动升级，将继续使用更新后的配置启动")
        preflight_provider_env_references(self.model_config)
        self._warn_if_vlm_not_configured(self.model_config)
        logger.info(t("config.loaded"))

    @classmethod
    def _warn_if_vlm_not_configured(cls, model_config: ModelConfig) -> None:
        if any(model_name.strip() for model_name in model_config.model_task_config.vlm.model_list):
            return
        logger.warning(cls.VLM_NOT_CONFIGURED_WARNING)

    def load_global_config(self) -> Config:
        config, updated = load_config_from_file(Config, self.bot_config_path, CONFIG_VERSION)
        if updated:
            logger.info("bot_config.toml 已自动升级，将继续使用更新后的配置")
        return config

    def load_model_config(self) -> ModelConfig:
        config, updated = load_config_from_file(ModelConfig, self.model_config_path, MODEL_CONFIG_VERSION, True)
        if updated:
            logger.info("model_config.toml 已自动升级，将继续使用更新后的配置")
        return config

    def get_global_config(self) -> Config:
        if self.global_config is None:
            raise RuntimeError(t("config.global_not_initialized"))
        return self.global_config

    def get_model_config(self) -> ModelConfig:
        if self.model_config is None:
            raise RuntimeError(t("config.model_not_initialized"))
        return self.model_config

    def register_reload_callback(self, callback: ConfigReloadCallback) -> None:
        """注册配置热重载回调。

        Args:
            callback: 配置热重载回调。允许无参回调，也允许接收
                ``Sequence[str]`` 类型的变更范围列表。
        """

        self._reload_callbacks.append(callback)

    def unregister_reload_callback(self, callback: ConfigReloadCallback) -> None:
        """注销配置热重载回调。

        Args:
            callback: 先前注册过的回调对象。
        """

        try:
            self._reload_callbacks.remove(callback)
        except ValueError:
            logger.debug(f"unregister_reload_callback 回调未注册静默忽略: callback={callback!r}")
            return

    @staticmethod
    def _normalize_changed_scopes(changed_scopes: Sequence[str] | None) -> tuple[str, ...]:
        """规范化配置变更范围列表。

        Args:
            changed_scopes: 原始配置变更范围。

        Returns:
            tuple[str, ...]: 去重后的配置变更范围元组。
        """

        if not changed_scopes:
            return ("bot", "model")

        normalized_scopes: list[str] = []
        for scope in changed_scopes:
            normalized_scope = str(scope or "").strip().lower()
            if normalized_scope not in {"bot", "model"}:
                continue
            if normalized_scope not in normalized_scopes:
                normalized_scopes.append(normalized_scope)
        return tuple(normalized_scopes)

    @staticmethod
    def _resolve_changed_scopes(changes: Sequence[FileChange]) -> tuple[str, ...]:
        """根据文件变更列表推断配置变更范围。

        Args:
            changes: 文件监听器返回的变更列表。

        Returns:
            tuple[str, ...]: 命中的配置变更范围元组。
        """

        changed_scopes: list[str] = []
        for change in changes:
            file_name = change.path.name
            if file_name == "bot_config.toml" and "bot" not in changed_scopes:
                changed_scopes.append("bot")
            if file_name == "model_config.toml" and "model" not in changed_scopes:
                changed_scopes.append("model")
        return tuple(changed_scopes)

    @staticmethod
    def _callback_accepts_scopes(callback: ConfigReloadCallback) -> bool:
        """判断回调是否接收配置变更范围参数。

        Args:
            callback: 待检测的回调对象。

        Returns:
            bool: 若回调可接收一个位置参数或可变位置参数，则返回 ``True``。
        """

        try:
            parameters = inspect.signature(callback).parameters.values()
        except (TypeError, ValueError):
            return False

        positional_params = {
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        }
        for parameter in parameters:
            if parameter.kind == inspect.Parameter.VAR_POSITIONAL:
                return True
            if parameter.kind in positional_params:
                return True
        return False

    async def _invoke_reload_callback(
        self,
        callback: ConfigReloadCallback,
        changed_scopes: Sequence[str],
    ) -> None:
        """执行单个配置热重载回调。

        Args:
            callback: 要执行的回调对象。
            changed_scopes: 本次热重载命中的配置范围。
        """

        if self._callback_accepts_scopes(callback):
            callback_with_scopes = cast(Callable[[Sequence[str]], object], callback)
            result = callback_with_scopes(changed_scopes)
        else:
            callback_without_scopes = cast(Callable[[], object], callback)
            result = callback_without_scopes()
        if asyncio.iscoroutine(result):
            await result

    async def reload_config(self, changed_scopes: Sequence[str] | None = None) -> bool:
        """重新加载主配置和模型配置。

        Args:
            changed_scopes: 本次触发热重载的配置范围。

        Returns:
            bool: 是否重载成功。

        Raises:
            ConfigFrozenError: 配置已冻结（ZG-10 启动完成后只读）
        """
        if self._frozen:
            raise ConfigFrozenError("配置已冻结（启动完成），运行时修改被拒绝")

        normalized_scopes = self._normalize_changed_scopes(changed_scopes)
        if not normalized_scopes:
            logger.debug("配置热重载未命中有效范围，已跳过")
            return True

        async with self._reload_lock:
            try:
                global_config_new = self.global_config
                model_config_new = self.model_config
                global_updated = False
                model_updated = False
                if "bot" in normalized_scopes or global_config_new is None:
                    global_config_new, global_updated = load_config_from_file(
                        Config,
                        self.bot_config_path,
                        CONFIG_VERSION,
                    )
                if "model" in normalized_scopes or model_config_new is None:
                    model_config_new, model_updated = load_config_from_file(
                        ModelConfig,
                        self.model_config_path,
                        MODEL_CONFIG_VERSION,
                        True,
                    )
            except Exception as exc:
                from src.core.error_escalation.types import ErrorLevel
                from src.core.error_escalation_port_registry import get_error_escalation_port
                port = get_error_escalation_port()
                if port is not None:
                    port.report(ErrorLevel.ERROR, '重新加载配置失败', exception=exc)
                logger.error(t("config.reload_failed", error=exc))
                return False

            if global_updated or model_updated:
                logger.warning(t("config.version_update_detected"))

            self.global_config = global_config_new
            self.model_config = model_config_new
            self.reload_revision += 1

            # ZG-7 接线：配置热更新覆盖运行时值 = TAINT_CONFIG_OVERRIDE
            try:
                from src.core.tainted_mask.mark import mark_taint
                from src.core.tainted_mask.taint_flag import TaintFlag

                mark_taint(TaintFlag.TAINT_CONFIG_OVERRIDE)
            except Exception as exc:
                from src.core.error_escalation.types import ErrorLevel
                from src.core.error_escalation_port_registry import get_error_escalation_port
                port = get_error_escalation_port()
                if port is not None:
                    port.report(ErrorLevel.WARNING, '重新加载配置文件失败', exception=exc)
                logger.warning(f"重新加载配置文件失败: {exc}")

            logger.info(t("config.hot_reload_completed"))

            for callback in list(self._reload_callbacks):
                try:
                    await self._invoke_reload_callback(callback, normalized_scopes)
                except Exception as exc:
                    from src.core.error_escalation.types import ErrorLevel
                    from src.core.error_escalation_port_registry import get_error_escalation_port
                    port = get_error_escalation_port()
                    if port is not None:
                        port.report(ErrorLevel.WARNING, '配置重载回调执行失败', exception=exc)
                    logger.warning(t("config.reload_callback_failed", error=exc))
            return True

    async def start_file_watcher(self) -> None:
        if self._file_watcher is not None and self._file_watcher.running:
            return
        self._file_watcher = FileWatcher(
            paths=[self.bot_config_path, self.model_config_path],
            debounce_ms=600,
            callback_timeout_s=15.0,
            callback_failure_threshold=3,
            callback_cooldown_s=30.0,
        )
        self._file_watcher_subscription_id = self._file_watcher.subscribe(
            self._handle_file_changes,
            paths=[self.bot_config_path, self.model_config_path],
        )
        await self._file_watcher.start()
        logger.info(t("config.file_watcher_started"))

    async def stop_file_watcher(self) -> None:
        if self._file_watcher is None:
            return
        if self._file_watcher_subscription_id is not None:
            self._file_watcher.unsubscribe(self._file_watcher_subscription_id)
            self._file_watcher_subscription_id = None
        watcher_stats = self._file_watcher.stats
        logger.info(
            t(
                "config.file_watcher_stop_stats",
                batches=watcher_stats.batches_seen,
                changes=watcher_stats.changes_seen,
                cooldown_skip=watcher_stats.callbacks_skipped_cooldown,
                failed=watcher_stats.callbacks_failed,
                ok=watcher_stats.callbacks_succeeded,
                restart=watcher_stats.restart_count,
                timeout=watcher_stats.callbacks_timed_out,
            )
        )
        await self._file_watcher.stop()
        self._file_watcher = None

    async def _handle_file_changes(self, changes: Sequence[FileChange]) -> None:
        """处理主配置与模型配置文件变更。

        Args:
            changes: 当前批次收集到的文件变更列表。
        """

        if not changes:
            return
        now_monotonic = asyncio.get_running_loop().time()
        if now_monotonic - self._last_hot_reload_monotonic < self._hot_reload_min_interval_s:
            logger.debug(t("config.reload_skipped_too_frequent"))
            return
        self._last_hot_reload_monotonic = now_monotonic
        logger.info(t("config.file_change_detected"))
        try:
            changed_scopes = self._resolve_changed_scopes(changes)
            await asyncio.wait_for(
                self.reload_config(changed_scopes=changed_scopes),
                timeout=self._hot_reload_timeout_s,
            )
        except asyncio.TimeoutError as exc:
            # P1: 补 port.report 双通道上报
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            _port = get_error_escalation_port()
            if _port is not None:
                _port.report(ErrorLevel.ERROR, "配置热重载超时", exception=exc)
            logger.error(t("config.reload_timeout", timeout_seconds=self._hot_reload_timeout_s))


def _template_path_of(config_path: Path) -> Path:
    """配置的 `.template` 基线路径（同目录、加后缀）。

    `.template` = **程序自己生成的默认形态**（`generate_new_config_file` 落盘），用来回答
    "这个弃用键是用户显式留的，还是我们写进默认值的"（见 `collect_generated_paths`）。
    """
    return config_path.with_name(f"{config_path.name}.template")


def _read_generated_paths(config_class: type[T], config_path: Path, new_ver: str) -> frozenset[str]:
    """读 `.template` 基线并导出"我们写进默认值"的被声明路径。

    - 基线不存在（老部署、或 `.template` 被删）⇒ 返回**空集**：宁可信"用户自己留的"而多响一次，
      也不能反过来（把用户的显式选择静默掉）。
    - 基线读不动（坏 TOML / 权限）⇒ 同上，并且双通道出声——这类失败只影响"出不出声"，不该阻断启动。
    """
    template_path = _template_path_of(config_path)
    if not template_path.exists():
        return frozenset()
    try:
        with open(template_path, "r", encoding="utf-8") as handle:
            template_data = tomlkit.load(handle).unwrap()
    except Exception as exc:
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port

        port = get_error_escalation_port()
        if port is not None:
            port.report(ErrorLevel.WARNING, "读取配置默认值基线失败，本次按'用户显式保留'处理", exception=exc)
        logger.warning(f"读取配置默认值基线失败（{template_path.name}），本次按'用户显式保留'处理: {exc}")
        return frozenset()
    return collect_generated_paths(config_class, template_data)


def generate_new_config_file(
    config_class: type[T], config_path: Path, inner_config_version: str, override_repr: bool = False
) -> None:
    """生成新的配置文件（同时落一份 `.template` 默认值基线）。

    :param config_class: 配置类
    :param config_path: 配置文件路径
    :param inner_config_version: 配置文件版本号

    ⚠️ `.template` 是**副作用最小**的基线载体：它只被 `_read_generated_paths` 读，不参与任何
    运行期决策；`.gitignore` 已覆盖 `config/*`，容器挂载的 `docker-config/mmc` 也跟着落一份。
    """
    if config_class is ModelConfig:
        config = create_default_model_config(config_class)
    else:
        config = config_class()
    write_config_to_file(config, config_path, inner_config_version, override_repr)
    _write_default_template(config, config_path, inner_config_version, override_repr)


def _write_default_template(
    config: ConfigBase, config_path: Path, inner_config_version: str, override_repr: bool
) -> None:
    """把刚生成的默认配置另存一份 `.template`（数据形态，不含注释）。

    写失败**不阻断**配置生成：基线只影响"弃用警告响不响"，不该让首启失败（写一张告警即可）。
    """
    template_path = _template_path_of(config_path)
    try:
        template = _build_config_template(config, inner_config_version, override_repr)
        with open(template_path, "w", encoding="utf-8") as handle:
            tomlkit.dump(template, handle)
    except Exception as exc:
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port

        port = get_error_escalation_port()
        if port is not None:
            port.report(ErrorLevel.WARNING, "写入配置默认值基线失败", exception=exc)
        logger.warning(f"写入配置默认值基线失败（{template_path.name}），后续弃用提示可能偏多: {exc}")



def load_config_from_file(
    config_class: type[T], config_path: Path, new_ver: str, override_repr: bool = False
) -> tuple[T, bool]:
    attribute_data = AttributeData()
    if not config_path.exists():
        logger.warning(f"配置文件缺失，正在生成默认配置: {config_path}")
        generate_new_config_file(config_class, config_path, new_ver, override_repr)
    with open(config_path, "r", encoding="utf-8") as f:
        config_data = tomlkit.load(f)
    inner_table = config_data.get("inner")
    if inner_table is not None:
        # 首启的配置没有 [inner] 段，tomlkit 的 remove 对不存在的键会直接抛 NonExistentKey
        config_data.remove("inner")
    config_data = config_data.unwrap()
    config_data = _normalize_loaded_bot_config_dict(config_data)

    # 留档先摘出来：它不在配置模型里（from_dict 会把不认识的键当"多余项"丢掉并告警），
    # 但**不能丢**——重写时要原样写回（dsh 档②"忽略但保留"）。
    raw_migrations = config_data.pop(MIGRATIONS_KEY, None)

    # 版本链前置校验 + 链式迁移：都在进 from_dict 之前
    # （档③：拒绝要在**任何写入之前**发生，原文件字节保持不动；拒绝路径双通道上报）
    # 消息里给**完整路径**——这份配置可能来自仓根 config/ 或 docker-config/mmc/，只报文件名分不清是谁
    try:
        raw_inner_version = _read_raw_inner_version(inner_table, str(config_path), new_ver)
        version_plan = plan_version_chain(str(config_path), raw_inner_version, new_ver, raw_migrations)
        # 字段级生命周期（4 段）：与版本链**同一个位置**——任何写入之前。
        # 弃用只出声（warning），移除是拒绝（ConfigFieldRefusedError，原文件不动）。
        # 顺序说明：放在 apply_config_upgrade_hooks **之前**——"这个字段已经被移除了"比
        # "该跑哪个迁移器"更根本；先让迁移器改一遍数据再拒绝，等于做了一次白工。
        # `generated_paths` = 程序默认值基线里的被声明路径 ⇒ 那些键是我们写进去的、不是用户的
        # 选择，弃用不出声（见 `collect_generated_paths`）。
        check_field_lifecycle(
            config_class,
            config_data,
            file_name=str(config_path),
            generated_paths=_read_generated_paths(config_class, config_path, new_ver),
        )
        hook_result = apply_config_upgrade_hooks(
            config_data,
            config_path.name,
            version_plan.old_version,
            new_ver,
            migrations=version_plan.records,
            file_name=str(config_path),
        )
    except ConfigVersionChainError as exc:
        _report_version_chain_refusal(exc)
        raise

    upgrade_hook_applied: bool = hook_result.migrated
    if hook_result.migrated:
        logger.warning(f"检测到配置升级钩子变更，已应用: {hook_result.reason}")
    config_data = hook_result.data
    try:
        updated: bool = False
        target_config = config_class.from_dict(attribute_data, config_data)
        if version_plan.upgrade_needed or upgrade_hook_applied:
            output_config_changes(attribute_data, logger, version_plan.old_version, new_ver, config_path.name)
            write_config_to_file(
                target_config,
                config_path,
                new_ver,
                override_repr,
                migrations=hook_result.migrations,
            )
            updated = True
        return target_config, updated
    except Exception as e:
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port
        port = get_error_escalation_port()
        if port is not None:
            port.report(ErrorLevel.CRITICAL, '解析配置文件失败', exception=e)
        logger.critical(t("config.parse_failed", file_name=config_path.name))
        raise e



def _read_raw_inner_version(inner_table: Any, file_name: str, new_version: str) -> Any:
    """读出 `inner.version` 的原始值，交给版本链前置校验。

    这里只剥掉 `inner` 这一层（它不是表就读不出 version）；"这个值是不是一个能比较的版本串"
    由 `plan_version_chain` 统一判定——版本链的事只有一处说了算。
    """
    if inner_table is None:
        return None
    if not isinstance(inner_table, Mapping):
        raise ConfigVersionParseError(
            f"{t('config.invalid_inner_version')}（inner 不是表，实际 {type(inner_table).__name__}）",
            file_name=file_name,
            old_version=str(inner_table),
            new_version=new_version,
        )
    return inner_table.get("version")


def _report_version_chain_refusal(exc: ConfigVersionChainError) -> None:
    """版本链拒绝的双通道上报（债务原则：异常不得单通道 —— logger + 上报 port）。

    拒绝语义的关键是"原文件不动"，所以这里只上报、不写盘、不兜底。
    """
    from src.core.error_escalation.types import ErrorLevel
    from src.core.error_escalation_port_registry import get_error_escalation_port

    port = get_error_escalation_port()
    if port is not None:
        port.report(ErrorLevel.ERROR, '配置版本链拒绝迁移（原文件未改动）', exception=exc)
    logger.error(f"配置版本链拒绝迁移，原文件未改动: {exc}")



def _build_config_template(
    config: ConfigBase, inner_config_version: str, override_repr: bool
) -> tomlkit.TOMLDocument:
    """按配置类生成**带字段注释的完整模板**（含 ``inner`` 版本戳，不含迁移留档）。

    模板是"已知字段该长什么样"的唯一出处：首启直接落盘，升级时用来就地更新旧文件。
    """
    template = tomlkit.document()

    # 首先写入配置文件版本信息
    version_table = tomlkit.table()
    version_table.add("version", inner_config_version)
    template.add("inner", version_table)

    # 递归解析配置项为表格
    for config_item_name, config_item in type(config).model_fields.items():
        if not config_item.repr and not override_repr:
            continue
        if config_item_name in ["field_docs", "_validate_any", "suppress_any_warning"]:
            continue
        config_field = getattr(config, config_item_name)
        if isinstance(config_field, ConfigBase):
            template.add(
                config_item_name, recursive_parse_item_to_table(config_field, override_repr=override_repr)
            )
        elif isinstance(config_field, list):
            aot = tomlkit.aot()
            for item in config_field:
                if not isinstance(item, ConfigBase):
                    raise TypeError(t("config.write_unsupported_type"))
                aot.append(recursive_parse_item_to_table(item, override_repr=override_repr))
            template.add(config_item_name, aot)
        else:
            raise TypeError(t("config.write_unsupported_type"))

    if isinstance(config, Config):
        try:
            a_memorix_web = template["a_memorix"]["web"]
            if "import_config" in a_memorix_web and "import" not in a_memorix_web:
                a_memorix_web["import"] = a_memorix_web.pop("import_config")
        except Exception as exc:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.WARNING, 'A_Memorix 配置写出时转换 web.import_config 失败', exception=exc)
            logger.warning("A_Memorix 配置写出时转换 web.import_config 失败", exc_info=True)

    return template


def _is_array_of_mappings(value: Any) -> bool:
    """是不是"表组成的数组"（TOML 的 ``[[table]]`` / AoT）。

    只认**非空且元素全是映射**的序列——空数组无从判断元素类型，交给调用方按整体替换处理。
    """
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        return False
    if not len(value):
        return False
    return all(isinstance(item, Mapping) for item in value)


def _merge_array_of_mappings(target: Sequence[Any], template: Sequence[Any]) -> None:
    """按**下标**逐项递归合并两个"表数组"（``[[models]]`` / ``[[api_providers]]``）。

    为什么需要它：合并整表数组时若直接整体替换，会吃掉盘上"模板里没有的键"——
    ``api_key`` 是 ``repr=False`` 字段，``override_repr=False`` 时**整键不出现**在模板里，
    整体替换会把盘的 ``api_key = "${VAR}"`` 一起换掉（3 段实测：引用被抹成空）。

    边界：只合并两边都有的下标；**模板多出的项照加，盘上多出的项保留**（只增不删）。
    """
    for index, template_item in enumerate(template):
        if index >= len(target):
            target.append(template_item)
            continue
        target_item = target[index]
        if isinstance(target_item, MutableMapping):
            _merge_config_template(target_item, template_item)
        else:
            target[index] = template_item


def _merge_config_template(target: MutableMapping[str, Any], template: Mapping[str, Any]) -> None:
    """把注释模板**就地**合进已存在的配置文档（P1.1a：改写不得吃掉未知字段）。

    - 模板里有的键 ⇒ 用模板（= 配置模型当前值）覆盖，旧的注释与格式由 tomlkit 留在原键上；
    - 模板里**没有**的键 ⇒ **一律不动**——用户自定义表、旧版本字段、别的程序写的键都留下
      （契约 §七"P1 必须保证不改写未知字段"；dsh 档②"忽略但保留"）；
    - 只增不删：这里没有任何删除路径。

    与既有件 ``toml_utils._update_toml_doc`` 的关系：那件是"把**数据**并进文档"且会跳过名为
    ``version`` 的键（节保存的保护），用作全量改写会漏写配置里真叫 ``version`` 的字段；
    这里要的是"把**注释模板**并进文档"，方向不同，故不硬套。
    """
    for key, template_value in template.items():
        if key not in target:
            target[key] = template_value
            continue

        target_value = target[key]

        # 结构相同 ⇒ **逐层递归合并**，而不是整体替换
        # （整体替换会吃掉盘上"模板里没有的键"：`repr=False` 的 api_key 在
        #  `override_repr=False` 时整键不出现在模板里，照旧法会把整张 provider 表换掉 ⇒ 引用被抹）
        if isinstance(template_value, Mapping) and isinstance(target_value, Mapping):
            _merge_config_template(target_value, template_value)
            continue
        if _is_array_of_mappings(template_value) and _is_array_of_mappings(target_value):
            _merge_array_of_mappings(target_value, template_value)
            continue

        # 模板值为空、盘上非空 ⇒ 保留盘上值（同上：不吃被跳过的字段）
        if template_value in ("", None) and target_value not in ("", None):
            continue

        # 既有键：值以模板为准（配置模型是已知字段的权威），原键上的注释/格式保留
        target[key] = template_value


def _collect_reference_api_keys(
    config: ConfigBase,
    full_config_data: MutableMapping[str, Any],
) -> list[tuple[int, str, str | None]]:
    """**合并之前**采集：盘上是引用、而对象里是解析值的那些 ``api_key``。

    为什么必须在合并前采集：合并（``_merge_config_template``）会把模板里的值盖到盘上文档上，
    之后就**分不清**"盘上原本是什么"。采集件三元组 = ``(下标, 盘上原文, 对象上的 raw 原文)``。

    判据（三条都只看"盘上 vs 待写"是否同一）：
      - 盘上 == 待写 ⇒ 无需处理（明文、空串、两次都写引用都走这支）；
      - 盘上是引用、待写不同 ⇒ 记入采集件，等合并后回放；
      - 拿不到 raw（``None``）⇒ 也记入，回放时**拒绝写出**（写明文换"这次升级成功"是本末倒置）。
    """
    from .model_configs import raw_api_key_of

    if not isinstance(config, ModelConfig):
        return []

    providers = getattr(config, "api_providers", None)
    providers_table = full_config_data.get("api_providers")
    if not providers or providers_table is None:
        return []

    collected: list[tuple[int, str, str | None]] = []
    for index, provider in enumerate(providers):
        try:
            provider_table = providers_table[index]
        except (IndexError, KeyError, TypeError):
            continue  # 盘上与内存的表长度不一致：不猜，交给合并逻辑按既有规则处理

        on_disk_value = provider_table.get("api_key") if isinstance(provider_table, Mapping) else None
        pending_value = getattr(provider, "api_key", None)
        if not isinstance(pending_value, str) or on_disk_value == pending_value:
            continue
        collected.append((index, str(on_disk_value), raw_api_key_of(provider)))

    return collected


def _restore_secret_references(
    config: ConfigBase,
    full_config_data: MutableMapping[str, Any],
    collected: Sequence[tuple[int, str, str | None]],
    config_path: Path,
) -> None:
    """**合并之后**回放：把采集到的盘上引用放回去（否则模板里的解析值就留在文件里了）。

    顺序是关键（3 段实测）：守卫若放在合并**之前**，合并会立刻把它覆盖掉；生产路径
    ``load_config_from_file(..., override_repr=True)`` 的模板里**带解析后的明文**，
    于是"放回 → 覆盖"→ 明文照样落盘。⇒ 采集在前、回放在后。

    :raises ConfigWriteRefusedError: 采集件里 raw 为 ``None``（盘上是引用但取不到原文）。
    """
    providers = getattr(config, "api_providers", None)
    providers_table = full_config_data.get("api_providers")
    if not providers or providers_table is None:
        return

    for index, _on_disk_value, raw_value in collected:
        try:
            provider_table = providers_table[index]
        except (IndexError, KeyError, TypeError):
            continue
        provider = providers[index]
        provider_label = getattr(provider, "name", None) or f"#{index}"

        if raw_value is None:
            message = (
                f"配置写回被拒绝：{config_path.name} 的 api_providers[{provider_label}].api_key "
                f"盘上是引用、但取不到原文（未经理析路径构造）——拒绝把解析后的明文写回文件"
            )
            logger.error(message)
            raise ConfigWriteRefusedError(message)

        if not isinstance(provider_table, MutableMapping):
            continue
        if provider_table.get("api_key") == raw_value:
            continue  # 合并后的值已经等于原文：无需回放（明文场景，或模板本就带引用）

        logger.warning(
            f"配置写回：{config_path.name} 的 api_providers[{provider_label}].api_key "
            f"盘上是引用，写回时以盘上原文为准（不把解析后的明文落盘）"
        )
        provider_table["api_key"] = raw_value


def write_config_to_file(
    config: ConfigBase,
    config_path: Path,
    inner_config_version: str,
    override_repr: bool = False,
    migrations: Sequence[Mapping[str, Any]] | None = None,
) -> None:
    """将配置写入文件

    :param config: 配置对象
    :param config_path: 配置文件路径
    :param inner_config_version: 配置文件版本号
    :param migrations: 要写入的迁移留档；``None`` = 沿用磁盘上已有的留档（档②：忽略但保留）

    写入形态（P1.1）：
      - **文件已存在 ⇒ 就地更新**：以原文件为底改已知键，模板里没有的键一律不动
        （未知字段、用户注释与格式都留下）；
      - 文件不存在 ⇒ 完整注释模板（首启形态）；
      - 落盘走 **tmp + os.replace**：要么旧文件、要么新文件，不留半截配置。
    """
    template = _build_config_template(config, inner_config_version, override_repr)

    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            full_config_data = tomlkit.load(f)
        # 写回守卫（顺序要紧）：**合并前**采集盘上引用 ⇒ 合并 ⇒ **合并后**回放
        # （放在合并之前会被合并立刻覆盖——3 段实测的假绿根因）
        collected_references = _collect_reference_api_keys(config, full_config_data)
        _merge_config_template(full_config_data, template)
        _restore_secret_references(config, full_config_data, collected_references, config_path)
    else:
        full_config_data = template

    # 迁移留档紧跟版本戳（两者同生共死）：写路径不认识它，但绝不把它抹掉
    if migrations is None:
        migrations = read_migrations_from_file(config_path)
    if migrations:
        migrations_tables = tomlkit.aot()
        for record in migrations:
            record_table = tomlkit.table()
            for record_key, record_value in record.items():
                record_table.add(record_key, record_value)
            migrations_tables.append(record_table)
        if MIGRATIONS_KEY not in full_config_data:
            full_config_data.add(tomlkit.comment(MIGRATIONS_COMMENT))
        full_config_data[MIGRATIONS_KEY] = migrations_tables

    # 备份旧文件（复制而非移动：写失败时原文件仍在原地；留档只增不改——见 archive_config_file）
    archive_config_file(config_path)

    # 原子写：先写临时文件再替换（写一半崩不会留半截配置——既有先例 toml_utils.py:105-115）
    temp_path = config_path.with_name(f"{config_path.name}.tmp")
    try:
        with open(temp_path, "w", encoding="utf-8") as f:
            tomlkit.dump(full_config_data, f)
        os.replace(temp_path, config_path)
    except Exception:
        # 写失败：清掉半截临时文件（原文件本来就没被动过），异常照抛给调用方
        temp_path.unlink(missing_ok=True)
        raise


class _ConfigProxy:
    """稳定配置代理，确保热重载后旧导入也能读取最新配置。"""

    def __init__(self, getter: Callable[[], ConfigBase]) -> None:
        self._getter = getter

    def __getattr__(self, name: str) -> Any:
        return getattr(self._getter(), name)

    def __getitem__(self, key: str) -> Any:
        return self._getter()[key]

    def __setattr__(self, name: str, value: Any) -> None:
        if name == "_getter":
            object.__setattr__(self, name, value)
            return
        setattr(self._getter(), name, value)

    def __repr__(self) -> str:
        return repr(self._getter())


# generate_new_config_file(Config, BOT_CONFIG_PATH, CONFIG_VERSION)
config_manager: ConfigManager | None = None
global_config: Config = cast(Config, _ConfigProxy(lambda: config_manager.get_global_config()))
model_config: ModelConfig = cast(ModelConfig, _ConfigProxy(lambda: config_manager.get_model_config()))


def initialize_config() -> None:
    """显式初始化配置管理器，由 main() 在启动入口处调用。"""
    global config_manager
    config_manager = ConfigManager()
    config_manager.initialize()
