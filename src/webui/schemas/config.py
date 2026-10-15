from typing import Any, List, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class ConfigReadRequest(BaseModel):
    """读接缝请求（F1）：``get(paths)``。

    ``paths`` 留空 = 该命名空间下已存储的全部叶路径（表单首屏用）；
    给了路径就只回这些路径——**客户端不再需要整份文件**，这正是 raw 端点失去存在理由的地方。
    """

    model_config = ConfigDict(extra='forbid')

    namespace: str = Field(..., description="配置平面：bot / model")
    paths: List[str] = Field(default_factory=list, description="要读的路径；空 = 该平面已存储的全部叶路径")


class ConfigMutateOp(BaseModel):
    """一次路径操作（F1）：``set`` / ``unset`` / ``remove_at``。

    ``unset`` 表示"重置为继承"（真删键），**不是**"写一个等于默认值的值"（F5）——
    后者会让 ``inherited`` 永远是 false，此后再改 schema 默认值也追不上。
    """

    model_config = ConfigDict(extra='forbid')

    op: Literal["set", "unset", "remove_at"] = Field(..., description="操作类型")
    path: str = Field(..., description="配置路径，如 chat.max_tokens、api_providers[0].api_key")
    value: Any = Field(default=None, description="set 的新值；可以是原值，也可以是读回来的秘密占位")
    index: int | None = Field(default=None, ge=0, description="remove_at 的下标")


class ConfigMutateRequest(BaseModel):
    """写接缝请求（F1/F5）：``mutate(ns, ops, expectedRevision)``。

    ``expectedRevision`` 是**必填**的——乐观锁的意义在于"写之前先证明你读到的是最新的"，
    可省略的锁等于没有锁。
    """

    model_config = ConfigDict(extra='forbid', populate_by_name=True)

    namespace: str = Field(..., description="配置平面：bot / model")
    expected_revision: int = Field(
        ...,
        ge=1,
        validation_alias=AliasChoices("expectedRevision", "expected_revision"),
        description="客户端读到的 revision；与当前不符即 409 拒绝",
    )
    ops: List[ConfigMutateOp] = Field(..., min_length=1, description="要实施的路径操作；未点名的字段根本不进写路径")


class ConfigSaveResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')

    success: bool = True
    message: str = "配置已保存"
    needs_restart: bool = Field(default=False, description="修改的配置节是否需要重启才能生效")
    restart_required_sections: List[str] = Field(default_factory=list, description="需要重启的配置节列表")


class PromptFileInfo(BaseModel):
    model_config = ConfigDict(extra='forbid')

    name: str = Field(..., description="Prompt 文件名")
    size: int = Field(..., description="文件大小")
    modified_at: float = Field(..., description="最后修改时间戳")
    display_name: str = Field(default="", description="Prompt 展示名称")
    advanced: bool = Field(default=False, description="是否为高级 Prompt")
    description: str = Field(default="", description="Prompt 描述")
    customized: bool = Field(default=False, description="是否存在用户自定义覆盖")
    custom_version_count: int = Field(default=0, description="用户自定义版本数量")


class PromptValidationResult(BaseModel):
    model_config = ConfigDict(extra='forbid')

    valid: bool = True
    missing_placeholders: List[str] = Field(default_factory=list)
    extra_placeholders: List[str] = Field(default_factory=list)
    message: str = ""


class PromptVersionInfo(BaseModel):
    model_config = ConfigDict(extra='forbid')

    id: str
    label: str
    created_at: float
    modified_at: float
    size: int
    active: bool = False


class PromptCatalogResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')

    success: bool = True
    languages: List[str]
    files: dict[str, List[PromptFileInfo]]


class PromptFileResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')

    success: bool = True
    language: str
    filename: str
    content: str
    customized: bool = False
    active_version_id: str | None = None
    versions: List[PromptVersionInfo] = Field(default_factory=list)
    validation: PromptValidationResult = Field(default_factory=PromptValidationResult)


class PromptVersionFileResponse(PromptFileResponse):
    model_config = ConfigDict(extra='forbid')

    version_id: str


class PromptVersionListResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')

    success: bool = True
    language: str
    filename: str
    active_version_id: str | None = None
    versions: List[PromptVersionInfo] = Field(default_factory=list)


class PromptUpdateRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    content: str
    version_id: str | None = None
    label: str = ""
    create_version: bool = False


class PromptGeneratorChatPrompt(BaseModel):
    model_config = ConfigDict(extra='forbid')

    platform: str = Field(default="", description="平台名")
    item_id: str = Field(default="", description="目标 ID")
    rule_type: str = Field(default="group", description="规则类型：group/private")
    prompt: str = Field(default="", description="额外 Prompt 内容")


class PromptGeneratorParsedResult(BaseModel):
    model_config = ConfigDict(extra='forbid')

    personality: str = Field(default="", description="对应 [personality].personality")
    reply_style: str = Field(default="", description="对应 [personality].reply_style")
    multiple_reply_style: List[str] = Field(default_factory=list, description="对应 multiple_reply_style")
    group_chat_prompt: str = Field(default="", description="对应 [chat.reply_style].group_chat_prompt")
    private_chat_prompts: str = Field(default="", description="对应 [chat.reply_style].private_chat_prompts")
    chat_prompts: List[PromptGeneratorChatPrompt] = Field(
        default_factory=list,
        description="对应 [[chat.reply_style.chat_prompts]]",
    )
    notes: List[str] = Field(default_factory=list, description="生成说明或人工检查建议")


class PromptGeneratorConfigBlock(BaseModel):
    model_config = ConfigDict(extra='forbid')

    id: str = Field(..., description="配置块 ID")
    section: str = Field(..., description="目标配置节")
    field: str = Field(..., description="目标字段")
    title: str = Field(..., description="展示标题")
    description: str = Field(default="", description="展示说明")
    value: Any = Field(..., description="字段值")
    toml: str = Field(..., description="单块 TOML 片段")


class PromptGeneratorRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    model_name: str = Field(..., min_length=1, description="model_config.toml 中定义的模型名称")
    source_text: str = Field(..., min_length=1, max_length=20000, description="任意人设、角色卡或风格描述")
    target_scene: str = Field(default="group", description="目标场景：group/private/both")
    language: str = Field(default="简体中文", max_length=32, description="生成语言")
    extra_requirements: str = Field(default="", max_length=4000, description="额外生成要求")
    temperature: float = Field(default=0.3, ge=0, le=2, description="生成温度")
    max_tokens: int = Field(default=1800, ge=256, le=8192, description="最大输出 token 数")


class PromptGeneratorResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')

    success: bool = True
    model_name: str
    result: PromptGeneratorParsedResult
    config_blocks: List[PromptGeneratorConfigBlock]
    toml_snippet: str
    raw_response: str
    reasoning: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class PromptGeneratorApplyRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    blocks: List[PromptGeneratorConfigBlock] = Field(default_factory=list, description="要写入的配置块")


class PromptGeneratorApplyResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')

    success: bool = True
    message: str
    applied_blocks: int
    sections: List[str]
