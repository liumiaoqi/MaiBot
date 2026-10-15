from enum import Enum
from pydantic import PrivateAttr
from typing import Any

import os
import re

from src.common.i18n import t

from .config_base import ConfigBase, Field

# 密钥外部化（P2/D1）：仅识别 ${VAR} 形态的引用，不发明第二套语法。
# 只在被引用的字段位置解析（不做全文替换），避免注释或普通字符串里的 ${...} 被误解析。
# 解析位（3 段冻结的边界，**别顺手扩**）：本轮只有 `APIProvider.api_key` 这一处。
#   - `auth_header_name` / `auth_query_name` / `default_headers` / `default_query` 里的
#     `${VAR}` **按契约不解析**，保持字面量（要不要扩位是独立决定，不是顺手加）；
#   - 注入链（唯一答案）：宿主 `.env`（或宿主 shell 环境，先有值者胜）→ compose
#     `environment:` → 容器进程环境 → 本模块在读取配置时解析。
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
    引用的环境变量缺失或为空会直接报错，**不会**静默变成空串。"""

    # 盘上那一行 api_key 的**原文**（引用 `${VAR}` 或明文），与解析后的 `api_key` 分开存。
    # 解析是"就地改写"⇒ 不留原文，写回时只能拿到真密钥（3 段实测到的写回洞）。
    # 只读访问点见模块级 `raw_api_key_of`：类体里不能加 `@property`（`AttrDocBase` 的字段说明
    # 提取只放行 model_post_init 与 @field_validator / @model_validator，属性仍会被顶回去）。
    # `None` = 未经解析路径构造、没留原文。
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

        密钥外部化（P2/D1）：``api_key`` 写成 ``${VAR}`` 时从环境变量取值；明文值原样工作。
        引用解析放在"非空校验"之前——引用解出来的值才算数。
        解析**就地改写** ``api_key``，所以先把盘上原文留在 ``_raw_api_key``（写回路径要用，
        见 ``raw_api_key_of``）；否则"配置自动升级改写"会把解析后的明文写回文件。

        Args:
            context: Pydantic 传入的上下文对象。

        Raises:
            ConfigEnvReferenceError: api_key 引用的环境变量未设置或为空。
                注意：经 pydantic 构造（`from_dict`/`cls(**data)`）时它会被包装成
                `ValidationError`，但错误文本仍带变量名与字段路径——不静默。
            ValueError: 当配置项缺失或组合不合法时抛出。
        """
        provider_path = f"api_providers[{self.name}].api_key" if self.name else "api_providers[].api_key"
        self._raw_api_key = self.api_key
        self.api_key = resolve_env_references(self.api_key, field_path=provider_path)

        if self.auth_type != OpenAICompatibleAuthType.NONE and not self.api_key:
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

    ``APIProvider.api_key`` 是**解析后**的值（可能就是真密钥），不能当写回源：配置自动
    升级改写走 ``_build_config_template``（逐字段 ``getattr``）⇒ 不加区分就会把解析后的
    明文写回 ``model_config.toml``（3 段实测的写回洞）。写回方拿到 ``None`` 表示这个对象
    没经过解析路径构造（没留原文），此时应**拒绝写出并出声**，不许静默写明文。

    注：做成模块级函数而不是 ``@property``，是因为 ``ConfigBase`` 的字段说明提取
    （``AttrDocBase._extract_field_docs(allow_extra_methods=False)``）只放行
    ``model_post_init`` 与 ``@field_validator`` / ``@model_validator`` —— ``@property``
    仍不在白名单里，加属性会让 ``APIProvider`` 构造即报错。
    """
    return provider._raw_api_key


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
