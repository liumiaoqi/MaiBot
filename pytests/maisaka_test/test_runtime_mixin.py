"""runtime_mixin 单元测试。

覆盖 MaisakaRuntimeDisplayMixin 的静态方法：
_build_cycle_time_records_text / _filter_redundant_tool_results /
_build_tool_metrics_text / _get_tool_detail_labels /
_normalize_tool_card_body_lines / _build_prompt_preview_metadata_from_tool_metrics。
"""

from src.maisaka.display.runtime_mixin import MaisakaRuntimeDisplayMixin


class TestBuildCycleTimeRecordsText:
    """_build_cycle_time_records_text 行为测试。"""

    def test_empty_returns_placeholder(self):
        assert MaisakaRuntimeDisplayMixin._build_cycle_time_records_text({}) == "流程耗时：无"

    def test_planner_and_tool_calls_ordered(self):
        result = MaisakaRuntimeDisplayMixin._build_cycle_time_records_text(
            {"planner": 1.5, "tool_calls": 0.5}
        )
        assert "Planner" in result
        assert "工具执行" in result
        # Planner 应在工具执行之前
        assert result.index("Planner") < result.index("工具执行")

    def test_extra_keys_appended(self):
        result = MaisakaRuntimeDisplayMixin._build_cycle_time_records_text(
            {"planner": 1.0, "custom_stage": 2.0}
        )
        assert "custom_stage" in result

    def test_non_numeric_values_skipped(self):
        result = MaisakaRuntimeDisplayMixin._build_cycle_time_records_text(
            {"planner": "not-a-number"}
        )
        assert result == "流程耗时：无"


class TestFilterRedundantToolResults:
    """_filter_redundant_tool_results 行为测试。"""

    def test_no_detail_returns_all_non_empty(self):
        result = MaisakaRuntimeDisplayMixin._filter_redundant_tool_results(
            tool_results=["摘要A", "摘要B", ""],
            tool_detail_results=[],
        )
        assert result == ["摘要A", "摘要B"]

    def test_filters_summaries_in_detail(self):
        result = MaisakaRuntimeDisplayMixin._filter_redundant_tool_results(
            tool_results=["重复摘要", "新摘要"],
            tool_detail_results=[
                {"summary": "重复摘要", "detail": {"key": "value"}},
            ],
        )
        assert result == ["新摘要"]

    def test_detail_without_dict_detail_keeps_summary(self):
        # detail 字段为空 dict 时不计入 detailed_summaries
        result = MaisakaRuntimeDisplayMixin._filter_redundant_tool_results(
            tool_results=["摘要"],
            tool_detail_results=[{"summary": "摘要", "detail": {}}],
        )
        assert result == ["摘要"]

    def test_non_string_results_skipped(self):
        result = MaisakaRuntimeDisplayMixin._filter_redundant_tool_results(
            tool_results=["有效", 123, None],
            tool_detail_results=[],
        )
        assert result == ["有效"]


class TestBuildToolMetricsText:
    """_build_tool_metrics_text 行为测试。"""

    def test_empty_metrics(self):
        # 空 dict 时 model_name = str(None) = "None"（truthy），输出 "模型：None"
        result = MaisakaRuntimeDisplayMixin._build_tool_metrics_text({})
        assert result == "模型：None"

    def test_model_name(self):
        result = MaisakaRuntimeDisplayMixin._build_tool_metrics_text(
            {"model_name": "deepseek-v3"}
        )
        assert "模型：deepseek-v3" in result

    def test_token_counts(self):
        result = MaisakaRuntimeDisplayMixin._build_tool_metrics_text(
            {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}
        )
        assert "输入 100" in result
        assert "输出 50" in result
        assert "总计 150" in result

    def test_timing_metrics(self):
        result = MaisakaRuntimeDisplayMixin._build_tool_metrics_text(
            {"prompt_ms": 10.5, "llm_ms": 200.3, "overall_ms": 210.8}
        )
        assert "prompt 10.5 ms" in result
        assert "llm 200.3 ms" in result
        assert "overall 210.8 ms" in result

    def test_large_token_uses_k_suffix(self):
        result = MaisakaRuntimeDisplayMixin._build_tool_metrics_text(
            {"total_tokens": 20000}
        )
        assert "总计 20.0k" in result


class TestGetToolDetailLabels:
    """_get_tool_detail_labels 行为测试。"""

    def test_reply_tool(self):
        labels = MaisakaRuntimeDisplayMixin._get_tool_detail_labels("reply")
        assert labels["prompt_title"] == "Reply Prompt"
        assert labels["prompt_category"] == "replyer"
        assert labels["request_kind"] == "replyer"

    def test_send_emoji_tool(self):
        labels = MaisakaRuntimeDisplayMixin._get_tool_detail_labels("send_emoji")
        assert labels["prompt_title"] == "Emotion Prompt"
        assert labels["request_kind"] == "emotion"

    def test_generic_tool(self):
        labels = MaisakaRuntimeDisplayMixin._get_tool_detail_labels("custom_tool")
        assert labels["prompt_title"] == "custom_tool Prompt"
        assert labels["request_kind"] == "sub_agent"

    def test_empty_tool_name(self):
        labels = MaisakaRuntimeDisplayMixin._get_tool_detail_labels("")
        assert labels["prompt_title"] == "tool Prompt"

    def test_case_insensitive(self):
        labels_upper = MaisakaRuntimeDisplayMixin._get_tool_detail_labels("REPLY")
        labels_lower = MaisakaRuntimeDisplayMixin._get_tool_detail_labels("reply")
        assert labels_upper == labels_lower


class TestNormalizeToolCardBodyLines:
    """_normalize_tool_card_body_lines 行为测试。"""

    def _make_instance(self):
        # mixin 类无需 __init__，用 __new__ 绕过
        return MaisakaRuntimeDisplayMixin.__new__(MaisakaRuntimeDisplayMixin)

    def test_string_split_by_lines(self):
        instance = self._make_instance()
        result = instance._normalize_tool_card_body_lines("a\nb\n\nc")
        assert result == ["a", "b", "c"]

    def test_list_of_items(self):
        instance = self._make_instance()
        result = instance._normalize_tool_card_body_lines(["x", "y", ""])
        assert result == ["x", "y"]

    def test_empty_string(self):
        instance = self._make_instance()
        assert instance._normalize_tool_card_body_lines("") == []

    def test_non_string_non_list(self):
        instance = self._make_instance()
        assert instance._normalize_tool_card_body_lines(None) == []
        assert instance._normalize_tool_card_body_lines(123) == []


class TestBuildPromptPreviewMetadataFromToolMetrics:
    """_build_prompt_preview_metadata_from_tool_metrics 行为测试。"""

    def test_non_dict_returns_empty(self):
        assert MaisakaRuntimeDisplayMixin._build_prompt_preview_metadata_from_tool_metrics(None) == {}
        assert MaisakaRuntimeDisplayMixin._build_prompt_preview_metadata_from_tool_metrics("string") == {}
        assert MaisakaRuntimeDisplayMixin._build_prompt_preview_metadata_from_tool_metrics(123) == {}

    def test_extracts_model_name(self):
        result = MaisakaRuntimeDisplayMixin._build_prompt_preview_metadata_from_tool_metrics(
            {"model_name": "test-model"}
        )
        assert result["model_name"] == "test-model"

    def test_extracts_duration_from_llm_ms(self):
        result = MaisakaRuntimeDisplayMixin._build_prompt_preview_metadata_from_tool_metrics(
            {"llm_ms": 150.0}
        )
        assert result["duration_ms"] == 150.0

    def test_extracts_duration_from_overall_ms(self):
        result = MaisakaRuntimeDisplayMixin._build_prompt_preview_metadata_from_tool_metrics(
            {"overall_ms": 300.0}
        )
        assert result["duration_ms"] == 300.0

    def test_llm_ms_takes_precedence_over_overall_ms(self):
        result = MaisakaRuntimeDisplayMixin._build_prompt_preview_metadata_from_tool_metrics(
            {"llm_ms": 100.0, "overall_ms": 200.0}
        )
        assert result["duration_ms"] == 100.0

    def test_empty_metrics(self):
        # 空 dict 时 model_name = str(None) = "None"（truthy），写入 model_name
        result = MaisakaRuntimeDisplayMixin._build_prompt_preview_metadata_from_tool_metrics({})
        assert result == {"model_name": "None"}