"""DeepSeek 成本追踪服务。

追踪 DeepSeek API 的 Token 消耗和费用，提供按智能体、按任务类型维度的成本报告。
"""


import sqlite3
import time
from collections import defaultdict
from pathlib import Path


from pydantic import BaseModel, Field

from src.common.logger import get_logger

logger = get_logger("maisaka_deepseek_cost_tracker")

_DB_PATH = Path("data/deepseek_cost.db")


class CostRecord(BaseModel):
    """成本记录。"""

    agent_id: str = Field(default="", description="智能体ID")
    task_type: str = Field(default="", description="任务类型")
    model_tier: str = Field(default="pro", description="模型层级")
    input_tokens: int = Field(default=0, description="输入Token数")
    output_tokens: int = Field(default=0, description="输出Token数")
    cache_hit_tokens: int = Field(default=0, description="缓存命中Token数")
    cost: float = Field(default=0.0, description="费用（元）")
    timestamp: float = Field(default=0.0, description="时间戳")


class CostTracker:
    """DeepSeek 成本追踪器。"""

    def __init__(self, db_path: Path | str | None = None) -> None:
        self._records: list[CostRecord] = []
        self._max_records = 10000
        self._db_path = Path(db_path) if db_path is not None else _DB_PATH
        self._init_db()
        self._load_from_db()

    def _init_db(self) -> None:
        """初始化 SQLite 持久化表。"""
        try:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(str(self._db_path)) as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS deepseek_cost_record (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        agent_id TEXT NOT NULL,
                        task_type TEXT NOT NULL,
                        model_tier TEXT NOT NULL,
                        input_tokens INTEGER NOT NULL,
                        output_tokens INTEGER NOT NULL,
                        cache_hit_tokens INTEGER NOT NULL,
                        cost REAL NOT NULL,
                        timestamp REAL NOT NULL
                    )
                    """
                )
                conn.commit()
        except Exception as exc:
            logger.warning("成本追踪 SQLite 初始化失败: %s", exc)

    def _load_from_db(self) -> None:
        """从 SQLite 加载最近 N 条记录到内存（重启不丢数据）。"""
        try:
            with sqlite3.connect(str(self._db_path)) as conn:
                rows = conn.execute(
                    """
                    SELECT agent_id, task_type, model_tier, input_tokens,
                           output_tokens, cache_hit_tokens, cost, timestamp
                    FROM deepseek_cost_record
                    ORDER BY timestamp DESC
                    LIMIT ?
                    """,
                    (self._max_records,),
                ).fetchall()
            self._records = [
                CostRecord(
                    agent_id=r[0], task_type=r[1], model_tier=r[2],
                    input_tokens=r[3], output_tokens=r[4], cache_hit_tokens=r[5],
                    cost=r[6], timestamp=r[7],
                )
                for r in reversed(rows)
            ]
        except Exception as exc:
            logger.warning("成本追踪 SQLite 加载失败: %s", exc)

    def reset(self) -> None:
        """清空累积状态（测试隔离用）。"""
        self._records.clear()

    def record(
        self,
        agent_id: str,
        task_type: str,
        model_tier: str,
        input_tokens: int,
        output_tokens: int,
        cache_hit_tokens: int = 0,
        cost: float = 0.0,
    ) -> None:
        """记录一次 API 调用的成本。"""
        record = CostRecord(
            agent_id=agent_id,
            task_type=task_type,
            model_tier=model_tier,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_hit_tokens=cache_hit_tokens,
            cost=cost,
            timestamp=time.time(),
        )
        self._records.append(record)

        if len(self._records) > self._max_records:
            self._records = self._records[-self._max_records:]

        try:
            with sqlite3.connect(str(self._db_path)) as conn:
                conn.execute(
                    """
                    INSERT INTO deepseek_cost_record
                    (agent_id, task_type, model_tier, input_tokens,
                     output_tokens, cache_hit_tokens, cost, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        agent_id, task_type, model_tier, input_tokens,
                        output_tokens, cache_hit_tokens, cost, record.timestamp,
                    ),
                )
                conn.commit()
        except Exception as exc:
            logger.warning("成本记录持久化失败: %s", exc)

    def get_agent_cost(self, agent_id: str, period_days: int = 30) -> dict[str, float]:
        """获取指定智能体在指定时间段内的成本汇总。"""
        cutoff = time.time() - period_days * 86400
        total_cost = 0.0
        total_input = 0
        total_output = 0
        total_cache_hit = 0

        for r in self._records:
            if r.agent_id == agent_id and r.timestamp >= cutoff:
                total_cost += r.cost
                total_input += r.input_tokens
                total_output += r.output_tokens
                total_cache_hit += r.cache_hit_tokens

        return {
            "total_cost": total_cost,
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "total_cache_hit_tokens": total_cache_hit,
        }

    def get_task_type_cost(self, task_type: str, period_days: int = 30) -> dict[str, float]:
        """获取指定任务类型在指定时间段内的成本汇总。"""
        cutoff = time.time() - period_days * 86400
        total_cost = 0.0
        total_input = 0
        total_output = 0

        for r in self._records:
            if r.task_type == task_type and r.timestamp >= cutoff:
                total_cost += r.cost
                total_input += r.input_tokens
                total_output += r.output_tokens

        return {
            "total_cost": total_cost,
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
        }

    def get_monthly_report(self) -> dict[str, dict[str, float]]:
        """获取月度成本报告，按智能体和任务类型维度。"""
        by_agent: dict[str, dict[str, float]] = defaultdict(
            lambda: {"cost": 0.0, "input_tokens": 0, "output_tokens": 0}
        )
        by_task: dict[str, dict[str, float]] = defaultdict(
            lambda: {"cost": 0.0, "input_tokens": 0, "output_tokens": 0}
        )

        for r in self._records:
            by_agent[r.agent_id]["cost"] += r.cost
            by_agent[r.agent_id]["input_tokens"] += r.input_tokens
            by_agent[r.agent_id]["output_tokens"] += r.output_tokens

            by_task[r.task_type]["cost"] += r.cost
            by_task[r.task_type]["input_tokens"] += r.input_tokens
            by_task[r.task_type]["output_tokens"] += r.output_tokens

        return {
            "by_agent": dict(by_agent),
            "by_task_type": dict(by_task),
        }
