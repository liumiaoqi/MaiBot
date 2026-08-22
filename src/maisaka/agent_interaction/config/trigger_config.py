from pydantic import BaseModel, Field



class MemoryDrivenTriggerConfig(BaseModel):
    enabled: bool = True
    recall_rate_limit_rpm: int = Field(default=10, ge=1, le=60)
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