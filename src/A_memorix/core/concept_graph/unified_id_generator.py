"""统一 id 生成器 — 概念-实体同源 id（MF-P1-001/002）。

F1 决策：`generate(name)` = `compute_hash(name)[:16]`（SHA256 前缀截断 16 字符）。

- 算法安全：SHA256 为 NIST 标准，无已知碰撞攻击
- 存量零迁移：存量实体 id（64 字符 SHA256）是统一 id（前 16 字符）的超集，前缀匹配直接兼容
- 长度适中：16 字符（64 bit），10 万节点规模碰撞概率 ~2.7e-8
- 同语义对象（同名概念/实体）产出相同 id——概念-实体同源对齐（MF-P1-002）
"""

import uuid

from ..utils.hash import compute_hash

_ID_LENGTH = 16
_MAX_COLLISION_ATTEMPTS = 100


class UnifiedIdGenerator:
    """统一 id 生成器。

    name → 16 字符 hex（SHA256 前缀截断）。碰撞时追加递增序号重试；
    碰撞溢出或 SHA256 不可用时降级 uuid4。
    """

    def __init__(self) -> None:
        self._name_to_id: dict[str, str] = {}
        self._id_to_name: dict[str, str] = {}

    def generate(self, name: str) -> str:
        """生成统一 id。

        Args:
            name: 概念/实体名称（UTF-8 原样哈希，归一化由调用方保证）

        Returns:
            16 字符 hex id
        """
        clean = str(name or "").strip()
        if not clean:
            return self.generate_uuid_fallback()

        existing = self._name_to_id.get(clean)
        if existing is not None:
            return existing

        base = compute_hash(clean)[:_ID_LENGTH]
        candidate = base
        for counter in range(1, _MAX_COLLISION_ATTEMPTS + 1):
            if candidate not in self._id_to_name:
                break
            # 碰撞：追加递增序号（保持 16 字符，序号占尾部）
            suffix = f"{counter:02d}"
            candidate = f"{base[:_ID_LENGTH - len(suffix)]}{suffix}"
        else:
            return self.generate_uuid_fallback()

        self._name_to_id[clean] = candidate
        self._id_to_name[candidate] = clean
        return candidate

    def generate_uuid_fallback(self) -> str:
        """降级到 uuid4（SHA256 不可用或碰撞溢出时）。"""
        return uuid.uuid4().hex[:_ID_LENGTH]

    def is_generated(self, candidate: str) -> bool:
        """candidate 是否已被本生成器产出（供迁移断点/碰撞检测）。"""
        return candidate in self._id_to_name
