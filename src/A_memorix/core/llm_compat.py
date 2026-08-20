"""A_memorix → src.llm_models 薄适配层（隔离违规修复）。

本模块是 A_memorix 内部唯一允许导入 src.llm_models 的适配层（host_service 除外）。
集中依赖于此，便于后续重构为 Protocol 注入。

TODO: 后续将 model_requirement 改为通过 port_registry 获取，
彻底消除 A_memorix 对 src.llm_models 的编译期依赖。
"""

from src.llm_models.model_requirement import model_requirement  # noqa: TID251

__all__ = ["model_requirement"]