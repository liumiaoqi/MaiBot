"""关系等级与快照模型。"""

from __future__ import annotations

from enum import IntEnum

from pydantic import BaseModel, Field


class RelationshipLevel(IntEnum):
    """关系等级枚举，值越大关系越近。"""

    STRANGER = 0
    ACQUAINTANCE = 1
    FAMILIAR = 2
    INTIMATE = 3

    @classmethod
    def from_score(cls, score: float) -> "RelationshipLevel":
        """根据分数判断关系等级。"""
        if score >= 900:
            return cls.INTIMATE
        if score >= 650:
            return cls.FAMILIAR
        if score >= 350:
            return cls.ACQUAINTANCE
        return cls.STRANGER

    def label_zh(self) -> str:
        """返回中文标签。"""
        labels = {
            RelationshipLevel.STRANGER: "陌生人",
            RelationshipLevel.ACQUAINTANCE: "认识",
            RelationshipLevel.FAMILIAR: "熟悉",
            RelationshipLevel.INTIMATE: "亲密",
        }
        return labels.get(self, "陌生人")


LEVEL_THRESHOLDS = {
    RelationshipLevel.STRANGER: 0,
    RelationshipLevel.ACQUAINTANCE: 350,
    RelationshipLevel.FAMILIAR: 650,
    RelationshipLevel.INTIMATE: 900,
}


class RelationshipSnapshot(BaseModel):
    """智能体与用户的关系快照。"""

    agent_id: str = Field(default="", description="智能体ID")
    user_id: str = Field(default="", description="用户ID")
    score: float = Field(default=0.0, ge=0.0, le=1000.0, description="关系分数(0-1000)")
    level: RelationshipLevel = Field(default=RelationshipLevel.STRANGER, description="关系等级")
    interaction_count: int = Field(default=0, ge=0, description="累计互动次数")
    last_interaction_at: float = Field(default=0.0, description="最后互动时间戳")
    created_at: float = Field(default=0.0, description="关系创建时间戳")

    def update_score(self, delta: float) -> None:
        """更新关系分数并重新计算等级。"""
        self.score = max(0.0, min(1000.0, self.score + delta))
        new_level = RelationshipLevel.from_score(self.score)
        self.level = new_level

    def to_prompt_text(self) -> str:
        """生成用于提示词注入的关系描述。"""
        level_label = self.level.label_zh()
        if self.level == RelationshipLevel.STRANGER:
            return f"你与对方的关系：{level_label}"

        parts = [f"你与对方的关系：{level_label}（分数{self.score:.0f}/1000）"]

        if self.level == RelationshipLevel.INTIMATE:
            parts.append("你们非常亲密，可以无话不谈")
        elif self.level == RelationshipLevel.FAMILIAR:
            parts.append("你们很熟悉，可以随意聊天")
        elif self.level == RelationshipLevel.ACQUAINTANCE:
            parts.append("你们认识但还不够熟悉")

        return "。".join(parts)