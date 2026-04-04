"""CLI 下的 Prompt 可视化渲染模块。"""

from __future__ import annotations

import hashlib
from base64 import b64decode
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from urllib.parse import quote
from typing import Any, Dict, List, Literal

import tempfile

from pydantic import BaseModel, Field as PydanticField
from rich.console import Group, RenderableType
from rich.pretty import Pretty
from rich.panel import Panel
from rich.text import Text

PROJECT_ROOT = Path(__file__).parent.parent.parent.absolute().resolve()
DATA_IMAGE_DIR = PROJECT_ROOT / "data" / "images"


class PromptImageDisplayMode(str, Enum):
    """图片在终端中的展示模式。"""

    LEGACY = "legacy"
    """不新增链接，仅保留原有的元信息展示。"""

    PATH_LINK = "path_link"
    """把图片落盘到临时目录并输出可点击路径。"""


class PromptImageDisplaySettings(BaseModel):
    """图片展示参数。"""

    display_mode: PromptImageDisplayMode = PydanticField(default=PromptImageDisplayMode.LEGACY)
    """图片展示模式。"""



@dataclass(slots=True)
class _MessageRenderResult:
    """可渲染结果与是否有工具调用信息。"""

    message_panel: Panel
    tool_call_panels: List[Panel]


class PromptCLIVisualizer:
    """负责构建 CLI 下 prompt 展示所需的所有可视化组件。"""

    @staticmethod
    def _get_role_badge_style(role: str) -> str:
        if role == "system":
            return "bold white on blue"
        if role == "user":
            return "bold black on green"
        if role == "assistant":
            return "bold black on yellow"
        if role == "tool":
            return "bold white on magenta"
        return "bold white on bright_black"

    @staticmethod
    def _get_role_badge_label(role: str) -> str:
        if role == "system":
            return "系统"
        if role == "user":
            return "用户"
        if role == "assistant":
            return "助手"
        if role == "tool":
            return "工具"
        return "未知"

    @staticmethod
    def _format_token_count(token_count: int) -> str:
        if token_count >= 10_000:
            return f"{token_count / 1000:.1f}k"
        return str(token_count)

    @classmethod
    def build_prompt_stats_text(
        cls,
        *,
        selected_history_count: int,
        built_message_count: int,
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int,
    ) -> str:
        """构造 prompt 统计文本。"""
        return (
            f"上下文消息数量={selected_history_count} "
            f"已构建消息数={built_message_count} "
            f"实际输入Token={cls._format_token_count(prompt_tokens)} "
            f"输出Token={cls._format_token_count(completion_tokens)} "
            f"总Token={cls._format_token_count(total_tokens)}"
        )

    @staticmethod
    def _normalize_image_format(image_format: str) -> str:
        """归一化图片扩展名。"""
        normalized = image_format.strip().lower()
        if normalized == "jpg":
            return "jpeg"
        return normalized

    @staticmethod
    def _build_image_cache_path(image_format: str, image_base64: str) -> Path:
        image_format = PromptCLIVisualizer._normalize_image_format(image_format)
        root = Path(tempfile.gettempdir()) / "maisaka_prompt_images"
        root.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256(image_base64.encode("utf-8")).hexdigest()
        return root / f"{digest}.{image_format}"

    @staticmethod
    def _build_file_uri(file_path: Path) -> str:
        normalized = file_path.as_posix()
        return f"file:///{quote(normalized, safe='/:')}"

    @staticmethod
    def _build_official_image_path(image_format: str, image_base64: str) -> Path | None:
        normalized_format = PromptCLIVisualizer._normalize_image_format(image_format)
        try:
            image_bytes = b64decode(image_base64)
        except Exception:
            return None

        digest = hashlib.sha256(image_bytes).hexdigest()
        official_path = DATA_IMAGE_DIR / f"{digest}.{normalized_format}"
        if official_path.exists():
            return official_path
        return None

    @staticmethod
    def _build_image_file_link(image_format: str, image_base64: str) -> tuple[str, Path] | None:
        """优先返回正式图片路径；不存在时回退到临时缓存路径。"""
        normalized_format = PromptCLIVisualizer._normalize_image_format(image_format) or "bin"
        official_path = PromptCLIVisualizer._build_official_image_path(image_format, image_base64)
        if official_path is not None:
            return PromptCLIVisualizer._build_file_uri(official_path), official_path

        try:
            image_bytes = b64decode(image_base64)
        except Exception:
            return None

        path = PromptCLIVisualizer._build_image_cache_path(normalized_format, image_base64)
        if not path.exists():
            try:
                path.write_bytes(image_bytes)
            except Exception:
                return None
        return PromptCLIVisualizer._build_file_uri(path), path

    @classmethod
    def _render_image_item(cls, image_format: str, image_base64: str, settings: PromptImageDisplaySettings) -> Panel:
        normalized_format = cls._normalize_image_format(image_format)
        approx_size = max(0, len(image_base64) * 3 // 4)
        size_text = f"{approx_size / 1024:.1f} KB" if approx_size >= 1024 else f"{approx_size} B"

        preview_parts: List[RenderableType] = [
            Text(f"图片格式 image/{normalized_format}  {size_text}", style="magenta")
        ]

        if settings.display_mode == PromptImageDisplayMode.PATH_LINK:
            path_result = cls._build_image_file_link(image_format, image_base64)
            if path_result is not None:
                file_uri, file_path = path_result
                preview_parts: List[RenderableType] = [
                    Text(f"图片格式 image/{normalized_format}  {size_text} 路径：{file_path}", style="magenta")
                ]
                
                preview_parts.append(Text.from_markup(f"[link={file_uri}]点击打开图片[/link]", style="cyan"))

        return Panel(
            Group(*preview_parts),
            border_style="magenta",
            padding=(0, 1),
        )

    @classmethod
    def _render_message_content(cls, content: Any, settings: PromptImageDisplaySettings) -> RenderableType:
        if isinstance(content, str):
            return Text(content)

        if isinstance(content, list):
            parts: List[RenderableType] = []
            for item in content:
                if isinstance(item, str):
                    parts.append(Text(item))
                    continue
                if isinstance(item, tuple) and len(item) == 2:
                    image_format, image_base64 = item
                    if isinstance(image_format, str) and isinstance(image_base64, str):
                        parts.append(cls._render_image_item(image_format, image_base64, settings))
                        continue
                if isinstance(item, dict) and item.get("type") == "text" and isinstance(item.get("text"), str):
                    parts.append(Text(item["text"]))
                else:
                    parts.append(Pretty(item, expand_all=True))
            return Group(*parts) if parts else Text("")

        if content is None:
            return Text("")

        return Pretty(content, expand_all=True)

    @classmethod
    def format_tool_call_for_display(cls, tool_call: Any) -> Dict[str, Any]:
        if isinstance(tool_call, dict):
            function_info = tool_call.get("function", {})
            return {
                "id": tool_call.get("id"),
                "name": function_info.get("name", tool_call.get("name")),
                "arguments": function_info.get("arguments", tool_call.get("arguments")),
            }

        return {
            "id": getattr(tool_call, "call_id", getattr(tool_call, "id", None)),
            "name": getattr(tool_call, "func_name", getattr(tool_call, "name", None)),
            "arguments": getattr(tool_call, "args", getattr(tool_call, "arguments", None)),
        }

    @classmethod
    def _render_tool_call_panel(cls, tool_call: Any, index: int, parent_index: int) -> Panel:
        title = Text.assemble(
            Text(" 工具调用 ", style="bold white on magenta"),
            Text(f"  #{parent_index}.{index}", style="muted"),
        )
        return Panel(
            Pretty(cls.format_tool_call_for_display(tool_call), expand_all=True),
            title=title,
            border_style="magenta",
            padding=(0, 1),
        )

    @classmethod
    def _render_message_panel(cls, message: Any, index: int, settings: PromptImageDisplaySettings) -> _MessageRenderResult:
        if isinstance(message, dict):
            raw_role = message.get("role", "unknown")
            content = message.get("content")
            tool_call_id = message.get("tool_call_id")
        else:
            raw_role = getattr(message, "role", "unknown")
            content = getattr(message, "content", None)
            tool_call_id = getattr(message, "tool_call_id", None)

        role = raw_role.value if hasattr(raw_role, "value") else str(raw_role)
        title = Text.assemble(
            Text(f" {cls._get_role_badge_label(role)} ", style=cls._get_role_badge_style(role)),
            Text(f"  #{index}", style="muted"),
        )

        parts: List[RenderableType] = []
        if content not in (None, "", []):
            parts.append(Text(" 内容 ", style="bold cyan"))
            parts.append(cls._render_message_content(content, settings))

        if tool_call_id:
            parts.append(
                Text.assemble(
                    Text(" 工具调用ID ", style="bold magenta"),
                    Text(" "),
                    Text(str(tool_call_id), style="magenta"),
                )
            )

        if not parts:
            parts.append(Text("[空]", style="muted"))

        message_panel = Panel(
            Group(*parts),
            title=title,
            border_style="dim",
            padding=(0, 1),
        )

        tool_call_panels: List[Panel] = []
        tool_calls = getattr(message, "tool_calls", None)
        if tool_calls:
            for tool_call_index, tool_call in enumerate(tool_calls, start=1):
                tool_call_panels.append(cls._render_tool_call_panel(tool_call, tool_call_index, index))

        return _MessageRenderResult(message_panel=message_panel, tool_call_panels=tool_call_panels)

    @classmethod
    def build_prompt_panels(
        cls,
        messages: list[Any],
        *,
        image_display_mode: Literal["legacy", "path_link"],
    ) -> List[Panel]:
        """构建完整 prompt 可视化面板。"""
        if image_display_mode not in {mode.value for mode in PromptImageDisplayMode}:
            image_display_mode = PromptImageDisplayMode.LEGACY
        settings = PromptImageDisplaySettings(
            display_mode=PromptImageDisplayMode(image_display_mode),
        )

        ordered_panels: List[Panel] = []
        for index, message in enumerate(messages, start=1):
            message_render_result = cls._render_message_panel(message, index, settings)
            ordered_panels.append(message_render_result.message_panel)
            ordered_panels.extend(message_render_result.tool_call_panels)
        return ordered_panels
