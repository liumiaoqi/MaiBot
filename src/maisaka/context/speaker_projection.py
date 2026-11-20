"""发言投影 — 把归属决策作用到 LLM Message（role + 首个文本片段）。

只做三件事：改 role、改消息头 `user=`/`is_self_message`、剥首部署名。
不改存储文本，不改出站文本。
"""

import re

from html import escape

from src.llm_models.payload_content.message import Message, TextMessagePart
from src.maisaka.context.attribution import AttributionDecision


__all__ = [
    "project_message",
    "rewrite_message_header",
    "strip_leading_speaker_tag",
]


_MESSAGE_HEADER_RE = re.compile(r"^(<message\b[^>]*>)\n", re.DOTALL)


def _speaker_tag_pattern(tag_format: str) -> "re.Pattern[str]":
    """把 `speaker_tag_format` 翻成"同形标记"的正则（只用于首部匹配）。"""
    parts: list[str] = []
    for chunk in re.split(r"(\{agent_name\}|\{agent_id\})", tag_format):
        if chunk in ("{agent_name}", "{agent_id}"):
            parts.append(".+?")
        elif chunk:
            parts.append(re.escape(chunk))
    return re.compile("^" + "".join(parts), re.DOTALL)


def strip_leading_speaker_tag(text: str, tag_format: str) -> tuple[str, str]:
    """剥掉模型自写在首部的发言标记；返回 ``(剥后文本, 被剥掉的标记)``。"""
    offset = len(text) - len(text.lstrip())
    match = _speaker_tag_pattern(tag_format).match(text[offset:])
    if match is None:
        return text, ""
    return text[offset + match.end() :], match.group(0)


def rewrite_message_header(text: str, *, user_name: str, is_self: bool) -> str:
    """改写首个 `<message ...>` 头的 `user=` 与 `is_self_message` 属性。

    头不存在或 `user_name` 为空时原样返回——名字由调用方保证，函数不猜。
    """
    if not user_name:
        return text

    match = _MESSAGE_HEADER_RE.match(text)
    if match is None:
        return text

    header = match.group(1)
    escaped_name = escape(user_name, quote=True)
    if 'user="' in header:
        header = re.sub(r'\buser="[^"]*"', f'user="{escaped_name}"', header, count=1)
    else:
        header = header[:-1] + f' user="{escaped_name}">'

    if is_self:
        if "is_self_message=" not in header:
            header = header[:-1] + ' is_self_message="true">'
    else:
        header = re.sub(r'\s+is_self_message="[^"]*"', "", header, count=1)

    return header + "\n" + text[match.end() :]


def project_message(
    message: Message,
    decision: AttributionDecision,
    *,
    display_name: str,
    tag_format: str,
) -> None:
    """把决策作用到消息：改 role；对首个文本片段剥署名并改头。"""
    if message.role is not decision.role:
        message.role = decision.role

    if not message.parts:
        return

    first = message.parts[0]
    if not isinstance(first, TextMessagePart):
        return

    text, _ = strip_leading_speaker_tag(first.text, tag_format)
    text = rewrite_message_header(
        text,
        user_name=display_name,
        is_self=decision.self_authored,
    )
    if text != first.text:
        first.text = text