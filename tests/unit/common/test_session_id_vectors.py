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
    (f) 表外异常边界：两个 id 都给假值 ⇒ ValueError；int 型 id ⇒ TypeError；
    (g) 行尾不敏感：表被**整份存成 CRLF** ⇒ `--check` 仍必须绿（判据口径 = 归一化后比对）；
    (h) 内容敏感：表里一行 expected **真被改**（不是行尾差）⇒ 必须红。

⚠️ (g)/(h) 是一对：判据是**行尾归一化后**比对 ⇒ 只有"行尾差异"被放过，
   "内容差异"必须仍然红 —— 两个方向各一条，缺任一条这条判据就是假的。

两份部署：宿主表 + 插件仓内副本（段二新增，判据顺延为 (i)~(o)）
    (i) `--emit-plugin-copy` 的两个落点**逐字节相同**（同一序列化器只渲染一次 + 写后回读），
        副本落点在插件仓内自足（`plugins/maibot-team.napcat-adapter/tests/fixtures/...`，无 `..`）；
    (j) 真副本 vs 真宿主表：**行尾归一化后**内容一致（两处独立检出，物化行尾各由自己的检出环境决定
        ⇒ 逐字节比会把"检出环境"当成"两份漂移"；实测差 387 字节全是行尾）；
    (k) 副本缺失 ⇒ 默认 `--check` 必须红，且**具名**报"副本缺失"；
    (l) 只让②支坏（副本被改一行）⇒ 红在 plugin-vs-host 支，且①支仍打印 `[OK]`；
    (m) **不短路**：①支先红 ⇒ ②支**仍然要跑并打印**（"看着在、其实没跑"的反面）；
    (n) 宿主表**多一条向量**、副本没跟 ⇒ 必须红，且**回读确认变异真的写进去了**
        （防"多行替换静默没匹配上、用例照绿"）；
    (o) 正对照：两份同步 ⇒ 默认 `--check` 返回 0（有红有绿才算判据——防"恒红"假象）；
    (p) 模式存在且**默认不写副本**：`--help` 里有 `--emit-plugin-copy`；无参数默认运行只写宿主表。
    (q) ⭐ **内容级对账**（归因层）：宿主表**加一条**向量（改名 ⇒ 集合差）、副本没跟 ⇒ 默认 `--check` 必须红，
        且**具名**报出"只在宿主表（副本没跟上）：<case>"（判红仍是②支同一条：归一后逐字节不等；
        字节层只会说"不一致 / 首个差异行：第 N 行"，这一层点名是哪条 case 没跟上）。

直看红（(c)(d)(h) 三条的"必须红"只有 `--runxfail` 才看得见）：
    uv run pytest tests/unit/common/test_session_id_vectors.py -q
    uv run pytest tests/unit/common/test_session_id_vectors.py -k corrupted_table --runxfail
    uv run pytest tests/unit/common/test_session_id_vectors.py -k changed_algorithm --runxfail
    uv run pytest tests/unit/common/test_session_id_vectors.py -k changed_row --runxfail
    uv run pytest tests/unit/common/test_session_id_vectors.py -k host_ahead_of_copy -s
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
# 同上：副本路径也自己算一份，由 (i) 断言它与生成器的 PLUGIN_COPY_PATH 认同一个文件
PLUGIN_COPY = REPO_ROOT / "plugins" / "maibot-team.napcat-adapter" / "tests" / "fixtures" / "session_id_vectors.json"

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


def test_crlf_table_must_still_be_green(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """(g) 好样本：表被**整份存成 CRLF**（编辑器存盘 / 检出物化）⇒ `--check` **仍必须绿**。

    这是 2026-10-17 缺陷的目标行为：判据 = **行尾归一化后**比对 ⇒ 行尾不是"表的内容"。
    `newline=""` 让 `\\n` 逐字写盘（不被平台翻译成 `\\r\\n`），才算真的合成出 CRLF 文件；
    文本取自生成器**现渲染的 LF 规范形**（不拿工作区那份——主仓那份此刻可能正是"LF 行 + CRLF 行尾"
    的混合物化态，直接 `\\n → \\r\\n` 会把它改写坏，那就不是在测"行尾差异"了）。
    """
    import scripts.gen_session_id_vectors as generator

    canonical = generator.render(generator.build_payload())
    crlf = canonical.replace("\n", "\r\n")
    assert crlf.count("\r\n") == canonical.count("\n") > 380, "坏样本没改成（应每行一个 CRLF）"

    crlf_table = tmp_path / "session_id_vectors.json"
    crlf_table.write_text(crlf, encoding="utf-8", newline="")
    assert crlf_table.read_bytes() != canonical.encode("utf-8"), "写盘后行尾应确实不同（逐字节层面）"

    monkeypatch.setattr(generator, "TABLE_PATH", crlf_table)

    assert main(["--check"]) == 0, "只有行尾不同的表**不许**被判过期（否则换检出环境就假红）"


@pytest.mark.xfail(strict=True, reason="证红：表里一行 expected 真被改（非行尾差）必须红 ⇒ `--runxfail` 看红")
def test_table_with_changed_row_must_be_red(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """(h) 坏样本③：把某行 expected 的**内容**改一个字符（行尾保持 LF）⇒ `--check` 必须红。

    与 (g) 成对：行尾归一化**只放过行尾**——"内容真被改"必须仍被抓住，否则 (b) 那条判据
    （表与生成器一致）就被这次修法掏空了。直看红：`-k changed_row --runxfail`。
    """
    import scripts.gen_session_id_vectors as generator

    text = TABLE.read_bytes().decode("utf-8")
    needle = '"expected": "'
    start = text.index(needle) + len(needle)
    flipped = "0" if text[start + 31] != "0" else "1"
    corrupted = text[: start + 31] + flipped + text[start + 32 :]
    assert corrupted != text, "坏样本没改成（应差一个字符）"

    broken = tmp_path / "session_id_vectors.json"
    broken.write_text(corrupted, encoding="utf-8", newline="\n")
    monkeypatch.setattr(generator, "TABLE_PATH", broken)

    assert main(["--check"]) == 0, "内容被改一行（行尾无差异）必须被判过期（红）"


# ── 两份部署：宿主表 + 插件仓内副本（段二新增，判据 (i)~(p)） ─────────────────────


def _corrupt_first_expected(text: str) -> str:
    """把表里第一条 `expected` 改一个字符 —— 只差一个字符的坏样本（②支与不短路用例共用）。"""
    needle = '"expected": "'
    start = text.index(needle) + len(needle)
    flipped = "0" if text[start + 31] != "0" else "1"
    corrupted = text[: start + 31] + flipped + text[start + 32 :]
    assert len(corrupted) == len(text) and corrupted != text, "坏样本没改成（应只差一个字符）"
    return corrupted


def test_emit_writes_two_byte_identical_copies(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """(i) `--emit-plugin-copy` 的两处落点**逐字节相同**，且副本落点在插件仓内自足。

    真表 / 真插件仓只读不动：两个落点都指到 tmp_path（等价调用）后进行 —— 免得测试写进插件仓。
    """
    import scripts.gen_session_id_vectors as generator

    assert generator.PLUGIN_COPY_PATH == PLUGIN_COPY, "生成器与判据必须认同一个副本文件"
    plugin_relative = PLUGIN_COPY.relative_to(REPO_ROOT)
    assert plugin_relative.parts == (
        "plugins",
        "maibot-team.napcat-adapter",
        "tests",
        "fixtures",
        "session_id_vectors.json",
    ), f"副本路径必须在插件仓内自足：{plugin_relative}"
    assert ".." not in plugin_relative.parts, "不许用 ../../src/... 往上爬（插件进程读不到宿主 src/）"

    host = tmp_path / "session_id_vectors.json"
    copy = tmp_path / "plugin" / "tests" / "fixtures" / "session_id_vectors.json"
    monkeypatch.setattr(generator, "TABLE_PATH", host)
    monkeypatch.setattr(generator, "PLUGIN_COPY_PATH", copy)

    assert generator.emit_both() == 0
    assert host.read_bytes() == copy.read_bytes(), "两份必须逐字节相同（同一序列化器只渲染一次）"
    assert host.read_bytes() == generator.render(generator.build_payload()).encode("utf-8"), "写出的还得是现算结果"
    assert b"\r\n" not in host.read_bytes(), "不许落 CRLF——逐字节比对跨平台一致的前提"
    assert b"\r\n" not in copy.read_bytes(), "不许落 CRLF（副本同）"


@pytest.mark.skipif(not PLUGIN_COPY.exists(), reason="插件副本尚未部署（跑 --emit-plugin-copy 落地后本条自动生效）")
def test_plugin_copy_matches_host_table_content() -> None:
    """(j) 真副本 vs 真宿主表：**行尾归一化后**内容一致。

    为什么不是逐字节：宿主表与副本是**两处独立检出**（副本在插件仓里），物化行尾各由自己的检出环境
    决定 ⇒ 逐字节比会把"检出环境"判成"两份漂移"（实测：CRLF 宿主表 14,601 字节 vs LF 副本 14,214 字节，
    388 行逐行全同）。这里另断言"字节差异只可能来自行尾"。
    """
    host_bytes = TABLE.read_bytes()
    copy_bytes = PLUGIN_COPY.read_bytes()

    assert host_bytes.replace(b"\r\n", b"\n") == copy_bytes.replace(b"\r\n", b"\n"), (
        f"插件副本与宿主表内容不一致：\n  {PLUGIN_COPY}\n  {TABLE}\n（跑 --emit-plugin-copy 让两份同源）"
    )
    assert TABLE.read_text(encoding="utf-8").splitlines() == PLUGIN_COPY.read_text(encoding="utf-8").splitlines()


def test_missing_plugin_copy_makes_check_red(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """(k) 副本缺失 ⇒ 默认 `--check` 必须红，且**具名**报"副本缺失"。

    只把副本落点指到一个不存在的临时路径（**不真删插件仓里的东西**）；宿主表仍指真表 ⇒
    ①支应当是绿的 —— 于是红只能出自"副本缺失"这一条，正是要钉的判据。
    """
    import scripts.gen_session_id_vectors as generator

    monkeypatch.setattr(generator, "PLUGIN_COPY_PATH", tmp_path / "not_emitted" / "session_id_vectors.json")
    capsys.readouterr()  # 丢掉此前输出，只看这一次

    assert main(["--check"]) != 0, "副本缺失必须判红（缺了 = 插件侧那份真源没部署）"
    out = capsys.readouterr().out
    assert "plugin-vs-host" in out and "副本缺失" in out, f"红要具名到 plugin-vs-host 的'副本缺失'：\n{out}"
    assert "表未过期" in out and "表已过期" not in out, f"①支应当绿（红只来自副本缺失）：\n{out}"


def test_altered_plugin_copy_makes_check_red(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """(l) 只让②支坏：副本被改一行 ⇒ 红在 plugin-vs-host，且①支仍打印 `[OK]`（判据 (d) 的一半）。

    只读模拟：宿主表与副本都用 temp 落点，副本 = 宿主表内容改一个字符；真插件仓一个字节都不动。
    """
    import scripts.gen_session_id_vectors as generator

    host = tmp_path / "session_id_vectors.json"
    host.write_bytes(TABLE.read_bytes())
    copy = tmp_path / "plugin" / "tests" / "fixtures" / "session_id_vectors.json"
    copy.parent.mkdir(parents=True, exist_ok=True)
    copy.write_text(_corrupt_first_expected(TABLE.read_bytes().decode("utf-8")), encoding="utf-8", newline="\n")
    monkeypatch.setattr(generator, "TABLE_PATH", host)
    monkeypatch.setattr(generator, "PLUGIN_COPY_PATH", copy)
    capsys.readouterr()

    assert main(["--check"]) != 0, "副本与宿主表差一个字符也必须红"
    out = capsys.readouterr().out
    assert "plugin-vs-host：副本与宿主表不一致" in out, f"红要具名到 plugin-vs-host：\n{out}"
    assert "首个差异行" in out, f"要打印首个差异行：\n{out}"
    assert "表未过期" in out and "表已过期" not in out, f"①支应当绿（红只来自副本漂移）：\n{out}"


def test_first_arm_fail_does_not_short_circuit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """(m) **不短路**：①支先红 ⇒ ②支**仍然要跑并打印**。

    造法：宿主表被改一行（①支必红），副本 = **同一份被改内容**（②支内容一致 ⇒ 绿）。
    于是输出必须同时含 `[FAIL] 表已过期…` 与 `[OK] plugin-vs-host…` —— 若实现是"第一支红了就 return"，
    第二支那行就不会出现（这正是"看着在、其实没跑"的形状）。
    """
    import scripts.gen_session_id_vectors as generator

    corrupted = _corrupt_first_expected(TABLE.read_bytes().decode("utf-8"))
    host = tmp_path / "session_id_vectors.json"
    host.write_text(corrupted, encoding="utf-8", newline="\n")
    copy = tmp_path / "plugin" / "tests" / "fixtures" / "session_id_vectors.json"
    copy.parent.mkdir(parents=True, exist_ok=True)
    copy.write_text(corrupted, encoding="utf-8", newline="\n")
    monkeypatch.setattr(generator, "TABLE_PATH", host)
    monkeypatch.setattr(generator, "PLUGIN_COPY_PATH", copy)
    capsys.readouterr()

    assert main(["--check"]) != 0, "①支红 ⇒ 总体必须红"
    out = capsys.readouterr().out
    assert "[FAIL] 表已过期" in out, f"①支应红：\n{out}"
    assert "[OK] plugin-vs-host" in out, f"①支红了以后②支仍然必须跑并打印（不短路）：\n{out}"


def test_host_table_extra_vector_makes_check_red(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """(n) 宿主表**多一条向量**、副本没跟 ⇒ 必须红；且**回读确认变异真的写进去了**。

    多行插入正是"多行替换静默没匹配上、用例照绿"的高发形状 ⇒ 插完先回读断言（行数 +1、新 case 在），
    再跑 `--check`。两支都会红（宿主表已不是现算结果；副本又对不上宿主表）——两条 FAIL 都得打印。
    """
    import scripts.gen_session_id_vectors as generator

    # 先归一化行尾再变异：主仓检出把表物化成 CRLF，直接按 "\n" 找锚点会 `substring not found`
    original = TABLE.read_bytes().decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    marker = "  {\n"
    insert_at = original.index(marker)
    extra = (
        "  {\n"
        '    "case": "probe_extra_vector_not_in_plugin_copy",\n'
        '    "platform": "probe",\n'
        '    "user_id": "u_probe",\n'
        '    "group_id": null,\n'
        '    "account_id": "",\n'
        '    "scope": "",\n'
        '    "expected": "probe_u_probe_private",\n'
        '    "covers": "段二变异样本：宿主表多一条向量、副本没跟"\n'
        "  },\n"
    )
    mutated = original[:insert_at] + extra + original[insert_at:]

    host = tmp_path / "session_id_vectors.json"
    host.write_text(mutated, encoding="utf-8", newline="\n")
    # ⚠️ 回读确认变异落地（防"替换静默没匹配上"）
    readback = host.read_text(encoding="utf-8")
    assert "probe_extra_vector_not_in_plugin_copy" in readback, "变异没写进去"
    assert readback.count("\n") == original.count("\n") + extra.count("\n"), "变异行数不对（插入没生效）"

    copy = tmp_path / "plugin" / "tests" / "fixtures" / "session_id_vectors.json"
    copy.parent.mkdir(parents=True, exist_ok=True)
    copy.write_text(original, encoding="utf-8", newline="\n")
    monkeypatch.setattr(generator, "TABLE_PATH", host)
    monkeypatch.setattr(generator, "PLUGIN_COPY_PATH", copy)
    capsys.readouterr()

    assert main(["--check"]) != 0, "宿主表多一条向量、副本没跟 ⇒ 必须红"
    out = capsys.readouterr().out
    assert "[FAIL] 表已过期" in out, f"①支应红（宿主表已非现算结果）：\n{out}"
    assert "plugin-vs-host：副本与宿主表不一致" in out, f"②支也要红并具名：\n{out}"
    assert "首个差异行" in out, f"要打印首个差异行：\n{out}"


def test_in_sync_copies_make_check_green(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """(o) 正对照：两份同步 ⇒ 默认 `--check` 返回 0（有红有绿才算判据——防"恒红"假象）。"""
    import scripts.gen_session_id_vectors as generator

    host = tmp_path / "session_id_vectors.json"
    host.write_bytes(TABLE.read_bytes())
    copy = tmp_path / "plugin" / "tests" / "fixtures" / "session_id_vectors.json"
    copy.parent.mkdir(parents=True, exist_ok=True)
    copy.write_bytes(TABLE.read_bytes())
    monkeypatch.setattr(generator, "TABLE_PATH", host)
    monkeypatch.setattr(generator, "PLUGIN_COPY_PATH", copy)
    capsys.readouterr()

    assert main(["--check"]) == 0, "两份同步必须绿"
    out = capsys.readouterr().out
    assert "表未过期" in out and "plugin-vs-host" in out and "[FAIL]" not in out, out


def test_emit_mode_exists_and_default_does_not_write_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """(p) 模式存在且**默认不写副本**：`--emit-plugin-copy` 是 CLI 上的真模式（不是 docstring 承诺）。

    真跑 `--emit-plugin-copy` 会写插件仓 ⇒ 这里证明三件事：
    ① `--help` 里两个模式都在；② `--host-only` 不能脱离 `--check` 单用；③ 无参数默认运行**只写宿主表**
    （落点指 tmp_path）——"副本只在显式模式下写"由本条钉住，不靠人记得。
    """
    import scripts.gen_session_id_vectors as generator

    with pytest.raises(SystemExit) as help_exit:  # argparse --help 的正常退出
        main(["--help"])
    assert help_exit.value.code == 0
    help_text = capsys.readouterr().out
    assert "--emit-plugin-copy" in help_text and "--check" in help_text, help_text

    with pytest.raises(SystemExit) as bad_usage:  # --host-only 收窄的是 --check 的面，不能单用
        main(["--host-only"])
    assert bad_usage.value.code == 2

    host = tmp_path / "session_id_vectors.json"
    copy = tmp_path / "plugin" / "tests" / "fixtures" / "session_id_vectors.json"
    monkeypatch.setattr(generator, "TABLE_PATH", host)
    monkeypatch.setattr(generator, "PLUGIN_COPY_PATH", copy)
    capsys.readouterr()

    assert main([]) == 0
    assert host.exists(), "默认模式该写宿主表"
    assert not copy.exists(), "默认模式**不许**写插件副本（写两份只在 --emit-plugin-copy 下发生）"


def test_host_ahead_of_copy_must_be_red(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """(q) ⭐ 坏样本③：**宿主表加了一条向量、副本没跟** ⇒ 默认 `--check` 必须红，且**具名**报出是哪条。

    ⚠️ **本条与 (c)(d) 的形态不同，理由说清**：(c)(d) 的坏样本改的是**被测判据自己的输入**
    （表字节 / 权威算法），故只能断言"**不红**"、把红交给 `--runxfail` 展示 —— 那里"红"是**期望结果**。
    本条的漂移是**在判据之外造的**（宿主表与副本的集合差）：判据跑起来本就该红、也确实红，
    ⇒ 断言直接写"**判定结果**"（红 + 归因）而非"不红"，于是**不能挂 `xfail`**
    （`xfail(strict=True)` 要求用例必须 FAILED；挂上就等于用一条"允许红"的标记去掩盖一条"必须红"的要求）。
    本条是**正向证红**：跑绿本身就是证据（下方"直看红"那条命令会打印被判到的原文）。

    这是"两份副本内容级对账"要钉的那条漂移：宿主侧重生成后表里多一条，
    副本还停在旧内容 ⇒ 插件侧会拿旧表算，**两边都不报错**，只是各算各的。

    坏样本怎么造（**三处都回读确认**，不靠"替换应当成功"）：

    1. 宿主表落点写**干净现算内容**（走生成器自己的 `render()`，不手抄序列化参数）；
    2. 把表里**一条向量的 case 名改掉**（锚点 = 该条 case 行 + 该条 `covers` 行，两段一起替换 ⇒ 唯一）：
       `群聊-无account-有scope` → `群聊-无account-有国scope`（在 `有` 后插入码点更大的 `国` ⇒ 排序位置**不变**），
       于是宿主表里多出一条 case、少了一条 —— 正是"宿主表加一条向量、副本没跟"的形状，
       且不会把红混进"表未排序"这种无关原因；该条 `expected` **不动**（仍由权威算法现算得出
       ⇒ 表的"值"部分保持正确，红只出自**集合差**）；
    3. 回读新表断言：新 case **在**新表、旧 case **不在**、条数**不变**、排序**不变**
       （真读磁盘 —— "替换静默没匹配上、用例照绿"那口坑就靠这几处断言堵）。

    副本路径**可注入**（monkeypatch 到 tmp 落点）⇒ 真插件仓那份一个字节都不动。

    直看红（`-s` 让它打印被判到的原文）：
        uv run pytest tests/unit/common/test_session_id_vectors.py -k host_ahead_of_copy -s
    """
    import scripts.gen_session_id_vectors as generator  # 同本文件既有各条：判据要改的是模块常量

    # ① 宿主表 = 干净现算内容（一条不差），副本 = 同一份原始字节
    original = generator.render(generator.build_payload())
    host = tmp_path / "session_id_vectors.json"
    host.write_text(original, encoding="utf-8", newline="\n")
    copy = tmp_path / "plugin" / "tests" / "fixtures" / "session_id_vectors.json"
    copy.parent.mkdir(parents=True, exist_ok=True)
    copy.write_bytes(host.read_bytes())
    clean_cases = [vector["case"] for vector in json.loads(original)["vectors"]]

    # ② 宿主表"加一条"：改掉一条向量的 case 名（两段锚点一起匹配，保证唯一命中）
    stale_case, drifted_case = "群聊-无account-有scope", "群聊-无account-有国scope"
    anchor = f'      "case": "{stale_case}"'
    covers = '"covers": "群支 + route 只有 scope 段 ⇒ 形状 platform_scope:x_group"'
    drifted_text = original.replace(anchor, f'      "case": "{drifted_case}"').replace(
        covers, f'"{covers[1:-1]}（证红：宿主表加一条、副本没跟）"'
    )
    assert drifted_text != original, "坏样本没改成（锚点没匹配上 ⇒ 用例会照绿）"
    assert drifted_text.count(anchor) == 0 and drifted_text.count(f'"{drifted_case}"') == 1, (
        "替换没落对位置（新 case 应恰好出现一次、旧 case 应消失）"
    )
    host.write_text(drifted_text, encoding="utf-8", newline="\n")

    # ③ 变异后回读确认（改的真是磁盘上那份，不是内存里的副本）
    read_back_cases = [vector["case"] for vector in json.loads(host.read_text(encoding="utf-8"))["vectors"]]
    assert drifted_case in read_back_cases, "变异没落盘（宿主表里没有新 case）"
    assert stale_case not in read_back_cases, "旧 case 应当已被改名（否则不算'加了一条'）"
    assert len(read_back_cases) == len(clean_cases), "只改名 ⇒ 条数不变（多/少一条都说明锚点锚歪了）"
    assert read_back_cases == sorted(read_back_cases), "改名后表仍须按 case 名排序（不许把红混进'表未排序'）"

    # ④ 判据面（副本路径可注入：真插件仓那份一个字节都不动）
    monkeypatch.setattr(generator, "TABLE_PATH", host)
    monkeypatch.setattr(generator, "PLUGIN_COPY_PATH", copy)
    capsys.readouterr()

    assert main(["--check"]) != 0, "宿主表比副本多一条向量 ⇒ 必须红（两边各自算 = 跨进程键分叉且没人报）"
    out = capsys.readouterr().out
    assert "plugin-vs-host" in out, f"红要落在 plugin-vs-host 支：\n{out}"
    # ⚠️ ①支**必然**同时红：宿主表"加了向量"就等于"与权威算法现算的对不上了"——定义使然，
    #    不是本条的判据面。本条要钉的是②支那层**归因**：字节层只会说"不一致 / 首个差异行：第 N 行"，
    #    归因层要**逐条具名**报出是哪条 case 没跟上（否则 14214 字节的表只能靠人肉 diff）。
    assert "首个差异行" in out, f"要打印首个差异行（判红那层的字节证据）：\n{out}"
    assert "内容级对账" in out, f"要打内容级对账那一层：\n{out}"
    assert drifted_case in out, f"要**具名**报出没跟上的那条 case（不能只说'不一致'）：\n{out}"
    assert "只在宿主表（副本没跟上）" in out, f"要指明漂移方向是'宿主表多、副本没跟'：\n{out}"
    assert "副本缺失" not in out, f"副本存在（只是旧），不该报缺失：\n{out}"
    print("\n[判据扫到的原文]\n" + out)
