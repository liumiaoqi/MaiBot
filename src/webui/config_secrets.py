"""配置面密钥处理（P2）：读路径脱敏 + 写路径保真。

两个方向成对出现，缺一个都会出事：

- **读路径**（``redact_config_secrets``）：WebUI 返回配置时，密钥叶替换为 ``{path, set}``，
  真实值不出浏览器。遍历覆盖嵌套容器（object / dict / array）。
- **写路径**（``merge_payload_with_reference``）：保存配置时把 ``{path, set}`` 占位还原成
  配置文件里的原值（明文或 ``${VAR}`` 引用文本），并且**参考里 payload 未提到的字段原样保留**
  ——不整段 replace（表项的整段替换会把用户在页面上没看到的字段吃掉）。
- **兜底**（``find_unresolved_sentinels``）：占位还原失败时列出来，让调用方**拒绝落盘**，
  而不是把 ``{path, set}`` 当成密钥写进 TOML（那会把配置文件写成下一次加载就炸的形状）。

敏感键口径与 ``src/llm_models/request_snapshot.py::_SENSITIVE_KEYS`` **同源**；
两处一致性由 ``pytests/webui/test_config_secrets.py`` 的防漂移用例守住
（本模块不 import llm_models：配置面读配置不该被模型层的导入链拖进来）。
"""

from typing import Any, Mapping
import re

# 敏感键口径。改这里必须同步 request_snapshot._SENSITIVE_KEYS（有防漂移测试）。
SENSITIVE_KEYS: frozenset[str] = frozenset(
    {"authorization", "api_key", "apikey", "token", "secret", "password", "bearer"}
)

# 精确集之外的后缀补充规则。
# 依据（实测本仓 587 个配置键）：真实配置里 `maim_message.auth_token`、
# `maim_message.api_server_allowed_api_keys` 都是密钥，但名字不在精确集里
# ——只靠精确集，`GET /config/bot` 会把它们明文发给浏览器。
# 本规则在 587 个键上只多命中这两个（无假阳性）。
# ⚠️ 别加 `_tokens`（复数）：`max_tokens` 会中招——那是每任务输出上限，不是密钥。
SENSITIVE_KEY_SUFFIXES: tuple[str, ...] = ("_token", "_secret", "_password", "_api_key", "_api_keys", "_apikey")

SENTINEL_PATH_KEY = "path"
SENTINEL_SET_KEY = "set"


def is_sensitive_key(key: Any) -> bool:
    """判断键名是否属于敏感键（大小写不敏感；精确名或敏感后缀）。"""
    if not isinstance(key, str):
        return False
    normalized_key = key.lower()
    return normalized_key in SENSITIVE_KEYS or normalized_key.endswith(SENSITIVE_KEY_SUFFIXES)


def build_redaction_sentinel(path: str, configured: bool) -> dict[str, Any]:
    """构造密钥占位 ``{path, set}``。``set`` 表示"配置里是否已填了值"。"""
    return {SENTINEL_PATH_KEY: path, SENTINEL_SET_KEY: configured}


def is_redaction_sentinel(value: Any) -> bool:
    """判断一个值是不是密钥占位。

    只认带 ``path``(str) + ``set``(bool) 两个键的字典；允许多余键（前端可以附加展示信息）。
    """
    if not isinstance(value, Mapping):
        return False
    if SENTINEL_PATH_KEY not in value or SENTINEL_SET_KEY not in value:
        return False
    return isinstance(value[SENTINEL_PATH_KEY], str) and isinstance(value[SENTINEL_SET_KEY], bool)


def is_configured(value: Any) -> bool:
    """判断密钥叶是否"已配置"：空串 / None / 空容器都算没配。"""
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (Mapping, list, tuple, set)):
        return len(value) > 0
    return True


def redact_config_secrets(data: Any, *, path: str = "") -> Any:
    """读路径脱敏：递归把敏感叶替换为 ``{path, set}``。

    - 嵌套容器全覆盖：字典逐键、列表逐下标（``a.b[0].c`` 形态的路径）。
    - 敏感键的**值本身是容器**时整块替换、不再下钻——避免容器里的密钥从子键漏出去。
    - 非容器叶（str/int/float/bool/None/日期等）原样返回。

    Args:
        data: 待脱敏的配置数据（tomlkit 文档/表也可以，只按 Mapping / list 走）。
        path: 当前所在路径前缀，调用方一般留空。

    Returns:
        脱敏后的纯 Python 结构（dict/list），可直接进 JSON 响应。
    """
    if isinstance(data, Mapping):
        redacted: dict[str, Any] = {}
        for key, value in data.items():
            key_text = str(key)
            child_path = f"{path}.{key_text}" if path else key_text
            if is_sensitive_key(key_text):
                redacted[key_text] = build_redaction_sentinel(child_path, is_configured(value))
                continue
            redacted[key_text] = redact_config_secrets(value, path=child_path)
        return redacted

    if isinstance(data, (list, tuple)):
        return [redact_config_secrets(item, path=f"{path}[{index}]") for index, item in enumerate(data)]

    return data


def find_unresolved_sentinels(data: Any, *, path: str = "") -> list[str]:
    """列出仍然残留的密钥占位路径（写路径还原失败的证据）。

    判断从严：只看形状，不比对路径——宁可拒绝一次落盘，也不把占位写进配置文件。
    报告位置优先用占位自带的来源路径（它说明密钥**本来在哪**），再附上提交位置。
    """
    if is_redaction_sentinel(data):
        recorded_path = str(data.get(SENTINEL_PATH_KEY, "")).strip()
        if recorded_path and path and recorded_path != path:
            return [f"{recorded_path}（提交于 {path}）"]
        return [recorded_path or path or "未知位置"]

    if isinstance(data, Mapping):
        unresolved: list[str] = []
        for key, value in data.items():
            key_text = str(key)
            child_path = f"{path}.{key_text}" if path else key_text
            unresolved.extend(find_unresolved_sentinels(value, path=child_path))
        return unresolved

    if isinstance(data, (list, tuple)):
        unresolved = []
        for index, item in enumerate(data):
            unresolved.extend(find_unresolved_sentinels(item, path=f"{path}[{index}]"))
        return unresolved

    return []


def merge_payload_with_reference(payload: Any, reference: Any) -> Any:
    """写路径保真：占位还原 + 未见字段保留。

    对齐规则：

    - ``{path, set}`` 占位 ⇒ 用参考里对应位置的原值（明文或 ``${VAR}`` 引用文本）还原；
      位置靠"名字 → 占位自带的来源下标"认领（见 ``_align_reference_item``），
      条目改名/增删/换序都不会把 A 提供商的密钥串到 B 上。
    - 字典 ⇒ 逐键递归（payload 里没有的键不参与结果；顶层由 ``_update_toml_doc`` 的合并保住原值，
      表项内由下面的列表分支显式补回）。
    - 列表 ⇒ 逐项对齐后按"参考字段打底 + payload 覆盖"重建——列表整体替换时，
      页面上没展示的字段不会被吃掉。
    - 其他 ⇒ 用 payload（用户显式给的值优先）。

    Args:
        payload: 前端提交的数据（可能含 ``{path, set}`` 占位）。
        reference: 配置文件里的当前数据。

    Returns:
        还原后的数据。还原不出来的占位会**原样留在结果里**，由
        ``find_unresolved_sentinels`` 检出后拒绝落盘。
    """
    if is_redaction_sentinel(payload):
        return reference

    if isinstance(payload, Mapping):
        reference_mapping = reference if isinstance(reference, Mapping) else {}
        merged: dict[str, Any] = {}
        for key, value in payload.items():
            key_text = str(key)
            if key_text in reference_mapping:
                merged[key_text] = merge_payload_with_reference(value, reference_mapping[key_text])
            elif is_redaction_sentinel(value):
                # 参考里压根没有这个密钥叶（本来就没配）⇒ 不落盘占位符
                continue
            else:
                merged[key_text] = value
        return merged

    if isinstance(payload, list):
        reference_list = reference if isinstance(reference, list) else []
        return [_merge_list_item(item, reference_list) for item in payload]

    return payload


def _recorded_list_index(item: Any) -> int | None:
    """从表项里的占位反推它在原列表中的下标（占位路径自带来源）。"""
    for sentinel in _iter_sentinels(item):
        match = re.search(r"\[(\d+)\]", sentinel[SENTINEL_PATH_KEY])
        if match is not None:
            return int(match.group(1))
    return None


def _iter_sentinels(value: Any) -> list[Mapping[str, Any]]:
    """递归收集一个值里出现的全部占位。"""
    if is_redaction_sentinel(value):
        return [value]
    if isinstance(value, Mapping):
        found: list[Mapping[str, Any]] = []
        for item in value.values():
            found.extend(_iter_sentinels(item))
        return found
    if isinstance(value, (list, tuple)):
        found = []
        for item in value:
            found.extend(_iter_sentinels(item))
        return found
    return []


def _align_reference_item(item: Any, reference_list: list[Any]) -> Any:
    """为列表项找参考项——只在**有身份依据**时才认领。

    1. ``name`` 唯一匹配（改名、换序都还认得出自己）；
    2. 表项里的占位自带来源下标（``api_providers[1].api_key`` ⇒ 原来在 1 号位）。

    两条都不成立就**不认领**：宁可让占位还原失败被拒（或让新条目按用户提交的样子落盘），
    也不按"位置看着像"把 A 提供商的密钥认给 B——那会把错误凭据悄悄写进配置。

    ⚠️ 已知局限（phase3 契约"已知局限"条目，交叉证伪实测）：**新建**表项（名字不在参考里）
    带着**别家占位**、且下标有效时会按下标认领 ⇒ 继承该位置的凭据（实测新 provider 拿到
    别家的 key）。改名场景需要这条兜底（否则改名即丢密钥），故保留；要根治得让占位自带来源
    表项名，把"改名"与"新建"区分开。
    """
    item_name = item.get("name") if isinstance(item, Mapping) else None
    if isinstance(item_name, str) and item_name:
        matched = [
            candidate
            for candidate in reference_list
            if isinstance(candidate, Mapping) and candidate.get("name") == item_name
        ]
        if len(matched) == 1:
            return matched[0]

    recorded_index = _recorded_list_index(item)
    if recorded_index is not None and 0 <= recorded_index < len(reference_list):
        return reference_list[recorded_index]

    return None


def _merge_list_item(item: Any, reference_list: list[Any]) -> Any:
    """合并单个列表项：认领到参考项的表项按"参考打底 + payload 覆盖"，否则原样放行。"""
    reference_item = _align_reference_item(item, reference_list)
    if reference_item is None:
        return item

    if not isinstance(item, Mapping) or not isinstance(reference_item, Mapping):
        return merge_payload_with_reference(item, reference_item)

    merged: dict[str, Any] = {str(key): value for key, value in reference_item.items()}
    for key, value in item.items():
        key_text = str(key)
        if key_text in reference_item:
            merged[key_text] = merge_payload_with_reference(value, reference_item[key_text])
        elif is_redaction_sentinel(value):
            continue
        else:
            merged[key_text] = value
    return merged
