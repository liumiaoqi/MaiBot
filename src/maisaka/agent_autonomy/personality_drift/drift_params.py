"""M1: 角色基因型——8-12 个行为参数的 dataclass。

参数存于 LayeredPersonality 的 EXPRESSION 层文本，通过 to_layer_text / from_layer_text 序列化。
漂移只作用于 EXPRESSION/EXPERIENCE 层，EXISTENCE 层不可改（性格内核稳定）。
"""

import json
from dataclasses import dataclass, field, fields
from typing import List


@dataclass
class DriftParam:
    """单个行为参数。"""

    name: str
    value: float
    min_val: float
    max_val: float
    initial_value: float
    history: List[float] = field(default_factory=list)

    def clamp(self) -> None:
        """将值约束到 [min_val, max_val]。"""
        self.value = max(self.min_val, min(self.max_val, self.value))

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "value": self.value,
            "min": self.min_val,
            "max": self.max_val,
            "initial": self.initial_value,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "DriftParam":
        return cls(
            name=d["name"],
            value=d["value"],
            min_val=d["min"],
            max_val=d["max"],
            initial_value=d["initial"],
        )


def _param(name: str, value: float, lo: float, hi: float) -> DriftParam:
    return DriftParam(name=name, value=value, min_val=lo, max_val=hi, initial_value=value)


@dataclass
class DriftParams:
    """角色基因型——10 个行为参数。

    来源：线虫进化实验线 exp41-50 洞见映射 + jiwen B1-B6 借鉴点。
    """

    exploration_rate: DriftParam = field(default_factory=lambda: _param("exploration_rate", 0.5, 0.0, 1.0))
    social_polarity: DriftParam = field(default_factory=lambda: _param("social_polarity", 0.0, -1.0, 1.0))
    recall_diversity: DriftParam = field(default_factory=lambda: _param("recall_diversity", 0.3, 0.0, 1.0))
    vitality_intensity: DriftParam = field(default_factory=lambda: _param("vitality_intensity", 0.6, 0.0, 1.0))
    vitality_decay: DriftParam = field(default_factory=lambda: _param("vitality_decay", 0.1, 0.0, 1.0))
    goal_persistence: DriftParam = field(default_factory=lambda: _param("goal_persistence", 0.5, 0.0, 1.0))
    social_strength: DriftParam = field(default_factory=lambda: _param("social_strength", 0.5, 0.0, 1.0))
    empathy: DriftParam = field(default_factory=lambda: _param("empathy", 0.5, 0.0, 1.0))
    curiosity: DriftParam = field(default_factory=lambda: _param("curiosity", 0.6, 0.0, 1.0))
    emotion_volatility: DriftParam = field(default_factory=lambda: _param("emotion_volatility", 0.3, 0.0, 1.0))

    def all_params(self) -> List[DriftParam]:
        """返回所有参数列表。"""
        return [getattr(self, f.name) for f in fields(self)]

    def get_param(self, name: str) -> DriftParam | None:
        """按名取参数，不存在返回 None。"""
        for p in self.all_params():
            if p.name == name:
                return p
        return None

    def to_layer_text(self) -> str:
        """序列化为 EXPRESSION 层文本（JSON）。"""
        return json.dumps(
            {p.name: p.to_dict() for p in self.all_params()},
            ensure_ascii=False,
            indent=2,
        )

    @classmethod
    def from_layer_text(cls, text: str) -> "DriftParams":
        """从 EXPRESSION 层文本解析。空文本返回默认值。"""
        if not text or not text.strip():
            return cls()
        try:
            data = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            return cls()
        params = cls()
        for p in params.all_params():
            d = data.get(p.name)
            if d is not None:
                loaded = DriftParam.from_dict(d)
                loaded.history = p.history
                setattr(params, _field_name_for_param(params, p.name), loaded)
        return params

    def clamp_all(self) -> None:
        """所有参数 clamp 到边界。"""
        for p in self.all_params():
            p.clamp()


def _field_name_for_param(params: DriftParams, param_name: str) -> str:
    """根据参数名找字段名。"""
    for f in fields(params):
        p = getattr(params, f.name)
        if p.name == param_name:
            return f.name
    return param_name