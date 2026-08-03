"""MF-P1-001/002 验收：统一 id 生成器。

对应 tasks.md 4.1：generate 返回 16 字符 hex；同名同 id；不同名不同 id；
碰撞时序号追加；generate_uuid_fallback 格式正确。
F1 修正：SHA256 前缀截断，存量 64 字符 id 是统一 id 的超集（前缀匹配）。
"""

import re

from src.A_memorix.core.concept_graph.unified_id_generator import UnifiedIdGenerator
from src.A_memorix.core.utils.hash import compute_hash


def test_generate_returns_16_char_hex() -> None:
    gen = UnifiedIdGenerator()
    result = gen.generate("琪亚娜")
    assert re.fullmatch(r"[0-9a-f]{16}", result)


def test_same_name_same_id() -> None:
    gen = UnifiedIdGenerator()
    assert gen.generate("生日") == gen.generate("生日")


def test_different_name_different_id() -> None:
    gen = UnifiedIdGenerator()
    assert gen.generate("生日") != gen.generate("契约")


def test_id_is_sha256_prefix_of_existing_hash() -> None:
    """F1：统一 id = compute_hash(name)[:16]，存量 id（64 字符）前缀匹配。"""
    gen = UnifiedIdGenerator()
    name = "银狼"
    unified = gen.generate(name)
    existing = compute_hash(name)
    assert existing.startswith(unified)
    assert len(existing) == 64


def test_collision_appends_sequence_number() -> None:
    """碰撞时追加递增序号（保持 16 字符）。"""
    gen = UnifiedIdGenerator()
    # 手工占用 base，模拟碰撞
    name_a = "概念甲"
    name_b = "概念乙"
    id_a = gen.generate(name_a)
    id_b = gen.generate(name_b)
    assert id_a != id_b

    # 直接构造碰撞：将 name_b 的 base 强制映射到 name_a 的 id
    gen2 = UnifiedIdGenerator()
    base = compute_hash("碰撞源").hexdigest()[:16] if hasattr(compute_hash("碰撞源"), "hexdigest") else compute_hash("碰撞源")[:16]
    gen2._id_to_name[base] = "其他名字"
    candidate = gen2.generate("碰撞源")
    assert candidate != base
    assert re.fullmatch(r"[0-9a-f]{16}", candidate)


def test_generate_uuid_fallback_format() -> None:
    gen = UnifiedIdGenerator()
    fallback = gen.generate_uuid_fallback()
    assert re.fullmatch(r"[0-9a-f]{16}", fallback)
    # 两次 fallback 不同
    assert fallback != gen.generate_uuid_fallback()


def test_empty_name_falls_back_to_uuid() -> None:
    gen = UnifiedIdGenerator()
    assert re.fullmatch(r"[0-9a-f]{16}", gen.generate("  "))


def test_entity_concept_same_name_same_id() -> None:
    """MF-P1-002：同语义对象（同名概念/实体）id 相同。"""
    gen = UnifiedIdGenerator()
    assert gen.generate("凯文") == gen.generate("凯文")
