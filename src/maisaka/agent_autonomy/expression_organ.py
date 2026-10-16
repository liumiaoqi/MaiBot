from itertools import count as _count
import re

from src.common.logger import get_logger
from src.maisaka.agent_autonomy.autonomy_logger import AutonomyEventType, AutonomyLogger

logger = get_logger("agent_autonomy.expression_organ")

#: 「只剩空括号」的空壳字符集（`()`、`（）`、`[]`、`【】`…）——剥掉署名后如果只剩这些，等于没内容。
_EMPTY_PAREN_ONLY = re.compile(r"^(?:[\s()（）\[\]【】{}｛｝<>《》「」『』·、,，.。!！?？~～-]|\*)+$")

#: 拒发计数（进程内累计，只增不清）——"计数 + 一条可区分日志"里的计数。
_rejected_outbound_counter = _count(1)


def _speaker_tag_pattern(tag_format: str) -> "re.Pattern[str]":
    """把 `speaker_tag_format` 翻成"**同形**标记"的正则（**只用于首部**匹配）。

    例：`【{agent_name}】` ⇒ `^【.+?】`。
    字面量部分转义后原样；占位符（`{agent_name}` / `{agent_id}`）换成非贪婪 `.+?`。
    ⇒ 它匹配"**任何**名字的该格式标记"，这正是"只剥同形、不剥别的"所需要的：
    模型自写的 `【银狼】` 会被剥掉，而 `他说【这本书】很好` 里的方括号**不在首部**，不受影响。
    """
    parts: list[str] = []
    for chunk in re.split(r"(\{agent_name\}|\{agent_id\})", tag_format):
        if chunk in ("{agent_name}", "{agent_id}"):
            parts.append(".+?")
        elif chunk:
            parts.append(re.escape(chunk))
    return re.compile("^" + "".join(parts), re.DOTALL)


def strip_leading_speaker_tag(text: str, tag_format: str) -> tuple[str, str]:
    """剥掉模型**自写在首部**的发言标记；返回 ``(剥后文本, 被剥掉的标记)``。

    只做两件事（其余一律不动）：

    - **只剥首部**（允许前面有空白），正文里的方括号**一律不动**；
    - **只剥与 `build_speaker_tag()` 同形**的那一个（同一 `speaker_tag_format` 派生的形状）。

    为什么要剥：模型经常自己写一个署名（实测 `agent=bronya` 的回复署名成 `【银狼】`），
    而这条链只"加前缀"、不做任何过滤 ⇒ **错署名原样出站**。
    """
    offset = len(text) - len(text.lstrip())
    match = _speaker_tag_pattern(tag_format).match(text[offset:])
    if match is None:
        return text, ""
    return text[offset + match.end() :], match.group(0)


def verify_outbound_signature(text: str, expected_tag: str, tag_format: str) -> tuple[bool, str]:
    """校验"出站文本的**首部署名** == 本发言者的标记"；返回 ``(是否一致, 具名原因)``。

    为什么是**署名一致性**而不是"不许双前缀"（lead 裁定）：实测那个错的形态是
    `agent=bronya` 却写 `【银狼】`——**只有一个前缀、但名字是错的**，
    "查重复前缀"这种判据**咬不住它**。所以这里同时咬两件事：
    ① 首部必须正好是 `expected_tag`；② 紧跟其后不许再有同形标记（双前缀）。
    """
    offset = len(text) - len(text.lstrip())
    head = text[offset:]
    if not head.startswith(expected_tag):
        return False, f"首部署名不是本发言者的标记：期望 {expected_tag!r}，实际前 16 字 {head[:16]!r}"
    rest = head[len(expected_tag) :]
    duplicate = _speaker_tag_pattern(tag_format).match(rest)
    if duplicate is not None:
        return False, f"首部标记之后又跟了一个同形标记（双前缀）: {duplicate.group(0)!r}"
    return True, ""


def is_sendable_outbound_text(text: str, tag_format: str) -> tuple[bool, str]:
    """出站前判"这段文本值不值得发"；返回 ``(可发, 具名原因)``。

    三种形态**都不许出站**（第三种是今晚实测的 `【Veliona】()`）：

    1. **空正文**——剥掉首部同形标记后为空；
    2. **只剩前缀**——文本就是那个标记；
    3. **只有空括号**——剥掉标记后只剩括号/空白这类空壳（`()`、`（）`、`【】`…）。

    ⚠️ 判据口径（team 裁定）：**要么不出、要么具名**——不出是行为，具名由调用方
    （`report_rejected_outbound_text`）落成日志 + 上报**双通道**。
    """
    body, _ = strip_leading_speaker_tag(text, tag_format)
    core = body.strip()
    if not core:
        return False, "空正文（剥掉署名后为空）"
    if _EMPTY_PAREN_ONLY.match(core):
        return False, f"只有空括号/空壳字符、无实际内容: {core[:20]!r}"
    return True, ""


def report_rejected_outbound_text(
    reason: str, *, agent_id: str, text: str, source: str
) -> int:
    """拒发时**双通道出声**（`AGENTS §七` #7 异常双通道）；返回本次序号（计数）。

    "具名"要能回答四件事：**谁**（agent/source）· **为什么**（reason）· **原文长什么样**
    （截断预览，排障时不必再猜）· **这是第几次**（计数，可 grep 统计）。
    """
    ordinal = next(_rejected_outbound_counter)
    logger.warning(
        "[outbound] 拒发空内容: 第%d次 agent=%s source=%s reason=%s 原文=%r",
        ordinal,
        agent_id,
        source,
        reason,
        text[:80],
    )
    from src.core.error_escalation.types import ErrorLevel
    from src.core.error_escalation_port_registry import get_error_escalation_port

    port = get_error_escalation_port()
    if port is not None:
        port.report(
            ErrorLevel.WARNING,
            f"[outbound] 拒发空内容: 第{ordinal}次 agent={agent_id} source={source} reason={reason}",
        )
    return ordinal


class ExpressionOrgan:
    """表达器官——以角色风格运行 Replyer，绑定发言标记。"""

    def __init__(self, agent_id: str, speaker_tag_format: str = "【{agent_name}】") -> None:
        self._agent_id = agent_id
        self._speaker_tag_format = speaker_tag_format
        self._agent_display_name: str | None = None
        self._autonomy_logger = AutonomyLogger.get()

    @property
    def agent_id(self) -> str:
        return self._agent_id

    def build_speaker_tag(self) -> str:
        """构建发言标记。

        Returns:
            如 "【银狼】" 格式的发言标记。
        """
        agent_name = self._get_agent_display_name()
        return self._speaker_tag_format.format(agent_name=agent_name, agent_id=self._agent_id)

    def should_show_speaker_tag(self, is_multi_agent_active: bool) -> bool:
        """判断是否应显示发言标记。

        Args:
            is_multi_agent_active: 当前会话是否有多个活跃智能体

        Returns:
            仅在多智能体活跃时显示发言标记
        """
        return is_multi_agent_active

    def prepend_speaker_tag(self, content: str, is_multi_agent_active: bool) -> str:
        """在消息内容前添加发言标记（仅在多智能体活跃时）。

        2026-10-16 收口（`outbound-text-final`）：**先剥模型自写的首部标记，再加本发言者的标记**。

        - 剥离**与多智能体开关无关**：模型写错名字时（实测 `agent=bronya` 写 `【银狼】`），
          若只在"要加前缀"时才剥，那么开关关闭时错署名就**原样出站**了 —— 这正是实测形态。
        - 加完再做一次**署名一致性校验**（首部 == 本 agent 的标记，且其后无同形标记）：
          "只有一个前缀但名字是错的"这种错，只有署名一致性咬得住。

        Args:
            content: 原始消息内容
            is_multi_agent_active: 当前会话是否有多个活跃智能体

        Returns:
            带发言标记的消息内容
        """
        content, stripped_tag = strip_leading_speaker_tag(content, self._speaker_tag_format)
        if stripped_tag:
            # 模型自写署名——**具名**记下来（它是"错署名"现象的现场证据）。
            self._autonomy_logger.log(
                self._agent_id,
                AutonomyEventType.EXPRESSION,
                f"剥离模型自写的首部标记: {stripped_tag}",
            )
        if not self.should_show_speaker_tag(is_multi_agent_active):
            return content
        tag = self.build_speaker_tag()
        composed = f"{tag}{content}"
        consistent, reason = verify_outbound_signature(composed, tag, self._speaker_tag_format)
        if not consistent:
            # 结构上不该发生（上一行刚拼的就是 tag+content）⇒ 真发生了就是逻辑错，**出声**。
            logger.warning(
                "[outbound] 署名一致性校验失败: agent=%s tag=%r reason=%s",
                self._agent_id,
                tag,
                reason,
            )
        self._autonomy_logger.log(
            self._agent_id,
            AutonomyEventType.EXPRESSION,
            f"添加发言标记: {tag}",
        )
        return composed

    def _get_agent_display_name(self) -> str:
        """获取智能体的显示名称。"""
        if self._agent_display_name is not None:
            return self._agent_display_name
        try:
            from src.core.adapters.agent_config_port import get_agent_config_provider

            registry = get_agent_config_provider()
            if registry.has_agent(self._agent_id):
                agent_config = registry.get_agent(self._agent_id)
                self._agent_display_name = agent_config.display_name or self._agent_id
                return self._agent_display_name
        except Exception as exc:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.WARNING, "获取 agent display_name 失败", exception=exc)
            logger.warning("获取 agent display_name 失败", exc_info=True)
        self._agent_display_name = self._agent_id
        return self._agent_display_name
