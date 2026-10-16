"""生成 session_id 向量表（表 = 输入 → 期望；唯一真源是权威算法本身）。

为什么有这张表
    宿主侧 `SessionUtils.calculate_session_id()` 与插件侧 `SessionIdMapper.calculate_session_id()`
    是**两份实现**——插件跑在独立进程里、无法 import `src/`，只能在插件内复制算法
    （见 `plugins/maibot-team.napcat-adapter/session_mapper.py` 的模块 docstring）。
    本脚本从**宿主算法**逐条算出 (platform, user_id, group_id, account_id, scope) → session_id，
    落成 `src/common/utils/session_id_vectors.json`，把"两份实现必须算出同一个 key"钉成可判据的数据。

用法
    uv run python scripts/gen_session_id_vectors.py            # 重新生成（覆盖表）
    uv run python scripts/gen_session_id_vectors.py --check    # 与磁盘表**逐字节**比对：0 = 未过期，1 = 已过期

约定
    · 表是**生成物**：要改表就改本脚本；手改表里一行会让 `--check` 变红
      （判据在 `tests/unit/common/test_session_id_vectors.py`）。
    · 表里**只放输入与期望**，不放算法：算法一改，期望值随之改变 ⇒ 表过期被抓住。
    · 每条向量带 `covers` 字段，逐条写明它覆盖哪个分支/边界。key 形状（插件 docstring 同款口径）：
      群聊 `platform[_account:x][_scope:x]_group_id`；私聊 `platform[_account:x][_scope:x]_user_id_private`。
    · 表外另有两类东西不在表里，由 `_self_check()` 在生成期与 `--check` 时都跑：
      ① **异常型边界**（没有 session_id 期望值，只有异常类型）：两个 id 都给假值 ⇒ ValueError（守卫分支）；
         `int` 型 id ⇒ TypeError（签名是 Optional[str]，`"_".join` 只吃 str）；
      ② **表内恒等式**：两个 id 都给 ⇒ 与"只给 group_id"同值（群支优先）；空串 account_id/scope 与 None 等价。
"""

from argparse import ArgumentParser
from pathlib import Path
from typing import Any

import json
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.common.utils.utils_session import SessionUtils  # noqa: E402  （脚本直跑时 sys.path[0]=scripts/，须先补仓根）

TABLE_PATH = PROJECT_ROOT / "src" / "common" / "utils" / "session_id_vectors.json"
GENERATOR_VERSION = 1
COMMENT = (
    "本文件为生成物，改它请改生成器（scripts/gen_session_id_vectors.py）"
    "——手改会在‘表是否过期’检查里变红。"
)

# 超长边界（≥200 字符）：单段长度只影响 hash 输入，算法里没有长度分支 ⇒ 期望值仍由现算得出。
_LONG_USER_ID = "u" * 220
_LONG_GROUP_ID = "g" * 300
_LONG_SCOPE = "s" * 200


def _spec(
    case: str,
    covers: str,
    *,
    platform: str = "qq",
    account_id: str | None = None,
    scope: str | None = None,
    user_id: str | None = None,
    group_id: str | None = None,
) -> dict[str, Any]:
    """一条向量：只写**输入**与它覆盖的分支说明；期望值不在这里手抄。"""
    return {
        "case": case,
        "covers": covers,
        "platform": platform,
        "account_id": account_id,
        "scope": scope,
        "user_id": user_id,
        "group_id": group_id,
    }


_VECTOR_SPECS: tuple[dict[str, Any], ...] = (
    # ── route 四组合 × 私聊支（4 条） ─────────────────────────────
    _spec(
        "私聊-无account-无scope",
        "私聊支：group_id 为假 ⇒ key 尾接字面量 'private'；account/scope 皆假 ⇒ route 段整体缺席",
        user_id="42",
    ),
    _spec(
        "私聊-有account-无scope",
        "私聊支 + route 只有 account 段（scope 假）⇒ 形状 platform_account:x_user_private",
        account_id="10001",
        user_id="42",
    ),
    _spec(
        "私聊-无account-有scope",
        "私聊支 + route 只有 scope 段（account 假）⇒ 形状 platform_scope:x_user_private",
        scope="webui",
        user_id="42",
    ),
    _spec(
        "私聊-有account-有scope",
        "私聊支 + route 两段齐全，钉住顺序 = account 在前、scope 在后",
        account_id="10001",
        scope="webui",
        user_id="42",
    ),
    # ── route 四组合 × 群支（4 条） ───────────────────────────────
    _spec(
        "群聊-无account-无scope",
        "群支：group_id 为真 ⇒ key 尾**直接**接 group_id，不追加 'private'；route 段缺席",
        group_id="88888",
    ),
    _spec(
        "群聊-有account-无scope",
        "群支 + route 只有 account 段 ⇒ 形状 platform_account:x_group",
        account_id="10001",
        group_id="88888",
    ),
    _spec(
        "群聊-无account-有scope",
        "群支 + route 只有 scope 段 ⇒ 形状 platform_scope:x_group",
        scope="webui",
        group_id="88888",
    ),
    _spec(
        "群聊-有account-有scope",
        "群支 + route 两段齐全（群侧重合私聊侧的顺序断言）",
        account_id="10001",
        scope="webui",
        group_id="88888",
    ),
    # ── 两个 id 都给：群支优先（4 条，覆盖 route 四组合） ──────────
    _spec(
        "两id都给-群支优先-无account-无scope",
        "user_id 与 group_id 同时给 ⇒ 群支优先、user_id 不参与拼接；必须与'群聊-无account-无scope'同值",
        user_id="42",
        group_id="88888",
    ),
    _spec(
        "两id都给-群支优先-有account-无scope",
        "群支优先 + account 段；必须与'群聊-有account-无scope'同值（user_id 被忽略）",
        account_id="10001",
        user_id="42",
        group_id="88888",
    ),
    _spec(
        "两id都给-群支优先-无account-有scope",
        "群支优先 + scope 段；必须与'群聊-无account-有scope'同值（user_id 被忽略）",
        scope="webui",
        user_id="42",
        group_id="88888",
    ),
    _spec(
        "两id都给-群支优先-有account-有scope",
        "群支优先 + route 两段；必须与'群聊-有account-有scope'同值（user_id 被忽略）",
        account_id="10001",
        scope="webui",
        user_id="42",
        group_id="88888",
    ),
    # ── 空串 vs None（4 条） ─────────────────────────────────────
    _spec(
        "空串account-等价于None-群",
        "空串 account_id 是假值 ⇒ 与 None 等价、不进 route；必须与'群聊-无account-无scope'同值",
        account_id="",
        group_id="88888",
    ),
    _spec(
        "空串scope-等价于None-私聊",
        "空串 scope 是假值 ⇒ 与 None 等价；必须与'私聊-无account-无scope'同值",
        scope="",
        user_id="42",
    ),
    _spec(
        "空串account与scope-等价于None-私聊",
        "route 两段都给空串 ⇒ route 整体缺席（插件构造默认 account_id='' scope='' 走的就是这条路径）",
        account_id="",
        scope="",
        user_id="42",
    ),
    _spec(
        "空串user_id-群支不参与",
        "空串 user_id 是假值：既不触发守卫（group_id 为真），也不参与拼接；必须与'群聊-无account-无scope'同值",
        user_id="",
        group_id="88888",
    ),
    # ── 分隔符 `_` / `:`（5 条） ─────────────────────────────────
    _spec(
        "分隔符-user_id含下划线",
        "下划线是 key 分隔符：id 内的字面下划线照抄 ⇒ 私聊 key 的段数比常规多（形状歧义留档）",
        user_id="a_b",
    ),
    _spec(
        "分隔符-group_id含下划线",
        "群支 group_id 内的下划线照抄 ⇒ 与 platform/route 段之间仍只有一条 '_' 相隔（形状歧义留档）",
        group_id="g_1",
    ),
    _spec(
        "分隔符-user_id含冒号",
        "冒号只属于 route 段的字面格式（account:/scope:）：id 内的冒号照抄、不被再解释",
        user_id="a:b",
    ),
    _spec(
        "分隔符-scope含冒号",
        "route 段内的冒号照抄 ⇒ 'scope:a:b' 整体是一个段，不会被拆成两段",
        scope="a:b",
        user_id="42",
    ),
    _spec(
        "分隔符-account_id含下划线",
        "account 段内的下划线照抄（account:x_y 是一个整段）",
        account_id="acc_1",
        user_id="42",
    ),
    # ── 空白（3 条） ─────────────────────────────────────────────
    _spec(
        "空白-user_id含首尾空格",
        "id 不做 strip：首尾空格进 key ⇒ 与 '42' 不同 hash（本行只钉 ' 42 ' 这一支）",
        user_id=" 42 ",
    ),
    _spec(
        "空白-user_id纯空格",
        "纯空格是**真值** ⇒ 不进守卫分支（守卫只判假值），私聊支照常拼 '   ' 与 'private'",
        user_id="   ",
    ),
    _spec(
        "空白-platform含下划线",
        "platform 是位置参数：含下划线照抄，key 首段形状随之变形（无校验、无规范化）",
        platform="qq_sandbox",
        user_id="42",
    ),
    # ── 字面量撞面（2 条） ───────────────────────────────────────
    _spec(
        "歧义-user_id字面private",
        "user_id 恰好等于私聊后缀 ⇒ key 尾出现两段 'private'（形状歧义留档，不改算法、只钉值）",
        user_id="private",
    ),
    _spec(
        "歧义-group_id字面private",
        "群支 group_id 恰为 'private' ⇒ key 尾只有一段 private；与上一条（两段）对照，两者 hash 不同",
        group_id="private",
    ),
    # ── Unicode（5 条） ─────────────────────────────────────────
    _spec(
        "unicode-user_id中文",
        "非 ASCII 走 md5 前的 utf-8 编码路径（encode() 默认 utf-8 ⇒ 中文按 3 字节/字进 hash）",
        user_id="张三",
    ),
    _spec(
        "unicode-group_id中文",
        "群支 group_id 中文同上（编码路径与私聊支同一条）",
        group_id="测试群",
    ),
    _spec(
        "unicode-user_id含emoji",
        "emoji 落在基本多文种平面外（4 字节 utf-8 序列）⇒ 与中文同一编码路径",
        user_id="麦麦🙂",
    ),
    _spec(
        "unicode-scope中文",
        "route 段内中文照抄 ⇒ 'scope:网页端' 是一个整段",
        scope="网页端",
        user_id="42",
    ),
    _spec(
        "unicode-platform含中文",
        "platform 中文照抄（platform 无校验）",
        platform="qq中文",
        user_id="42",
    ),
    # ── 超长（3 条） ─────────────────────────────────────────────
    _spec(
        "超长-user_id220字符",
        "≥200 字符不截断：hash 前无长度分支 ⇒ 只钉'原样进 hash'这一条",
        user_id=_LONG_USER_ID,
    ),
    _spec(
        "超长-group_id300字符",
        "群支超长同样不截断（与私聊支共用编码路径，差异只在支路拼法）",
        group_id=_LONG_GROUP_ID,
    ),
    _spec(
        "超长-scope200字符",
        "route 段超长不截断（route 段与 id 段拼接方式相同）",
        scope=_LONG_SCOPE,
        user_id="42",
    ),
    # ── 数字型（字符串 vs int）（3 条） ───────────────────────────
    _spec(
        "数字型-user_id字符串123",
        "数字**字符串**按 str 原样拼（对照：int 123 会 TypeError，见 _self_check ② 的探针，不落表）",
        user_id="123",
    ),
    _spec(
        "数字型-group_id前导零",
        "前导零保留、不做数值规整 ⇒ '007' 与 '7' 是不同 key（本行只钉 '007'）",
        group_id="007",
    ),
    _spec(
        "数字型-account_id字符串",
        "account 段内的数字字符串照抄（route 段不再做类型转换）",
        account_id="10001",
        user_id="123",
    ),
    # ── 跨平台（1 条） ──────────────────────────────────────────
    _spec(
        "跨平台-同id不同platform",
        "platform 是 key 首段、必然参与 ⇒ 同 id 不同平台必须得到不同 hash（与'私聊-无account-无scope'对照）",
        platform="telegram",
        user_id="42",
    ),
)


def _call(
    platform: str = "qq",
    *,
    account_id: str | None = None,
    scope: str | None = None,
    user_id: str | None = None,
    group_id: str | None = None,
) -> str:
    """把一组输入交给**权威算法**（本脚本不复制算法、不做第二份实现）。"""
    return SessionUtils.calculate_session_id(
        platform,
        user_id=user_id,
        group_id=group_id,
        account_id=account_id,
        scope=scope,
    )


def _expected(spec: dict[str, Any]) -> str:
    """一条向量的期望值 = 权威算法现算。"""
    return _call(
        spec["platform"],
        account_id=spec["account_id"],
        scope=spec["scope"],
        user_id=spec["user_id"],
        group_id=spec["group_id"],
    )


def _self_check() -> None:
    """生成期自检：异常型边界 + 表内恒等式 + 表自身形状。破了就抛 ⇒ 生成/比对两条路都非零退出。"""
    # ① 守卫分支：两个 id 都给假值（None / 空串）必须抛 ValueError
    for user_id, group_id in ((None, None), ("", "")):
        try:
            _call(user_id=user_id, group_id=group_id)
        except ValueError:
            continue
        raise AssertionError(f"守卫分支失效：user_id={user_id!r} group_id={group_id!r} 没抛 ValueError")

    # ② 签名外的 int 型 id：应为 TypeError（"_".join 只吃 str），而不是被静默 str() 化
    try:
        _call(user_id=123)  # 故意越签名：这里要的正是"签名说 Optional[str]、实际不吃 int"的证据
    except TypeError:
        pass
    else:
        raise AssertionError("int 型 id 没抛 TypeError ⇒ 签名（Optional[str]）与实际行为脱节")

    # ③ 群支优先：两个 id 都给 ⇒ 必须与只给 group_id 同值（route 四组合逐个验）
    for account_id, scope in ((None, None), ("10001", None), (None, "webui"), ("10001", "webui")):
        both = _call(account_id=account_id, scope=scope, user_id="42", group_id="88888")
        group_only = _call(account_id=account_id, scope=scope, group_id="88888")
        if both != group_only:
            raise AssertionError(f"群支优先失效：account_id={account_id!r} scope={scope!r}")

    # ④ 假 route 等价：空串 account_id / scope 与 None 同值
    if _call(account_id="", scope="", user_id="42") != _call(user_id="42"):
        raise AssertionError("空串 account_id/scope 与 None 不等价")

    # ⑤ 表自身形状：case 名唯一（排序才稳定）+ 每条都有 covers（逐条注明覆盖分支是硬要求）
    cases = [spec["case"] for spec in _VECTOR_SPECS]
    if len(set(cases)) != len(cases):
        raise AssertionError("case 名重复 ⇒ 排序不稳定、--check 会假红")
    for spec in _VECTOR_SPECS:
        if not spec["covers"]:
            raise AssertionError(f"向量 {spec['case']!r} 缺 covers：必须逐条注明覆盖哪个分支/边界")


def build_payload() -> dict[str, Any]:
    """按权威算法现算整张表（排序键 = case 名 ⇒ 逐字节可复现）。"""
    _self_check()
    vectors: list[dict[str, Any]] = []
    for spec in sorted(_VECTOR_SPECS, key=lambda item: item["case"]):
        vector = dict(spec)
        vector["expected"] = _expected(spec)
        vectors.append(vector)
    return {
        "_comment": COMMENT,
        "generator_version": GENERATOR_VERSION,
        "generated_by": "scripts/gen_session_id_vectors.py",
        "vectors": vectors,
    }


def render(payload: dict[str, Any]) -> str:
    """固定序列化参数：ensure_ascii=False（保中文）、缩进 2、末尾恰好一个换行 ⇒ 逐字节可复现。"""
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def write_table(path: Path | None = None) -> Path:
    """把现生成的表写盘（覆盖）。`path` 缺省 = TABLE_PATH（调用时解析，便于测试改指向）。"""
    target = TABLE_PATH if path is None else path
    payload = build_payload()
    target.parent.mkdir(parents=True, exist_ok=True)
    # newline="\n"：Windows 上不落 CRLF，保证与 --check 的逐字节比对跨平台一致
    target.write_text(render(payload), encoding="utf-8", newline="\n")
    print(f"[OK] 已写出向量表：{target}（{len(payload['vectors'])} 条向量）")
    return target


def check_table(path: Path | None = None) -> int:
    """表过期检查：磁盘表 vs 按权威算法现生成 —— **逐字节**比对。

    Returns:
        int: 0 = 未过期；1 = 已过期（已打印首个差异行）。
    """
    target = TABLE_PATH if path is None else path
    generated_text = render(build_payload())
    if not target.exists():
        print(f"[FAIL] 表不存在：{target} —— 先跑 `uv run python scripts/gen_session_id_vectors.py` 生成")
        return 1

    if target.read_bytes() == generated_text.encode("utf-8"):
        print(f"[OK] 表未过期：{target}（{len(json.loads(generated_text)['vectors'])} 条向量，逐字节一致）")
        return 0

    disk_lines = target.read_bytes().decode("utf-8", errors="replace").splitlines()
    generated_lines = generated_text.splitlines()
    print(f"[FAIL] 表已过期：{target} 与权威算法现生成的结果不一致（逐字节比对失败）")
    for index in range(min(len(disk_lines), len(generated_lines))):
        if disk_lines[index] != generated_lines[index]:
            print(f"  首个差异行：第 {index + 1} 行")
            print(f"    表上： {disk_lines[index]}")
            print(f"    生成： {generated_lines[index]}")
            return 1
    print(f"  行数不同：表 {len(disk_lines)} 行 / 生成 {len(generated_lines)} 行")
    return 1


def main(argv: list[str] | None = None) -> int:
    """CLI：默认重新生成；`--check` 只比对不写盘（0 = 未过期；1 = 已过期）。"""
    parser = ArgumentParser(description="生成/校验 session_id 向量表（真源 = src/common/utils/utils_session.py）")
    parser.add_argument("--check", action="store_true", help="与磁盘表逐字节比对；不一致退出码 1（不写文件）")
    args = parser.parse_args(argv)

    if args.check:
        return check_table()

    write_table()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
