"""session_id 向量表的判据（表 = 生成物；唯一真源 = src/common/utils/utils_session.py）。

被断言的表：`src/common/utils/session_id_vectors.json`，由 `scripts/gen_session_id_vectors.py` 生成。
为什么要有这张表：宿主 `SessionUtils.calculate_session_id()` 与插件 `SessionIdMapper.calculate_session_id()`
是**两份实现**（插件跑在独立进程里、无法 import `src/`），必须钉住"同输入 ⇒ 同 key"。

判据：
    (a) 逐行断言：每行输入经权威算法算出 == 表里 expected（失败时把 case 名列出来）；
    (b) 表过期检查：生成器 `--check` 必须返回 0（表被手改、或算法改了没重生成 ⇒ 这里红）；
    (c) 证红①：表被改一行 ⇒ `--check` 必须红（`xfail(strict=True)` 锁住"必须红"）；
    (d) 证红②：算法被改一行（打后缀替身）⇒ `--check` 必须红（同上）；
    (e) 方向性可赋值：表 ⊇ 插件形参面的全部"支路 × route"组合；
    (f) 表外异常边界：两个 id 都给假值 ⇒ ValueError；int 型 id ⇒ TypeError。

直看红（(c)(d) 两条的"必须红"只有 `--runxfail` 才看得见）：
    uv run pytest tests/unit/common/test_session_id_vectors.py -q
    uv run pytest tests/unit/common/test_session_id_vectors.py -k corrupted_table --runxfail
    uv run pytest tests/unit/common/test_session_id_vectors.py -k changed_algorithm --runxfail
"""

from pathlib import Path
from typing import Any

import json

import pytest

from scripts.gen_session_id_vectors import TABLE_PATH, main
from src.common.utils.utils_session import SessionUtils


REPO_ROOT = Path(__file__).resolve().parents[3]
# 判据自己算表路径（不复用生成器的常量）：生成器若认错文件，test_table_path_agrees_with_generator 会对不上
TABLE = REPO_ROOT / "src" / "common" / "utils" / "session_id_vectors.json"

# 插件形参面的必需组合：支路(私聊/群) × account 真假 × scope 真假
_PLUGIN_COMBOS = {
    (branch, account_truthy, scope_truthy)
    for branch in ("private", "group")
    for account_truthy in (False, True)
    for scope_truthy in (False, True)
}


def _vectors() -> list[dict[str, Any]]:
    return json.loads(TABLE.read_text(encoding="utf-8"))["vectors"]


def test_table_path_agrees_with_generator() -> None:
    """判据与生成器必须认同一张表（否则 `--check` 检查的不是被逐行断言的那张）。"""
    assert TABLE_PATH == TABLE
    assert TABLE.exists(), f"表不存在：{TABLE}（跑 scripts/gen_session_id_vectors.py 生成）"


def test_vectors_match_authoritative_algorithm() -> None:
    """(a) 逐行：权威算法对每行输入算出的 session_id 必须 == 表里 expected。"""
    vectors = _vectors()
    assert len(vectors) >= 30, f"向量条数应 ≥30（覆盖不足）：{len(vectors)}"

    mismatches = []
    for vector in vectors:
        actual = SessionUtils.calculate_session_id(
            vector["platform"],
            user_id=vector["user_id"],
            group_id=vector["group_id"],
            account_id=vector["account_id"],
            scope=vector["scope"],
        )
        if actual != vector["expected"]:
            mismatches.append(f"{vector['case']}：表上 {vector['expected']} / 实算 {actual}")
    assert not mismatches, "期望值对不上权威算法的向量：\n" + "\n".join(mismatches)


def test_vector_cases_unique_sorted_and_justified() -> None:
    """表的形状：case 唯一 + 按 case 名排序（`--check` 逐字节可复现的前提）+ 每条都注明覆盖分支。"""
    vectors = _vectors()
    cases = [vector["case"] for vector in vectors]

    assert len(set(cases)) == len(cases), "case 名重复 ⇒ 排序不稳定"
    assert cases == sorted(cases), "表未按 case 名排序 ⇒ 生成结果不可逐字节复现"
    assert all(vector["covers"] for vector in vectors), "每条向量都必须有 covers（覆盖哪个分支/边界）"


def test_table_is_not_stale() -> None:
    """(b) 表过期检查：`--check` 必须返回 0（表被手改过、或算法改了没重生成 ⇒ 这里红）。"""
    assert main(["--check"]) == 0


def test_table_covers_plugin_parameter_surface() -> None:
    """(e) 方向性可赋值：表 ⊇ 插件必需组合。

    插件 `plugins/maibot-team.napcat-adapter/session_mapper.py` 的形参面 =
    platform / user_id / group_id / account_id / scope（构造默认 account_id="" scope=""，
    故"假 route"是它的常规路径）⇒ 私聊/群 × account 真假 × scope 真假 = 8 个必需组合，
    另有"两个 id 都给（群支优先）"的 4 个组合：每个组合表里都得有行。
    """
    covered = set()
    for vector in _vectors():
        branch = "group" if vector["group_id"] else "private"
        covered.add((branch, bool(vector["account_id"]), bool(vector["scope"])))

    missing = _PLUGIN_COMBOS - covered
    assert not missing, f"表缺这些组合（插件侧要算的输入形状）：{sorted(missing)}"


def test_error_paths_are_locked() -> None:
    """(f) 表外的异常边界：两个 id 都给假值 ⇒ ValueError；int 型 id ⇒ TypeError（签名是 Optional[str]）。

    这两条没有 session_id 期望值（只有异常类型），故不落表，由生成器 `_self_check()` 与这里各锁一次。
    """
    for user_id, group_id in ((None, None), ("", "")):
        with pytest.raises(ValueError):
            SessionUtils.calculate_session_id("qq", user_id=user_id, group_id=group_id)

    with pytest.raises(TypeError):
        SessionUtils.calculate_session_id("qq", user_id=123)


@pytest.mark.xfail(strict=True, reason="证红：表被手改（改一行 expected）必须红")
def test_corrupted_table_must_be_red(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """(c) 坏样本①：把表里某行 expected 改一个字符 ⇒ `--check` 必须红。

    改的是**临时副本**（真表只读）：测试中途崩掉也不会把真表留在改坏状态；比对逻辑与真表逐字节路径同一条。

    直看红：`uv run pytest tests/unit/common/test_session_id_vectors.py -k corrupted_table --runxfail`
    """
    import scripts.gen_session_id_vectors as generator

    text = TABLE.read_bytes().decode("utf-8")
    needle = '"expected": "'
    start = text.index(needle) + len(needle)
    flipped = "0" if text[start + 31] != "0" else "1"
    corrupted = text[: start + 31] + flipped + text[start + 32 :]
    assert len(corrupted) == len(text) and corrupted != text, "坏样本没改成（应只差一个字符）"

    broken = tmp_path / "session_id_vectors.json"
    broken.write_text(corrupted, encoding="utf-8", newline="\n")
    monkeypatch.setattr(generator, "TABLE_PATH", broken)

    assert main(["--check"]) == 0, "改了一行 expected 的表必须被判过期（红）"


@pytest.mark.xfail(strict=True, reason="证红：算法被改一行（打后缀替身）必须红")
def test_changed_algorithm_must_be_red(monkeypatch: pytest.MonkeyPatch) -> None:
    """(d) 坏样本②：给权威算法打一个"照原样算完再加后缀"的替身 ⇒ `--check` 必须红。

    替身**保留守卫分支与类型行为**（两个 id 都给假值仍抛 ValueError、int 仍抛 TypeError），
    于是红只能出自"期望值对不上权威算法"，不会混进生成期自检失败。

    直看红：`uv run pytest tests/unit/common/test_session_id_vectors.py -k changed_algorithm --runxfail`
    """
    real = SessionUtils.calculate_session_id

    def shifted(platform: str, *, user_id=None, group_id=None, account_id=None, scope=None) -> str:
        if not user_id and not group_id:
            raise ValueError("UserID 或 GroupID 必须提供其一")
        return real(platform, user_id=user_id, group_id=group_id, account_id=account_id, scope=scope) + "x"

    monkeypatch.setattr(SessionUtils, "calculate_session_id", staticmethod(shifted))

    assert main(["--check"]) == 0, "算法改了、表没重生成 ⇒ 必须被判过期（红）"
