"""
配置管理API路由
"""

from pathlib import Path
from typing import Annotated, Any, Dict, List, Tuple, Union, get_args, get_origin
import copy
import json
import os
import re
import time
import types

from fastapi import APIRouter, Body, Depends, Query
from fastapi.responses import FileResponse
import tomlkit

from src.common.logger import get_logger
from src.common.prompt_i18n import clear_prompt_cache, extract_prompt_placeholders, list_prompt_templates
from src.common.runtime_paths import resolve_data_file
from src.config.config import (
    CONFIG_DIR,
    Config,
    ConfigFrozenError,
    ModelConfig,
    PROJECT_ROOT,
    config_manager,  # noqa: TID251 — 配置管理页面需直接操作配置对象
)
from src.config.config_base import AttributeData, ConfigBase
from src.config.model_configs import (
    APIProvider,
    ModelInfo,
    ModelTaskConfig,
)
from src.config.official_configs import (
    AMemorixConfig,
    BotConfig,
    ChatConfig,
    ChineseTypoConfig,

    DebugConfig,
    EmojiConfig,
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
    ResponsePostProcessConfig,
    ResponseSplitterConfig,
    VisualConfig,
    VoiceConfig,
    WebUIConfig,
)
from src.llm_models.utils_model import LLMOrchestrator
from src.webui import config_store
from src.webui.config_paths import (
    ConfigPathError,
    MISSING,
    assign_path,
    expand_declaration,
    format_path,
    iter_leaf_paths,
    lookup_path,
    parse_declaration,
    parse_path,
    remove_index,
    remove_path,
    to_declaration_key,
    to_plain,
)
from src.webui.config_schema import ConfigSchemaGenerator
from src.webui.config_secrets import (
    SENTINEL_SET_KEY,
    SecretClaimError,
    SecretDeclarationError,
    claim_secret_value,
    describe_secret_value,
    find_secret_root,
    find_unresolved_sentinels,
    is_secret_claim,
    merge_payload_with_reference,
    redact_config_secrets,
    redact_subtree,
)
from src.webui.dependencies import require_auth
from src.webui.errors import AppError
from src.webui.errors.codes import ErrorCode
from src.webui.schemas.base import ApiResponse
from src.webui.schemas.config import (
    ConfigMutateOp,
    ConfigMutateRequest,
    ConfigReadRequest,
    ConfigSaveResponse,
    PromptCatalogResponse,
    PromptFileInfo,
    PromptFileResponse,
    PromptGeneratorApplyRequest,
    PromptGeneratorApplyResponse,
    PromptGeneratorChatPrompt,
    PromptGeneratorConfigBlock,
    PromptGeneratorParsedResult,
    PromptGeneratorRequest,
    PromptGeneratorResponse,
    PromptUpdateRequest,
    PromptValidationResult,
    PromptVersionFileResponse,
    PromptVersionInfo,
    PromptVersionListResponse,
)
from src.common.utils.toml_utils import _update_toml_doc, save_toml_with_format

logger = get_logger("webui")

# 模块级别的类型别名（解决 B008 ruff 错误）
ConfigBody = Annotated[Dict[str, Any], Body()]
SectionBody = Annotated[Any, Body()]

router = APIRouter(prefix="/config", tags=["config"], dependencies=[Depends(require_auth)])
compat_router = APIRouter(prefix="/api/config", tags=["config-compat"], dependencies=[Depends(require_auth)])

PROMPTS_DIR = PROJECT_ROOT / "prompts"
CUSTOM_PROMPTS_DIR = resolve_data_file("custom_prompts")  # 数据根只从唯一来源取（runtime_paths）
MAISAKA_PROMPT_PREVIEW_DIR = (PROJECT_ROOT / "logs" / "maisaka_prompt").resolve()
_SCHEMA_CACHE: Dict[str, Dict[str, Any]] = {}
_PROMPT_VERSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")
_LEGACY_CUSTOM_PROMPT_VERSION_ID = "legacy-current"

# 修改后需要重启 MaiBot 才能生效的配置节
_RESTART_REQUIRED_SECTIONS = frozenset({
    "bot", "database", "log", "webui", "debug",
})

# 热重载结果（写路径的统一语义；前端可按需展示，不必各自解释一遍）
HOT_RELOAD_OK = "ok"
HOT_RELOAD_REFUSED_FROZEN = "refused_frozen"


async def _reload_config_or_report(context: str) -> str:
    """热重载配置并返回状态（``ok`` / ``refused_frozen``）——**全模块唯一的重载入口**。

    两条纪律写在这里，免得后人重犯（对抗审查 F14 + 2026-10-16 收尾令）：

    1. ``config_manager.reload_config`` 是 ``async def``（``src/config/config.py:489``）：
       **必须 await**。不 await 等于把协程丢掉——既不重载、又只留一条 ``RuntimeWarning``，
       而接口看起来像"保存成功顺带热重载了"。本模块曾有 6 处这种写法，现已全部收敛到这里。
    2. 冻结态（ZG-10：启动完成后配置只读）是**预期**分支，不是错误：文件**已经写成功**了，
       所以**绝不**回 500——如实返回 ``refused_frozen``，由调用方告诉用户
       "已落盘，热重载被拒，实际生效靠重启或文件监听"。

    Args:
        context: 日志上下文（哪个端点触发的），便于排障。

    Returns:
        ``HOT_RELOAD_OK`` 或 ``HOT_RELOAD_REFUSED_FROZEN``。
    """
    try:
        await config_manager.reload_config()
    except ConfigFrozenError as error:
        logger.warning(f"{context}：配置已落盘，但热重载被拒（配置已冻结）：{error}")
        return HOT_RELOAD_REFUSED_FROZEN
    return HOT_RELOAD_OK


def _needs_restart_flag(restart_sections: List[str], hot_reload: str) -> bool:
    """重启提示：命中重启节，**或**热重载被拒（那说明改动还没生效）。

    后者是这次收尾统一起来的口径：热重载被冻结挡下时，"是否需要重启"的诚实答案是"是"，
    不然用户会以为改完即生效（旧代码正是这么答的）。
    """
    return bool(restart_sections) or hot_reload == HOT_RELOAD_REFUSED_FROZEN


def _get_cached_schema(cache_key: str, config_class: type[ConfigBase], include_nested: bool = True) -> Dict[str, Any]:
    schema = _SCHEMA_CACHE.get(cache_key)
    if schema is None:
        schema = ConfigSchemaGenerator.generate_config_schema(config_class, include_nested=include_nested)
        _SCHEMA_CACHE[cache_key] = schema
    return copy.deepcopy(schema)


def _safe_prompt_path(language: str, filename: str) -> Path:
    """校验并解析 prompts 下的文件路径。"""

    normalized_language = language.strip()
    normalized_filename = filename.strip()

    if not normalized_language or any(part in normalized_language for part in ("..", "/", "\\")):
        raise AppError(ErrorCode.PARAM_INVALID, "无效的 Prompt 语言目录")
    if not normalized_filename.endswith(".prompt") or any(part in normalized_filename for part in ("..", "/", "\\")):
        raise AppError(ErrorCode.PARAM_INVALID, "无效的 Prompt 文件名")

    prompt_path = (PROMPTS_DIR / normalized_language / normalized_filename).resolve()
    prompts_root = PROMPTS_DIR.resolve()
    try:
        prompt_path.relative_to(prompts_root)
    except ValueError as exc:
        raise AppError(ErrorCode.PARAM_INVALID, "Prompt 路径越界") from exc
    return prompt_path


def _safe_custom_prompt_path(language: str, filename: str) -> Path:
    """校验并解析 data/custom_prompts 下的用户覆盖文件路径。"""

    normalized_language = language.strip()
    normalized_filename = filename.strip()

    if not normalized_language or any(part in normalized_language for part in ("..", "/", "\\")):
        raise AppError(ErrorCode.PARAM_INVALID, "无效的 Prompt 语言目录")
    if not normalized_filename.endswith(".prompt") or any(part in normalized_filename for part in ("..", "/", "\\")):
        raise AppError(ErrorCode.PARAM_INVALID, "无效的 Prompt 文件名")

    prompt_path = (CUSTOM_PROMPTS_DIR / normalized_language / normalized_filename).resolve()
    custom_prompts_root = CUSTOM_PROMPTS_DIR.resolve()
    try:
        prompt_path.relative_to(custom_prompts_root)
    except ValueError as exc:
        raise AppError(ErrorCode.PARAM_INVALID, "Prompt 路径越界") from exc
    return prompt_path


def _safe_prompt_version_id(version_id: str) -> str:
    """校验 Prompt 自定义版本 ID。"""

    normalized_version_id = version_id.strip()
    if (
        not normalized_version_id
        or normalized_version_id in {".", ".."}
        or not _PROMPT_VERSION_ID_PATTERN.fullmatch(normalized_version_id)
    ):
        raise AppError(ErrorCode.PARAM_INVALID, "无效的 Prompt 版本 ID")
    return normalized_version_id


def _safe_custom_prompt_versions_dir(language: str, filename: str) -> Path:
    """解析指定 Prompt 的自定义版本目录。"""

    custom_prompt_path = _safe_custom_prompt_path(language, filename)
    versions_dir = custom_prompt_path.parent / ".versions" / custom_prompt_path.stem
    custom_prompts_root = CUSTOM_PROMPTS_DIR.resolve()
    resolved_versions_dir = versions_dir.resolve()
    try:
        resolved_versions_dir.relative_to(custom_prompts_root)
    except ValueError as exc:
        raise AppError(ErrorCode.PARAM_INVALID, "Prompt 版本路径越界") from exc
    return resolved_versions_dir


def _prompt_version_manifest_path(language: str, filename: str) -> Path:
    return _safe_custom_prompt_versions_dir(language, filename) / "manifest.json"


def _prompt_version_file_path(language: str, filename: str, version_id: str) -> Path:
    normalized_version_id = _safe_prompt_version_id(version_id)
    version_path = _safe_custom_prompt_versions_dir(language, filename) / f"{normalized_version_id}.prompt"
    versions_dir = _safe_custom_prompt_versions_dir(language, filename).resolve()
    resolved_version_path = version_path.resolve()
    try:
        resolved_version_path.relative_to(versions_dir)
    except ValueError as exc:
        raise AppError(ErrorCode.PARAM_INVALID, "Prompt 版本路径越界") from exc
    return resolved_version_path


def _read_prompt_version_manifest(language: str, filename: str) -> Dict[str, Any]:
    manifest_path = _prompt_version_manifest_path(language, filename)
    if not manifest_path.exists():
        return {"active_version_id": None, "versions": []}

    try:
        raw_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AppError(ErrorCode.SYS_INTERNAL_ERROR, f"Prompt 版本清单损坏: {manifest_path}", http_status=500) from exc

    if not isinstance(raw_manifest, dict):
        raise AppError(ErrorCode.SYS_INTERNAL_ERROR, f"Prompt 版本清单格式错误: {manifest_path}", http_status=500)

    versions = raw_manifest.get("versions", [])
    if not isinstance(versions, list):
        versions = []

    return {
        "active_version_id": raw_manifest.get("active_version_id")
        if isinstance(raw_manifest.get("active_version_id"), str)
        else None,
        "versions": [version for version in versions if isinstance(version, dict)],
    }


def _write_prompt_version_manifest(language: str, filename: str, manifest: Dict[str, Any]) -> None:
    manifest_path = _prompt_version_manifest_path(language, filename)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")


def _create_prompt_version_id(language: str, filename: str) -> str:
    base_version_id = time.strftime("v%Y%m%d%H%M%S")
    version_id = base_version_id
    suffix = 2
    while _prompt_version_file_path(language, filename, version_id).exists():
        version_id = f"{base_version_id}-{suffix}"
        suffix += 1
    return version_id


def _default_prompt_version_label(filename: str) -> str:
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    prompt_name = filename.removesuffix(".prompt")
    return f"{prompt_name} 自定义版本 {timestamp}"


def _normalize_prompt_version_label(filename: str, label: str) -> str:
    normalized_label = label.strip()
    return normalized_label or _default_prompt_version_label(filename)


def _build_prompt_validation(default_content: str, custom_content: str) -> PromptValidationResult:
    try:
        default_placeholders = extract_prompt_placeholders(default_content)
        custom_placeholders = extract_prompt_placeholders(custom_content)
    except ValueError as exc:
        return PromptValidationResult(valid=False, message=f"Prompt 参数格式错误: {exc}")

    missing_placeholders = sorted(default_placeholders - custom_placeholders)
    extra_placeholders = sorted(custom_placeholders - default_placeholders)
    if not missing_placeholders and not extra_placeholders:
        return PromptValidationResult()

    message_parts: List[str] = []
    if missing_placeholders:
        message_parts.append(f"缺少参数: {', '.join(missing_placeholders)}")
    if extra_placeholders:
        message_parts.append(f"多余参数: {', '.join(extra_placeholders)}")
    return PromptValidationResult(
        valid=False,
        missing_placeholders=missing_placeholders,
        extra_placeholders=extra_placeholders,
        message="自定义 Prompt 参数必须与默认 Prompt 完全一致，" + "；".join(message_parts),
    )


def _ensure_prompt_parameters_match(prompt_path: Path, custom_content: str) -> PromptValidationResult:
    default_content = prompt_path.read_text(encoding="utf-8")
    validation = _build_prompt_validation(default_content, custom_content)
    if not validation.valid:
        raise AppError(ErrorCode.PARAM_INVALID, validation.message, http_status=400)
    return validation


def _list_prompt_versions(language: str, filename: str) -> List[PromptVersionInfo]:
    manifest = _read_prompt_version_manifest(language, filename)
    active_version_id = manifest.get("active_version_id")
    versions: List[PromptVersionInfo] = []
    for raw_version in manifest["versions"]:
        version_id = raw_version.get("id")
        if not isinstance(version_id, str):
            continue
        version_path = _prompt_version_file_path(language, filename, version_id)
        if not version_path.exists():
            continue
        stat = version_path.stat()
        versions.append(
            PromptVersionInfo(
                id=version_id,
                label=raw_version.get("label") if isinstance(raw_version.get("label"), str) else version_id,
                created_at=float(raw_version.get("created_at") or stat.st_ctime),
                modified_at=stat.st_mtime,
                size=stat.st_size,
                active=version_id == active_version_id,
            )
        )

    custom_prompt_path = _safe_custom_prompt_path(language, filename)
    if custom_prompt_path.exists() and not active_version_id and not versions:
        stat = custom_prompt_path.stat()
        versions.append(
            PromptVersionInfo(
                id=_LEGACY_CUSTOM_PROMPT_VERSION_ID,
                label="当前自定义（旧格式）",
                created_at=stat.st_ctime,
                modified_at=stat.st_mtime,
                size=stat.st_size,
                active=True,
            )
        )
    return sorted(versions, key=lambda version: version.modified_at, reverse=True)


def _get_active_prompt_version_id(language: str, filename: str) -> str | None:
    manifest = _read_prompt_version_manifest(language, filename)
    active_version_id = manifest.get("active_version_id")
    if isinstance(active_version_id, str):
        return active_version_id
    if _safe_custom_prompt_path(language, filename).exists():
        return _LEGACY_CUSTOM_PROMPT_VERSION_ID
    return None


def _save_prompt_version(
    language: str,
    filename: str,
    content: str,
    version_id: str | None,
    label: str,
    create_version: bool,
) -> str:
    manifest = _read_prompt_version_manifest(language, filename)
    versions = manifest["versions"]
    existing_version_ids = {
        raw_version["id"] for raw_version in versions if isinstance(raw_version.get("id"), str)
    }

    normalized_version_id = version_id.strip() if isinstance(version_id, str) else ""
    if normalized_version_id:
        _safe_prompt_version_id(normalized_version_id)
    if (
        normalized_version_id
        and not create_version
        and normalized_version_id != _LEGACY_CUSTOM_PROMPT_VERSION_ID
        and normalized_version_id not in existing_version_ids
    ):
        raise AppError(ErrorCode.BIZ_NOT_FOUND, "Prompt 自定义版本不存在")

    should_create_version = (
        create_version
        or not normalized_version_id
        or normalized_version_id == _LEGACY_CUSTOM_PROMPT_VERSION_ID
    )
    if should_create_version:
        normalized_version_id = _create_prompt_version_id(language, filename)
        now = time.time()
        versions.append(
            {
                "id": normalized_version_id,
                "label": _normalize_prompt_version_label(filename, label),
                "created_at": now,
            }
        )
    version_path = _prompt_version_file_path(language, filename, normalized_version_id)
    version_path.parent.mkdir(parents=True, exist_ok=True)
    version_path.write_text(content, encoding="utf-8", newline="\n")

    for raw_version in versions:
        if raw_version.get("id") != normalized_version_id:
            continue
        raw_version["label"] = _normalize_prompt_version_label(
            filename,
            label if label.strip() else str(raw_version.get("label")),
        )
        raw_version["modified_at"] = time.time()
        break

    manifest["active_version_id"] = normalized_version_id
    manifest["versions"] = versions
    _write_prompt_version_manifest(language, filename, manifest)
    return normalized_version_id


def _set_active_prompt_version(language: str, filename: str, version_id: str | None) -> None:
    manifest = _read_prompt_version_manifest(language, filename)
    manifest["active_version_id"] = version_id
    _write_prompt_version_manifest(language, filename, manifest)


def _safe_maisaka_prompt_preview_path(relative_path: str) -> Path:
    """校验并解析 MaiSaka Prompt 预览路径。"""

    normalized_path = relative_path.strip().replace("\\", "/")
    if not normalized_path or normalized_path.startswith("/") or ".." in Path(normalized_path).parts:
        raise AppError(ErrorCode.PARAM_INVALID, "无效的 Prompt 预览路径")

    preview_path = (MAISAKA_PROMPT_PREVIEW_DIR / normalized_path).resolve()
    try:
        preview_path.relative_to(MAISAKA_PROMPT_PREVIEW_DIR)
    except ValueError as exc:
        raise AppError(ErrorCode.PARAM_INVALID, "Prompt 预览路径越界") from exc

    if preview_path.suffix.lower() not in {".html", ".json", ".txt"}:
        raise AppError(ErrorCode.PARAM_INVALID, "只允许打开 Prompt 预览文件")
    return preview_path


def _toml_to_plain_dict(obj: Any) -> Any:
    """递归转换 tomlkit 文档/Table 为纯 Python 字典，避免 from_dict 触发 tomlkit __setitem__

    实现已收敛到 ``config_paths.to_plain``（新接缝也要用同一份转换，两处各写一份迟早不一致）。
    """
    return to_plain(obj)


def _read_plain_config(config_path: str) -> Any:
    """读取配置文件为纯 Python 结构——写路径的"参考值"（密钥占位从这里还原）。"""
    with open(config_path, "r", encoding="utf-8") as f:
        return _toml_to_plain_dict(tomlkit.load(f))


def _restore_config_secrets(payload: Any, reference: Any, declared: Any = None) -> Any:
    """写路径保真（P2）：还原 ``{path, set}`` 密钥占位 + 保留页面上未展示的字段。

    占位还原不出来时**拒绝落盘**并指明位置——把 ``{path, set}`` 写进 TOML 会让配置文件
    在下一次加载时就炸，比起写坏文件宁可这一次保存失败。

    Args:
        payload: 请求体里的配置数据。
        reference: 配置文件里的当前数据（键对齐用）。
        declared: 秘密声明路径集合；给了就只把"来源确实是秘密"的表当占位
            （否则一张恰好长成 ``{path, set}`` 的普通数据表会被吃掉 —— 对抗审查 F6）。

    Returns:
        还原后的配置数据。

    Raises:
        AppError: 仍有未还原的密钥占位。
    """
    restored = merge_payload_with_reference(payload, reference, declared=declared)
    unresolved_sentinels = find_unresolved_sentinels(restored, declared=declared)
    if unresolved_sentinels:
        raise AppError(
            ErrorCode.PARAM_INVALID,
            "密钥占位未能还原：" + "、".join(unresolved_sentinels) + "；请重新加载配置页后再保存",
            http_status=400,
        )
    return restored


def _coerce_numeric_value(value: Any, target_type: Any) -> Any:
    """根据配置字段类型，把旧 WebUI 可能写入的数字字符串还原为数字。"""
    if target_type is str:
        if isinstance(value, (int, float)):
            return str(value)
        return value

    if target_type is int:
        if isinstance(value, str):
            try:
                parsed_value = float(value.strip())
            except ValueError:
                return value
            if parsed_value.is_integer():
                return int(parsed_value)
        return value

    if target_type is float:
        if isinstance(value, str):
            try:
                return float(value.strip())
            except ValueError:
                return value
        return value

    return value


def _coerce_value_by_annotation(value: Any, annotation: Any) -> Any:
    """递归按 ConfigBase 字段注解修正数据类型，避免保存时把数字写成字符串。"""
    value = _coerce_numeric_value(value, annotation)
    origin = get_origin(annotation)
    args = get_args(annotation)

    if origin in {Union, types.UnionType}:
        for candidate_type in args:
            if candidate_type is type(None):
                continue
            coerced_value = _coerce_value_by_annotation(value, candidate_type)
            if coerced_value != value or type(coerced_value) is not type(value):
                return coerced_value
        return value

    if origin in {list, List} and isinstance(value, list) and args:
        item_type = args[0]
        return [_coerce_value_by_annotation(item, item_type) for item in value]

    if origin in {dict, Dict} and isinstance(value, dict) and len(args) >= 2:
        value_type = args[1]
        return {key: _coerce_value_by_annotation(item, value_type) for key, item in value.items()}

    if isinstance(value, dict) and isinstance(annotation, type) and issubclass(annotation, ConfigBase):
        return _coerce_config_numeric_values(value, annotation)

    return value


def _coerce_config_numeric_values(data: Dict[str, Any], config_type: type[ConfigBase]) -> Dict[str, Any]:
    """按配置类 schema 统一修正所有数字字段类型。"""
    for field_name, field_info in config_type.model_fields.items():
        if field_name in data:
            data[field_name] = _coerce_value_by_annotation(data[field_name], field_info.annotation)
    return data


def _collect_orphaned_model_api_providers(config_data: Dict[str, Any]) -> Dict[str, str]:
    """收集引用了不存在 API Provider 的模型。"""
    providers = config_data.get("api_providers", [])
    provider_names = {provider.get("name") for provider in providers if isinstance(provider, dict)}
    orphaned_models: Dict[str, str] = {}

    for model in config_data.get("models", []):
        if not isinstance(model, dict):
            continue
        model_name = model.get("name")
        api_provider = model.get("api_provider")
        if model_name is None or not api_provider:
            continue
        if api_provider not in provider_names:
            orphaned_models[str(model_name)] = str(api_provider)

    return orphaned_models


def _validate_api_provider_section(section_data: Any) -> None:
    """只校验 api_providers 小节本身，避免历史坏模型引用阻断 Provider 修复。"""
    if not isinstance(section_data, list) or not section_data:
        raise AppError(ErrorCode.PARAM_INVALID, "API 提供商列表不能为空")

    coerced_providers = [
        _coerce_config_numeric_values(copy.deepcopy(provider), APIProvider)
        for provider in section_data
        if isinstance(provider, dict)
    ]
    if len(coerced_providers) != len(section_data):
        raise AppError(ErrorCode.PARAM_INVALID, "API 提供商配置格式无效")

    provider_names: List[str] = []
    try:
        for provider_data in coerced_providers:
            provider = APIProvider.from_dict(AttributeData(), provider_data)
            provider_names.append(provider.name)
    except Exception as exc:
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port
        port = get_error_escalation_port()
        if port is not None:
            port.report(ErrorLevel.WARNING, 'API 提供商配置验证失败', exception=exc)
        logger.warning("操作异常 in config.py", exc_info=True)
        raise AppError(ErrorCode.PARAM_INVALID, f"API 提供商配置验证失败: {exc}") from exc

    if len(provider_names) != len(set(provider_names)):
        raise AppError(ErrorCode.PARAM_INVALID, "API 提供商名称不能重复")


def _ensure_prompt_generator_model_exists(model_name: str) -> None:
    """确认请求模型存在于 model_config.toml 的 models 中。"""

    normalized_model_name = model_name.strip()
    if not any(model.name == normalized_model_name for model in config_manager.get_model_config().models):
        raise AppError(ErrorCode.BIZ_NOT_FOUND, f"未找到模型: {normalized_model_name}", http_status=404)


_PROMPT_GENERATOR_REFERENCE_CONFIG: Dict[str, Any] = {
    "personality": "是一个大二女大学生，现在正在上网和群友聊天。包容且善良",
    "reply_style": (
        "你的风格平淡简短。可以参考贴吧，知乎的回复风格。不浮夸不过分修辞，不使用复杂句。"
        "只回复简短的内容就好。\n"
        "（禁止生成固定化、模板化的怼人、威胁或玩梗句式，尤其避免“你搁这…呢”“你才…/你全家…”"
        "“…你个头”“…了是吧”“再…就禁言/踢/封”“技术群不是让你…”“v我/转我…”“排队…”“子曰…”"
        "等相似结构；需要反驳、提醒或调侃时，改用自然、具体、低攻击性的当场回应。)"
    ),
    "multiple_reply_style": [
        "如果有人对你有敌意，或者很无聊的玩笑，尝试讽刺并且之后不会理他了，十分无语",
        "用1-2个字进行回复",
        "用1-2个符号进行回复",
        "言辭凝練古雅，穿插《論語》經句卻不晦澀，以文言短句為基，輔以淺白語意，持長者溫和風範，全用繁體字表達，具先秦儒者談吐韻致。",
        "你的风格平淡简短。你很慵懒，打算随便回几句应付一下.不浮夸不长篇大论，不要过分修辞和复杂句。",
    ],
    "group_chat_prompt": (
        "你正在qq群里聊天，下面是群里正在聊的内容，其中包含聊天记录和聊天中的图片和表情包。\n"
        "回复尽量简短一些。最好一次对一个话题进行回复，但必须考虑不同群友发言之间的交互，"
        "免得啰嗦或者回复内容太乱。请注意把握聊天内容。\n"
        "不要总是提及自己的身份背景，根据聊天内容自由发挥，但是要日常不浮夸，不要刻意找话题，。\n"
        "不用刻意回复其他人发送的表情包，只要关注表情包表达的含义。你可以适当发送表情包表达情绪。"
        "控制回复的频率，意思是如果有人不喜欢你或者不理你，就不要强行回复，回复前读空气。"
        "不要每个人的消息都回复，优先回复你感兴趣的或者主动提及你的，适当回复其他话题。不要硬找话题。\n"
    ),
    "private_chat_prompts": (
        "你正在聊天，下面是正在聊的内容，其中包含聊天记录和聊天中的图片。\n"
        "回复尽量简短一些。请注意把握聊天内容。\n"
        "请考虑对方的发言频率，想法，思考自己何时回复以及回复内容。\n"
    ),
}


def _build_prompt_generator_reference_config() -> str:
    """构建固定的人设参考快照，不读取运行时配置。"""

    lines = [
        "[personality]",
        f"personality = {_toml_string(_PROMPT_GENERATOR_REFERENCE_CONFIG['personality'])}",
        f"reply_style = {_toml_string(_PROMPT_GENERATOR_REFERENCE_CONFIG['reply_style'])}",
        "multiple_reply_style = [",
    ]
    lines.extend(f"  {_toml_string(item)}," for item in _PROMPT_GENERATOR_REFERENCE_CONFIG["multiple_reply_style"])
    lines.extend(
        [
            "]",
            "",
            "[chat.reply_style]",
            f"group_chat_prompt = {_toml_string(_PROMPT_GENERATOR_REFERENCE_CONFIG['group_chat_prompt'])}",
            f"private_chat_prompts = {_toml_string(_PROMPT_GENERATOR_REFERENCE_CONFIG['private_chat_prompts'])}",
        ]
    )
    return "\n".join(lines)


def _build_prompt_generator_instruction(request: PromptGeneratorRequest) -> str:
    """构建给 LLM 的人设解析提示词。"""

    target_scene_label = {
        "group": "群聊",
        "private": "私聊",
        "both": "群聊和私聊",
    }.get(request.target_scene.strip().lower(), "群聊")
    reference_config = _build_prompt_generator_reference_config()

    return f"""你是 MaiBot/MaiM 的配置人设解析助手。请把用户提供的任意文段、角色卡、人设、说话风格或聊天要求，改写成可以直接放入 bot_config.toml 的麦麦人设配置。

目标场景：{target_scene_label}
主要输出语言：{request.language.strip() or "简体中文"}

默认人设参考：
下面是用于本功能的固定默认参考人设，只用于理解麦麦默认语气、字段职责和通用聊天边界；生成时必须以用户原文为主，不要逐字照抄。如果用户原文缺少场景规则，可以沿用这些设定的精神。
{reference_config}

必须只输出一个 JSON 对象，不要 Markdown，不要代码块，不要额外解释。JSON 结构如下：
{{
  "personality": "对应 [personality].personality。使用第二人称描述稳定人格、身份和长期特质，建议 80-220 字，不要写成小说设定。",
  "reply_style": "对应 [personality].reply_style。描述麦麦说话方式、回复长度、语气、互动习惯和禁用表达。",
  "multiple_reply_style": ["可选备用表达风格，每项一段，最多 5 项"],
  "group_chat_prompt": "对应 [chat.reply_style].group_chat_prompt。只写群聊场景规则，不要重复人格设定。",
  "private_chat_prompts": "对应 [chat.reply_style].private_chat_prompts。只写私聊场景规则，不要重复人格设定。",
  "chat_prompts": [
    {{"platform": "", "item_id": "", "rule_type": "group", "prompt": "如果原文明确提到某个平台或群/私聊专属规则，才生成此项；否则返回空数组"}}
  ],
  "notes": ["需要人工检查或迁移到配置时注意的事项"]
}}

生成要求：
1. 输出要适合聊天型 bot，像真实聊天参与者，不要像客服、旁白、小说角色卡或系统公告。
2. personality 放稳定身份与人格；reply_style 放表达风格和边界；chat prompt 放聊天场景规则。不要三处重复同一段话。
3. 除非特别提到，reply_style 和 multiple_reply_style 最好不要是特别具体的句式，而是描述性的风格要求，方便覆盖不同话题和场景的回复。
4. 默认回复应日常、自然、不过度展开；可以保留原文中的鲜明风格，但要改成可维护的配置文字。
5. 如果信息不足，请根据原文谨慎补全通用聊天规则，并在 notes 中说明需要人工确认，不要反问用户。
6. 字段值必须都是字符串、字符串数组或对象数组，不能为 null。

额外要求：
{request.extra_requirements.strip() or "无"}

用户原文：
{request.source_text.strip()}"""


def _extract_json_object(raw_response: str) -> Dict[str, Any]:
    """从模型输出中解析 JSON 对象。"""

    text = raw_response.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start_index = text.find("{")
        end_index = text.rfind("}")
        if start_index < 0 or end_index <= start_index:
            raise ValueError("模型没有返回可解析的 JSON 对象") from None
        parsed = json.loads(text[start_index : end_index + 1])

    if not isinstance(parsed, dict):
        raise ValueError("模型返回的 JSON 顶层必须是对象")
    return parsed


def _coerce_prompt_generator_string(value: Any) -> str:
    """把模型输出的任意字段安全转为字符串。"""

    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (list, tuple)):
        return "\n".join(_coerce_prompt_generator_string(item) for item in value if item is not None).strip()
    return str(value).strip()


def _coerce_prompt_generator_string_list(value: Any, max_items: int = 8) -> List[str]:
    """把模型输出字段转成字符串列表。"""

    if value is None:
        return []
    if isinstance(value, str):
        candidates = [value]
    elif isinstance(value, list):
        candidates = value
    else:
        candidates = [value]

    items: List[str] = []
    for item in candidates:
        normalized_item = _coerce_prompt_generator_string(item)
        if normalized_item:
            items.append(normalized_item)
    return items[:max_items]


def _normalize_prompt_generator_result(raw_data: Dict[str, Any]) -> PromptGeneratorParsedResult:
    """规范化模型 JSON 输出，避免前端收到不稳定结构。"""

    chat_prompts: List[PromptGeneratorChatPrompt] = []
    raw_chat_prompts = raw_data.get("chat_prompts")
    if isinstance(raw_chat_prompts, list):
        for item in raw_chat_prompts:
            if not isinstance(item, dict):
                continue
            prompt = _coerce_prompt_generator_string(item.get("prompt"))
            platform = _coerce_prompt_generator_string(item.get("platform"))
            item_id = _coerce_prompt_generator_string(item.get("item_id"))
            if not prompt or not platform or not item_id:
                continue
            rule_type = _coerce_prompt_generator_string(item.get("rule_type")) or "group"
            chat_prompts.append(
                PromptGeneratorChatPrompt(
                    platform=platform,
                    item_id=item_id,
                    rule_type=rule_type if rule_type in {"group", "private"} else "group",
                    prompt=prompt,
                )
            )

    return PromptGeneratorParsedResult(
        personality=_coerce_prompt_generator_string(raw_data.get("personality")),
        reply_style=_coerce_prompt_generator_string(raw_data.get("reply_style")),
        multiple_reply_style=_coerce_prompt_generator_string_list(raw_data.get("multiple_reply_style"), max_items=5),
        group_chat_prompt=_coerce_prompt_generator_string(raw_data.get("group_chat_prompt")),
        private_chat_prompts=_coerce_prompt_generator_string(raw_data.get("private_chat_prompts")),
        chat_prompts=chat_prompts[:8],
        notes=_coerce_prompt_generator_string_list(raw_data.get("notes"), max_items=8),
    )


def _toml_string(value: str) -> str:
    """生成可嵌入 TOML basic string 的值。"""

    return json.dumps(value, ensure_ascii=False)


def _build_prompt_generator_toml(result: PromptGeneratorParsedResult) -> str:
    """把结构化结果转换为 bot_config.toml 片段。"""

    lines = [
        "[personality]",
        f"personality = {_toml_string(result.personality)}",
        f"reply_style = {_toml_string(result.reply_style)}",
        "multiple_reply_style = [",
    ]
    lines.extend(f"  {_toml_string(item)}," for item in result.multiple_reply_style)
    lines.extend(
        [
            "]",
            "multiple_probability = 0.15",
            "",
            "[chat]",
        ]
    )

    if result.group_chat_prompt:
        lines.append(f"group_chat_prompt = {_toml_string(result.group_chat_prompt)}")
    if result.private_chat_prompts:
        lines.append(f"private_chat_prompts = {_toml_string(result.private_chat_prompts)}")

    for chat_prompt in result.chat_prompts:
        lines.extend(
            [
                "",
                "[[chat.reply_style.chat_prompts]]",
                f"platform = {_toml_string(chat_prompt.platform)}",
                f"item_id = {_toml_string(chat_prompt.item_id)}",
                f"rule_type = {_toml_string(chat_prompt.rule_type)}",
                f"prompt = {_toml_string(chat_prompt.prompt)}",
            ]
        )

    return "\n".join(lines)


def _prompt_generator_chat_prompt_to_dict(chat_prompt: PromptGeneratorChatPrompt) -> Dict[str, str]:
    """把额外 Prompt 项转换成 bot_config.toml 可保存的普通字典。"""

    return {
        "platform": chat_prompt.platform,
        "item_id": chat_prompt.item_id,
        "rule_type": chat_prompt.rule_type,
        "prompt": chat_prompt.prompt,
    }


def _build_prompt_generator_block_toml(section: str, field: str, value: Any) -> str:
    """生成单个配置块的 TOML 预览。"""

    if field == "chat_prompts" and isinstance(value, list):
        lines: List[str] = []
        for item in value:
            if not isinstance(item, dict):
                continue
            lines.extend(
                [
                    "[[chat.reply_style.chat_prompts]]",
                    f"platform = {_toml_string(_coerce_prompt_generator_string(item.get('platform')))}",
                    f"item_id = {_toml_string(_coerce_prompt_generator_string(item.get('item_id')))}",
                    f"rule_type = {_toml_string(_coerce_prompt_generator_string(item.get('rule_type')) or 'group')}",
                    f"prompt = {_toml_string(_coerce_prompt_generator_string(item.get('prompt')))}",
                    "",
                ]
            )
        return "\n".join(lines).strip()

    lines = [f"[{section}]"]
    if isinstance(value, list):
        lines.append(f"{field} = [")
        lines.extend(f"  {_toml_string(_coerce_prompt_generator_string(item))}," for item in value)
        lines.append("]")
    else:
        lines.append(f"{field} = {_toml_string(_coerce_prompt_generator_string(value))}")
    return "\n".join(lines)


def _build_prompt_generator_config_blocks(result: PromptGeneratorParsedResult) -> List[PromptGeneratorConfigBlock]:
    """把生成结果拆成可单独写入的配置块。"""

    blocks: List[PromptGeneratorConfigBlock] = []

    def add_block(
        block_id: str,
        section: str,
        field: str,
        title: str,
        description: str,
        value: Any,
    ) -> None:
        blocks.append(
            PromptGeneratorConfigBlock(
                id=block_id,
                section=section,
                field=field,
                title=title,
                description=description,
                value=value,
                toml=_build_prompt_generator_block_toml(section, field, value),
            )
        )

    add_block(
        "personality.personality",
        "personality",
        "personality",
        "人格设定",
        "写入 bot_config.toml 的 [personality].personality，会覆盖当前人格设定字段。",
        result.personality,
    )
    add_block(
        "personality.reply_style",
        "personality",
        "reply_style",
        "表达风格",
        "写入 bot_config.toml 的 [personality].reply_style，会覆盖当前表达风格字段。",
        result.reply_style,
    )
    if result.multiple_reply_style:
        add_block(
            "personality.multiple_reply_style",
            "personality",
            "multiple_reply_style",
            "备用表达风格",
            "写入 bot_config.toml 的 [personality].multiple_reply_style，会替换当前备用表达风格列表。",
            result.multiple_reply_style,
        )
    if result.group_chat_prompt:
        add_block(
            "chat.reply_style.group_chat_prompt",
            "chat.reply_style",
            "group_chat_prompt",
            "群聊提示词",
            "写入 bot_config.toml 的 [chat.reply_style].group_chat_prompt，会覆盖当前群聊提示词。",
            result.group_chat_prompt,
        )
    if result.private_chat_prompts:
        add_block(
            "chat.reply_style.private_chat_prompts",
            "chat.reply_style",
            "private_chat_prompts",
            "私聊提示词",
            "写入 bot_config.toml 的 [chat.reply_style].private_chat_prompts，会覆盖当前私聊提示词。",
            result.private_chat_prompts,
        )
    if result.chat_prompts:
        add_block(
            "chat.reply_style.chat_prompts",
            "chat.reply_style",
            "chat_prompts",
            "额外聊天流 Prompt",
            "写入 bot_config.toml 的 [[chat.reply_style.chat_prompts]]，会替换当前额外 Prompt 列表。",
            [_prompt_generator_chat_prompt_to_dict(item) for item in result.chat_prompts],
        )

    return blocks


_PROMPT_GENERATOR_ALLOWED_BLOCK_FIELDS = {
    ("personality", "personality"),
    ("personality", "reply_style"),
    ("personality", "multiple_reply_style"),
    ("chat.reply_style", "group_chat_prompt"),
    ("chat.reply_style", "private_chat_prompts"),
    ("chat.reply_style", "chat_prompts"),
}


def _normalize_prompt_generator_block_value(block: PromptGeneratorConfigBlock) -> Tuple[str, str, Any]:
    """校验并规范化单个配置块，避免人设生成器写入非人设字段。"""

    section = block.section.strip()
    field = block.field.strip()
    if (section, field) not in _PROMPT_GENERATOR_ALLOWED_BLOCK_FIELDS:
        raise AppError(ErrorCode.PARAM_INVALID, f"不允许写入配置字段: {section}.{field}", http_status=400)

    if field in {"personality", "reply_style", "group_chat_prompt", "private_chat_prompts"}:
        value = _coerce_prompt_generator_string(block.value)
        if not value:
            raise AppError(ErrorCode.PARAM_INVALID, f"配置块 {section}.{field} 不能为空", http_status=400)
        return section, field, value

    if field == "multiple_reply_style":
        value = _coerce_prompt_generator_string_list(block.value, max_items=5)
        if not value:
            raise AppError(ErrorCode.PARAM_INVALID, "备用表达风格配置块不能为空")
        return section, field, value

    if field == "chat_prompts":
        if not isinstance(block.value, list):
            raise AppError(ErrorCode.PARAM_INVALID, "额外聊天流 Prompt 必须是数组")

        chat_prompts: List[Dict[str, str]] = []
        for item in block.value:
            if not isinstance(item, dict):
                continue
            platform = _coerce_prompt_generator_string(item.get("platform"))
            item_id = _coerce_prompt_generator_string(item.get("item_id"))
            prompt = _coerce_prompt_generator_string(item.get("prompt"))
            rule_type = _coerce_prompt_generator_string(item.get("rule_type")) or "group"
            if not platform or not item_id or not prompt:
                raise AppError(ErrorCode.PARAM_INVALID, "额外聊天流 Prompt 需要包含 platform、item_id 和 prompt")
            chat_prompts.append(
                {
                    "platform": platform,
                    "item_id": item_id,
                    "rule_type": rule_type if rule_type in {"group", "private"} else "group",
                    "prompt": prompt,
                }
            )
        if not chat_prompts:
            raise AppError(ErrorCode.PARAM_INVALID, "额外聊天流 Prompt 配置块不能为空")
        return section, field, chat_prompts[:8]

    raise AppError(ErrorCode.PARAM_INVALID, f"无法识别配置字段: {section}.{field}", http_status=400)


def _resolve_prompt_generator_section(config_data: Dict[str, Any], section: str) -> Dict[str, Any]:
    """按点分配置节定位可写入的 TOML 表。"""

    current: Any = config_data
    for section_part in section.split("."):
        if not isinstance(current, dict) or section_part not in current:
            raise AppError(ErrorCode.BIZ_NOT_FOUND, f"配置节 '{section}' 不存在", http_status=404)
        current = current[section_part]

    if not isinstance(current, dict):
        raise AppError(ErrorCode.PARAM_INVALID, f"配置节 '{section}' 不是可写对象", http_status=400)
    return current


async def _apply_prompt_generator_config_blocks(
    blocks: List[PromptGeneratorConfigBlock],
) -> PromptGeneratorApplyResponse:
    """把选中的人设生成器配置块写入 bot_config.toml。"""

    if not blocks:
        raise AppError(ErrorCode.PARAM_INVALID, "请选择要注入的配置块")

    config_path = os.path.join(CONFIG_DIR, "bot_config.toml")
    if not os.path.exists(config_path):
        raise AppError(ErrorCode.BIZ_NOT_FOUND, "配置文件不存在")

    with open(config_path, "r", encoding="utf-8") as f:
        config_data = tomlkit.load(f)

    section_updates: Dict[str, Dict[str, Any]] = {}
    for block in blocks:
        section, field, value = _normalize_prompt_generator_block_value(block)
        section_updates.setdefault(section, {})[field] = value

    for section, section_data in section_updates.items():
        _update_toml_doc(_resolve_prompt_generator_section(config_data, section), section_data)

    try:
        plain_config_data = _coerce_config_numeric_values(_toml_to_plain_dict(config_data), Config)
        Config.from_dict(AttributeData(), copy.deepcopy(plain_config_data))
    except AppError:
        raise
    except Exception as e:
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port
        port = get_error_escalation_port()
        if port is not None:
            port.report(ErrorLevel.WARNING, '配置数据验证失败', exception=e)
        logger.warning(f"配置数据验证失败: {e}")
        raise AppError(ErrorCode.PARAM_INVALID, f"配置数据验证失败: {str(e)}") from e

    save_toml_with_format(plain_config_data, config_path)
    hot_reload = await _reload_config_or_report("prompt-generator/apply")
    applied_sections = sorted(section_updates)
    logger.info(f"人设生成器已注入 {len(blocks)} 个配置块: {', '.join(applied_sections)}")
    message = f"已注入 {len(blocks)} 个配置块"
    if hot_reload == HOT_RELOAD_REFUSED_FROZEN:
        message += "（已落盘；热重载被拒：配置已冻结，实际生效依赖重启或文件监听）"
    return PromptGeneratorApplyResponse(
        message=message,
        applied_blocks=len(blocks),
        sections=applied_sections,
    )


# ===== 架构获取接口 =====


@router.get("/prompts", response_model=ApiResponse[PromptCatalogResponse])
async def list_prompt_files():
    """列出 prompts 目录下的语言和 Prompt 文件。"""

    try:
        if not PROMPTS_DIR.exists():
            return ApiResponse(data=PromptCatalogResponse(languages=[], files={}))

        languages: List[str] = []
        files: Dict[str, List[PromptFileInfo]] = {}
        for language_dir in sorted(PROMPTS_DIR.iterdir(), key=lambda item: item.name):
            if not language_dir.is_dir():
                continue

            language = language_dir.name
            prompt_template_infos = list_prompt_templates(locale=language, prompts_root=PROMPTS_DIR)
            prompt_files: List[PromptFileInfo] = []
            for prompt_file in sorted(language_dir.glob("*.prompt"), key=lambda item: item.name):
                custom_prompt_file = _safe_custom_prompt_path(language, prompt_file.name)
                effective_prompt_file = custom_prompt_file if custom_prompt_file.exists() else prompt_file
                stat = effective_prompt_file.stat()
                template_info = prompt_template_infos.get(prompt_file.stem)
                metadata = template_info.metadata if template_info and template_info.path == prompt_file else None
                versions = _list_prompt_versions(language, prompt_file.name)
                prompt_files.append(
                    PromptFileInfo(
                        name=prompt_file.name,
                        size=stat.st_size,
                        modified_at=stat.st_mtime,
                        display_name=metadata.display_name if metadata else "",
                        advanced=metadata.advanced if metadata else False,
                        description=metadata.description if metadata else "",
                        customized=custom_prompt_file.exists(),
                        custom_version_count=len(versions),
                    )
                )

            languages.append(language)
            files[language] = prompt_files

        return ApiResponse(data=PromptCatalogResponse(languages=languages, files=files))
    except AppError:
        raise
    except Exception as e:
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port
        port = get_error_escalation_port()
        if port is not None:
            port.report(ErrorLevel.ERROR, '列出 Prompt 文件失败', exception=e)
        logger.error(f"列出 Prompt 文件失败: {e}", exc_info=True)
        raise AppError(ErrorCode.SYS_INTERNAL_ERROR, f"列出 Prompt 文件失败: {str(e)}") from e


@router.get("/prompts/{language}/{filename}", response_model=ApiResponse[PromptFileResponse])
async def get_prompt_file(language: str, filename: str):
    """读取指定语言下的 Prompt 文件内容。"""

    prompt_path = _safe_prompt_path(language, filename)
    custom_prompt_path = _safe_custom_prompt_path(language, filename)
    if not prompt_path.exists() or not prompt_path.is_file():
        raise AppError(ErrorCode.BIZ_NOT_FOUND, "Prompt 文件不存在")

    try:
        effective_prompt_path = custom_prompt_path if custom_prompt_path.exists() else prompt_path
        content = effective_prompt_path.read_text(encoding="utf-8")
        default_content = prompt_path.read_text(encoding="utf-8")
        validation = (
            _build_prompt_validation(default_content, content) if custom_prompt_path.exists() else PromptValidationResult()
        )
        return ApiResponse(data=PromptFileResponse(
            language=language,
            filename=filename,
            content=content,
            customized=custom_prompt_path.exists(),
            active_version_id=_get_active_prompt_version_id(language, filename),
            versions=_list_prompt_versions(language, filename),
            validation=validation,
        ))
    except AppError:
        raise
    except Exception as e:
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port
        port = get_error_escalation_port()
        if port is not None:
            port.report(ErrorLevel.ERROR, '读取 Prompt 文件失败', exception=e)
        logger.error(f"读取 Prompt 文件失败: {prompt_path} {e}", exc_info=True)
        raise AppError(ErrorCode.SYS_INTERNAL_ERROR, f"读取 Prompt 文件失败: {str(e)}") from e


@router.get("/prompts/{language}/{filename}/default", response_model=ApiResponse[PromptFileResponse])
async def get_default_prompt_file(language: str, filename: str):
    """只读获取内置 Prompt 模板内容，不读取或修改用户自定义覆盖。"""

    prompt_path = _safe_prompt_path(language, filename)
    if not prompt_path.exists() or not prompt_path.is_file():
        raise AppError(ErrorCode.BIZ_NOT_FOUND, "Prompt 文件不存在")

    try:
        content = prompt_path.read_text(encoding="utf-8")
        return ApiResponse(data=PromptFileResponse(
            language=language,
            filename=filename,
            content=content,
            customized=False,
            active_version_id=_get_active_prompt_version_id(language, filename),
            versions=_list_prompt_versions(language, filename),
        ))
    except AppError:
        raise
    except Exception as e:
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port
        port = get_error_escalation_port()
        if port is not None:
            port.report(ErrorLevel.ERROR, '读取默认 Prompt 文件失败', exception=e)
        logger.error(f"读取默认 Prompt 文件失败: {prompt_path} {e}", exc_info=True)
        raise AppError(ErrorCode.SYS_INTERNAL_ERROR, f"读取默认 Prompt 文件失败: {str(e)}") from e


@router.get("/prompts/{language}/{filename}/versions", response_model=ApiResponse[PromptVersionListResponse])
async def list_prompt_versions(language: str, filename: str):
    """列出指定 Prompt 的自定义版本。"""

    prompt_path = _safe_prompt_path(language, filename)
    if not prompt_path.exists() or not prompt_path.is_file():
        raise AppError(ErrorCode.BIZ_NOT_FOUND, "Prompt 文件不存在")

    return ApiResponse(data=PromptVersionListResponse(
        language=language,
        filename=filename,
        active_version_id=_get_active_prompt_version_id(language, filename),
        versions=_list_prompt_versions(language, filename),
    ))


@router.get("/prompts/{language}/{filename}/versions/{version_id}", response_model=ApiResponse[PromptVersionFileResponse])
async def get_prompt_version_file(language: str, filename: str, version_id: str):
    """读取指定 Prompt 自定义版本内容。"""

    prompt_path = _safe_prompt_path(language, filename)
    custom_prompt_path = _safe_custom_prompt_path(language, filename)
    if not prompt_path.exists() or not prompt_path.is_file():
        raise AppError(ErrorCode.BIZ_NOT_FOUND, "Prompt 文件不存在")

    normalized_version_id = _safe_prompt_version_id(version_id)
    if normalized_version_id == _LEGACY_CUSTOM_PROMPT_VERSION_ID:
        if not custom_prompt_path.exists():
            raise AppError(ErrorCode.BIZ_NOT_FOUND, "Prompt 自定义版本不存在")
        content = custom_prompt_path.read_text(encoding="utf-8")
    else:
        version_path = _prompt_version_file_path(language, filename, normalized_version_id)
        if not version_path.exists() or not version_path.is_file():
            raise AppError(ErrorCode.BIZ_NOT_FOUND, "Prompt 自定义版本不存在")
        content = version_path.read_text(encoding="utf-8")

    validation = _build_prompt_validation(prompt_path.read_text(encoding="utf-8"), content)
    return ApiResponse(data=PromptVersionFileResponse(
        language=language,
        filename=filename,
        version_id=normalized_version_id,
        content=content,
        customized=True,
        active_version_id=_get_active_prompt_version_id(language, filename),
        versions=_list_prompt_versions(language, filename),
        validation=validation,
    ))


@router.post("/prompts/{language}/{filename}/versions/{version_id}/activate", response_model=ApiResponse[PromptFileResponse])
async def activate_prompt_version(language: str, filename: str, version_id: str):
    """启用指定 Prompt 自定义版本。"""

    prompt_path = _safe_prompt_path(language, filename)
    if not prompt_path.exists() or not prompt_path.is_file():
        raise AppError(ErrorCode.BIZ_NOT_FOUND, "Prompt 文件不存在")

    normalized_version_id = _safe_prompt_version_id(version_id)
    if normalized_version_id == _LEGACY_CUSTOM_PROMPT_VERSION_ID:
        custom_prompt_path = _safe_custom_prompt_path(language, filename)
        if not custom_prompt_path.exists():
            raise AppError(ErrorCode.BIZ_NOT_FOUND, "Prompt 自定义版本不存在")
        content = custom_prompt_path.read_text(encoding="utf-8")
    else:
        version_path = _prompt_version_file_path(language, filename, normalized_version_id)
        if not version_path.exists() or not version_path.is_file():
            raise AppError(ErrorCode.BIZ_NOT_FOUND, "Prompt 自定义版本不存在")
        content = version_path.read_text(encoding="utf-8")

    validation = _ensure_prompt_parameters_match(prompt_path, content)
    custom_prompt_path = _safe_custom_prompt_path(language, filename)
    custom_prompt_path.parent.mkdir(parents=True, exist_ok=True)
    custom_prompt_path.write_text(content, encoding="utf-8", newline="\n")
    if normalized_version_id != _LEGACY_CUSTOM_PROMPT_VERSION_ID:
        _set_active_prompt_version(language, filename, normalized_version_id)
    clear_prompt_cache()
    return ApiResponse(data=PromptFileResponse(
        language=language,
        filename=filename,
        content=content,
        customized=True,
        active_version_id=_get_active_prompt_version_id(language, filename),
        versions=_list_prompt_versions(language, filename),
        validation=validation,
    ))


@router.put("/prompts/{language}/{filename}", response_model=ApiResponse[PromptFileResponse])
async def update_prompt_file(language: str, filename: str, request: PromptUpdateRequest):
    """更新指定语言下的 Prompt 文件内容。"""

    prompt_path = _safe_prompt_path(language, filename)
    custom_prompt_path = _safe_custom_prompt_path(language, filename)
    if not prompt_path.parent.exists() or not prompt_path.parent.is_dir():
        raise AppError(ErrorCode.BIZ_NOT_FOUND, "Prompt 语言目录不存在")
    if not prompt_path.exists() or not prompt_path.is_file():
        raise AppError(ErrorCode.BIZ_NOT_FOUND, "Prompt 文件不存在")

    try:
        validation = _ensure_prompt_parameters_match(prompt_path, request.content)
        custom_prompt_path.parent.mkdir(parents=True, exist_ok=True)
        active_version_id = _save_prompt_version(
            language=language,
            filename=filename,
            content=request.content,
            version_id=request.version_id,
            label=request.label,
            create_version=request.create_version,
        )
        custom_prompt_path.write_text(request.content, encoding="utf-8", newline="\n")
        clear_prompt_cache()
        return ApiResponse(data=PromptFileResponse(
            language=language,
            filename=filename,
            content=request.content,
            customized=True,
            active_version_id=active_version_id,
            versions=_list_prompt_versions(language, filename),
            validation=validation,
        ))
    except AppError:
        raise
    except Exception as e:
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port
        port = get_error_escalation_port()
        if port is not None:
            port.report(ErrorLevel.ERROR, '保存 Prompt 文件失败', exception=e)
        logger.error(f"保存 Prompt 文件失败: {prompt_path} {e}", exc_info=True)
        raise AppError(ErrorCode.SYS_INTERNAL_ERROR, f"保存 Prompt 文件失败: {str(e)}") from e


@router.delete("/prompts/{language}/{filename}", response_model=ApiResponse[PromptFileResponse])
async def reset_prompt_file(language: str, filename: str):
    """删除用户自定义覆盖，恢复使用内置 Prompt 模板。"""

    prompt_path = _safe_prompt_path(language, filename)
    custom_prompt_path = _safe_custom_prompt_path(language, filename)
    if not prompt_path.exists() or not prompt_path.is_file():
        raise AppError(ErrorCode.BIZ_NOT_FOUND, "Prompt 文件不存在")

    try:
        if custom_prompt_path.exists():
            custom_prompt_path.unlink()
            _set_active_prompt_version(language, filename, None)
            clear_prompt_cache()
        content = prompt_path.read_text(encoding="utf-8")
        return ApiResponse(data=PromptFileResponse(
            language=language,
            filename=filename,
            content=content,
            customized=False,
            active_version_id=None,
            versions=_list_prompt_versions(language, filename),
        ))
    except AppError:
        raise
    except Exception as e:
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port
        port = get_error_escalation_port()
        if port is not None:
            port.report(ErrorLevel.ERROR, '恢复 Prompt 默认模板失败', exception=e)
        logger.error(f"恢复 Prompt 默认模板失败: {prompt_path} {e}", exc_info=True)
        raise AppError(ErrorCode.SYS_INTERNAL_ERROR, f"恢复 Prompt 默认模板失败: {str(e)}") from e


@router.get("/maisaka-prompt-preview", response_class=FileResponse)
async def get_maisaka_prompt_preview(path: str = Query(..., description="logs/maisaka_prompt 下的相对预览路径")):
    """打开 MaiSaka 监控中生成的 Prompt 预览。"""

    preview_path = _safe_maisaka_prompt_preview_path(path)
    if not preview_path.exists() or not preview_path.is_file():
        raise AppError(ErrorCode.BIZ_NOT_FOUND, "Prompt 预览文件不存在")
    media_type = {
        ".html": "text/html",
        ".json": "application/json",
        ".txt": "text/plain",
    }.get(preview_path.suffix.lower(), "application/octet-stream")
    return ApiResponse(data=FileResponse(preview_path, media_type=media_type))


@router.post("/prompt-generator/generate", response_model=ApiResponse[PromptGeneratorResponse])
async def generate_prompt_persona(request: PromptGeneratorRequest):
    """使用已定义模型把任意文段解析为 MaiBot 人设配置片段。"""

    model_name = request.model_name.strip()
    _ensure_prompt_generator_model_exists(model_name)

    prompt = _build_prompt_generator_instruction(request)
    try:
        orchestrator = LLMOrchestrator(
            capabilities=["text_generation"],
            request_type="webui_prompt_generator",
        )
        llm_result = await orchestrator.generate_response_async(
            prompt=prompt,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            model_name=model_name,
        )
        raw_response = llm_result.response.strip()
        parsed_data = _extract_json_object(raw_response)
        parsed_result = _normalize_prompt_generator_result(parsed_data)
        if not parsed_result.personality or not parsed_result.reply_style:
            raise ValueError("模型返回缺少 personality 或 reply_style 字段")

        return ApiResponse(data=PromptGeneratorResponse(
            model_name=llm_result.model_name or model_name,
            result=parsed_result,
            config_blocks=_build_prompt_generator_config_blocks(parsed_result),
            toml_snippet=_build_prompt_generator_toml(parsed_result),
            raw_response=raw_response,
            reasoning=llm_result.reasoning,
            prompt_tokens=llm_result.prompt_tokens,
            completion_tokens=llm_result.completion_tokens,
            total_tokens=llm_result.total_tokens,
        ))
    except AppError:
        raise
    except Exception as e:
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port
        port = get_error_escalation_port()
        if port is not None:
            port.report(ErrorLevel.ERROR, 'Prompt 生成失败', exception=e)
        logger.error(f"Prompt 生成失败: {e}", exc_info=True)
        raise AppError(ErrorCode.SYS_INTERNAL_ERROR, f"Prompt 生成失败: {str(e)}") from e


@router.post("/prompt-generator/apply", response_model=ApiResponse[PromptGeneratorApplyResponse])
async def apply_prompt_generator_blocks(request: PromptGeneratorApplyRequest):
    """把人设生成器产出的配置块写入 bot_config.toml。"""

    try:
        # ⚠️ 必须包信封：声明是 ``ApiResponse[PromptGeneratorApplyResponse]``，
        # 而本文件其余 14 处同形端点也都是 ``return ApiResponse(data=...)``；
        # 前端 ``client.ts:191`` 检测到 ``code`` 字段会自动解包，所以包了才对得上两端。
        # 原先直接返回裸模型 ⇒ 响应校验缺 ``data`` ⇒ **每次成功都 500**（存量缺陷，
        # 收尾令要求这条路径也验"无 500"时才暴露出来；同期无任何用例覆盖它）。
        result = await _apply_prompt_generator_config_blocks(request.blocks)
        return ApiResponse(data=result)
    except AppError:
        raise
    except Exception as e:
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port
        port = get_error_escalation_port()
        if port is not None:
            port.report(ErrorLevel.ERROR, 'Prompt 配置块注入失败', exception=e)
        logger.error(f"Prompt 配置块注入失败: {e}", exc_info=True)
        raise AppError(ErrorCode.SYS_INTERNAL_ERROR, f"Prompt 配置块注入失败: {str(e)}") from e


@router.get("/schema/bot")
async def get_bot_config_schema():
    """获取麦麦主程序配置架构"""
    try:
        # Config 类包含所有子配置
        schema = _get_cached_schema("bot", Config)
        return {"success": True, "schema": schema}
    except AppError:
        raise
    except Exception as e:
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port
        port = get_error_escalation_port()
        if port is not None:
            port.report(ErrorLevel.ERROR, '获取配置架构失败', exception=e)
        logger.error(f"获取配置架构失败: {e}")
        raise AppError(ErrorCode.SYS_INTERNAL_ERROR, f"获取配置架构失败: {str(e)}") from e


@compat_router.get("/schema")
async def get_compat_bot_config_schema():
    """兼容旧版 /api/config/schema，返回主程序配置架构。"""
    return await get_bot_config_schema()


@compat_router.get("/schema/bot")
async def get_compat_bot_config_schema_alias():
    """兼容旧版 /api/config/schema/bot。"""
    return await get_bot_config_schema()


@router.get("/schema/model")
async def get_model_config_schema():
    """获取模型配置架构（包含提供商和模型任务配置）"""
    try:
        schema = _get_cached_schema("model", ModelConfig)
        return {"success": True, "schema": schema}
    except AppError:
        raise
    except Exception as e:
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port
        port = get_error_escalation_port()
        if port is not None:
            port.report(ErrorLevel.ERROR, '获取模型配置架构失败', exception=e)
        logger.error(f"获取模型配置架构失败: {e}")
        raise AppError(ErrorCode.SYS_INTERNAL_ERROR, f"获取模型配置架构失败: {str(e)}") from e


# ===== 子配置架构获取接口 =====


@router.get("/schema/section/{section_name}")
async def get_config_section_schema(section_name: str):
    """
    获取指定配置节的架构

    支持的section_name:
    - bot: BotConfig
    - personality: PersonalityConfig
    - chat: ChatConfig
    - visual: VisualConfig
    - message_receive: MessageReceiveConfig
    - emoji: EmojiConfig
    - expression: ExpressionConfig
    - jargon: JargonConfig
    - keyword_reaction: KeywordReactionConfig
    - chinese_typo: ChineseTypoConfig
    - response_post_process: ResponsePostProcessConfig
    - response_splitter: ResponseSplitterConfig
    - log: LogConfig
    - maim_message: MaimMessageConfig
    - webui: WebUIConfig

    - mcp: MCPConfig
    - plugin: PluginConfig
    - plugin_runtime: PluginRuntimeConfig
    - a_memorix: AMemorixConfig
    - debug: DebugConfig
    - voice: VoiceConfig
    - model_task_config: ModelTaskConfig
    - api_provider: APIProvider
    - model_info: ModelInfo
    """
    section_map = {
        "bot": BotConfig,
        "personality": PersonalityConfig,
        "chat": ChatConfig,
        "visual": VisualConfig,
        "message_receive": MessageReceiveConfig,
        "emoji": EmojiConfig,
        "expression": ExpressionConfig,
        "jargon": JargonConfig,
        "keyword_reaction": KeywordReactionConfig,
        "chinese_typo": ChineseTypoConfig,
        "response_post_process": ResponsePostProcessConfig,
        "response_splitter": ResponseSplitterConfig,
        "log": LogConfig,
        "maim_message": MaimMessageConfig,
        "webui": WebUIConfig,

        "mcp": MCPConfig,
        "plugin": PluginConfig,
        "plugin_runtime": PluginRuntimeConfig,
        "a_memorix": AMemorixConfig,
        "debug": DebugConfig,
        "voice": VoiceConfig,
        "model_task_config": ModelTaskConfig,
        "api_provider": APIProvider,
        "model_info": ModelInfo,
    }

    if section_name not in section_map:
        raise AppError(ErrorCode.BIZ_NOT_FOUND, f"配置节 '{section_name}' 不存在", http_status=404)

    try:
        config_class = section_map[section_name]
        schema = _get_cached_schema(f"section:{section_name}", config_class, include_nested=False)
        return {"success": True, "schema": schema}
    except AppError:
        raise
    except Exception as e:
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port
        port = get_error_escalation_port()
        if port is not None:
            port.report(ErrorLevel.ERROR, '获取配置节架构失败', exception=e)
        logger.error(f"获取配置节架构失败: {e}")
        raise AppError(ErrorCode.SYS_INTERNAL_ERROR, f"获取配置节架构失败: {str(e)}") from e


# ===== 配置读取接口 =====


@router.get("/bot")
async def get_bot_config():
    """获取麦麦主程序配置（秘密叶脱敏：只回三态标记，真值不出浏览器）

    脱敏判据来自 **schema 声明**（``maim_message.auth_token`` 等字段声明处标了
    ``x-secret``），不再是"名字像密钥就脱"的黑名单猜法。
    """
    try:
        config_path = os.path.join(CONFIG_DIR, "bot_config.toml")
        if not os.path.exists(config_path):
            raise AppError(ErrorCode.BIZ_NOT_FOUND, "配置文件不存在")

        config_data = _read_plain_config(config_path)

        return {
            "success": True,
            "config": redact_config_secrets(
                config_data,
                namespace=config_store.NAMESPACE_BOT,
                model_cls=Config,
            ),
        }
    except AppError:
        raise
    except Exception as e:
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port
        port = get_error_escalation_port()
        if port is not None:
            port.report(ErrorLevel.ERROR, '读取配置文件失败', exception=e)
        logger.error(f"读取配置文件失败: {e}")
        raise AppError(ErrorCode.SYS_INTERNAL_ERROR, f"读取配置文件失败: {str(e)}") from e


@router.get("/model")
async def get_model_config():
    """获取模型配置（包含提供商和模型任务配置）

    秘密叶脱敏：``api_key`` 等替换为三态标记——``set`` 只说明"配没配"，
    真值（明文或 ``${VAR}`` 引用文本）都不出浏览器。**引用也是秘密**：``${VAR}``
    只是"值放在哪"，不是"要不要脱敏"。
    """
    try:
        config_path = os.path.join(CONFIG_DIR, "model_config.toml")
        if not os.path.exists(config_path):
            raise AppError(ErrorCode.BIZ_NOT_FOUND, "配置文件不存在")

        config_data = _read_plain_config(config_path)

        return {
            "success": True,
            "config": redact_config_secrets(
                config_data,
                namespace=config_store.NAMESPACE_MODEL,
                model_cls=ModelConfig,
            ),
        }
    except AppError:
        raise
    except Exception as e:
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port
        port = get_error_escalation_port()
        if port is not None:
            port.report(ErrorLevel.ERROR, '读取配置文件失败', exception=e)
        logger.error(f"读取配置文件失败: {e}")
        raise AppError(ErrorCode.SYS_INTERNAL_ERROR, f"读取配置文件失败: {str(e)}") from e


# ===== 配置更新接口 =====


@router.post("/bot")
async def update_bot_config(config_data: ConfigBody):
    """更新麦麦主程序配置"""
    try:
        config_path = os.path.join(CONFIG_DIR, "bot_config.toml")
        # 密钥占位还原 + 页面上未展示的字段保真（P2 写路径）
        reference_config = _read_plain_config(config_path) if os.path.exists(config_path) else {}
        config_data = _restore_config_secrets(
            config_data, reference_config, config_store.secret_field_paths(config_store.NAMESPACE_BOT)
        )
        config_data = _coerce_config_numeric_values(config_data, Config)

        # 验证配置数据
        try:
            Config.from_dict(AttributeData(), copy.deepcopy(config_data))
        except AppError:
            raise
        except Exception as e:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.WARNING, '配置数据验证失败', exception=e)
            logger.warning(f"配置数据验证失败: {e}")
            raise AppError(ErrorCode.PARAM_INVALID, f"配置数据验证失败: {str(e)}") from e

        # 保存配置文件（自动保留注释和格式）
        config_path = os.path.join(CONFIG_DIR, "bot_config.toml")
        save_toml_with_format(config_data, config_path)
        hot_reload = await _reload_config_or_report("POST /config/bot")

        # 判断是否需要重启
        restart_sections = [s for s in config_data if s in _RESTART_REQUIRED_SECTIONS]
        logger.info("麦麦主程序配置已更新")
        return ApiResponse(
            data=ConfigSaveResponse(
                needs_restart=_needs_restart_flag(restart_sections, hot_reload),
                restart_required_sections=restart_sections,
                hot_reload=hot_reload,
            )
        )
    except AppError:
        raise
    except Exception as e:
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port
        port = get_error_escalation_port()
        if port is not None:
            port.report(ErrorLevel.ERROR, '保存配置文件失败', exception=e)
        logger.error(f"保存配置文件失败: {e}")
        raise AppError(ErrorCode.SYS_INTERNAL_ERROR, f"保存配置文件失败: {str(e)}") from e


@router.post("/model")
async def update_model_config(config_data: ConfigBody):
    """更新模型配置"""
    try:
        config_path = os.path.join(CONFIG_DIR, "model_config.toml")
        # 密钥占位还原 + 页面上未展示的字段保真（P2 写路径）
        reference_config = _read_plain_config(config_path) if os.path.exists(config_path) else {}
        config_data = _restore_config_secrets(
            config_data, reference_config, config_store.secret_field_paths(config_store.NAMESPACE_MODEL)
        )
        config_data = _coerce_config_numeric_values(config_data, ModelConfig)

        # 验证配置数据
        try:
            ModelConfig.from_dict(AttributeData(), copy.deepcopy(config_data))
        except AppError:
            raise
        except Exception as e:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.WARNING, '配置数据验证失败', exception=e)
            logger.warning(f"配置数据验证失败: {e}")
            raise AppError(ErrorCode.PARAM_INVALID, f"配置数据验证失败: {str(e)}") from e

        # 保存配置文件（自动保留注释和格式）
        save_toml_with_format(config_data, config_path)
        hot_reload = await _reload_config_or_report("POST /config/model")

        logger.info("模型配置已更新")
        return ApiResponse(
            data=ConfigSaveResponse(
                message="模型配置已保存",
                needs_restart=True,
                restart_required_sections=["model"],
                hot_reload=hot_reload,
            )
        )
    except AppError:
        raise
    except Exception as e:
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port
        port = get_error_escalation_port()
        if port is not None:
            port.report(ErrorLevel.ERROR, '保存配置文件失败', exception=e)
        logger.error(f"保存配置文件失败: {e}")
        raise AppError(ErrorCode.SYS_INTERNAL_ERROR, f"保存配置文件失败: {str(e)}") from e


# ===== 配置节更新接口 =====


@router.post("/bot/section/{section_name}")
async def update_bot_config_section(section_name: str, section_data: SectionBody):
    """更新麦麦主程序配置的指定节（保留注释和格式）"""
    try:
        # 读取现有配置
        config_path = os.path.join(CONFIG_DIR, "bot_config.toml")
        if not os.path.exists(config_path):
            raise AppError(ErrorCode.BIZ_NOT_FOUND, "配置文件不存在")

        with open(config_path, "r", encoding="utf-8") as f:
            config_data = tomlkit.load(f)

        # 更新指定节
        if section_name not in config_data:
            raise AppError(ErrorCode.BIZ_NOT_FOUND, f"配置节 '{section_name}' 不存在", http_status=404)

        # 密钥占位还原 + 页面上未展示的字段保真（P2 写路径；列表节不能整段 replace）
        section_data = _restore_config_secrets(
            section_data,
            _toml_to_plain_dict(config_data[section_name]),
            config_store.secret_field_paths(config_store.NAMESPACE_BOT),
        )

        # 使用递归合并保留注释（对于字典类型）
        # 对于数组类型（如 platforms, aliases），直接替换
        if isinstance(section_data, list):
            # 列表直接替换
            config_data[section_name] = section_data
        elif isinstance(section_data, dict) and isinstance(config_data[section_name], dict):
            # 字典递归合并
            _update_toml_doc(config_data[section_name], section_data)
        else:
            # 其他类型直接替换
            config_data[section_name] = section_data

        # 验证完整配置
        try:
            plain_config_data = _coerce_config_numeric_values(_toml_to_plain_dict(config_data), Config)
            Config.from_dict(AttributeData(), copy.deepcopy(plain_config_data))
        except AppError:
            raise
        except Exception as e:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.WARNING, '配置数据验证失败', exception=e)
            logger.warning(f"配置数据验证失败: {e}")
            raise AppError(ErrorCode.PARAM_INVALID, f"配置数据验证失败: {str(e)}") from e

        config_data = plain_config_data

        # 保存配置（格式化数组为多行，保留注释）
        save_toml_with_format(config_data, config_path)
        hot_reload = await _reload_config_or_report(f"POST /config/bot/section/{section_name}")

        logger.info(f"配置节 '{section_name}' 已更新（保留注释）")
        needs_restart = section_name in _RESTART_REQUIRED_SECTIONS
        return ApiResponse(
            data=ConfigSaveResponse(
                message=f"配置节 '{section_name}' 已保存",
                needs_restart=_needs_restart_flag(
                    [section_name] if needs_restart else [], hot_reload
                ),
                restart_required_sections=[section_name] if needs_restart else [],
                hot_reload=hot_reload,
            )
        )
    except AppError:
        raise
    except Exception as e:
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port
        port = get_error_escalation_port()
        if port is not None:
            port.report(ErrorLevel.ERROR, '更新配置节失败', exception=e)
        logger.error(f"更新配置节失败: {e}")
        raise AppError(ErrorCode.SYS_INTERNAL_ERROR, f"更新配置节失败: {str(e)}") from e


@router.post("/model/section/{section_name}")
async def update_model_config_section(section_name: str, section_data: SectionBody):
    """更新模型配置的指定节（保留注释和格式）"""
    try:
        # 读取现有配置
        config_path = os.path.join(CONFIG_DIR, "model_config.toml")
        if not os.path.exists(config_path):
            raise AppError(ErrorCode.BIZ_NOT_FOUND, "配置文件不存在")

        with open(config_path, "r", encoding="utf-8") as f:
            config_data = tomlkit.load(f)
        original_plain_config_data = _coerce_config_numeric_values(_toml_to_plain_dict(config_data), ModelConfig)

        # 更新指定节
        if section_name not in config_data:
            raise AppError(ErrorCode.BIZ_NOT_FOUND, f"配置节 '{section_name}' 不存在", http_status=404)

        # 密钥占位还原 + 页面上未展示的字段保真（P2 写路径；`[[api_providers]]` 整段 replace
        # 会把用户没在页面上看到、也没提交的字段吃掉）
        section_data = _restore_config_secrets(
            section_data,
            _toml_to_plain_dict(config_data[section_name]),
            config_store.secret_field_paths(config_store.NAMESPACE_MODEL),
        )

        # 使用递归合并保留注释（对于字典类型）
        # 对于数组表（如 [[models]], [[api_providers]]），直接替换
        if isinstance(section_data, list):
            # 列表直接替换
            config_data[section_name] = section_data
        elif isinstance(section_data, dict) and isinstance(config_data[section_name], dict):
            # 字典递归合并
            _update_toml_doc(config_data[section_name], section_data)
        else:
            # 其他类型直接替换
            config_data[section_name] = section_data

        # 验证完整配置
        try:
            plain_config_data = _coerce_config_numeric_values(_toml_to_plain_dict(config_data), ModelConfig)
            ModelConfig.from_dict(AttributeData(), copy.deepcopy(plain_config_data))
        except AppError:
            raise
        except Exception as e:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.ERROR, '配置数据验证失败，详细错误', exception=e)
            logger.error(f"配置数据验证失败，详细错误: {str(e)}")
            allow_orphaned_provider_save = False
            # 特殊处理：如果是更新 api_providers，检查是否有模型引用了已删除的provider
            if section_name == "api_providers" and "api_provider" in str(e):
                _validate_api_provider_section(section_data)
                original_orphaned = _collect_orphaned_model_api_providers(original_plain_config_data)
                orphaned_models = _collect_orphaned_model_api_providers(plain_config_data)
                introduced_orphaned_models = [
                    model_name
                    for model_name, api_provider in orphaned_models.items()
                    if original_orphaned.get(model_name) != api_provider
                ]

                if orphaned_models and not introduced_orphaned_models:
                    logger.warning(
                        "api_providers 已保存，但模型配置中仍存在历史无效引用: "
                        + ", ".join(
                            f"{model_name} -> {api_provider}"
                            for model_name, api_provider in orphaned_models.items()
                        )
                    )
                    allow_orphaned_provider_save = True
                elif introduced_orphaned_models:
                    error_msg = (
                        "以下模型引用了已删除的提供商: "
                        f"{', '.join(introduced_orphaned_models)}。"
                        "请先在模型管理页面删除这些模型，或重新分配它们的提供商。"
                    )
                    raise AppError(ErrorCode.PARAM_INVALID, error_msg, http_status=400) from e
                else:
                    raise AppError(ErrorCode.PARAM_INVALID, f"配置数据验证失败: {str(e)}") from e
            if not allow_orphaned_provider_save:
                raise AppError(ErrorCode.PARAM_INVALID, f"配置数据验证失败: {str(e)}") from e

        config_data = plain_config_data

        # 保存配置（格式化数组为多行，保留注释）
        save_toml_with_format(config_data, config_path)
        hot_reload = await _reload_config_or_report(f"POST /config/model/section/{section_name}")

        logger.info(f"配置节 '{section_name}' 已更新（保留注释）")
        message = f"配置节 '{section_name}' 已保存"
        if hot_reload == HOT_RELOAD_REFUSED_FROZEN:
            message += "（已落盘；热重载被拒：配置已冻结，实际生效依赖重启或文件监听）"
        return {"success": True, "message": message, "hot_reload": hot_reload}
    except AppError:
        raise
    except Exception as e:
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port
        port = get_error_escalation_port()
        if port is not None:
            port.report(ErrorLevel.ERROR, '更新配置节失败', exception=e)
        logger.error(f"更新配置节失败: {e}")
        raise AppError(ErrorCode.SYS_INTERNAL_ERROR, f"更新配置节失败: {str(e)}") from e


# ===== 路径操作接缝（2 段 · F1 读形状 / F2 秘密三态 / F3 认领规则 / F5 revision）=====
#
# 与上面的"整份 / 整节"端点的关系：那些是**遗留入口**（待拆），这里是新接缝。
# 新接缝的形状是"按路径读、按路径写"——客户端不再需要整份文件。
#
# `GET|POST /config/bot/raw` 连同兼容别名 `/api/config/raw` 已于 5 段**下线**
# （2026-10-16 lmq 拍板）：它是配置面上已知的**明文密钥出站路径**——实测直出
# `maim_message.auth_token` 与 `maim_message.api_server_allowed_api_keys` 的真值。
# 随之关闭的是"在 WebUI 里手改 TOML 原文"这一个逃生舱（**不是**配置编辑能力：
# 核心/详细模式与按路径读写都在）。前端「源文件」页签已同批移除。


def _namespace_or_400(namespace: str) -> config_store.NamespaceSpec:
    """命名空间不合法 ⇒ 400（客户端传错了，不是服务端坏了，别落到 500）。"""
    try:
        return config_store.namespace_spec(namespace)
    except config_store.UnknownNamespaceError as error:
        raise AppError(ErrorCode.PARAM_INVALID, str(error), http_status=400) from error


def _default_read_targets(stored: Any, declared: frozenset[str]) -> list[tuple[Any, ...]]:
    """整平面读的目标路径 = 已存储的全部叶路径 + 已声明的秘密路径。

    两处细节都是判据级的：

    - **只丢掉"落在**已声明**秘密内部的叶子"**：``auth_token`` 是数组，"列叶"会摊出
      ``maim_message.auth_token[0]``；它们的根会由下面的声明展开统一补一个标记，所以这里丢掉
      避免重复。⚠️ 名字层兜住的键（没人声明）**不能丢**——展开补不到它们，丢了就等于
      这个密钥在整平面读里**根本不出现**，而它本该以一个标记出现。
    - **"未配置"要主动报告**：F2 三态里 ``set: false`` 那一态，文件里压根没有对应键，
      只遍历已存储的数据永远看不到它，所以声明路径要按实际下标展开后单独补进去。
    """
    targets: list[tuple[Any, ...]] = []
    seen: set[str] = set()

    for tokens in iter_leaf_paths(stored):
        secret_root = find_secret_root(tokens, declared)
        if (
            secret_root is not None
            and len(secret_root) < len(tokens)
            and to_declaration_key(secret_root) in declared
        ):
            continue
        path_text = format_path(tokens)
        if path_text in seen:
            continue
        seen.add(path_text)
        targets.append(tokens)

    for declared_path in sorted(declared):
        try:
            declared_tokens = parse_declaration(declared_path)
        except ConfigPathError as error:
            # 声明表是**服务端自己的数据**：它写错了是**我们的** bug，不是客户端请求错。
            # 混进下面的 PARAM_INVALID(400) 会把服务端故障报成"你参数不对"（F12）——
            # 排障的人于是去查请求，而问题在声明表里。单独抛类型，由端点映射成 5xx + 上报。
            raise SecretDeclarationError(declared_path, error) from error
        for concrete in expand_declaration(declared_tokens, stored):
            path_text = format_path(concrete)
            if path_text in seen:
                continue
            seen.add(path_text)
            targets.append(concrete)
    return targets


def _build_read_entry(
    spec: config_store.NamespaceSpec,
    stored: Any,
    tokens: tuple[Any, ...],
    revision: int,
    declared: frozenset[str],
) -> Dict[str, Any]:
    """构造读接缝的一项：``{path, value | 秘密标记, inherited, revision}``。

    ⚠️ 秘密判定必须**双向**做（见 ``config_secrets.find_secret_root`` 的 docstring）：
    这条路径自己（或其**祖先**）是秘密 ⇒ 出标记；否则取子树时还要把**里面**的秘密
    （它的**后代**）换成标记——只做前者 = 请求一个祖先容器就把密钥整包领走。

    ⚠️ **标记说的必须是"被请求位置"的状态**（F10 修复，2026-10-16）：请求
    ``maim_message.auth_token[7]`` 而数组只有 3 项时，旧实现回的是**秘密根**的三态
    （``set: true`` + 根的 ``kind``）⇒ 客户端看到"这个位置已配置"、还拿到一个**并不存在**
    的数组形态。现在按被请求位置取状态：
    ``配置=set 为真 / 未配置或位置不存在=set 为假``，并且**不带 ``kind``**
    （未配置的位置没有"值形态"可言）。``inherited`` 与 "set 为假" 同向——"这里没有值"
    就是"读到的不是文件里的值"（schema 默认或根本没有），客户端据此知道可以写新值。
    """
    path_text = format_path(tokens)

    # 方向甲「路径在秘密里」：请求的位置落在某个秘密字段**内部**（例如它的数组元素）
    # ⇒ 发出去的是**该位置**的标记（值本身永远不出站）。
    secret_root = find_secret_root(tokens, declared)
    if secret_root is not None:
        # ⚠️ 标记必须按**被请求位置**（tokens）现算，不能拿 secret_root 去算（F10）：
        # `describe_secret_value` 对"位置不存在"给的正是 `set: false` 且不带 `kind`
        # （`is_configured(MISSING)` 为假）⇒ 客户端看到"这里没有值，可以写"，而不是
        # 拿秘密根的形态去猜一个并不存在的位置。
        marker = describe_secret_value(stored, tokens)
        return {
            "path": path_text,
            "value": marker,
            "inherited": not marker.get(SENTINEL_SET_KEY, False),
            "revision": revision,
        }

    stored_value = lookup_path(stored, tokens)
    if stored_value is not MISSING:
        # 方向乙「秘密在路径里」：子树里若有秘密字段，**按同一套判据**换成标记再出站
        return {
            "path": path_text,
            "value": redact_subtree(stored, tokens, declared),
            "inherited": False,
            "revision": revision,
        }

    # 文件里没有 ⇒ 值来自 schema 默认（`inherited` 说的就是"没被覆盖"）
    default_value = config_store.schema_default(spec.name, tokens)
    if default_value is MISSING:
        raise AppError(ErrorCode.PARAM_INVALID, f"未知配置路径：{path_text}", http_status=400)
    return {"path": path_text, "value": default_value, "inherited": True, "revision": revision}


@router.post("/get")
async def read_config_paths(request: ConfigReadRequest):
    """按路径读配置（F1 读接缝）。

    每项形状：``{path, value | 秘密标记, inherited, revision}``

    - ``value``：已存储的值；秘密路径换成三态标记（``$secret`` / ``set`` / ``kind``）。
    - ``inherited``：该路径**有没有被覆盖**——判据是"文件里有没有这个键"，
      **不是**"值等不等于默认值"（值恰好等于默认值也可以是显式配的）。
    - ``revision``：命名空间版本号，写的时候原样带回去（``mutate`` 的 ``expectedRevision``）。

    ``paths`` 留空 = 该平面已存储的全部叶路径 + 已声明的秘密路径
    （后者即使没配也回 ``set: false``——"没配"本身是要报告的状态）。
    """
    try:
        spec = _namespace_or_400(request.namespace)
        # F11：内容与 revision **必须同源取回**。分两步调（load_stored → current_revision）
        # 会让写者插在中间，客户端拿到 (旧内容, 新 revision)，带着它去写还会被**接受**
        # ⇒ 乐观锁失效。实测双线程下 40 次读 40 次撕裂。
        stored, revision = config_store.read_snapshot(spec.name)
        declared = config_store.secret_field_paths(spec.name)

        targets = [parse_path(path) for path in request.paths] if request.paths else _default_read_targets(
            stored, declared
        )
        entries = [_build_read_entry(spec, stored, tuple(tokens), revision, declared) for tokens in targets]

        return {"success": True, "namespace": spec.name, "revision": revision, "entries": entries}
    except AppError:
        raise
    except config_store.ConfigFileMissingError as error:
        raise AppError(ErrorCode.BIZ_NOT_FOUND, "配置文件不存在", http_status=404) from error
    except SecretDeclarationError as error:
        # F12：**服务端**声明表写错了 ⇒ 5xx + 双通道上报，绝不是"客户端参数不合法"。
        # 注意这条必须排在下面的 (ConfigPathError, SecretClaimError) 之前/之外——
        # SecretDeclarationError 不是 ConfigPathError 的子类，刻意如此。
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port
        port = get_error_escalation_port()
        if port is not None:
            port.report(ErrorLevel.ERROR, "服务端秘密声明表配置错误", exception=error)
        logger.error(f"服务端秘密声明表配置错误：{error}")
        raise AppError(ErrorCode.SYS_INTERNAL_ERROR, str(error)) from error
    except (ConfigPathError, SecretClaimError) as error:
        raise AppError(ErrorCode.PARAM_INVALID, str(error), http_status=400) from error
    except Exception as e:
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port
        port = get_error_escalation_port()
        if port is not None:
            port.report(ErrorLevel.ERROR, '按路径读取配置失败', exception=e)
        logger.error(f"按路径读取配置失败: {e}")
        raise AppError(ErrorCode.SYS_INTERNAL_ERROR, f"按路径读取配置失败: {str(e)}") from e


def _apply_operation(
    document: Any,
    operation: ConfigMutateOp,
    baseline: Any,
    declared: frozenset[str],
) -> None:
    """在 ``tomlkit`` 文档上实施一次路径操作（写完才落盘，中途异常不留半份）。

    Args:
        document: 待改的文档（就是"已存储的那份"，不是客户端提交的副本）。
        operation: 一次操作。
        baseline: **变更前**的已存储结构——秘密占位的认领基准（F1：对已存储的那份解析）。
        declared: 该命名空间的秘密声明路径集合（认领时判来源/靶子身份）。
    """
    tokens = parse_path(operation.path)

    if operation.op == "set":
        if operation.value is None:
            # TOML 无法表达 null ⇒ 这是客户端请求不合法，不是服务端坏了（对抗审查 F7）
            raise AppError(
                ErrorCode.PARAM_INVALID,
                f"set 必须带 value（TOML 无法表达 null）：{operation.path}",
                http_status=400,
            )
        value = operation.value
        if is_secret_claim(value, declared):
            # 客户端把读回来的占位原样写回 ⇒ 按 F3 两级规则认领原值；
            # 认不到（或靶子不是来源那个秘密字段）会抛 SecretClaimError ⇒ 整次写入作废。
            # 用 is_secret_claim 而非纯形状判断：一张恰好长成 {path,set} 的**普通数据表**
            # 必须能被正常写入，不能被当成占位吃掉（对抗审查 F6）
            value = claim_secret_value(value, baseline, target_path=operation.path, declared=declared)
        assign_path(document, tokens, value)
        return

    if operation.op == "unset":
        # 重置为继承 = **真删键**（F5）；不是写一个恰好等于默认值的值
        remove_path(document, tokens)
        return

    if operation.index is None:
        raise AppError(
            ErrorCode.PARAM_INVALID,
            f"remove_at 必须带 index（路径：{operation.path}）",
            http_status=400,
        )
    remove_index(document, tokens, operation.index)


def _touched_sections(operations: List[ConfigMutateOp]) -> set[str]:
    """这次写入碰到了哪些顶层节（重启提示用）。"""
    sections: set[str] = set()
    for operation in operations:
        tokens = parse_path(operation.path)
        first_token = tokens[0]
        if isinstance(first_token, str):
            sections.add(first_token)
    return sections


def _restart_sections_for(namespace: str, touched_sections: set[str]) -> List[str]:
    """哪些改动需要重启才生效。

    沿用既有端点的口径：模型配置**整体**需要重启（``POST /config/model`` 就是这么答的），
    主程序配置按节判断。
    """
    if namespace == config_store.NAMESPACE_MODEL:
        return ["model"]
    return sorted(touched_sections & _RESTART_REQUIRED_SECTIONS)


def _validate_namespace_document(spec: config_store.NamespaceSpec, plain: Any) -> None:
    """写入前的整体校验：模型不通过 ⇒ 400（提交的数据不合法，不是服务端坏了）。"""
    try:
        spec.model.from_dict(AttributeData(), copy.deepcopy(plain))
    except AppError:
        raise
    except Exception as error:
        raise AppError(ErrorCode.PARAM_INVALID, f"配置数据验证失败: {error}", http_status=400) from error


@router.post("/mutate")
async def mutate_config(request: ConfigMutateRequest):
    """按路径写配置（F1 写接缝 / F5 revision）。

    - **解析基准 = 已存储的那份**：操作作用在文件当前内容上，**没点名的路径根本不进写路径**
      ⇒ 页面上没展示的字段不可能被整段 replace 吃掉。
    - ``set`` 的值可以是原值，也可以是**读回来的秘密占位**：按 F3 两级规则
      （名字唯一匹配 → 占位自带来源路径）认领原值；**认不到 ⇒ 400 并拒绝整次写入**。
    - ``unset`` = 重置为继承（真删键）；``remove_at`` = 删数组元素（不用 ``set null`` 代替）。
    - ``expectedRevision`` 与当前不符 ⇒ **409 + 双 revision**，不自动合并、不静默覆盖。

    校验不通过时**文件一个字节不动、revision 也不前进**。
    """
    try:
        spec = _namespace_or_400(request.namespace)
        touched_sections = _touched_sections(request.ops)
        declared = config_store.secret_field_paths(spec.name)

        def _apply(document: Any, baseline: Any) -> None:
            """``baseline`` 是**锁定后、变更前**的已存储快照——秘密认领的解析基准（F1）。"""
            for operation in request.ops:
                _apply_operation(document, operation, baseline, declared)

        try:
            new_revision = config_store.commit(
                spec.name,
                request.expected_revision,
                _apply,
                validate=lambda plain: _validate_namespace_document(spec, plain),
            )
        except config_store.RevisionConflictError as error:
            raise AppError(
                ErrorCode.BIZ_STATE_CONFLICT,
                str(error),
                details={
                    "namespace": error.namespace,
                    "expected_revision": error.expected,
                    "current_revision": error.current,
                },
                http_status=409,
            ) from error
        except config_store.ConfigFileMissingError as error:
            raise AppError(ErrorCode.BIZ_NOT_FOUND, "配置文件不存在", http_status=404) from error
        except (ConfigPathError, SecretClaimError) as error:
            raise AppError(ErrorCode.PARAM_INVALID, str(error), http_status=400) from error

        # 写盘已经成功 ⇒ 从这里往后**任何**失败都不能再让客户端以为"没保存"。
        # 热重载统一走 `_reload_config_or_report`（await + 冻结态如实上报，不 500）
        hot_reload = await _reload_config_or_report(f"POST /config/mutate ({spec.name})")

        restart_sections = _restart_sections_for(spec.name, touched_sections)
        logger.info(f"配置 '{spec.name}' 已按路径更新（revision={new_revision}，共 {len(request.ops)} 个操作）")
        message = f"配置 '{spec.name}' 已保存"
        if hot_reload == HOT_RELOAD_REFUSED_FROZEN:
            message += "（已落盘；热重载被拒绝：配置已冻结，实际生效依赖重启或文件监听）"
        return {
            "success": True,
            "namespace": spec.name,
            "revision": new_revision,
            "applied": len(request.ops),
            "message": message,
            "hot_reload": hot_reload,
            "needs_restart": _needs_restart_flag(restart_sections, hot_reload),
            "restart_required_sections": restart_sections,
        }
    except AppError:
        raise
    except (ConfigPathError, SecretClaimError) as error:
        raise AppError(ErrorCode.PARAM_INVALID, str(error), http_status=400) from error
    except Exception as e:
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port
        port = get_error_escalation_port()
        if port is not None:
            port.report(ErrorLevel.ERROR, '按路径写入配置失败', exception=e)
        logger.error(f"按路径写入配置失败: {e}")
        raise AppError(ErrorCode.SYS_INTERNAL_ERROR, f"按路径写入配置失败: {str(e)}") from e
