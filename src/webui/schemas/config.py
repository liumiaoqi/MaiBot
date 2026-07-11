from typing import Any, List

from pydantic import BaseModel, Field


class PromptFileInfo(BaseModel):
    name: str = Field(..., description="Prompt 文件名")
    size: int = Field(..., description="文件大小")
    modified_at: float = Field(..., description="最后修改时间戳")
    display_name: str = Field(default="", description="Prompt 展示名称")
    advanced: bool = Field(default=False, description="是否为高级 Prompt")
    description: str = Field(default="", description="Prompt 描述")
    customized: bool = Field(default=False, description="是否存在用户自定义覆盖")
    custom_version_count: int = Field(default=0, description="用户自定义版本数量")


class PromptValidationResult(BaseModel):
    valid: bool = True
    missing_placeholders: List[str] = Field(default_factory=list)
    extra_placeholders: List[str] = Field(default_factory=list)
    message: str = ""


class PromptVersionInfo(BaseModel):
    id: str
    label: str
    created_at: float
    modified_at: float
    size: int
    active: bool = False


class PromptCatalogResponse(BaseModel):
    success: bool = True
    languages: List[str]
    files: dict[str, List[PromptFileInfo]]


class PromptFileResponse(BaseModel):
    success: bool = True
    language: str
    filename: str
    content: str
    customized: bool = False
    active_version_id: str | None = None
    versions: List[PromptVersionInfo] = Field(default_factory=list)
    validation: PromptValidationResult = Field(default_factory=PromptValidationResult)


class PromptVersionFileResponse(PromptFileResponse):
    version_id: str


class PromptVersionListResponse(BaseModel):
    success: bool = True
    language: str
    filename: str
    active_version_id: str | None = None
    versions: List[PromptVersionInfo] = Field(default_factory=list)


class PromptUpdateRequest(BaseModel):
    content: str
    version_id: str | None = None
    label: str = ""
    create_version: bool = False


class PromptGeneratorChatPrompt(BaseModel):
    platform: str = Field(default="", description="平台名")
    item_id: str = Field(default="", description="目标 ID")
    rule_type: str = Field(default="group", description="规则类型：group/private")
    prompt: str = Field(default="", description="额外 Prompt 内容")


class PromptGeneratorParsedResult(BaseModel):
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
    id: str = Field(..., description="配置块 ID")
    section: str = Field(..., description="目标配置节")
    field: str = Field(..., description="目标字段")
    title: str = Field(..., description="展示标题")
    description: str = Field(default="", description="展示说明")
    value: Any = Field(..., description="字段值")
    toml: str = Field(..., description="单块 TOML 片段")


class PromptGeneratorRequest(BaseModel):
    model_name: str = Field(..., min_length=1, description="model_config.toml 中定义的模型名称")
    source_text: str = Field(..., min_length=1, max_length=20000, description="任意人设、角色卡或风格描述")
    target_scene: str = Field(default="group", description="目标场景：group/private/both")
    language: str = Field(default="简体中文", max_length=32, description="生成语言")
    extra_requirements: str = Field(default="", max_length=4000, description="额外生成要求")
    temperature: float = Field(default=0.3, ge=0, le=2, description="生成温度")
    max_tokens: int = Field(default=1800, ge=256, le=8192, description="最大输出 token 数")


class PromptGeneratorResponse(BaseModel):
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
    blocks: List[PromptGeneratorConfigBlock] = Field(default_factory=list, description="要写入的配置块")


class PromptGeneratorApplyResponse(BaseModel):
    success: bool = True
    message: str
    applied_blocks: int
    sections: List[str]