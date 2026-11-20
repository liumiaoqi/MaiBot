"""`ModelConfigPort` 的类型视图与真实配置类的字段对账。

为什么需要：本仓没有类型检查器（`pyproject.toml` 无 mypy/pyright，CI 只跑 ruff），
`src/core/types.py` 里的 `*Like` Protocol 只是**文档级**约束。旧配置类删掉一个字段时，
视图不会报错——协议里仍写着一个不存在的字段，消费方要到运行时才缺数据。

判据：视图声明的每个字段都必须在真实类上存在（防虚构）。
**反向不成立**：真实类多出字段不算错——视图按设计只声明本接缝消费者实际读到的字段，
新增但无人读的字段本来就不该进契约。
"""

import pytest

from src.config.config import ModelConfig
from src.config.model_configs import APIProvider, ModelInfo, ModelTaskConfig, TaskConfig

from src.core import types as core_types

VIEW_PAIRS = [
    ("TaskConfigLike", core_types.TaskConfigLike, TaskConfig),
    ("ModelInfoLike", core_types.ModelInfoLike, ModelInfo),
    ("APIProviderLike", core_types.APIProviderLike, APIProvider),
    ("ModelTaskConfigLike", core_types.ModelTaskConfigLike, ModelTaskConfig),
    ("ModelConfigLike", core_types.ModelConfigLike, ModelConfig),
]


@pytest.mark.parametrize(
    ("view_name", "view", "real"),
    VIEW_PAIRS,
    ids=[pair[0] for pair in VIEW_PAIRS],
)
def test_view_declares_only_existing_fields(view_name: str, view: type, real: type) -> None:
    """视图声明的字段必须在真实类上存在，且视图不能是空壳。"""
    declared = set(getattr(view, "__annotations__", {}))
    assert declared, f"{view_name} 一个字段都没声明——空视图等于没有契约"

    missing = declared - set(real.model_fields)
    assert not missing, (
        f"{view_name} 声明了 {real.__name__} 上不存在的字段 {sorted(missing)}："
        f"真实类删字段后视图没跟着改，这份契约已经失效"
    )


def test_model_config_view_covers_exactly_the_consumed_attributes() -> None:
    """`get_model_config()` 的消费者只读三样；扩大或缩小都要显式改这条测试。"""
    declared = set(core_types.ModelConfigLike.__annotations__)
    assert declared == {"models", "model_task_config", "api_providers"}
