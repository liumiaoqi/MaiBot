"""token_estimator 纯函数单元测试。

覆盖 estimate_text / estimate_system_prompt / estimate_tools_schema /
estimate_message / estimate_messages 的正常、边界与异常输入。

规格基线 = `src/core/token_meter/estimate.py` 文件头：每 token ≈ 4 字符
（`CHARS_PER_TOKEN = 4`，对齐 dsh `@deepseek-ai/dsh-token-meter`）+ 结构开销
`BLOCK_OVERHEAD = 4` / `ROLE_OVERHEAD = 4`。

本文件在 ZG-N6 迁移（commit `0e088ca42`）前写于旧的 2 字符/token 规格
（旧实现见 `0e088ca42^:src/maisaka/context/token_estimator.py`），迁移后未同步，
本次按 4 字符/token 重算断言与注释。
"""

from types import SimpleNamespace

from src.maisaka.context.token_estimator import (
    BLOCK_OVERHEAD,
    CHARS_PER_TOKEN,
    DEFAULT_CONTEXT_WINDOW,
    ROLE_OVERHEAD,
    estimate_message,
    estimate_messages,
    estimate_system_prompt,
    estimate_text,
    estimate_tools_schema,
)


class TestEstimateText:
    """estimate_text 行为测试。"""

    def test_empty_string_returns_zero(self):
        assert estimate_text("") == 0

    def test_single_char_ceil_to_one(self):
        # len=1, ceil(1/4)=1
        assert estimate_text("a") == 1

    def test_two_chars_one_token(self):
        # len=2, ceil(2/4)=1
        assert estimate_text("ab") == 1

    def test_three_chars_one_token(self):
        # len=3, ceil(3/4)=1（2 字符/token 的旧规格下是 2）
        assert estimate_text("abc") == 1

    def test_chinese_text(self):
        # 中文 4 字符 → ceil(4/4)=1。CJK 按字符计价会低估真实 token——
        # estimate.py 头注明「CJK 低估已知不修」（对齐 dsh 已知限制），此处只钉现行启发式。
        assert estimate_text("你好世界") == 1

    def test_long_text_scaling(self):
        text = "x" * 100
        # ceil(100/4)=25
        assert estimate_text(text) == 25

    def test_odd_length_ceil(self):
        # len=5 → ceil(5/4)=2
        assert estimate_text("abcde") == 2


class TestEstimateSystemPrompt:
    """estimate_system_prompt 行为测试。"""

    def test_empty_prompt_only_overhead(self):
        # 空文本 0 + BLOCK_OVERHEAD
        assert estimate_system_prompt("") == BLOCK_OVERHEAD

    def test_prompt_includes_block_overhead(self):
        result = estimate_system_prompt("abcd")
        # estimate_text("abcd")=1 + BLOCK_OVERHEAD
        assert result == 1 + BLOCK_OVERHEAD

    def test_prompt_structure_overhead_constant(self):
        # 验证结构开销常量
        assert BLOCK_OVERHEAD == 4


class TestEstimateToolsSchema:
    """estimate_tools_schema 行为测试。"""

    def test_empty_list_only_overhead(self):
        # json.dumps([]) = "[]" len=2 → ceil(2/4)=1 + BLOCK_OVERHEAD
        result = estimate_tools_schema([])
        assert result == 1 + BLOCK_OVERHEAD

    def test_simple_tools(self):
        tools = [{"name": "search"}]
        import json

        expected_text = json.dumps(tools, ensure_ascii=False)
        expected = estimate_text(expected_text) + BLOCK_OVERHEAD
        assert estimate_tools_schema(tools) == expected

    def test_chinese_in_tools_preserved(self):
        tools = [{"description": "搜索工具"}]
        import json

        expected_text = json.dumps(tools, ensure_ascii=False)
        # ensure_ascii=False 保证中文不被转义
        assert "搜索工具" in expected_text
        assert estimate_tools_schema(tools) == estimate_text(expected_text) + BLOCK_OVERHEAD


class TestEstimateMessage:
    """estimate_message 行为测试。"""

    def test_empty_projection_returns_role_and_block_overhead(self):
        message = SimpleNamespace(processed_plain_text="")
        result = estimate_message(message)
        assert result == BLOCK_OVERHEAD + ROLE_OVERHEAD

    def test_message_with_text(self):
        message = SimpleNamespace(processed_plain_text="abcd")
        # estimate_text("abcd")=1 + BLOCK_OVERHEAD + ROLE_OVERHEAD
        assert estimate_message(message) == 1 + BLOCK_OVERHEAD + ROLE_OVERHEAD

    def test_enable_visual_message_param_accepted(self):
        # 轻量近似不依赖 enable_visual_message，两个值应相等
        message = SimpleNamespace(processed_plain_text="hello")
        assert estimate_message(message, enable_visual_message=True) == estimate_message(
            message, enable_visual_message=False
        )

    def test_missing_projection_attribute_degrades_without_crashing(self):
        # 缺 processed_plain_text 属性：生产不会出现这种形状——LLMContextMessage 的
        # processed_plain_text 是 @abstractmethod，每个具体子类都实现
        # （src/maisaka/context/messages.py:582）。此用例只钉 estimate_message docstring
        # 承诺的「不抛异常」：实现落到「未知 → str(message) 后启发式计价 + 结构开销」
        # 兜底（estimate.py:110 / 末行 return），故断言该兜底规则本身，不钉具体数值
        # ——数值是 repr 长度折 token，随 repr 变而变。
        message = SimpleNamespace()
        result = estimate_message(message)
        assert isinstance(result, int)
        assert result == estimate_text(str(message)) + BLOCK_OVERHEAD + ROLE_OVERHEAD

    def test_none_projection_value_degrades_without_crashing(self):
        # 投影属性值为 None（非缺失，但同样走不到 projection 分支：estimate.py:146
        # 用 `is not None` 判据），最终落到同一「未知 → str(message)」兜底。
        message = SimpleNamespace(processed_plain_text=None)
        result = estimate_message(message)
        assert isinstance(result, int)
        assert result == estimate_text(str(message)) + BLOCK_OVERHEAD + ROLE_OVERHEAD

    def test_projection_property_exception_degrades_without_crashing(self):
        # 取投影时抛异常 → estimate.py:153-156 的 except 吞掉后走未知兜底。
        #
        # 不用 MagicMock 构造：MagicMock().content 不是 None 而是一个 Mock，
        # 实现会先在 content 分支落空（既非 str 也非 list）再取投影，与注释声称的
        # 「取投影抛异常」路径不一致；且断言值会退化成 mock 地址的 repr 长度
        # （`<MagicMock id='1417891845792'>` → ceil(30/4)+8=16），是形状噪声而非规格。
        # 本仓已有同类教训：mock 能造出生产造不出的形状（`watchdog.runner_health`
        # 事故，AGENTS.md §七；同目录 conftest.py 亦因此装配真实实例）。
        touched: list[int] = []

        class ExplodingProjection:
            @property
            def processed_plain_text(self) -> str:
                touched.append(1)
                raise RuntimeError("boom")

            def __str__(self) -> str:
                return "<ExplodingProjection>"

        message = ExplodingProjection()
        result = estimate_message(message)
        # 证明确实触达了投影属性并抛异常，而不是被前面某个分支短路
        assert touched == [1]
        assert isinstance(result, int)
        assert result == estimate_text(str(message)) + BLOCK_OVERHEAD + ROLE_OVERHEAD


class TestEstimateMessages:
    """estimate_messages 行为测试。"""

    def test_empty_list_returns_zero(self):
        assert estimate_messages([]) == 0

    def test_single_message(self):
        message = SimpleNamespace(processed_plain_text="abcd")
        assert estimate_messages([message]) == estimate_message(message)

    def test_multiple_messages_summed(self):
        m1 = SimpleNamespace(processed_plain_text="ab")  # 1 + 8
        m2 = SimpleNamespace(processed_plain_text="abcd")  # 1 + 8
        m3 = SimpleNamespace(processed_plain_text="")  # 0 + 8
        total = estimate_messages([m1, m2, m3])
        assert total == estimate_message(m1) + estimate_message(m2) + estimate_message(m3)

    def test_constants_consistency(self):
        # ZG-N6 迁移把 CHARS_PER_TOKEN 从 2 改成 4（estimate.py:14，对齐 dsh）
        assert CHARS_PER_TOKEN == 4
        assert DEFAULT_CONTEXT_WINDOW == 65536
        assert ROLE_OVERHEAD == 4
