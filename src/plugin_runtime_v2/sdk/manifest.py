"""Manifest v3 格式定义 — 替代 v2 的 _manifest.json。

核心变更：capabilities_required → scopes，新增 dependencies/i18n，
manifest_version 从 2 升级为 3，id 格式要求 组织名.插件名。
"""


from typing import Literal

from pydantic import BaseModel, Field, field_validator


class AuthorInfo(BaseModel):
    """作者信息。"""

    name: str
    url: str = ""


class HostAppRequirement(BaseModel):
    """宿主应用版本要求。"""

    min_version: str = ""
    max_version: str = ""


class SDKRequirement(BaseModel):
    """SDK 版本要求。"""

    min_version: str = "4.0.0"
    max_version: str = ""


class I18nLocale(BaseModel):
    """国际化语言配置。"""

    locale: str
    path: str = ""


class I18nConfig(BaseModel):
    """国际化配置。"""

    default_locale: str = "zh-CN"
    locales: list[I18nLocale] = Field(default_factory=list)


class ManifestV3(BaseModel):
    """Manifest v3 — 插件元数据格式。

    与 v2 的差异：
    - manifest_version 从 2 升级为 3
    - capabilities_required 替换为 scopes
    - 新增 dependencies 字段（插件级依赖）
    - 新增 i18n 字段（国际化配置）
    - id 格式要求 组织名.插件名
    """

    manifest_version: Literal[3] = 3
    id: str = Field(..., pattern=r"^[a-zA-Z0-9_-]+(\.[a-zA-Z0-9_-]+)+$")
    version: str
    name: str
    description: str = ""
    author: AuthorInfo
    license: str = ""
    host_application: HostAppRequirement = Field(default_factory=HostAppRequirement)
    sdk: SDKRequirement = Field(default_factory=SDKRequirement)
    scopes: list[str] = Field(..., min_length=1)
    dependencies: list[str] = Field(default_factory=list)
    i18n: I18nConfig | None = None

    @field_validator("scopes")
    @classmethod
    def _validate_scopes(cls, v: list[str]) -> list[str]:
        from src.plugin_runtime_v2.scope.vocabulary import ScopeVocabulary

        invalid = [s for s in v if not ScopeVocabulary.validate(s)]
        if invalid:
            raise ValueError(f"无效的 scope: {invalid}")
        return v
