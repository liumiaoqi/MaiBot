"""出站载荷契约（`msg-seam` P2 ③）—— **两条支路各一份键集，不许合成一份**。

## 为什么是两份而不是一份

今晚实测确认出站有**两条支路**，它们的载荷形状**本质不同**（不是同一契约的两个变体）：

| 支路 | 谁读 | 必需键 | 生产者证据 |
|---|---|---|---|
| **A · 工具 args** | 插件 `@Tool(name="napcat.send_text")` 的 `parameters_schema` | `session_id` · `text` | **已证实**（真机 `driver=plugin…gateway.qq_gateway tool=napcat.send_text`） |
| **B · maim_message bridge** | 插件 `_handle_outbound_message` | `message_info` · `message_segment` | ⚠️ **未证实（无生产者）** |

⚠️ **B 那份显式标"未证实/无生产者"**：bridge **连得上**（真机日志有 `[bridge] 已连接 maim_message WS`）
但**没有任何一次出站记录** ⇒ 本契约只记**形状**，**别当"已在用"**。
`has_producer_evidence("bridge") is False` 就是给下一个人看的判据。

## 怎么用它（谁读 / 怎么校验它会红）

- **谁读**：主仓写侧（`src/platform_io/drivers/plugin_driver.py`）+ **探针**
  （`tests/plugin_runtime_v2/runner/test_gateway_payload_contract.py`）。
- **校验两条**（缺一不可）：
  1. **源级"写者提供 ⊇ 读者必需"**：从插件 `plugin.py` 的 `@Tool` 声明里取 `required`，
     与写者实际构造的键对比 ⇒ **方向性可赋值**（这正是今晚 `KeyError: 'session_id'` 的形状）；
  2. **合成少一个必需键 ⇒ `validate` 必须报出来**（空列表 = 合格；非空 = 缺哪些）。
- **B 支路"今天不该有调用点"**：探针断言主仓侧**没有**构造 B 形状载荷的写者 ——
  若哪天有人加了生产者，那条断言会红，逼他先把 B 的"证据"字段改成"已证实"。
"""

from typing import Any, Dict, Iterable, List, Mapping

BRANCH_TOOL = "tool"
BRANCH_BRIDGE = "bridge"

#: 每条支路的**顶层必需键**（以**读者声明**为准，不是以写者习惯为准）
REQUIRED_KEYS: Dict[str, tuple[str, ...]] = {
    BRANCH_TOOL: ("session_id", "text"),
    BRANCH_BRIDGE: ("message_info", "message_segment"),
}

#: 嵌套必需键（点号路径）；B 比 A 深一层，故单列
NESTED_REQUIRED_KEYS: Dict[str, tuple[str, ...]] = {
    BRANCH_TOOL: (),
    BRANCH_BRIDGE: ("message_info", "message_segment.data"),
}

#: "至少给一个"的候选路径组（B 的目标既可能是群也可能是私聊接收者）
ALTERNATIVE_PATH_GROUPS: Dict[str, tuple[tuple[str, ...], ...]] = {
    BRANCH_TOOL: (),
    BRANCH_BRIDGE: (
        ("message_info.group_info.group_id", "message_info.receiver_info.user_info.user_id"),
    ),
}

#: 生产者证据（**只有 A 有真机证据**；B 的形状有**宿主侧 legacy 先例**，但**插件侧无出站记录**）
PRODUCER_EVIDENCE: Dict[str, str] = {
    BRANCH_TOOL: "已证实：真机 driver=plugin.maibot-team.napcat-adapter.gateway.qq_gateway tool=napcat.send_text",
    BRANCH_BRIDGE: (
        "未证实（插件侧无生产者）：形状是 legacy maim_message 那套"
        "（宿主侧先例见 src/chat/message_receive/uni_message_sender.py 与 src/common/utils/utils_message.py），"
        "但真机上 bridge 连得上、**零出站记录** ⇒ 本契约只记形状，别当'已在用'"
    ),
}


def branches() -> tuple[str, ...]:
    """契约覆盖的支路（**两条**；合成成一条即失去意义）。"""

    return tuple(REQUIRED_KEYS)


def has_producer_evidence(branch: str) -> bool:
    """该支路**是否有生产者证据**（B = False ⇒ 调用方/读者别当它已在用）。"""

    return not PRODUCER_EVIDENCE.get(branch, "未证实").startswith("未证实")


def _missing_paths(payload: Mapping[str, Any], paths: Iterable[str]) -> List[str]:
    missing: List[str] = []
    for path in paths:
        cursor: Any = payload
        for part in path.split("."):
            if not isinstance(cursor, Mapping) or part not in cursor:
                missing.append(path)
                break
            cursor = cursor[part]
    return missing


def validate(branch: str, payload: Mapping[str, Any]) -> List[str]:
    """校验某支路的载荷；返回**缺失的键/路径**（空列表 = 合格）。

    ⚠️ 只做**形状（键在不在）**校验：值的类型/语义由**读者声明的 schema** 负责（那条在插件侧）。
    ⚠️ 未知支路 ⇒ 返回 `["<未知支路>"]`（fail-closed：不认识就不放行，且**具名**）。
    """

    if branch not in REQUIRED_KEYS:
        return [f"<未知支路:{branch}>"]

    missing = _missing_paths(payload, REQUIRED_KEYS[branch])
    nested = NESTED_REQUIRED_KEYS.get(branch, ())
    missing.extend(_missing_paths(payload, (path for path in nested if path.count(".") > 0)))

    for group in ALTERNATIVE_PATH_GROUPS.get(branch, ()):
        if all(_missing_paths(payload, (path,)) for path in group):
            missing.append(" | ".join(group))
    return missing
