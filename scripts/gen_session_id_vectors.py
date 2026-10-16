"""生成 session_id 向量表（表 = 输入 → 期望；唯一真源是权威算法本身）。

为什么有这张表
    宿主侧 `SessionUtils.calculate_session_id()` 与插件侧 `SessionIdMapper.calculate_session_id()`
    是**两份实现**——插件跑在独立进程里、无法 import `src/`，只能在插件内复制算法
    （见 `plugins/maibot-team.napcat-adapter/session_mapper.py` 的模块 docstring）。
    本脚本从**宿主算法**逐条算出 (platform, user_id, group_id, account_id, scope) → session_id，
    落成 `src/common/utils/session_id_vectors.json`，把"两份实现必须算出同一个 key"钉成可判据的数据。

用法
    uv run python scripts/gen_session_id_vectors.py            # 重新生成（覆盖表）
    uv run python scripts/gen_session_id_vectors.py --check    # 与磁盘表比对（**行尾归一化**）：0 = 未过期，1 = 已过期
    uv run python scripts/gen_session_id_vectors.py --emit-plugin-copy   # 写两份：宿主表 + 插件仓内副本（逐字节相同）
    uv run python scripts/gen_session_id_vectors.py --check --host-only  # 只跑①支（生成物新鲜度），不查插件副本部署

两份部署（同一份内容、两处落点）
    ① 宿主表 `src/common/utils/session_id_vectors.json`；
    ② 插件仓内副本 `plugins/maibot-team.napcat-adapter/tests/fixtures/session_id_vectors.json`
       —— 路径**在插件仓内自足**（`tests/fixtures/...`，不写 `../../src/...`）：插件跑在独立进程、
       读不到宿主 `src/`，它只能读自己树里这份。
    两份由**同一个序列化器只渲染一次**产出 ⇒ 逐字节相同是构造性质（`emit_both` 写后还回读比对）；
    默认 `--check` **两支都跑、都打印（不短路）**：① 宿主表 vs 现算 ② 插件副本 vs 宿主表；
    副本**缺失也判红**（缺了 = 插件侧那份真源没部署 ⇒ 此后两份会各自漂移而无判据）；
    ②支判红后另打一层**内容级对账**（`_content_drift_report`）：按 case 逐条比、**具名**报出
    "只在宿主表（副本没跟上）：<case>" —— 判红仍是同一条（归一后逐字节不等），这一层只做**归因**；
    两支的**行尾都归一化后再比**（副本在插件仓里、宿主表在宿主检出里，物化行尾各由自己的检出环境决定）。

约定
    · 表是**生成物**：要改表就改本脚本；手改表里一行会让 `--check` 变红
      （判据在 `tests/unit/common/test_session_id_vectors.py`）。
    · **判据口径 = "行尾归一化后比对"，不是"逐字节"**：比对前把磁盘表的 `\r\n`（以及孤立 `\r`）
      归一成 `\n`，再与现生成的 LF 文本比。**依据**：`.gitattributes` 的 `* text=auto` 只归一
      "入库"、**不强制工作区**（`.gitattributes:7-10`）⇒ 同一个 blob 在不同检出环境会物化成
      不同行尾；**逐字节比会把"检出环境的行尾"当成"表的内容"**，同一份内容给出不同结论
      （2026-10-17 缺陷：主仓检出 CRLF ⇒ 假红，而 38/38 向量逐条全同）。
      ⚠️ 只归一**行尾**：**不改**大小写/空白/编码 ⇒ "表真被改一行"仍然红
      （`tests/unit/common/test_session_id_vectors.py` 里有四个坏/好样本钉住这两侧）。
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
# 插件仓内副本（第二处落点）。**路径在插件仓内自足**：宿主侧前缀是"怎么走到插件仓"，
# 插件侧看到的是 `tests/fixtures/...`（插件进程 import 不到宿主 `src/`，两份实现各读各的那份
# ⇒ 只能靠"同一序列化器产出 + --check 第二支"来防漂移）。
PLUGIN_COPY_PATH = (
    PROJECT_ROOT / "plugins" / "maibot-team.napcat-adapter" / "tests" / "fixtures" / "session_id_vectors.json"
)
GENERATOR_VERSION = 1
ENCODING = "utf-8"
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


def _normalize_eol(text: str) -> str:
    """把行尾归一到 LF：`\\r\\n` 与孤立 `\\r` 都算行尾差异，不是内容差异。

    只碰行尾这一个维度——大小写/空白/编码一律不动（动了就会把"内容真被改"也放过）。
    """
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _byte_index_to_line(text: str, index: int) -> tuple[int, int]:
    """字符偏移量 → (1 基行号, 1 基列号)；`splitlines(keepends=True)` 对 CRLF/孤立 CR 同样切行。"""
    line = 1
    column = 0
    for character in text:
        column += 1
        if character in "\r\n":
            line += 1
            column = 0
    return line, column


def _first_diff_line(disk_text: str, generated_text: str) -> str:
    """首个差异行的证据（1 基行号 + 两侧原文）。

    行尾归一后仍有差异 ⇒ 这不是"行尾"问题：先逐行定位首个差异行；**行数相同却逐行全等**
    时（归一后文本应已相等，走到这里只可能是编码/字节层面）退回首个差异**字符**位置
    —— 绝不打印"行数不同：N 行 / N 行"这种自相矛盾的措辞。
    """
    disk_lines = _normalize_eol(disk_text).splitlines()
    generated_lines = _normalize_eol(generated_text).splitlines()
    label = "行尾归一化后比对"

    for index in range(min(len(disk_lines), len(generated_lines))):
        if disk_lines[index] != generated_lines[index]:
            return (
                f"  首个差异行：第 {index + 1} 行（{label}）\n"
                f"    表上： {disk_lines[index]}\n"
                f"    生成： {generated_lines[index]}"
            )
    if len(disk_lines) != len(generated_lines):
        return f"  行数不同（{label}）：表 {len(disk_lines)} 行 / 生成 {len(generated_lines)} 行"

    limit = min(len(disk_text), len(generated_text))
    for index in range(limit):
        if disk_text[index] != generated_text[index]:
            line, column = _byte_index_to_line(disk_text, index)
            return (
                f"  首个差异字符：第 {line} 行第 {column} 列（{label}）\n"
                f"    表上： {disk_text[index]!r}\n"
                f"    生成： {generated_text[index]!r}"
            )
    return f"  前缀全等、仅在长度上分叉（{label}）：表 {len(disk_text)} 字符 / 生成 {len(generated_text)} 字符"


def write_table(path: Path | None = None) -> Path:
    """把现生成的表写盘（覆盖）。`path` 缺省 = TABLE_PATH（调用时解析，便于测试改指向）。"""
    # 默认模式**只写宿主表**，不碰插件仓 —— 要写两份得显式 `--emit-plugin-copy`（见 `emit_both`）。
    target = TABLE_PATH if path is None else path
    payload = build_payload()
    target.parent.mkdir(parents=True, exist_ok=True)
    # newline="\n"：Windows 上不落 CRLF，保证生成物跨平台一致（判据见 check_table 的行尾归一化）
    target.write_text(render(payload), encoding=ENCODING, newline="\n")
    print(f"[OK] 已写出向量表：{target}（{len(payload['vectors'])} 条向量）")
    return target


def check_table(path: Path | None = None) -> int:
    """表过期检查：磁盘表 vs 按权威算法现生成 —— **行尾归一化后**比对。

    比对前把磁盘表的 `\\r\\n`/孤立 `\\r` 归一成 `\\n`（见模块 docstring 的"判据口径"）：
    工作区物化行尾由检出环境决定，**不是表的内容**。其余维度一律逐字节相等才算未过期。

    Returns:
        int: 0 = 未过期；1 = 已过期（已打印首个差异行/字符）。
    """
    target = TABLE_PATH if path is None else path
    generated_text = render(build_payload())
    if not target.exists():
        print(f"[FAIL] 表不存在：{target} —— 先跑 `uv run python scripts/gen_session_id_vectors.py` 生成")
        return 1

    disk_bytes = target.read_bytes()
    disk_text = disk_bytes.decode(ENCODING, errors="replace")
    generated_bytes = generated_text.encode(ENCODING)
    eol_only = disk_bytes != generated_bytes and _normalize_eol(disk_text) == generated_text

    if disk_text == generated_text or eol_only:
        note = "（工作区行尾与生成物不同 = 检出环境差异，已归一）；" if eol_only else ""
        count = len(json.loads(generated_text)["vectors"])
        print(f"[OK] 表未过期：{target}（{count} 条向量，{note}行尾归一化后一致）")
        return 0

    print(f"[FAIL] 表已过期：{target} 与权威算法现生成的结果不一致（行尾归一化后比对失败）")
    print(_first_diff_line(disk_text, generated_text))
    return 1


def _report_first_difference(left: str, right: str, *, left_label: str, right_label: str) -> None:
    """打印首个差异行（两侧先各自行尾归一，再逐行比；前缀全同但行数不同则报行数）。

    给②支（plugin-vs-host）用——标签是"副本 / 宿主表"；①支用 `_first_diff_line`（它另带
    "首个差异字符"的兜底，见其 docstring）。
    """
    left_lines = _normalize_eol(left).splitlines()
    right_lines = _normalize_eol(right).splitlines()
    for index in range(min(len(left_lines), len(right_lines))):
        if left_lines[index] != right_lines[index]:
            print(f"  首个差异行：第 {index + 1} 行")
            print(f"    {left_label}：{left_lines[index]}")
            print(f"    {right_label}：{right_lines[index]}")
            return
    print(f"  行数不同：{left_label} {len(left_lines)} 行 / {right_label} {len(right_lines)} 行")


def _content_drift_report(copy_bytes: bytes, host_bytes: bytes, *, copy_label: str, host_label: str) -> list[str]:
    """**内容级对账**（归因层）：把两份副本按"向量条目"逐条比，**具名**报出漂移的 case。

    为什么在"归一后逐字节"之外还要这一层：字节判据给的是"**红了**"，这一层给的是
    "**红了、红在哪几条向量上**"——典型形态正是本条要钉的「宿主表加了一条向量、插件副本没跟」：
    字节层只会说"不一致 / 首个差异行：第 N 行"，这里直接点名 `只在宿主表（副本没跟上）：<case>`
    （14214 字节的表靠人肉 diff 是不现实的）。

    ⚠️ 它**只做归因**：判红仍是②支那一条（归一后逐字节不等），不另立判据、不放松强度。
    """
    try:
        copy_payload = json.loads(copy_bytes.decode(ENCODING))
        host_payload = json.loads(host_bytes.decode(ENCODING))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        return [f"  内容级对账：跳过（有一侧不是合法 JSON：{error}）"]

    copy_vectors = {vector["case"]: vector for vector in copy_payload.get("vectors", [])}
    host_vectors = {vector["case"]: vector for vector in host_payload.get("vectors", [])}

    only_host = sorted(set(host_vectors) - set(copy_vectors))
    only_copy = sorted(set(copy_vectors) - set(host_vectors))
    mismatched = sorted(
        case for case in set(host_vectors) & set(copy_vectors) if host_vectors[case] != copy_vectors[case]
    )

    lines = [f"  内容级对账（按 case 逐条比，共 {len(host_vectors)} / {len(copy_vectors)} 条）："]
    if not only_host and not only_copy and not mismatched:
        lines.append("    向量条目完全相同 ⇒ 差异不在向量内容上（头注 / 顶层字段 / 空白或行尾形态）")
        return lines
    if only_host:
        lines.append(f"    只在{host_label}（副本没跟上）：{', '.join(only_host)}")
    if only_copy:
        lines.append(f"    只在{copy_label}（宿主表没有）：{', '.join(only_copy)}")
    if mismatched:
        lines.append(f"    同 case 但条目内容不同：{', '.join(mismatched)}")
    return lines


def _report_content_drift(copy_bytes: bytes, host_bytes: bytes, *, copy_label: str, host_label: str) -> None:
    """打印内容级对账（`_content_drift_report` 的输出）。"""
    for line in _content_drift_report(copy_bytes, host_bytes, copy_label=copy_label, host_label=host_label):
        print(line)


def check_plugin_vs_host(copy_path: Path | None = None, host_path: Path | None = None) -> int:
    """② 支 plugin-vs-host：插件仓内副本 vs 宿主表 —— **行尾归一化后**比对。

    判据口径与①支一致（见模块 docstring 的"判据口径"）：宿主表与副本是**两处独立检出**
    （副本在插件仓里），物化行尾各由自己的检出环境决定 ⇒ 逐字节比会把"检出环境"当成"两份漂移"
    （2026-10-17 实测：主仓宿主表 14,601 字节 CRLF / 副本 14,214 字节 LF，归一化后 388 行逐行全同）。
    字节不同而内容相同 ⇒ **仍判绿**，但**如实打一条说明**（不静默：让"行尾差异"看得见）。

    副本**缺失也判红**（具名"副本缺失"）：缺了 = 插件侧那份真源没部署
    （插件读不到宿主 `src/`，它只能读自己树里这份）⇒ 此后两份各自漂移、没人看得见。

    判红之后另打一层**内容级对账**（`_content_drift_report`）：按 case 逐条比、**具名**报出
    "只在宿主表（副本没跟上）：<case>" —— 判红条件**不变**（仍是"归一化后逐字节不等"），这一层只做归因。

    Returns:
        int: 0 = 两份内容一致；1 = 不一致 / 副本缺失 / 宿主表缺失。
    """
    copy = PLUGIN_COPY_PATH if copy_path is None else copy_path
    host = TABLE_PATH if host_path is None else host_path

    if not copy.exists():
        print(f"[FAIL] plugin-vs-host：副本缺失 —— {copy}")
        print("  缺副本 = 插件侧没有可读的真源（插件进程 import 不到宿主 src/）⇒ 补的办法：")
        print("  `uv run python scripts/gen_session_id_vectors.py --emit-plugin-copy`（会写插件仓，需 lead 放行）")
        return 1

    if not host.exists():
        print(f"[FAIL] plugin-vs-host：宿主表缺失，无法比对 —— {host}（见 host-vs-fresh 支）")
        return 1

    copy_bytes = copy.read_bytes()
    host_bytes = host.read_bytes()
    copy_text = _normalize_eol(copy_bytes.decode(ENCODING, errors="replace"))
    host_text = _normalize_eol(host_bytes.decode(ENCODING, errors="replace"))

    if copy_text == host_text:
        note = ""
        if copy_bytes != host_bytes:
            note = (
                f"；两处检出物化行尾不同（副本 {len(copy_bytes)} 字节 / 宿主 {len(host_bytes)} 字节）"
                "= 检出环境差异，已归一"
            )
        print(f"[OK] plugin-vs-host：副本与宿主表一致 —— {copy}\n     == {host}（{len(host_text)} 字符{note}）")
        return 0

    print(f"[FAIL] plugin-vs-host：副本与宿主表不一致 —— {copy} vs {host}（行尾归一化后比对失败）")
    _report_first_difference(copy_text, host_text, left_label="副本", right_label="宿主表")
    # 归因层：判红照旧（上面那一条），下面这层只回答"红在哪几条向量上"
    _report_content_drift(copy_bytes, host_bytes, copy_label="副本", host_label="宿主表")
    return 1


def check_both_arms(path: Path | None = None) -> int:
    """默认 `--check`：**两支都跑、都打印**（不短路）——① host-vs-fresh + ② plugin-vs-host。

    为什么要"不短路"：只让一支坏时，**另一支的结论也必须打印出来** —— 否则分不清
    "另一支真的过了"还是"它根本没跑"（2026-10-17 教训：看着在、其实没生效）。
    `--check --host-only` 走的是①支单跑（`check_table`）。

    Returns:
        int: 0 = 两支全通过；1 = 任一支红（打印已指明是哪一支）。
    """
    host_status = check_table(path)
    copy_status = check_plugin_vs_host(host_path=path)
    if host_status or copy_status:
        print("[FAIL] --check：有未通过项（看上面对应的那一支：host-vs-fresh / plugin-vs-host）")
        return 1
    print("[OK] --check：两支全通过（宿主表 vs 现算 · 插件副本 vs 宿主表）")
    return 0


def emit_both(host_path: Path | None = None, copy_path: Path | None = None) -> int:
    """写两份：宿主表 + 插件仓内副本（`--emit-plugin-copy` 的实现）。

    "逐字节相同"不靠"两次调用应当一样"来保证 —— 这里**只渲染一次**，同一串字节写两个落点，
    再**回读**两份做逐字节比对（写盘环节若改了字节：编码 / 换行 / 截断，这里当场红）。

    Args:
        host_path: 宿主表落点（缺省 = TABLE_PATH；测试改指向用）。
        copy_path: 插件仓内副本落点（缺省 = PLUGIN_COPY_PATH；测试改指向用）。

    Returns:
        int: 0 = 两份都已写出且回读逐字节一致；1 = 写出的两份不一致。
    """
    host = TABLE_PATH if host_path is None else host_path
    copy = PLUGIN_COPY_PATH if copy_path is None else copy_path
    payload = build_payload()
    text = render(payload)  # ← 唯一一次渲染：两份内容由构造保证相同
    for target in (host, copy):
        target.parent.mkdir(parents=True, exist_ok=True)
        # newline="\n"：同 write_table，Windows 上不落 CRLF（否则两份"逐字节相同"在不同机器上不成立）
        target.write_text(text, encoding=ENCODING, newline="\n")

    host_bytes = host.read_bytes()
    copy_bytes = copy.read_bytes()
    print(f"[OK] 已写出两份（同一序列化器产出，{len(payload['vectors'])} 条向量，{len(host_bytes)} 字节）：")
    print(f"  宿主表：  {host}")
    print(f"  插件副本：{copy}")
    if host_bytes != copy_bytes:
        print("[FAIL] 两份写盘结果不一致（回读逐字节比对失败）—— 写盘环节改了字节，别急着提交")
        return 1
    print("[OK] 回读逐字节一致：两份 == 同一序列化器输出")
    return 0


def main(argv: list[str] | None = None) -> int:
    """CLI：默认重新生成；`--check` 只比对不写盘（0 = 未过期；1 = 已过期）。"""
    parser = ArgumentParser(description="生成/校验 session_id 向量表（真源 = src/common/utils/utils_session.py）")
    parser.add_argument("--check", action="store_true", help="与磁盘表比对（行尾归一化）；不一致退出码 1（不写文件）")
    parser.add_argument(
        "--emit-plugin-copy",
        action="store_true",
        help="写两份：宿主表 + 插件仓内副本 tests/fixtures/session_id_vectors.json（同一序列化器产出 ⇒ 逐字节相同）",
    )
    parser.add_argument(
        "--host-only",
        action="store_true",
        help="配合 --check：只跑①支 host-vs-fresh（生成物新鲜度），不查插件副本部署",
    )
    args = parser.parse_args(argv)

    if args.host_only and not args.check:
        parser.error("--host-only 只与 --check 搭配（它收窄的是 --check 的检查面）")
    if args.check and args.emit_plugin_copy:
        parser.error("--check 与 --emit-plugin-copy 互斥（前者不写盘、后者写盘）")

    if args.check and not args.host_only:
        return check_both_arms()

    if args.check:
        return check_table()

    if args.emit_plugin_copy:
        return emit_both()

    write_table()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
