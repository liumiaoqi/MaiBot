from pydantic import BaseModel, Field


class InteractionTriggerConfig(BaseModel):
    enabled: bool = True
    cooldown_minutes: int = Field(default=30, ge=5)
    max_interactions_per_hour: int = Field(default=2, ge=1, le=10)
    max_interactions_per_day: int = Field(default=8, ge=1, le=20)
    echo_enabled: bool = True
    echo_max_depth: int = Field(default=3, ge=1, le=5)
    echo_decay_ratio: float = Field(default=0.5, ge=0.1, le=1.0)
    monologue_enabled: bool = True
    monologue_min_interval_minutes: int = Field(default=15, ge=5)
    monologue_idle_threshold_minutes: int = Field(default=30, ge=10)
    monologue_emotion_intensity_threshold: int = Field(default=40, ge=0, le=100)


class MemoryDrivenTriggerConfig(BaseModel):
    enabled: bool = True
    positive_memory_trigger_bonus: float = Field(default=0.2, ge=0.0, le=0.5)
    negative_memory_trigger_penalty: float = Field(default=0.3, ge=0.0, le=0.5)
    reunion_trigger_probability: float = Field(default=0.15, ge=0.0, le=1.0)
    reunion_threshold_hours: int = Field(default=24, ge=6)
    memory_weight_in_trigger: float = Field(default=0.3, ge=0.0, le=1.0)
    propagated_memory_weight_ratio: float = Field(default=0.5, ge=0.0, le=1.0)
    memory_decay_days: int = Field(default=7, ge=3)
    memory_decay_ratio: float = Field(default=0.3, ge=0.0, le=1.0)
    frequent_interaction_threshold: int = Field(default=3, ge=2)
    frequent_interaction_reinforce_ratio: float = Field(default=0.2, ge=0.0, le=0.5)