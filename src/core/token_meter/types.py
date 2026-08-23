"""ZG-N6 统一 Token 计量服务——数据类型。

对齐 dsh `@deepseek-ai/dsh-token-meter` 的 types.ts，
所有类型深度不可变（frozen dataclass），保证 measure() 返回的快照不被消费方篡改。
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class TokenSurfaceNode:
    """表层节点——带位置 + token 数 + 类型标签。

    对齐 dsh surface-fold.ts 的 SurfaceNode 概念。
    """

    tokens: int
    position: int
    kind: str


@dataclass(frozen=True)
class TokenMeasurementBaseline:
    """基线——计量来源标记。

    kind 取值：
    - "none"——无基线（初版默认，完整启发式估算）
    - "estimated"——启发式估算基线
    - "usage"——提供方真实用量基线（锚点复用，后续按需实现）
    """

    kind: str
    tokens: int


@dataclass(frozen=True)
class TokenMeasurement:
    """压力快照——measure() 返回值。

    深度不可变（nodes 用 tuple），消费方持有至本次决策完成。
    对齐 dsh TokenMeasurement。

    Attributes:
        total_tokens: 总 token 数（含非表层如 system prompt）
        surface_tokens: 表层 token 数（消息序列）
        nodes: 表层节点序列（tuple 保证不可变）
        log_revision: 日志修订号（初版固定 0）
        baseline: 基线标记
        surface_delta_tokens: 表层增量（相对上次 measure，初版固定 0）
    """

    total_tokens: int
    surface_tokens: int
    nodes: tuple[TokenSurfaceNode, ...]
    log_revision: int
    baseline: TokenMeasurementBaseline
    surface_delta_tokens: int