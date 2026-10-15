"""`AttrDocBase` 方法白名单：`@field_validator` / `@model_validator` 可用，**其它方法仍被拒**。

## 背景（task-6 追加）

`config_base.py` 原先一刀切：配置类体里出现 `model_post_init` 以外的方法就抛 `AttributeError`
⇒ `ConfigSchemaGenerator.generate_config_schema()` 直接 500 ⇒ pydantic 官方的约束写法
**结构性不可用**，约束只能写成 `model_post_init` 里的 if/raise —— 而那种写法**进不了生成的 schema**，
与"schema 单源"直接冲突（0 段盘底那句"0 validator 装饰器"的真相）。

2026-10-16 改成**白名单**：`model_post_init` + 被 `@field_validator` / `@model_validator`
装饰的函数。`@property`、普通辅助方法、内部函数**仍然被拒**（先例：`model_configs.py` 的
`raw_api_key_of` 就是为绕开本限制才做成模块级函数的）。

## 本文件是这次改动的判据

- **E1** 两种校验器**真能跑**（下面是两条最小配置类，断言校验生效）
- **E2** **字段说明提取不受影响**（方法被跳过、`AnnAssign + 字符串` 照旧配对，`field_docs` 完整）
- **E3** **生成器不再因方法报错**（改动前这里会 `AttributeError`）
- **E4** 现有 93 个配置类的 `field_docs` 与 schema 输出**逐字节不变** —— 由
  `C:\\hub\\.scratch\\cfg-schema-dump-docs-schema.py` 的前后 sha256 比对给出
  （`98f5fc813fa8c4e474a552c59a80b00c3441b56771903d31af8944f3028a8299`），不在本文件内跑

⚠️ **反向边界**：白名单**不是**"允许任意方法"。下面 `_PlainMethodConfig` / `_PropertyConfig`
两条用例就是这条边界的哨兵 —— 它们一旦变绿，说明有人把判据放宽了。
"""

import pydantic
import pytest
from pydantic import ValidationError, field_validator, model_validator

from src.config.config_base import ConfigBase, Field
from src.webui.config_schema import ConfigSchemaGenerator


class _WithFieldValidator(ConfigBase):
    """E1/E2/E3 · 字段级校验器：`min_length` 表达不了的约束（这里用"不许全空白"做示例）"""

    name: str = Field(default="ok")
    """名字。"""

    @field_validator("name")
    @classmethod
    def _reject_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("name 不能是空白")
        return value


class _WithModelValidator(ConfigBase):
    """E1 · 模型级校验器：**跨字段**条件（`Field(...)` 表达不了的那一类）"""

    low: int = Field(default=1)
    """下界。"""

    high: int = Field(default=10)
    """上界。"""

    @model_validator(mode="after")
    def _check_order(self):
        if self.high < self.low:
            raise ValueError("high 不能小于 low")
        return self


class _WithQualifiedDecorator(ConfigBase):
    """白名单判据要认 `ast.Attribute` 形式（`@pydantic.field_validator`），不只是裸名"""

    value: int = Field(default=0)
    """一个值。"""

    @pydantic.field_validator("value")
    @classmethod
    def _reject_negative(cls, value: int) -> int:
        if value < 0:
            raise ValueError("value 不能为负")
        return value


class _PlainMethodConfig(ConfigBase):
    """反向边界哨兵：普通辅助方法**仍然不许**出现在配置类体里"""

    value: int = Field(default=0)
    """一个值。"""

    def helper(self) -> int:  # noqa: PLR6301 -- 故意留一个普通方法，用于断言白名单没被放宽
        return self.value


class _PropertyConfig(ConfigBase):
    """反向边界哨兵：`@property` **仍然不许**（`model_configs.py:raw_api_key_of` 的既有先例）"""

    value: int = Field(default=0)
    """一个值。"""

    @property
    def doubled(self) -> int:
        return self.value * 2


# ── E1：两种校验器真能跑 ──────────────────────────────────────────────────────


def test_field_validator_actually_validates():
    assert _WithFieldValidator(name="麦麦").name == "麦麦"
    with pytest.raises(ValidationError):
        _WithFieldValidator(name="   ")


def test_model_validator_actually_validates():
    assert _WithModelValidator(low=1, high=5).high == 5
    with pytest.raises(ValidationError):
        _WithModelValidator(low=5, high=1)


def test_qualified_decorator_form_also_works():
    """`@pydantic.field_validator`（`ast.Attribute` 分支）同样被放行且生效。"""
    assert _WithQualifiedDecorator(value=3).value == 3
    with pytest.raises(ValidationError):
        _WithQualifiedDecorator(value=-1)


# ── E2：字段说明提取不受影响 ──────────────────────────────────────────────────


def test_field_docs_survive_methods():
    """方法被跳过、`AnnAssign + 字符串` 照旧配对 ⇒ 带校验器的类 `field_docs` 依然完整。"""
    assert _WithFieldValidator.get_class_field_docs() == {"name": "名字。"}
    assert _WithModelValidator.get_class_field_docs() == {"low": "下界。", "high": "上界。"}
    assert _WithQualifiedDecorator.get_class_field_docs() == {"value": "一个值。"}


def test_field_docs_reached_via_generator():
    """生成器内部走的是同一条提取路径（`_get_class_field_docs`），description 应来自 docstring。"""
    schema = ConfigSchemaGenerator.generate_config_schema(_WithModelValidator)
    by_name = {node["name"]: node for node in schema["fields"]}
    assert by_name["low"]["description"] == "下界。"
    assert by_name["high"]["description"] == "上界。"


# ── E3：生成器不再因方法报错 ──────────────────────────────────────────────────


@pytest.mark.parametrize(
    "config_class",
    [_WithFieldValidator, _WithModelValidator, _WithQualifiedDecorator],
    ids=["field_validator", "model_validator", "qualified_decorator"],
)
def test_generator_no_longer_chokes_on_methods(config_class):
    """改动前：`generate_config_schema` 抛 `AttributeError`（端点 500）。现在必须正常出字段。"""
    schema = ConfigSchemaGenerator.generate_config_schema(config_class)
    assert [node["name"] for node in schema["fields"]], "至少应产出一个字段"


# ── 反向边界：白名单没有被放宽成"任意方法" ────────────────────────────────────


def test_plain_method_still_rejected():
    with pytest.raises(AttributeError, match="model_post_init"):
        _PlainMethodConfig.get_class_field_docs()


def test_property_still_rejected():
    with pytest.raises(AttributeError, match="model_post_init"):
        _PropertyConfig.get_class_field_docs()


def test_plain_method_also_blocks_generator():
    """白名单没放宽 ⇒ 生成器对普通方法**仍然**报错（端点的 500 保护还在）。"""
    with pytest.raises(AttributeError, match="model_post_init"):
        ConfigSchemaGenerator.generate_config_schema(_PlainMethodConfig)
