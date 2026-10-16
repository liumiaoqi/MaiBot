"""`social_rel` 学习强度 → 检索排序 `confidence` 位的**实验性接缝**（逆熵 · 阶段 C 首件）。

设计出处：`.shared/decisions/negentropy_gate_b_1017.md` §二 ＋ `..._gate_c_1017.md` §六（C-1/C-2/C-3）。
本轮**只做这一件接入**：不加列、不改 schema、不动真库结构。

## 默认关（预登记 P1）

只有环境变量 ``MAIBOT_SOCIAL_REL_CONFIDENCE`` 取真值（`1/true/yes/on`，忽略大小写）时才生效。
**未设或是别的值时**：``enabled()`` 为假 ⇒ ``override()`` 恒 `None`、``effective_confidence()``
原样返回入参、``strengths()`` 不读文件 ⇒ 调用点走原值，**默认路径逐位不变**（连文件 IO 都不发生）。

## 值来源：数据根下的 sidecar（C-1 定稿）

``resolve_data_file("social_rel_strength.json")`` —— **只读**。本模块**从不写库、从不写文件**：
- A_memorix 的 ``relations.confidence`` 写侧**仍只有** 0004 真值回路（`v5_memory.py:126-168`）；
- ⚠️ **不给任何库加列/表/索引**：含 `relations` 表的是**三份同 schema 的 `metadata.db`**
  （门 C 文档 C-3 记录：主库 `MaiBot.db` 里**没有** `relations`；容器数据根那份 `relations` 为 0 行）
  ⇒ 本接缝对三者**一概不碰**，学习强度落 sidecar。

sidecar 形状（约定）：``{"<relation hash_value>": <float ∈ [0,1]>, ...}``。
坏数据**逐条跳过并出声**（不是静默当作 1.0）：缺文件 / 非 dict / 非数值 / 超出 [0,1] 都记一条日志，
该 hash 退回**原有** confidence —— fail-closed，绝不把"没学到"当成"高置信"。

## C-2 的执行期约束（会让对照作废的那个坑）

两臂对照要在 ``dual_path.py:992``（候选集已定、尚未打分）取一次快照；而 ``:1020-1023`` **就地改写
``meta``**、``:1030`` 写 ``item.score`` ⇒ **快照必须深拷贝**，否则第二臂读到的是第一臂改过的对象。
``snapshot_items()`` 就是给这个分叉点用的（深拷贝 + 一句为什么）。
"""

import copy
import json
import os
from pathlib import Path
from typing import Any, Iterable, List, Mapping

from src.common.logger import get_logger
from src.common.runtime_paths import resolve_data_file

logger = get_logger("social_rel_confidence")

ENV_VAR = "MAIBOT_SOCIAL_REL_CONFIDENCE"
SIDECAR_NAME = "social_rel_strength.json"
_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})


def enabled() -> bool:
    """接缝是否启用（**默认关**：未设或非真值 ⇒ False）。"""

    return str(os.environ.get(ENV_VAR, "") or "").strip().lower() in _TRUE_VALUES


def sidecar_path() -> Path:
    """sidecar 落点：**数据根**（唯一来源 `resolve_data_file`，不是 CWD 相对、不是自推根）。"""

    return resolve_data_file(SIDECAR_NAME)


class SocialRelConfidenceSeam:
    """学习强度的读取端（只读；未启用时零副作用）。"""

    def __init__(self) -> None:
        self._cache_key: tuple[str, int, int] | None = None
        self._cache: dict[str, float] = {}
        self._logged_state: str = ""

    # ── 对外 ────────────────────────────────────────────────────────────

    def strengths(self) -> Mapping[str, float]:
        """当前 sidecar 里的强度表（未启用 ⇒ 空表，且**不读文件**）。"""

        if not enabled():
            return {}
        path = sidecar_path()
        try:
            stat = path.stat()
            key = (str(path), int(stat.st_mtime_ns), int(stat.st_size))
        except OSError:
            self._log_state(f"未启用以外的情形：sidecar 不存在（{path}）⇒ 不覆盖，走默认路径")
            self._cache_key, self._cache = None, {}
            return {}

        if key == self._cache_key:
            return self._cache

        raw = path.read_text(encoding="utf-8")
        table = self._parse(raw, path)
        self._cache_key, self._cache = key, table
        self._log_state(f"已载入 sidecar（{path}）：{len(table)} 条强度")
        return table

    def override(self, hash_value: str) -> float | None:
        """该 hash 的学习强度；未启用 / 不在表里 ⇒ `None`（调用点据此走原值）。"""

        if not hash_value:
            return None
        return self.strengths().get(str(hash_value))

    def effective_confidence(self, hash_value: str, fallback: float) -> float:
        """接缝的**唯一取数语义**：有学习强度用它，否则返回 `fallback` **原值**（不做任何变换）。"""

        learned = self.override(hash_value)
        return fallback if learned is None else learned

    def snapshot_items(self, items: Iterable[Any]) -> List[Any]:
        """同刻对照的候选快照：**深拷贝**（原因见模块 docstring 的 C-2 段）。

        在 `dual_path.py:992`（候选已定、尚未打分）处调用一次，两臂共用同一份内容。
        """

        return copy.deepcopy(list(items))

    def describe(self) -> str:
        """给启动/日志用的单行自述（真机重启后该看到的就是这一行）。"""

        state = "启用" if enabled() else "未启用（默认关）"
        return f"social_rel 强度接缝：{state} · 开关={ENV_VAR} · sidecar={sidecar_path()}"

    def reset_cache(self) -> None:
        """测试/热重载用：清掉 mtime 缓存与"只报一次"的状态。"""

        self._cache_key = None
        self._cache = {}
        self._logged_state = ""

    # ── 内部 ────────────────────────────────────────────────────────────

    def _parse(self, raw: str, path: Path) -> dict[str, float]:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.warning("social_rel 强度 sidecar 不是合法 JSON（%s）：%s ⇒ 不覆盖", path, exc)
            return {}
        if not isinstance(payload, dict):
            logger.warning("social_rel 强度 sidecar 顶层必须是对象（%s）⇒ 不覆盖", path)
            return {}

        table: dict[str, float] = {}
        skipped: list[str] = []
        for key, value in payload.items():
            try:
                number = float(value)
            except (TypeError, ValueError):
                skipped.append(str(key))
                continue
            if not 0.0 <= number <= 1.0:
                skipped.append(str(key))
                continue
            table[str(key)] = number
        if skipped:
            logger.warning(
                "social_rel 强度 sidecar 有 %d 条非法条目（非数值/越界）已跳过：%s",
                len(skipped), ", ".join(skipped[:5]),
            )
        return table

    def _log_state(self, message: str) -> None:
        if message != self._logged_state:
            self._logged_state = message
            logger.info("social_rel 强度接缝：%s", message)


social_rel_confidence = SocialRelConfidenceSeam()
