"""ZG-27 驱逐评分与防误杀（对标 Linux mm/oom_kill.c）。

Linux 源码参考：
- mm/oom_kill.c:199 — oom_badness 显式分数计算
- mm/oom_kill.c:217 — adj==OOM_SCORE_ADJ_MIN 返回 LONG_MIN（硬保护）
- mm/oom_kill.c:228-229 — points += adj 归一化

6 层硬保护冗余（spec 5.5.4 决策 4 + design 2.1.3.3）：
  Layer 1: is_pinned=True → -1（硬保护）
  Layer 2: priority_score=-1000 → -1（人格记忆硬保护）
  Layer 3: protected_until 未过期 → -1
  Layer 4: 水位 MIN 硬底线 usage<watermark_min → -1
  Layer 5: scan_objects 内部保护（shrinker 各自实现）
  Layer 6: VectorShrinker V1 count_objects 返回 0
"""

from dataclasses import dataclass


@dataclass
class EvictableItem:
    """可驱逐对象评分（对标 Linux mm/oom_kill.c:199 oom_badness）。

    oom_badness 是纯函数（给定 is_pinned/priority_score/protected_until 确定输出，spec 7.4 规则 4）。
    """

    is_pinned: bool = False
    """硬保护（不可驱逐）"""
    priority_score: int = 0
    """[-1000, 1000]，对标 oom_score_adj"""
    protected_until: float = 0.0
    """保护截止时间戳"""

    def oom_badness(self, current_time: float, watermark_min: int, usage: int = 0) -> int:
        """返回驱逐分数：-1 不可驱逐，正数越大越优先驱逐。

        对标 oom_kill.c:199 oom_badness + oom_kill.c:217 adj==OOM_SCORE_ADJ_MIN。
        """
        # Layer 1: is_pinned 硬保护（对标 oom_kill.c:217 adj==OOM_SCORE_ADJ_MIN）
        if self.is_pinned:
            return -1
        # Layer 2: priority_score=-1000 硬保护（人格记忆）
        if self.priority_score <= -1000:
            return -1
        # Layer 3: protected_until 未过期
        if self.protected_until > 0 and current_time < self.protected_until:
            return -1
        # Layer 4: 水位 MIN 硬底线（usage < min_val 等效 oom_score_adj=-1000）
        if usage < watermark_min:
            return -1
        # 基线 = usage + priority_score 归一化（对标 oom_kill.c:228-229 points += adj）
        return max(0, usage + self.priority_score)