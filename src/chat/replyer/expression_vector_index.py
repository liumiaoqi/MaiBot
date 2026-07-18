"""兼容 re-export — 已迁移到 src/maisaka/replyer/expression_vector_index.py。

此文件保留 6 个月供兼容，后续删除。请从新路径导入。
"""
from src.maisaka.replyer.expression_vector_index import *  # noqa: F401,F403
from src.maisaka.replyer.expression_vector_index import (
    ExpressionVectorIndex,
    ExpressionVectorIndexUpsertItem,
    expression_vector_index,
    normalize_text,
    resolve_project_path,
)
