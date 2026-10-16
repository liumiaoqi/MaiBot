"""`msg-seam` P2 ③ 的探针：出站契约**两条支路各一份键集**，且校验**红得起来**。

四条判据（缺一不可）：
1. **两份不是一份**：契约里两条支路的键集必须**不同**（合成一份 ⇒ 红）；
2. **B 支路显式标"未证实/无生产者"**：`has_producer_evidence(BRIDGE) is False`，且主仓侧**今天没有**
   构造 B 形状载荷的写者（有人加了生产者 ⇒ 这条红，逼他先改证据字段）；
3. **方向性可赋值**（源级）：插件 `@Tool` 声明的 `required` ⊆ 写者 `plugin_driver` 实际提供的键；
4. **合成缺键 ⇒ 必红**：`validate` 对"少给一个必需键"必须报出来（含鉴别力样例）。
"""

import ast
from pathlib import Path

import pytest

from src.plugin_runtime_v2.host.gateway_payload_contract import (
    BRANCH_BRIDGE,
    BRANCH_TOOL,
    NESTED_REQUIRED_KEYS,
    PRODUCER_EVIDENCE,
    REQUIRED_KEYS,
    branches,
    has_producer_evidence,
    validate,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
PLUGIN_PY = REPO_ROOT / "plugins" / "maibot-team.napcat-adapter" / "plugin.py"
PLUGIN_DRIVER_PY = REPO_ROOT / "src" / "platform_io" / "drivers" / "plugin_driver.py"


# ── 1 两份不是一份 ─────────────────────────────────────────────────────


def test_two_branches_with_different_key_sets() -> None:
    """契约必须覆盖**两条**支路，且两条的键集**不同**（合成一份就失去意义）。"""

    assert branches() == (BRANCH_TOOL, BRANCH_BRIDGE)
    assert set(REQUIRED_KEYS[BRANCH_TOOL]) != set(REQUIRED_KEYS[BRANCH_BRIDGE])
    assert not (set(REQUIRED_KEYS[BRANCH_TOOL]) & set(REQUIRED_KEYS[BRANCH_BRIDGE])), "两条支路不该共享必需键"


# ── 2 B 支路：未证实 + 今天不该有生产者 ────────────────────────────────


def test_bridge_branch_is_marked_unproven() -> None:
    assert has_producer_evidence(BRANCH_BRIDGE) is False
    assert PRODUCER_EVIDENCE[BRANCH_BRIDGE].startswith("未证实"), "B 支路必须自述'未证实'"
    assert has_producer_evidence(BRANCH_TOOL) is True, "A 支路有真机证据"


def test_bridge_branch_has_no_producer_today() -> None:
    """**新运行时侧**今天没有构造 B 形状的写者（`src/plugin_runtime_v2/host/**`）。

    ⚠️ 口径修正（2026-10-17，探针第一次跑就抓到我说得太宽）：`message_segment` **不是**主仓没有的东西 ——
    它是 **legacy maim_message** 那套形状，宿主侧先例在 `src/chat/message_receive/uni_message_sender.py`
    与 `src/common/utils/utils_message.py`（共 47 处命中）。**真正未证实的是"插件侧 bridge 支路在生产里有没有出站"**
    （真机：连得上、零记录）。⇒ 本条只查**新运行时**（`plugin_runtime_v2/host`，排除本契约自身），
    盯的是"**网关侧会不会悄悄长出一个 B 生产者**"。
    """

    scoped = [
        path
        for path in (REPO_ROOT / "src" / "plugin_runtime_v2" / "host").rglob("*.py")
        if path.name != "gateway_payload_contract.py"
    ]
    hits = [
        f"{path.relative_to(REPO_ROOT)}:{index}"
        for path in scoped
        for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1)
        if "message_segment" in line
    ]
    assert hits == [], f"新运行时侧出现了 B 形状的写者：{hits} —— 请先更新契约的 PRODUCER_EVIDENCE"


# ── 3 方向性可赋值（源级：读者必需 ⊆ 写者提供）─────────────────────────


def _reader_required_keys(tool_name: str = "napcat.send_text") -> set[str]:
    """从插件 `plugin.py` 的 `@Tool(...)` 里取 `parameters_schema["required"]`。"""

    tree = ast.parse(PLUGIN_PY.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Name) and func.id == "Tool"):
            continue
        keywords = {kw.arg: kw.value for kw in node.keywords}
        name_node = keywords.get("name")
        if not (isinstance(name_node, ast.Constant) and name_node.value == tool_name):
            continue
        schema_node = keywords.get("parameters_schema")
        schema = ast.literal_eval(schema_node) if schema_node is not None else {}
        return set(schema.get("required") or [])
    raise AssertionError(f"插件里找不到 @Tool(name={tool_name!r}) —— 扫描器自己瞎了")


def _writer_provided_keys() -> set[str]:
    """从写者 `plugin_driver.py` 里取 `args={...}` 的字面键（它是往工具送载荷的地方）。"""

    tree = ast.parse(PLUGIN_DRIVER_PY.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.keyword) and node.arg == "args" and isinstance(node.value, ast.Dict):
            return {k.value for k in node.value.keys if isinstance(k, ast.Constant)}
    raise AssertionError("写者里找不到 args={...} —— 扫描器自己瞎了")


def test_writer_provides_superset_of_reader_requires() -> None:
    """**方向性可赋值**：写者提供的键 ⊇ 读者声明必需（今晚 `KeyError: 'session_id'` 就是这里破了）。"""

    required = _reader_required_keys()
    provided = _writer_provided_keys()

    assert required, "读者声明里 required 为空 —— 扫描器自己瞎了"
    assert required <= provided, f"写者少给了必需键：{sorted(required - provided)}（多给无妨：{sorted(provided - required)}）"
    # 契约本身与读者声明一致（别让契约飘成第二份规格）
    assert set(REQUIRED_KEYS[BRANCH_TOOL]) == required, "契约的 A 键集与插件声明不一致"


def test_discrimination_sabotaged_writer_must_be_caught() -> None:
    """**鉴别力**：合成一个"少给 `session_id`"的写者 ⇒ 上面的 ⊇ 判据必须判假。"""

    sabotaged = "args={'text': 'hi'}\n"
    tree = ast.parse(sabotaged)
    provided = {
        k.value
        for node in ast.walk(tree)
        if isinstance(node, ast.keyword) and node.arg == "args" and isinstance(node.value, ast.Dict)
        for k in node.value.keys
        if isinstance(k, ast.Constant)
    }
    assert not (_reader_required_keys() <= provided), "合成坏样本没被识别 ⇒ 判据失效"


# ── 4 合成缺键 ⇒ validate 必红 ─────────────────────────────────────────


@pytest.mark.parametrize(
    ("branch", "payload", "expect_missing"),
    [
        (BRANCH_TOOL, {"session_id": "s", "text": "t"}, []),
        (BRANCH_TOOL, {"session_id": "s"}, ["text"]),  # 今晚那类 KeyError 的形状
        (BRANCH_TOOL, {}, ["session_id", "text"]),
        (BRANCH_BRIDGE, {"message_info": {"group_info": {"group_id": "1"}}, "message_segment": {"data": []}}, []),
        (BRANCH_BRIDGE, {"message_segment": {"data": []}}, ["message_info"]),
        (BRANCH_BRIDGE, {"message_info": {}, "message_segment": {}}, ["message_segment.data"]),
        ("unknown-branch", {}, ["<未知支路:unknown-branch>"]),  # fail-closed 且具名
    ],
)
def test_validate_reports_missing_keys(branch: str, payload: dict, expect_missing: list) -> None:
    missing = validate(branch, payload)
    for expected in expect_missing:
        assert expected in missing, f"{branch}: 期望报出 {expected!r}，实际 {missing}"
    if not expect_missing:
        assert missing == [], f"{branch}: 合格载荷不该报缺 {missing}"


def test_bridge_nested_keys_are_declared() -> None:
    """B 的嵌套必需键在契约里单列（`message_segment.data` 是今晚确认过的形状）。"""

    assert "message_segment.data" in NESTED_REQUIRED_KEYS[BRANCH_BRIDGE]
