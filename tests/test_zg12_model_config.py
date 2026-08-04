"""ZG-12 模型配置重写核心测试（T56-T59 + T59c 错误分类）。"""

import pytest

from src.config.model_configs import APIProvider, ModelInfo
from src.llm_models.declaration_validator import DeclarationValidator
from src.llm_models.error_classifier import (
    PERMANENT,
    TRANSIENT,
    classify_error,
    is_permanent,
)
from src.llm_models.model_registry import ModelRegistry
from src.llm_models.model_requirement import (
    DeclarationError,
    ModelEntry,
    model_requirement,
)
from src.llm_models.task_name_mapping import resolve_legacy_task_name


def _mk_entry(name, capabilities, category="llm", provider="deepseek"):
    return ModelEntry(
        category=category, name=name, model_identifier=name,
        api_provider=provider, capabilities=frozenset(capabilities),
    )


def _mk_registry(models, providers=None):
    reg = ModelRegistry()
    reg.build_index(
        providers or [APIProvider(name="deepseek", base_url="http://x", api_key="k", client_type="openai")],
        models,
    )
    return reg


# ── T56 注册表核心 ──────────────────────────────────────────


class TestModelRegistry:
    def test_build_index_three_level(self):
        reg = _mk_registry([
            _mk_entry("flash", {"text_generation", "tool_calling"}),
            _mk_entry("bge", {"embedding"}, category="embedding", provider="ali"),
        ])
        assert reg._model_index[("llm", "flash")].name == "flash"
        assert "bge" in [m.name for m in reg._capability_index["embedding"]]

    def test_query_intersection_and_category(self):
        reg = _mk_registry([
            _mk_entry("flash", {"text_generation", "tool_calling"}),
            _mk_entry("pro", {"text_generation", "tool_calling", "reasoning"}),
            _mk_entry("bge", {"embedding"}, category="embedding"),
        ])
        r = reg.query_by_capability(["text_generation", "tool_calling"])
        assert r.name in {"flash", "pro"}
        r2 = reg.query_by_capability(["embedding"], category="embedding")
        assert r2.category == "embedding" and r2.name == "bge"

    def test_query_prefer_validation(self):
        reg = _mk_registry([
            _mk_entry("flash", {"text_generation"}),
            _mk_entry("bge", {"embedding"}, category="embedding"),
        ])
        with pytest.raises(DeclarationError) as exc:
            reg.query_by_capability(["text_generation"], prefer=(("llm", "nope"),))
        assert "不存在" in str(exc.value)
        # prefer 模型存在但缺能力（flash 无 embedding 而 bge 有）
        with pytest.raises(DeclarationError) as exc:
            reg.query_by_capability(["embedding"], prefer=(("llm", "flash"),))
        assert "缺少能力" in str(exc.value)
        with pytest.raises(DeclarationError):
            reg.query_by_capability(["vision"])

    def test_fallback_chain(self):
        reg = _mk_registry([
            _mk_entry("flash", {"text_generation"}),
            _mk_entry("pro", {"text_generation"}),
        ])
        chain = reg.get_fallback_chain("llm", "flash", "text_generation")
        assert "pro" in chain and "flash" not in chain

    def test_refresh_index_diff(self):
        @model_requirement(capabilities=["text_generation"], critical=True)
        class _Comp:  # noqa: N801
            pass

        reg = _mk_registry([_mk_entry("flash", {"text_generation"})])
        affected = reg.refresh_index(
            [APIProvider(name="deepseek", base_url="http://x", api_key="k", client_type="openai")],
            [_mk_entry("pro", {"text_generation"})],
        )
        assert "_Comp" in affected
        from src.llm_models.model_requirement import clear_declarations

        clear_declarations()


# ── T57 声明层 ──────────────────────────────────────────────


class TestDeclarationLayer:
    def test_model_requirement_decorator(self):
        @model_requirement(capabilities=["text_generation", "tool_calling"], critical=True)
        class ThinkingOrgan:  # noqa: N801
            pass

        assert ThinkingOrgan._model_requirement.capabilities == frozenset(
            {"text_generation", "tool_calling"}
        )
        assert ThinkingOrgan._model_requirement.critical is True
        from src.llm_models.model_requirement import clear_declarations, get_all_declarations

        assert "ThinkingOrgan" in get_all_declarations()
        clear_declarations()

    def test_validator_classification(self):
        @model_requirement(capabilities=["text_generation"], critical=True)
        class CriticalComp:  # noqa: N801
            pass

        @model_requirement(capabilities=["vision"], critical=False)
        class DegradedComp:  # noqa: N801
            pass

        # 全部满足 → passed
        reg = _mk_registry([
            _mk_entry("flash", {"text_generation"}),
            _mk_entry("vlm", {"vision"}),
        ])
        report = DeclarationValidator().validate_all_declarations(reg)
        assert report.status == "passed"

        # 无 text 模型 → critical fast_fail；无 vision → degraded
        reg2 = _mk_registry([_mk_entry("bge", {"embedding"}, category="embedding")])
        report2 = DeclarationValidator().validate_all_declarations(reg2)
        assert report2.status == "fast_fail"
        assert "CriticalComp" in report2.fast_fail_components
        assert "DegradedComp" in report2.degraded_components
        from src.llm_models.model_requirement import clear_declarations

        clear_declarations()


# ── T58 兼容层 ──────────────────────────────────────────────


class TestLegacyCompatibility:
    def test_resolve_legacy_task_name(self):
        assert resolve_legacy_task_name("planner") == frozenset(
            {"text_generation", "tool_calling"}
        )
        assert resolve_legacy_task_name("embedding") == frozenset({"embedding"})
        assert resolve_legacy_task_name("lpmm_entity_extract") == frozenset(
            {"text_generation", "tool_calling"}
        )
        with pytest.raises(ValueError):
            resolve_legacy_task_name("unknown_task")


# ── T59c 错误分类 ───────────────────────────────────────────


class TestErrorClassifier:
    def test_permanent_codes(self):
        for code in (400, 401, 402, 403, 404, 422):
            assert classify_error(code) == PERMANENT, code
            assert is_permanent(code), code

    def test_transient_codes(self):
        for code in (408, 429, 500, 502, 503, 504, 529):
            assert classify_error(code) == TRANSIENT, code

    def test_unknown_code(self):
        assert classify_error(599) == "unknown"
        assert not is_permanent(599)


# ── ModelInfo 默认迁移（T14 配套）────────────────────────────


class TestModelInfoDefaultCapabilities:
    def test_category_default_migration(self):
        mi = ModelInfo(model_identifier="m1", name="t1", api_provider="ali")
        assert {"text_generation", "tool_calling"} <= mi.capabilities

        emb = ModelInfo(
            model_identifier="b1", name="b1", api_provider="ali", category="embedding"
        )
        assert emb.capabilities == {"embedding"}

        vis = ModelInfo(
            model_identifier="v1", name="v1", api_provider="ali", visual=True
        )
        assert "vision" in vis.capabilities
        assert "text_generation" in vis.capabilities

    def test_category_name_duplicate_rejected(self):
        from src.config.config import ModelConfig

        providers = [APIProvider(name="ali", base_url="http://x", api_key="k", client_type="openai")]
        with pytest.raises(ValueError) as exc:
            ModelConfig(
                models=[
                    ModelInfo(model_identifier="a1", name="same", api_provider="ali"),
                    ModelInfo(model_identifier="a2", name="same", api_provider="ali"),
                ],
                api_providers=providers,
            )
        assert "重复模型标识" in str(exc.value)

        # 不同 category 同名合法
        ModelConfig(
            models=[
                ModelInfo(model_identifier="a1", name="same", api_provider="ali"),
                ModelInfo(
                    model_identifier="a2", name="same", api_provider="ali", category="embedding"
                ),
            ],
            api_providers=providers,
        )
