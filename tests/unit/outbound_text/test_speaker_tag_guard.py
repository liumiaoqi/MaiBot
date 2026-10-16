"""`outbound-text-final` 三件的判据（agent_autonomy 出站文本收口）。

落点：`expression_organ.py`（形状权威 + 剥离 + 署名校验 + 空内容判据 + 拒发双通道）·
`bridge/reply_context_extender.py`（四个出站点共用的闸）· 四个出站点自身。

三件的判据分开：

1. **只剥首部、只剥同形**——模型自写的 `【银狼】` 剥掉；`他说【这本书】很好` 原样不动。
2. **署名一致性**——首部署名必须正好是本 agent 的标记；且"只有一个错名前缀"也要咬住
   （实测形态：`agent=bronya` 却写 `【银狼】`）。
3. **空内容不许出站**——空正文 / 只剩前缀 / 只有空括号（实测 `【Veliona】()`）三种都拒，
   且拒发要**双通道具名**（logger + error_escalation_port）+ 计数。
"""

import pytest

from src.maisaka.agent_autonomy.expression_organ import (
    ExpressionOrgan,
    is_sendable_outbound_text,
    report_rejected_outbound_text,
    strip_leading_speaker_tag,
    verify_outbound_signature,
)

_FMT = "【{agent_name}】"


# ── 1. 只剥首部、只剥同形 ────────────────────────────────────────────


@pytest.mark.parametrize(
    ("text", "expected_body", "expected_tag"),
    [
        # 模型自写的错名首标记（**实测现场**）
        ("【银狼】在呢", "在呢", "【银狼】"),
        # 自己名字的重复标记（幂等：剥掉后由调用方重新加）
        ("【bronya】在呢", "在呢", "【bronya】"),
        # 首部标记 + 前导空白
        ("   【银狼】在呢", "在呢", "【银狼】"),
        # 剥完就空了
        ("【银狼】", "", "【银狼】"),
    ],
)
def test_strip_leading_speaker_tag_only_at_head(
    text: str, expected_body: str, expected_tag: str
) -> None:
    body, removed = strip_leading_speaker_tag(text, _FMT)
    assert body == expected_body
    assert removed == expected_tag


@pytest.mark.parametrize(
    "text",
    [
        "他说【这本书】很好",  # 正文里的方括号：一律不动
        "在呢【银狼】",  # 标记不在首部：不动
        "（银狼）在呢",  # 不同形（圆括号）：不动
        "在呢",
        "",
    ],
)
def test_strip_leading_speaker_tag_leaves_other_text_alone(text: str) -> None:
    body, removed = strip_leading_speaker_tag(text, _FMT)
    assert body == text, f"不该动却被改动了: {text!r} -> {body!r}"
    assert removed == ""


def test_strip_respects_custom_tag_format() -> None:
    """形状来自 `speaker_tag_format`（可配），不是写死的 `【】`。"""
    body, removed = strip_leading_speaker_tag("<bronya> 在呢", "<{agent_name}> ")
    assert removed == "<bronya> "
    assert body == "在呢"


# ── 2. 署名一致性（咬住"只有一个错名前缀"）────────────────────────────


def test_signature_consistency_accepts_correct_head() -> None:
    ok, reason = verify_outbound_signature("【bronya】在呢", "【bronya】", _FMT)
    assert ok, reason


def test_signature_consistency_rejects_wrong_name() -> None:
    """**实测形态**：`agent=bronya` 却写 `【银狼】` —— 只有一个前缀、但名字是错的。"""
    ok, reason = verify_outbound_signature("【银狼】在呢", "【bronya】", _FMT)
    assert not ok
    assert "期望" in reason and "bronya" in reason


def test_signature_consistency_rejects_double_prefix() -> None:
    ok, reason = verify_outbound_signature("【bronya】【银狼】在呢", "【bronya】", _FMT)
    assert not ok
    assert "双前缀" in reason


def test_prepend_replaces_model_written_wrong_tag() -> None:
    """**端到端形态**：模型自写 `【银狼】` ⇒ 出站首部是本 agent 的 `【bronya】`（错署名不再出站）。"""
    organ = ExpressionOrgan("bronya", _FMT)
    result = organ.prepend_speaker_tag("【银狼】在呢", True)
    assert result == "【bronya】在呢", result


def test_prepend_strips_even_when_multi_agent_inactive() -> None:
    """开关关闭时**也要剥**：否则错署名原样出站（实测就是这么漏出去的）。"""
    organ = ExpressionOrgan("bronya", _FMT)
    assert organ.prepend_speaker_tag("【银狼】在呢", False) == "在呢"


def test_prepend_keeps_body_brackets_and_adds_tag() -> None:
    organ = ExpressionOrgan("bronya", _FMT)
    assert organ.prepend_speaker_tag("他说【这本书】很好", True) == "【bronya】他说【这本书】很好"


# ── 3. 空内容不许出站（三种形态）────────────────────────────────────


@pytest.mark.parametrize(
    ("text", "hint"),
    [
        ("", "空正文"),
        ("   ", "空正文"),
        ("【bronya】", "空正文"),  # 只剩前缀
        ("【银狼】", "空正文"),  # 只剩**错名**前缀（剥同形不认名字）
        ("【Veliona】()", "空括号"),  # **实测现场**
        ("()", "空括号"),
        ("（）", "空括号"),
        ("【】", "空括号"),
        ("（。）", "空括号"),
    ],
)
def test_unsendable_contents_are_refused(text: str, hint: str) -> None:
    sendable, reason = is_sendable_outbound_text(text, _FMT)
    assert not sendable, f"空壳内容被放行了: {text!r}"
    assert hint in reason, f"拒绝原因不具名: {reason}"


@pytest.mark.parametrize(
    "text",
    [
        "在呢",
        "【bronya】在呢",
        "【银狼】在呢",  # 内容非空 ⇒ 可发（署名由第 2 件负责改对，不是这里的活）
        "（）里有点东西",
        "……",
    ],
)
def test_normal_contents_are_sendable(text: str) -> None:
    sendable, reason = is_sendable_outbound_text(text, _FMT)
    assert sendable, f"正常内容被误判为不可发: {text!r} reason={reason}"


class _RecordingPort:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def report(self, level, message, **kwargs):  # type: ignore[no-untyped-def]
        self.calls.append((level.name if hasattr(level, "name") else str(level), message))


def test_rejected_text_reports_dual_channel_and_counts(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """**双通道 + 计数**：拒发必须同时进 logger 与上报口，且带序号（可 grep 统计）。"""
    from src.core.error_escalation_port_registry import (
        reset_error_escalation_port,
        set_error_escalation_port,
    )

    port = _RecordingPort()
    set_error_escalation_port(port)  # type: ignore[arg-type]
    try:
        with caplog.at_level("WARNING"):
            first = report_rejected_outbound_text(
                "空正文（剥掉署名后为空）", agent_id="veliona", text="【Veliona】", source="guided_reply"
            )
            second = report_rejected_outbound_text(
                "只有空括号", agent_id="veliona", text="【Veliona】()", source="guided_reply"
            )
    finally:
        reset_error_escalation_port()

    assert second == first + 1, "计数没递增"
    assert "拒发空内容" in caplog.text, "logger 通道没出声"
    assert "veliona" in caplog.text and "guided_reply" in caplog.text, "日志不具名"
    assert len(port.calls) == 2, f"上报口通道没出声（收到 {port.calls}）"
    assert "guided_reply" in port.calls[0][1]


# ── 闸：四个出站点共用的入口 ─────────────────────────────────────────


def _stub_config_port(tag_format: str):
    class _AutonomyConfig:
        speaker_tag_format = tag_format

    class _Port:
        def get_agent_autonomy_config(self):
            return _AutonomyConfig()

    return _Port()


def test_guard_refuses_empty_and_allows_normal() -> None:
    from src.core.app_config_port_registry import (
        reset_app_config_port,
        set_app_config_port,
    )
    from src.maisaka.agent_autonomy.bridge.reply_context_extender import ReplyToolContextExtender

    set_app_config_port(_stub_config_port(_FMT))  # type: ignore[arg-type]
    try:
        assert ReplyToolContextExtender.guard_outbound_text(
            "【bronya】在呢", agent_id="bronya", source="guided_reply"
        )
        assert not ReplyToolContextExtender.guard_outbound_text(
            "【Veliona】()", agent_id="veliona", source="guided_reply"
        )
        assert not ReplyToolContextExtender.guard_outbound_text(
            "", agent_id="veliona", source="guided_reply"
        )
    finally:
        reset_app_config_port()


def test_sequence_guard_keeps_image_only_reply() -> None:
    """**反向判据（防过度拒发）**：图片/表情序列没有可见文本，但它**不是空内容**，必须放行。

    这条盯的是"闸只咬纯文本序列"：少这条，富回复里的图片会被一起拒掉（把修 bug 变成造 bug）。
    """
    from src.common.data_models.message_component_data_model import (
        AtComponent,
        MessageSequence,
    )
    from src.core.app_config_port_registry import (
        reset_app_config_port,
        set_app_config_port,
    )
    from src.maisaka.agent_autonomy.bridge.reply_context_extender import ReplyToolContextExtender

    set_app_config_port(_stub_config_port(_FMT))  # type: ignore[arg-type]
    try:
        non_text_only = MessageSequence(components=[AtComponent(target_user_id="10001")])
        assert ReplyToolContextExtender.guard_outbound_sequence(
            non_text_only, agent_id="bronya", source="guided_reply"
        ), "纯非文本分量序列被误拒（会把富回复的图片/@ 一起拒掉）"

        empty_text = MessageSequence(components=[])
        assert not ReplyToolContextExtender.guard_outbound_sequence(
            empty_text, agent_id="bronya", source="guided_reply"
        ), "空序列被放行"

        only_tag = MessageSequence(components=[_text("【bronya】")])
        assert not ReplyToolContextExtender.guard_outbound_sequence(
            only_tag, agent_id="bronya", source="guided_reply"
        ), "只剩前缀的序列被放行"
    finally:
        reset_app_config_port()


def _text(value: str):
    from src.common.data_models.message_component_data_model import TextComponent

    return TextComponent(value)
