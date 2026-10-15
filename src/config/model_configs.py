from enum import Enum
from pydantic import PrivateAttr
from typing import TYPE_CHECKING, Any

import os
import re

from src.common.i18n import t
from src.common.logger import get_logger

from .config_base import ConfigBase, Field

if TYPE_CHECKING:
    # 仅类型注解用（本仓 `config_utils.py` 已有同一先例）：`ModelConfig` 定义在 `config.py`，
    # 而 `config.py` 要 import 本模块 ⇒ 运行期 import 会成环。`preflight_provider_env_references`
    # 实际只读 `api_providers`，不需要这个类在运行期存在。
    from .config import ModelConfig

logger = get_logger("config.model_configs")
"""本模块的 logger：启动期环境引用预校验要用（`preflight_provider_env_references`）。"""

# 密钥外部化（P2/D1）：仅识别 ${VAR} 形态的引用，不发明第二套语法。
# 只在被引用的字段位置解析（不做全文替换），避免注释或普通字符串里的 ${...} 被误解析。
# 解析位（3 段冻结、4 段归位后的边界，**别顺手扩**）：只有 `APIProvider.api_key` 这一处，
# 且解析发生在**注入客户端之前**（`AdapterClient` 侧调用 `resolve_provider_env_references`），
# **不在**配置对象构造时。理由见 `APIProvider.model_post_init` 与 `raw_api_key_of` 的说明。
#   - `auth_header_name` / `auth_query_name` / `default_headers` / `default_query` 里的
#     `${VAR}` **按契约不解析**，保持字面量（要不要扩位是独立决定，不是顺手加）；
#   - 注入链（唯一答案）：宿主 `.env`（或宿主 shell 环境，先有值者胜）→ compose
#     `environment:` → 容器进程环境 → 本模块在**注入客户端之前**解析。
_ENV_REFERENCE_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


class ConfigEnvReferenceError(ValueError):
    """配置里的环境变量引用无法解析。

    引用缺失时**必须报错**：静默退化成空串会被下游当成"没配 key"，排障成本高。

    Attributes:
        variable: 未设置（或为空）的环境变量名。
        field_path: 出现该引用的配置字段路径。
    """

    def __init__(self, *, variable: str, field_path: str) -> None:
        self.variable = variable
        self.field_path = field_path
        super().__init__(
            f"配置字段 {field_path} 引用的环境变量 {variable} 未设置或为空；"
            f"请设置该环境变量，或把 {field_path} 直接写成明文值"
            f"（Docker 部署：在仓根 `.env` 补上 {variable}=…，再 `docker compose up -d` 重建容器——"
            f"`restart` 不会重读环境变量）"
        )


def resolve_env_references(value: str, *, field_path: str) -> str:
    """把字段值里的 ``${VAR}`` 引用替换为环境变量的值。

    - **明文值原样返回**（双模式过渡：老配置不动也能跑）。
    - 引用的变量未设置或为空 ⇒ 抛 ``ConfigEnvReferenceError``（含变量名与字段路径）。
    - 单趟替换，替换结果不再二次解析（引用值里再出现 ``${...}`` 不会被展开）。
    - 不以合法变量名形态出现的 ``${...}``（如 ``${}``、``${1A}``）不是本机制认领的引用，保持字面量。

    Args:
        value: 待解析的字段值。
        field_path: 该值所在的配置字段路径，仅用于错误信息。

    Returns:
        解析后的字段值。

    Raises:
        ConfigEnvReferenceError: 引用的环境变量未设置或为空。
    """

    def _replace_reference(match: re.Match[str]) -> str:
        variable_name = match.group(1)
        resolved_value = os.environ.get(variable_name)
        if resolved_value is None or not resolved_value.strip():
            raise ConfigEnvReferenceError(variable=variable_name, field_path=field_path)
        return resolved_value

    return _ENV_REFERENCE_PATTERN.sub(_replace_reference, value)


class OpenAICompatibleAuthType(str, Enum):
    """OpenAI 兼容接口的鉴权方式。"""

    BEARER = "bearer"
    HEADER = "header"
    QUERY = "query"
    NONE = "none"


class ReasoningParseMode(str, Enum):
    """推理内容解析策略。"""

    AUTO = "auto"
    NATIVE = "native"
    THINK_TAG = "think_tag"
    NONE = "none"


class ToolArgumentParseMode(str, Enum):
    """工具调用参数的解析策略。"""

    AUTO = "auto"
    STRICT = "strict"
    REPAIR = "repair"
    DOUBLE_DECODE = "double_decode"


class APIProvider(ConfigBase):
    """API提供商配置类"""

    name: str = Field(
        default="",
        json_schema_extra={
            "x-widget": "input",
            "x-icon": "tag",
        },
    )
    """API服务商名称 (可随意命名, 在models的api-provider中需使用这个命名)"""

    base_url: str = Field(
        default="",
        json_schema_extra={
            "x-widget": "input",
            "x-icon": "link",
        },
    )
    """API服务商的BaseURL"""

    api_key: str = Field(
        default_factory=str,
        repr=False,
        json_schema_extra={
            "x-widget": "input",
            "x-icon": "key",
            # 秘密判定走 schema 声明（F2）：WebUI 读路径据此把值换成存在标记，客户端永远收不到值。
            # 与 `config_secrets.SECRET_FIELD_PATHS` 取并集、派生优先 ⇒ 声明后那张表的同名行可删。
            "x-secret": True,
        },
    )
    """API密钥。对于不需要鉴权的兼容端点，可将 `auth_type` 设为 `none`。
    可写成 `"${ENV_VAR}"` 从环境变量取值（密钥外部化，避免明文进配置）；明文值原样使用。
    本字段**存的就是盘上原文**（引用不在这里解析——4 段把它挪到注入客户端之前，
    见 `resolve_provider_env_references`），所以在配置对象上看到 `"${VAR}"` 是**正常状态**。
    引用的环境变量缺失或为空在**建客户端时**直接报错，**不会**静默变成空串。"""

    # 盘上那一行 api_key 的**原文**（引用 `${VAR}` 或明文）。
    #
    # 4 段（解析时机归位）之后 `api_key` **本身**就是盘上原文——解析挪到了
    # `resolve_provider_env_references`（注入客户端之前调用），不再就地改写。
    # 本属性因此变成"历史留痕 + 防御位"：老代码/老测试读它仍能拿到原文；
    # 写回守卫 `_collect_reference_api_keys` / `_restore_secret_references` 也仍读它，
    # 只是**不再触发**——它守的是"对象里是解析值、盘上是引用"这个差，而那个差已经不存在了
    # （判据：`config.py` 的采集条件 `on_disk_value != pending_value` 恒不成立）。
    # ⚠️ 不许因为它"不再触发"就删守卫与 `pytests/config_test/test_secret_writeback_guard.py`：
    # 它是"将来又出现第三条拿到解析后对象的写路径"时的最后一道闸（F4 死线）。
    # 只读访问点见模块级 `raw_api_key_of`：类体里不能加 `@property`（`AttrDocBase` 的字段说明
    # 提取只放行 model_post_init 与 @field_validator / @model_validator，属性仍会被顶回去）。
    _raw_api_key: str | None = PrivateAttr(default=None)

    client_type: str = Field(
        default="openai",
        json_schema_extra={
            "x-widget": "select",
            "x-icon": "settings",
        },
    )
    """客户端类型 (可选: openai/google, 默认为openai)"""

    auth_type: str = Field(
        default=OpenAICompatibleAuthType.BEARER.value,
        json_schema_extra={
            "x-widget": "select",
            "x-icon": "shield",
        },
    )
    """OpenAI 兼容接口的鉴权方式。可选值：`bearer`、`header`、`query`、`none`。"""

    auth_header_name: str = Field(
        default="Authorization",
        json_schema_extra={
            "x-widget": "input",
            "x-icon": "header",
        },
    )
    """当 `auth_type` 为 `header` 时使用的请求头名称。"""

    auth_header_prefix: str = Field(
        default="Bearer",
        json_schema_extra={
            "x-widget": "input",
            "x-icon": "shield-check",
        },
    )
    """当 `auth_type` 为 `header` 时使用的请求头前缀。留空表示直接发送原始密钥。"""

    auth_query_name: str = Field(
        default="api_key",
        json_schema_extra={
            "x-widget": "input",
            "x-icon": "link",
        },
    )
    """当 `auth_type` 为 `query` 时使用的查询参数名称。"""

    default_headers: dict[str, str] = Field(
        default_factory=dict,
        json_schema_extra={
            "x-widget": "custom",
            "x-icon": "header",
        },
    )
    """所有请求默认附带的 HTTP Header。"""

    default_query: dict[str, str] = Field(
        default_factory=dict,
        json_schema_extra={
            "x-widget": "custom",
            "x-icon": "list-filter",
        },
    )
    """所有请求默认附带的查询参数。"""

    organization: str | None = Field(
        default=None,
        json_schema_extra={
            "x-widget": "input",
            "x-icon": "building-2",
        },
    )
    """OpenAI 官方接口可选的 `organization`。"""

    project: str | None = Field(
        default=None,
        json_schema_extra={
            "x-widget": "input",
            "x-icon": "folder-kanban",
        },
    )
    """OpenAI 官方接口可选的 `project`。"""

    model_list_endpoint: str = Field(
        default="/models",
        json_schema_extra={
            "x-widget": "input",
            "x-icon": "list",
        },
    )
    """模型列表端点路径。适用于 OpenAI 兼容接口的探测与管理。"""

    reasoning_parse_mode: str = Field(
        default=ReasoningParseMode.AUTO.value,
        json_schema_extra={
            "x-widget": "select",
            "x-icon": "brain",
        },
    )
    """推理内容解析模式。可选值：`auto`、`native`、`think_tag`、`none`。"""

    tool_argument_parse_mode: str = Field(
        default=ToolArgumentParseMode.AUTO.value,
        json_schema_extra={
            "x-widget": "select",
            "x-icon": "braces",
        },
    )
    """工具参数解析模式。可选值：`auto`、`strict`、`repair`、`double_decode`。"""

    max_retry: int = Field(
        default=3,
        ge=0,
        json_schema_extra={
            "x-widget": "input",
            "x-icon": "repeat",
        },
    )
    """最大重试次数 (单个模型API调用失败, 最多重试的次数)"""

    timeout: int = Field(
        default=60,
        ge=1,
        json_schema_extra={
            "x-widget": "input",
            "x-icon": "clock",
            "step": 1,
        },
    )
    """API调用的超时时长 (超过这个时长, 本次请求将被视为"请求超时", 单位: 秒)"""

    retry_interval: int = Field(
        default=5,
        ge=1,
        json_schema_extra={
            "x-widget": "input",
            "x-icon": "timer",
            "step": 1,
        },
    )
    """重试间隔 (如果API调用失败, 重试的间隔时间, 单位: 秒)"""

    def model_post_init(self, context: Any = None) -> None:
        """执行 API 提供商配置的后置校验。

        密钥外部化（P2/D1）：``api_key`` 里的 ``${VAR}`` **不在构造期解析**——构造期解析是
        **就地改写**，对象里会存下解析后的明文，而写路径（配置自动升级 / 钩子命中时
        ``_build_config_template`` 逐字段 ``getattr``）恰好吃这个对象 ⇒ 任何一次
        ``MODEL_CONFIG_VERSION`` 提升都会把明文写回文件（3 段实测到的写回洞）。

        4 段（解析时机归位）：解析挪到 **adapter 读出配置后、注入客户端之前**
        （``resolve_provider_env_references``，唯一调用点
        ``src/llm_models/model_client/base_client.py`` 的 ``get_client_class_instance``，
        且只作用在**传给工厂的副本**上）。
        ⇒ 写回路径看到的 ``api_key`` 与盘上是**同一个字符串**，那份差（对象明文 vs 盘上引用）
        不再存在 ⇒ 写回守卫**不再被触发**（守卫本身按 F4 死线**留在原位**，见
        ``raw_api_key_of`` 与 ``pytests/config_test/test_secret_writeback_guard.py``）。

        校验口径随之调整：``${VAR}`` 形态**未经解析**，所以"非空"判据不再能拿解析后的值说事——
        引用形态本身算"已配置"（`auth_type=none` 之外的空串才算没配）。变量缺失的报错
        因此也从**启动期**推后到**建客户端时**（缺变量这件事在真正要用它的那一刻才致命，
        而启动期报错会让"只是换了个没配变量的环境"的容器起不来）。

        Args:
            context: Pydantic 传入的上下文对象。

        Raises:
            ValueError: 当配置项缺失或组合不合法时抛出。
        """
        # 原文留痕：归位之前它是"解析后的 api_key 之外唯一存有原文的地方"；归位之后
        # api_key 本身就是原文 ⇒ 这里记的是**同一个值**（对写回判据而言是恒等）。
        #
        # ⚠️ 但它**不是死的**：本方法仍是"这个对象经过配置构造路径"的唯一标记点 ——
        # `raw_api_key_of` 返回 `None` 正是"`_raw_api_key` 没被设过"（有人绕开本方法）。
        # 写回守卫的第三条防御分支（取不到原文 ⇒ 拒绝写出）就挂在这个判据上，
        # 而 F4 死线要求守卫与 `pytests/config_test/test_secret_writeback_guard.py` 的
        # 5 条测试必须在位 ⇒ **删掉这一行会让那条防御分支恒不可达、失去对象**。
        self._raw_api_key = self.api_key

        if self.auth_type != OpenAICompatibleAuthType.NONE and not self.api_key.strip():
            raise ValueError(t("config.api_key_empty"))
        if not self.base_url and self.client_type != "gemini":  # TODO: 允许gemini使用base_url
            raise ValueError(t("config.api_base_url_empty"))
        if not self.name:
            raise ValueError(t("config.api_provider_name_empty"))
        if self.auth_type == OpenAICompatibleAuthType.HEADER and not self.auth_header_name.strip():
            raise ValueError("当 auth_type=header 时，auth_header_name 不能为空")
        if self.auth_type == OpenAICompatibleAuthType.QUERY and not self.auth_query_name.strip():
            raise ValueError("当 auth_type=query 时，auth_query_name 不能为空")
        super().model_post_init(context)


def raw_api_key_of(provider: APIProvider) -> str | None:
    """取 ``provider.api_key`` 在**盘上的原文**（``${VAR}`` 引用或明文）——写回路径专用。

    4 段（解析时机归位）之后的语义变化（**如实说明，不许含糊**）：

    - 归位之前：``APIProvider.api_key`` 是**解析后**的值（可能就是真密钥），原文存在
      ``_raw_api_key``——两者不同，写回方必须走本函数才不至于把明文写回文件。
    - 归位之后：解析不再就地改写 ⇒ ``provider.api_key`` **本身就是盘上原文**。于是本函数
      退化成**恒等取值**（正常构造路径下 `raw_api_key_of(p) == p.api_key`）。
    - **为什么还留着**：`config.py` 的写回守卫（``_collect_reference_api_keys`` /
      ``_restore_secret_references``）按 F4 死线**必须在位**，它就是靠本函数取"该写回什么"；
      而"取不到原文 ⇒ 拒绝写出"这条**防御分支**的可达性判据正是"这个对象有没有经过配置
      构造路径"（`None` ⇔ 绕开了 ``model_post_init``）。⇒ 守卫**不再触发**是**预期结果**
      （判据：采集条件 ``on_disk_value != pending_value`` 现在恒不成立——盘上是引用、
      对象里也是同一个引用），不是"守卫失效"；删掉它等于把最后一道闸拆了。

    注：做成模块级函数而不是 ``@property``，是因为 ``ConfigBase`` 的字段说明提取
    （``AttrDocBase._extract_field_docs(allow_extra_methods=False)``）只放行
    ``model_post_init`` 与 ``@field_validator`` / ``@model_validator`` —— ``@property``
    仍不在白名单里，加属性会让 ``APIProvider`` 构造即报错。
    """
    return provider._raw_api_key


def provider_api_key_field_path(provider: APIProvider) -> str:
    """provider 的 ``api_key`` 在配置里的字段路径（错误消息用，两处调用点共用一份口径）。

    为什么单独抽出来：注入边界（``resolve_provider_env_references``）与启动期预校验
    （``ConfigManager.initialize`` → ``preflight_provider_env_references``）都要报
    "哪个字段的引用缺了"——两处各拼一次字符串，迟早出现两种写法，而现场排障最恨这个。
    """
    return f"api_providers[{provider.name}].api_key" if provider.name else "api_providers[].api_key"


def resolve_provider_env_references(provider: APIProvider) -> APIProvider:
    """返回一份"``api_key`` 已解析"的 provider 副本——**注入客户端之前**的唯一解析入口。

    为什么必须是副本（而不是就地改写）：就地改写就是 3 段那个写回洞的根因。传入的
    ``provider`` 往往**就是** `ConfigManager` 持有的那份配置对象（`api_providers[0]`），
    就地写它等于把明文塞回配置对象 ⇒ 下一次版本升级照样写回文件。副本把解析结果**限制在
    注入链这一段**：客户端拿到真密钥，配置对象继续持有盘上原文。

    - 未落在 ``${VAR}`` 形态上（明文 / 空串）⇒ 原对象**原样返回**（不复制，双读期不吃亏）。
    - 引用缺变量 ⇒ 抛 ``ConfigEnvReferenceError``（含变量名与字段路径），**不静默退化成空串**。
    - 只解析 ``api_key``：``default_headers`` / ``default_query`` / ``auth_header_name`` /
      ``auth_query_name`` 里的 ``${VAR}`` 按 3 段冻结的契约**保持字面量**（扩位是独立决定）。

    Args:
        provider: 从配置读出的 API 提供商。

    Returns:
        解析后的 provider（明文场景返回入参本身）。

    Raises:
        ConfigEnvReferenceError: ``api_key`` 引用的环境变量未设置或为空。
    """
    raw_api_key = provider.api_key
    resolved_api_key = resolve_env_references(raw_api_key, field_path=provider_api_key_field_path(provider))
    if resolved_api_key == raw_api_key:
        return provider
    # model_copy 不跑校验器（`api_key` 只是换个字符串，形状没变），也就不会重入 model_post_init。
    return provider.model_copy(update={"api_key": resolved_api_key})


def preflight_provider_env_references(model_config: ModelConfig) -> None:
    """启动期预校验：把每个 provider 的 ``api_key`` 引用**试解一遍**，缺变量即报错。

    存在的理由（失败响度）：解析迁到注入边界之后，"缺变量"从**启动失败**退化成
    "**首次建客户端才炸**"——那是响度上的退步：容器 `ready=True`、心跳正常，直到用户第一条
    消息进来才失败（`AGENTS §七` #4"未接线不得静默跳过：要么接线，要么初始化失败出声"；
    dsh 口径"**配置错误要响亮**"）。本函数把响度拿回来：**启动即校验**。

    两条死规矩：

    - **只读不写**：用 ``resolve_env_references``（纯函数）逐个试解，**不碰磁盘** ⇒ 盘上仍是
      ``${VAR}``。它不构造客户端、不缓存结果；注入边界那一份解析**照旧**单独做
      （两处各司其职：这里负责"现在就说"，那里负责"给出真值"）。
    - **只查有引用的字段**：明文（双读期的合法形态）与空串（``auth_type=none``）都不受影响。

    校验**覆盖面**＝"provider 的 api_key"，与 3 段冻结的解析位一致——要扩到
    ``default_headers`` 之类，先改契约（那里按契约保持字面量）。

    Args:
        model_config: 已加载的模型配置。

    Raises:
        ConfigEnvReferenceError: 任一 provider 的 ``api_key`` 引用缺变量/变量为空。
            异常在**双通道**留痕后原样抛出（调用方——启动入口——据此拒绝启动）。
    """
    checked = 0
    for provider in model_config.api_providers:
        try:
            resolve_env_references(provider.api_key, field_path=provider_api_key_field_path(provider))
            checked += 1
        except ConfigEnvReferenceError as exc:
            _report_env_reference_preflight_failure(exc, provider=provider, checked=checked)
            raise
    logger.debug("启动期环境引用预校验通过：%d 个 provider 的 api_key 均可解析", checked)


def _report_env_reference_preflight_failure(
    error: ConfigEnvReferenceError,
    *,
    provider: APIProvider,
    checked: int,
) -> None:
    """预校验失败的双通道上报（债务原则：异常不得单通道 —— logger + 上报 port）。

    与版本链拒绝（``config._report_version_chain_refusal``）同构：只上报，**不改文件、不兜底**
    ——缺变量的正确处置是"把变量补上再启动"；替用户塞一个空值等于把隐患推向第一次调用。
    """
    from src.core.error_escalation.types import ErrorLevel
    from src.core.error_escalation_port_registry import get_error_escalation_port

    port = get_error_escalation_port()
    if port is not None:
        port.report(ErrorLevel.CRITICAL, "启动期配置环境引用缺失，拒绝启动", exception=error)
    logger.critical(
        f"启动期配置校验失败：provider {provider.name or '(未命名)'} 的 api_key 引用缺变量"
        f"（已检查 {checked} 个 provider）——{error}"
    )


class ModelInfo(ConfigBase):
    """单个模型信息配置类"""

    _validate_any: bool = False
    suppress_any_warning: bool = True

    category: str = Field(
        default="llm",
        min_length=1,
        # default 也必须过校验：缺键取到 "" 要报错（原先由 model_post_init 兜）
        validate_default=True,
        json_schema_extra={
            "x-widget": "select",
            "x-icon": "folder",
            # ⚠️ 本字段的 annotation 是 `str`，允许值**只存在于这里**（类型侧没有 Literal）——
            # 于是 UI 只给 3 个选项、模型侧却接受任意字符串。收成 Literal 属**行为收紧**
            # （旧配置可能带自定义 category），需拍板；1 段只记录，不改。
            "options": ["llm", "embedding", "voice"],
        },
    )
    """能力域粗分（llm/embedding/voice），仅用于组织分组，(category, name) 组合唯一。
    能力筛选以 capabilities 为准（ZG-12 组件自治）。"""

    capabilities: set[str] = Field(
        default_factory=set,
        json_schema_extra={
            "x-widget": "custom",
            "x-icon": "badge",
        },
    )
    """模型能力标签集（text_generation / tool_calling / vision / embedding / voice）。
    visual=True 会自动迁移为含 "vision"；字段集以 ZG-16 调研结论为准。"""

    model_identifier: str = Field(
        default="",
        json_schema_extra={
            "x-widget": "input",
            "x-icon": "package",
        },
    )
    """模型标识符 (API服务商提供的模型标识符)"""

    name: str = Field(
        default="",
        min_length=1,
        # default 也必须过校验：缺键取到 "" 要报错（原先由 model_post_init 兜）
        validate_default=True,
        json_schema_extra={
            "x-widget": "input",
            "x-icon": "tag",
        },
    )
    """模型名称 (可随意命名, 在models中需使用这个命名)"""

    api_provider: str = Field(
        default="",
        min_length=1,
        # default 也必须过校验：缺键取到 "" 要报错（原先由 model_post_init 兜）
        validate_default=True,
        json_schema_extra={
            "x-widget": "select",
            "x-icon": "link",
        },
    )
    """API服务商名称 (对应在api_providers中配置的服务商名称)"""

    price_in: float = Field(
        default=0.0,
        ge=0,
        json_schema_extra={
            "x-widget": "input",
            "x-icon": "dollar-sign",
            "step": 0.001,
        },
    )
    """输入价格 (用于API调用统计, 单位：元/ M token) (可选, 若无该字段, 默认值为0)"""

    cache: bool = Field(
        default=False,
        json_schema_extra={
            "x-widget": "switch",
            "x-icon": "database",
        },
    )
    """是否启用模型输入缓存计费。开启后命中缓存的输入 token 使用 cache_price_in 计费。"""

    cache_price_in: float = Field(
        default=0.0,
        ge=0,
        json_schema_extra={
            "x-widget": "input",
            "x-icon": "database-zap",
            "step": 0.001,
        },
    )
    """缓存命中输入价格 (用于API调用统计, 单位：元/ M token)。仅当 cache=true 时使用。"""

    price_out: float = Field(
        default=0.0,
        ge=0,
        json_schema_extra={
            "x-widget": "input",
            "x-icon": "dollar-sign",
            "step": 0.001,
        },
    )
    """输出价格 (用于API调用统计, 单位：元/ M token) (可选, 若无该字段, 默认值为0)"""

    temperature: float | None = Field(
        default=None,
        json_schema_extra={
            "x-widget": "input",
            "x-icon": "thermometer",
        },
    )
    """模型级别温度（可选），会覆盖任务配置中的温度"""

    max_tokens: int | None = Field(
        default=None,
        json_schema_extra={
            "x-widget": "input",
            "x-icon": "layers",
        },
    )
    """模型级别最大token数（可选），会覆盖任务配置中的max_tokens"""

    context_window: int | None = Field(
        default=None,
        json_schema_extra={
            "x-widget": "input",
            "x-icon": "maximize",
        },
    )
    """模型输入窗口大小 (token 数)。null 时 fallback 全局默认 (65536=64K, DeepSeek 起步)。"""

    force_stream_mode: bool = Field(
        default=False,
        json_schema_extra={
            "x-widget": "switch",
            "x-icon": "zap",
        },
    )
    """强制流式输出模式 (若模型不支持非流式输出, 请设置为true启用强制流式输出, 默认值为false)"""

    visual: bool = Field(
        default=False,
        json_schema_extra={
            "x-widget": "switch",
            "x-icon": "image",
        },
    )
    """是否为多模态模型。开启后表示该模型支持视觉输入。"""

    extra_params: dict[str, Any] = Field(
        default_factory=dict,
        json_schema_extra={
            "x-widget": "custom",
            "x-icon": "sliders",
        },
    )
    """额外参数 (用于API调用时的额外配置)。
    OpenAI 兼容客户端会将该字典拆分为请求附加项：headers 会作为请求头传入，query 会作为 URL 查询参数传入，body 会合并到请求体。
    未放入 headers/query/body 的普通键，也会作为请求体额外字段传入；例如 {enable_thinking = "false"} 会传为请求体字段 enable_thinking。
    该字段不会以 extra_params 这个键整体发送给模型服务商。
    temperature 和 max_tokens 也可写在此处作为模型级默认值，但更推荐使用同名独立配置项。
    Gemini 客户端会按自身支持的字段筛选并映射到 GenerateContentConfig、EmbedContentConfig 或音频请求配置中。"""

    def model_post_init(self, context: Any = None):
        self.model_identifier = self.model_identifier.strip()
        if not self.model_identifier:
            raise ValueError(t("config.model_identifier_empty_generic"))
        # name / api_provider / category 的非空约束已上移到各自 Field(min_length=1, validate_default=True)。
        # model_identifier 留在这里：它判的是 **strip 之后**非空，Field 的 min_length 只管原始长度，
        # `"   "` 这类全空白值只有 strip 后才能判出来。
        # visual=True 自动迁移为 vision 能力（T14）
        if getattr(self, "visual", False) and "vision" not in self.capabilities:
            self.capabilities.add("vision")
        # capabilities 按 category 默认迁移（旧配置无新字段——不算配置写错）。
        # 并集语义：visual 模型同时是文本模型（vision + text_generation + tool_calling）。
        if self.category == "embedding":
            self.capabilities.add("embedding")
        elif self.category == "voice":
            self.capabilities.add("voice")
        else:
            self.capabilities.update({"text_generation", "tool_calling"})
        return super().model_post_init(context)


class TaskConfig(ConfigBase):
    """任务配置类"""

    model_list: list[str] = Field(
        default_factory=list,
        json_schema_extra={
            "x-widget": "custom",
            "x-icon": "list",
        },
    )
    """使用的模型列表, 每个元素对应上面的模型名称(name)"""

    max_tokens: int = Field(
        default=4096,
        ge=1,
        json_schema_extra={
            "x-widget": "input",
            "x-icon": "layers",
            "step": 1,
        },
    )
    """任务最大输出token数"""

    temperature: float = Field(
        default=0.3,
        ge=0,
        le=2,
        json_schema_extra={
            "x-widget": "slider",
            "x-icon": "thermometer",
            "step": 0.1,
        },
    )
    """模型温度"""

    slow_threshold: float = Field(
        default=15.0,
        ge=0,
        json_schema_extra={
            "x-widget": "input",
            "x-icon": "alert-circle",
            "step": 0.1,
            "advanced": True,
        },
    )
    """超时警告时间（秒），超过此时间会输出警告日志"""

    selection_strategy: str = Field(
        default="balance",
        json_schema_extra={
            "x-widget": "select",
            "x-icon": "shuffle",
            "options": ["balance", "random", "sequential"],
        },
    )
    """模型选择策略：balance（负载均衡）、random（随机选择）或 sequential（按配置顺序优先选择）"""

    hard_timeout: float = Field(
        default=240.0,
        ge=1.0,
        json_schema_extra={
            "x-widget": "input",
            "x-icon": "clock",
            "step": 1.0,
            "advanced": True,
        },
    )
    """任务硬超时（秒），到点未返回则取消请求并尝试切换下一个模型；防止上游代理静默排队导致主循环饥饿"""


class ModelTaskConfig(ConfigBase):
    """模型配置类"""

    replyer: TaskConfig = Field(
        default_factory=TaskConfig,
        json_schema_extra={
            "x-widget": "custom",
            "x-icon": "message-square",
        },
    )
    """回复模型，影响麦麦的回复表现"""

    planner: TaskConfig = Field(
        default_factory=TaskConfig,
        json_schema_extra={
            "x-widget": "custom",
            "x-icon": "map",
        },
    )
    """规划模型，决定麦麦的行动，需要有一定Agent能力的模型"""

    memory: TaskConfig = Field(
        default_factory=TaskConfig,
        json_schema_extra={
            "x-widget": "custom",
            "x-icon": "brain",
            "advanced": True,
        },
    )
    """记忆模型配置，用于长期记忆总结、抽取、写回等高记忆任务；留空时由调用方按需回退"""

    mid_memory: TaskConfig = Field(
        default_factory=TaskConfig,
        json_schema_extra={
            "x-widget": "custom",
            "x-icon": "archive",
            "advanced": True,
        },
    )
    """聊天回想模型配置；留空时自动继用 planner 模型"""

    utils: TaskConfig = Field(
        default_factory=TaskConfig,
        json_schema_extra={
            "x-widget": "custom",
            "x-icon": "wrench",
        },
    )
    """执行文本概括，整理等小任务，是麦麦必须的模型。可以选择速度快的小尺寸模型"""

    learner: TaskConfig = Field(
        default_factory=TaskConfig,
        json_schema_extra={
            "x-widget": "custom",
            "x-icon": "graduation-cap",
            "advanced": True,
        },
    )
    """学习模型配置，用于表达方式学习和黑话学习；留空时用 utils 模型"""

    expression_use: TaskConfig = Field(
        default_factory=TaskConfig,
        json_schema_extra={
            "x-widget": "custom",
            "x-icon": "message-circle-more",
            "advanced": True,
        },
    )
    """表达方式使用模型配置；留空时用 utils 模型"""

    emoji: TaskConfig = Field(
        default_factory=TaskConfig,
        json_schema_extra={
            "x-widget": "custom",
            "x-icon": "smile",
            "advanced": True,
        },
    )
    """表情包发送模型配置；留空时保持原有 planner/vlm 选择逻辑"""

    vlm: TaskConfig = Field(
        default_factory=TaskConfig,
        json_schema_extra={
            "x-widget": "custom",
            "x-icon": "image",
        },
    )
    """视觉模型，需要能够识图的模型"""

    voice: TaskConfig = Field(
        default_factory=TaskConfig,
        json_schema_extra={
            "x-widget": "custom",
            "x-icon": "volume-2",
            "advanced": True,
        },
    )
    """语音识别模型"""

    embedding: TaskConfig = Field(
        default_factory=TaskConfig,
        json_schema_extra={
            "x-widget": "custom",
            "x-icon": "database",
        },
    )
    """嵌入模型，需要文本嵌入类型的模型，不可使用LLM"""
