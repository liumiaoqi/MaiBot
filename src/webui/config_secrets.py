"""配置面密钥处理（2 段 · 秘密角色）：**schema 声明** + 读路径脱敏 + 写路径认领。

**这一版和上一版的差别（结构性，不是加个开关）**

上一版靠**名字黑名单**猜秘密：精确集（``api_key``/``token``…）+ 后缀补漏（``_token``…）。
黑名单的病是**默认不保密**——本轮就漏了一个 ``maim_message.auth_token``，靠后缀层才补上，
下一个人加 ``credential`` / ``passphrase`` 字段时会再漏一次，而"漏"的表现是**密钥直出浏览器**。

这一版把判定**上移到字段声明处**（F2），两条通道取并集：

1. **派生通道（权威）**：pydantic 字段的 ``Field(json_schema_extra={"x-secret": True})``。
   本仓既有约定就是靠 ``json_schema_extra`` 挂字段元数据（``x-widget``/``x-icon``/三语 label），
   ``config_schema.py`` 已把它原样合并进 schema 输出 ⇒ **零新机制**：加一个字段 = 在定义处多写一行。
2. **声明表（过渡与兜底）**：``SECRET_FIELD_PATHS``。用于派生通道还没标记到的字段
   （例如改 ``src/config/**`` 不在本段写范围内的那些），也是"派生通道没到位时"的显式台账。

外加一条**过渡层**：``is_sensitive_key``（名字后缀）。它**不是判据**，只是为了"新加的密钥字段
在没人声明之前不出站"这唯一目的而保留——所以它必须可度量：``undeclared_transitional_keys``
报出"只有后缀层兜住、声明通道还没覆盖"的键，那就是过渡层可以拆掉的那天。

**三个方向成对出现，缺一个都会出事**

- **读路径**（``redact_config_secrets``）：秘密叶替换为三态标记（F2），真值不出浏览器。
- **写整份**（``merge_payload_with_reference``）：整份 replace 时把占位还原成原值、
  未见字段原样保留——给**遗留**端点用（新的 ``mutate`` 走路径操作，根本不需要这一步）。
- **写认领**（``claim_secret_value``）：路径写回时按 F3 两级规则认领来源值，
  认不到就**拒绝整次写入**，绝不按位置猜。

⚠️ **秘密 ≠ 引用**：``${VAR}`` 引用（F4，3 段的机制）解析出来**仍然是秘密**——引用只是
"值放在哪"，不是"要不要脱敏"。三态里的 ``kind: "reference"`` 就是这个意思。

敏感键口径与 ``src/llm_models/request_snapshot.py::_SENSITIVE_KEYS`` **同源**；
两处一致性由 ``pytests/webui/test_config_secrets.py`` 的防漂移用例守住
（本模块不 import llm_models：配置面读配置不该被模型层的导入链拖进来）。
"""

from typing import Any, Final, Iterable, Iterator, Mapping, Sequence
import re
import types
import typing

from src.webui.config_paths import (
    MISSING,
    PathToken,
    format_path,
    lookup_path,
    parse_path,
    to_declaration_key,
)

# ── 过渡层：名字口径（**不是判据**，见模块 docstring） ──────────────────────

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


def is_sensitive_key(key: Any) -> bool:
    """**过渡层**：按键名猜敏感（大小写不敏感；精确名或敏感后缀）。

    保留它只为"没人声明的密钥字段也别出站"这层兜底；**新代码不要再往这里加名字**——
    加字段的时候在字段声明处写 ``json_schema_extra={"x-secret": True}``，那是判据。
    想知道过渡层还兜着哪些没人声明的键，用 ``undeclared_transitional_keys``。
    """
    if not isinstance(key, str):
        return False
    normalized_key = key.lower()
    return normalized_key in SENSITIVE_KEYS or normalized_key.endswith(SENSITIVE_KEY_SUFFIXES)


# ── 判据通道：schema 声明 ────────────────────────────────────────────────

SECRET_FIELD_PATHS: dict[str, tuple[str, ...]] = {
    # 命名空间 = 配置平面（`bot` = bot_config.toml，`model` = model_config.toml）；
    # section 不是命名空间，它只是路径前缀（F1 实作口径）。
    "bot": (
        "maim_message.auth_token",
        "maim_message.api_server_allowed_api_keys",
    ),
    "model": (
        # `APIProvider.api_key`。派生通道标记落地后这里可以删（并集会自动覆盖），
        # 留着是为了"标记还没落地"的那段时间也有判据。
        "api_providers[].api_key",
    ),
}

SECRET_EXTRA_KEY: Final[str] = "x-secret"
"""字段声明处的秘密标记键：``Field(json_schema_extra={"x-secret": True})``。"""


def declares_secret(field_info: Any) -> bool:
    """字段是否在**声明处**标了 ``x-secret: True``。

    只认 ``True``（不认字符串 ``"true"``）：声明是判据，判据不该有"差不多算真"的写法。
    """
    extra = getattr(field_info, "json_schema_extra", None)
    if not isinstance(extra, Mapping):
        return False
    return extra.get(SECRET_EXTRA_KEY) is True


def derive_secret_field_paths(model_cls: Any, prefix: str = "") -> set[str]:
    """从 pydantic 模型**派生**秘密字段路径（声明表之外的第二条通道，权威）。

    遍历规则与 schema 生成器一致：嵌套模型递归、``list[Model]`` 的元素路径带 ``[]``。
    被声明的字段**不再下钻**——它整块都会被脱敏，子键没有单独表达的机会。

    Args:
        model_cls: pydantic 模型类（duck-type 判 ``model_fields``，不 import 配置层）。
        prefix: 内部递归用的路径前缀。

    Returns:
        声明路径集合，形如 ``{"api_providers[].api_key"}``（不含命名空间前缀）。
    """
    fields = getattr(model_cls, "model_fields", None)
    if not isinstance(fields, Mapping):
        return set()

    found: set[str] = set()
    for field_name, field_info in fields.items():
        path = f"{prefix}{field_name}"
        if declares_secret(field_info):
            found.add(path)
            continue
        annotation = getattr(field_info, "annotation", None)
        element = element_model(annotation)
        if element is None:
            continue
        nested_prefix = f"{path}[]." if sequence_element(annotation) is not None else f"{path}."
        found |= derive_secret_field_paths(element, nested_prefix)
    return found


def collect_secret_field_paths(namespace: str, model_cls: Any = None) -> frozenset[str]:
    """命名空间的秘密路径全集 = **声明表 ∪ 派生通道**（派生优先，取并集）。

    Args:
        namespace: ``bot`` / ``model``。
        model_cls: 该命名空间的根模型类；给了就带上派生通道。

    Returns:
        声明路径的 frozenset（下标写成 ``[]``），可直接喂给
        ``redact_config_secrets`` 与 ``undeclared_transitional_keys``。
    """
    collected = set(SECRET_FIELD_PATHS.get(namespace, ()))
    if model_cls is not None:
        collected |= derive_secret_field_paths(model_cls)
    return frozenset(collected)


def undeclared_transitional_keys(data: Any, secret_paths: Iterable[str]) -> list[str]:
    """报告**只有过渡层兜住**的键（声明通道还没覆盖的那些）。

    这不是错误，是台账：过渡层何时能拆，取决于这张表什么时候空。空的含义是
    "配置里所有看起来像密钥的键，都已有正式声明"。
    """
    declared = set(secret_paths)
    collected: list[str] = []
    for tokens, key in _iter_mapping_keys(data):
        if to_declaration_key(tokens) in declared:
            continue
        if is_sensitive_key(key):
            collected.append(to_declaration_key(tokens))
    return sorted(set(collected))


def _iter_mapping_keys(data: Any, prefix: Sequence[PathToken] = ()) -> Iterator[tuple[tuple[PathToken, ...], str]]:
    """递归产出 ``(tokens, key)``——只用于覆盖率台账，不参与读写。"""
    if isinstance(data, Mapping):
        for key, value in data.items():
            key_text = str(key)
            child = (*prefix, key_text)
            yield child, key_text
            yield from _iter_mapping_keys(value, child)
        return
    if isinstance(data, (list, tuple)) and not isinstance(data, (str, bytes)):
        for index, item in enumerate(data):
            yield from _iter_mapping_keys(item, (*prefix, index))


# ── 三态标记（F2）──────────────────────────────────────────────────────

SENTINEL_PATH_KEY: Final[str] = "path"
SENTINEL_SET_KEY: Final[str] = "set"
SENTINEL_MARKER_KEY: Final[str] = "$secret"
SENTINEL_KIND_KEY: Final[str] = "kind"
SENTINEL_ORIGIN_NAME_KEY: Final[str] = "origin_name"

KIND_LITERAL: Final[str] = "literal"
KIND_REFERENCE: Final[str] = "reference"

# 与 F4（3 段 ``resolve_env_references``）同语法：整串就是一个 ${VAR} 才算"纯引用"。
# 漂移由 pytests/webui/test_config_seam.py 的对拍用例守住（拿她的公开函数当判据，
# 不去 import 她的私有正则——那个名字她有权改）。
ENV_REFERENCE_PATTERN: Final[re.Pattern[str]] = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def is_env_reference_text(value: Any) -> bool:
    """整串是否恰好是一个 ``${VAR}`` 引用（``"prefix-${VAR}"`` **不算**纯引用）。"""
    return isinstance(value, str) and ENV_REFERENCE_PATTERN.fullmatch(value) is not None


def is_configured(value: Any) -> bool:
    """判断密钥叶是否"已配置"：空串 / None / 空容器都算没配。"""
    if value is None or value is MISSING:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (Mapping, list, tuple, set)):
        return len(value) > 0
    return True


def secret_kind(value: Any) -> str | None:
    """秘密值的形态：``reference``（整串/整表都是 ``${VAR}``）或 ``literal``；未配置返回 ``None``。

    列表型秘密（``auth_token: list[str]``）要求**每一项都是纯引用**才算 ``reference``——
    混着写（一项明文一项引用）时归 ``literal``，因为此时"值里确实躺着一份明文"，
    对客户端来说它就不该被当成"只是个引用"。这条口径写在这里，别在调用方各猜一遍。
    """
    if not is_configured(value):
        return None

    texts: list[str] = []
    if isinstance(value, str):
        if value.strip():
            texts.append(value.strip())
    elif isinstance(value, (list, tuple)):
        texts = [item.strip() for item in value if isinstance(item, str) and item.strip()]

    if texts and all(is_env_reference_text(text) for text in texts):
        return KIND_REFERENCE
    return KIND_LITERAL


def build_redaction_sentinel(
    path: str,
    configured: bool,
    *,
    kind: str | None = None,
    origin_name: str | None = None,
) -> dict[str, Any]:
    """构造秘密占位。

    形状 = F2 冻结三键（``$secret`` / ``set`` / ``kind``）**加** ``path``：
    加 ``path`` 是 F3 的要求——"占位自带来源路径"是写回时认领原值的依据，
    没有它，客户端把整份读回来的东西写回去就会变成"没配密钥"。

    Args:
        path: 该秘密**在配置里的来源路径**（不是提交位置）。
        configured: 是否已配置（F2 三态的中间态靠它区分）。
        kind: ``literal`` / ``reference``；``configured=False`` 时留 ``None`` 且不输出该键。
        origin_name: 所属表项的 ``name``（F3 规则①"按名认领"的依据），没有就不输出。

    Returns:
        可直接进 JSON 响应的标记字典。
    """
    sentinel: dict[str, Any] = {
        SENTINEL_PATH_KEY: path,
        SENTINEL_MARKER_KEY: True,
        SENTINEL_SET_KEY: bool(configured),
    }
    if configured:
        sentinel[SENTINEL_KIND_KEY] = kind if kind is not None else KIND_LITERAL
    if origin_name:
        sentinel[SENTINEL_ORIGIN_NAME_KEY] = origin_name
    return sentinel


def is_redaction_sentinel(value: Any) -> bool:
    """判断一个值是不是秘密占位。

    认两种形状：本版 ``{$secret, path, set}`` 与上一版遗留的 ``{path, set}``
    （遗留形状仍要能还原——老客户端手里的占位不该因为服务端升级就变成废纸）。
    允许多余键（前端可以附加展示信息）。
    """
    if not isinstance(value, Mapping):
        return False
    if SENTINEL_PATH_KEY not in value or SENTINEL_SET_KEY not in value:
        return False
    return isinstance(value[SENTINEL_PATH_KEY], str) and isinstance(value[SENTINEL_SET_KEY], bool)


def is_secret_claim(value: Any, declared: Iterable[str] | None = None) -> bool:
    """判断一个值是不是**可认领**的秘密占位：形状对 **且** 来源确实落在秘密字段里。

    为什么必须比 ``is_redaction_sentinel`` 更严（对抗审查 F6，已复现）：
    占位形状是 ``{path: str, set: bool}``，而**普通数据表可能恰好长这样**——
    ``ModelInfo.extra_params: dict[str, Any]`` 就可达。只比形状的后果：

    - 新写接缝：用户提交的合法表被当成占位去认领 ⇒ **400**（明明数据没问题）；
    - 遗留整份写：``merge_payload_with_reference`` 直接把它换成参考值 ⇒ **静默吃掉用户的数据**；
    - ``find_unresolved_sentinels`` 也会把它报成"未还原的占位" ⇒ 再补一刀 400。

    这三条都不是"漏真值"，但都是真的会咬人。判据换成"形状对 + 来源是秘密"之后，
    普通表走普通数据路径，占位走占位路径，两边不再互相冒充。

    Args:
        value: 待判断的值。
        declared: 秘密声明路径集合；``None`` 时退化成**纯形状**判断（兼容不掌握声明的旧调用方）。

    Returns:
        是否应当按"认领秘密占位"处理。
    """
    if not is_redaction_sentinel(value):
        return False
    if declared is None:
        return True

    recorded_path = str(value.get(SENTINEL_PATH_KEY, "")).strip()
    if not recorded_path:
        return False
    try:
        source_tokens = parse_path(recorded_path)
    except ValueError:
        return False
    return find_secret_root(source_tokens, declared) is not None


# ── 读路径 ─────────────────────────────────────────────────────────────


def redact_config_secrets(
    data: Any,
    *,
    secret_paths: Iterable[str] | None = None,
    namespace: str = "",
    model_cls: Any = None,
) -> Any:
    """读路径脱敏：把秘密叶整块替换成三态标记，真值不出浏览器。

    - 秘密判定 = 声明通道（``secret_paths``，或由 ``namespace`` + ``model_cls`` 现算）∪ 过渡层。
    - 秘密键的**值本身是容器**时整块替换、不再下钻——避免容器里的密钥从子键漏出去。
    - 非秘密叶原样返回（防过度脱敏：``max_tokens`` 必须还是数字）。
    - ``origin_name``：秘密叶若在某个带 ``name`` 的表项里，把表项名一并写进占位（F3 规则①）。

    Args:
        data: 待脱敏的配置数据（tomlkit 文档 / 纯 dict / list 都行）。
        secret_paths: 秘密声明路径集合；``None`` 且未给 namespace 时**只有过渡层生效**。
        namespace: 命名空间（``bot``/``model``），用于现算声明集合。
        model_cls: 命名空间根模型类（配合 namespace 现算声明集合）。

    Returns:
        脱敏后的纯 Python 结构（dict/list），可直接进 JSON 响应。
    """
    declared = resolve_declared_paths(secret_paths, namespace=namespace, model_cls=model_cls)
    return _redact(data, (), declared, None)


def resolve_declared_paths(
    secret_paths: Iterable[str] | None = None,
    *,
    namespace: str = "",
    model_cls: Any = None,
) -> frozenset[str]:
    """把"要按哪些声明路径判秘密"解析成一个集合（三选一，优先级从高到低）。"""
    if secret_paths is not None:
        return frozenset(secret_paths)
    if namespace:
        return collect_secret_field_paths(namespace, model_cls)
    return frozenset()


def _redact(data: Any, tokens: tuple[PathToken, ...], declared: frozenset[str], origin_name: str | None) -> Any:
    """递归脱敏；``tokens`` 跟住当前位置（声明路径匹配靠它，不靠字符串前缀）。"""
    if isinstance(data, Mapping):
        current_origin = _origin_name_of(data, origin_name)
        redacted: dict[str, Any] = {}
        for key, value in data.items():
            key_text = str(key)
            child_tokens = (*tokens, key_text)
            child_path = format_path(child_tokens)
            if _is_secret_path(child_tokens, key_text, declared):
                redacted[key_text] = build_redaction_sentinel(
                    child_path,
                    is_configured(value),
                    kind=secret_kind(value),
                    origin_name=current_origin,
                )
                continue
            redacted[key_text] = _redact(value, child_tokens, declared, current_origin)
        return redacted

    if isinstance(data, (list, tuple)) and not isinstance(data, (str, bytes)):
        redacted_items: list[Any] = []
        for index, item in enumerate(data):
            child_tokens = (*tokens, index)
            if is_secret_path(child_tokens, declared):
                # 声明以 `[]` 结尾 = "这个数组的**每个元素**都是秘密" ⇒ 元素整块换标记。
                # 判据挂在**元素**路径上（`a[]`），与 `find_secret_root` 同口径——
                # 挂在容器路径（`a`）上是不行的：`to_declaration_key(("a",))` 给的是 `a`，
                # 永远匹配不到声明 `a[]`（第一版就是这么写错的，用例当场抓住）。
                # 少了这一段，list 分支会逐元素原样返回 = 声明被**静默忽略**（对抗审查 F5）。
                # ⚠️ 今天不触发（派生通道的子路径前缀永远带一个点、末段一定是字段名 ⇒
                # 永远不产出尾部 `[]`）；只有**手写**声明表条目才可能引入这种形态。
                redacted_items.append(
                    build_redaction_sentinel(
                        format_path(child_tokens),
                        is_configured(item),
                        kind=secret_kind(item),
                    )
                )
                continue
            redacted_items.append(_redact(item, child_tokens, declared, origin_name))
        return redacted_items

    return data


def describe_secret_value(stored_root: Any, tokens: Sequence[PathToken]) -> dict[str, Any]:
    """给单个路径现算三态标记（``get(paths)`` 用）。

    与 ``_redact`` 走同一个 ``build_redaction_sentinel``——一处形状，两个调用方，
    免得"整份读"和"按路径读"发出的标记长得不一样。
    """
    value = lookup_path(stored_root, tokens)
    configured = is_configured(value)
    origin_name = _origin_name_at(stored_root, tokens)
    return build_redaction_sentinel(
        format_path(tokens),
        configured,
        kind=secret_kind(value) if configured else None,
        origin_name=origin_name,
    )


def is_secret_path(tokens: Sequence[PathToken], declared: Iterable[str]) -> bool:
    """**单条**路径算不算秘密：声明通道优先，没被声明的才轮到过渡名字层兜底。

    这是全模块**唯一的**秘密判据入口——``_redact`` 与 ``find_secret_root`` 都调它，
    否则"整份读"和"按路径读"会各自有一套口径（那正是 F4 那个洞的形态）。

    ⚠️ 根是下标时（有人把**数组本身**当根丢进来，例如 ``redact_config_secrets([...])``）
    只走名字层：声明路径一定以键名开头（``config_paths.to_declaration_key`` 也明确拒绝
    以下标开头的路径），拿它去比对只会抛异常。
    """
    if not tokens:
        return False
    if isinstance(tokens[0], int):
        return is_sensitive_key(tokens[-1])
    declared_set = declared if isinstance(declared, frozenset) else frozenset(declared)
    if to_declaration_key(tokens) in declared_set:
        return True
    return is_sensitive_key(tokens[-1])


def find_secret_root(
    tokens: Sequence[PathToken],
    declared: Iterable[str],
) -> tuple[PathToken, ...] | None:
    """返回**包含这条路径的最短秘密路径**——秘密判定必须**双向**做。

    ⚠️ **双向语义（2026-10-16 对抗审查 F1 的教训，别只做一半）**：

    - **方向甲 · "路径在秘密里"**：请求 ``maim_message.auth_token[0]``——秘密字段是**它的祖先**
      （``auth_token`` 是数组，"列叶"会把数组摊成 ``[0]``/``[1]``）。只比对整条路径会得到
      "这不是秘密"，然后**把令牌明文发出去**。
    - **方向乙 · "秘密在路径里"**：请求 ``maim_message`` / ``api_providers`` / ``api_providers[0]``
      ——秘密字段是**它的后代**。这条曾经完全没做：非秘密路径一律原样返回，
      于是**请求一个祖先容器就把整棵子树连密钥一起交出去**。更糟的是脱敏标记自己公布了
      秘密路径（``"path": "maim_message.auth_token"``）⇒ 客户端不用猜就知道该请求哪个祖先。

    方向甲由本函数（沿**前缀链**找根）解决；方向乙由 ``redact_subtree`` 解决（把子树按同一
    判据走一遍）。**只做甲不做乙 = 秘密照样出站**——这就是上一轮四条判据门全绿却漏掉的洞。

    防复发的闸不靠"想到哪些形状"，而是机械穷举：
    ``pytests/webui/test_config_seam.py::TestExhaustivePrefixLeakGate`` 会遍历两个平面
    **每一条路径前缀**（含中间层、含数组项本身）逐个请求并断言零泄漏。改这里的逻辑前先看那道闸。
    """
    for length in range(1, len(tokens) + 1):
        prefix = tuple(tokens[:length])
        if is_secret_path(prefix, declared):
            return prefix
    return None


def redact_subtree(stored_root: Any, tokens: Sequence[PathToken], declared: Iterable[str]) -> Any:
    """取某个子树，并把它**内部**的秘密整块换成标记后再返回（方向乙，见 ``find_secret_root``）。

    调用前提：``tokens`` 这条路径**自己不是秘密**（否则应该直接出标记，不必取子树）。
    内部走的是 ``_redact``——与整份读同一套判据（``is_secret_path``：声明 ∪ 名字层），
    所以"整份读"与"按路径读"不可能给出不同的保密性。

    Args:
        stored_root: 已存储的配置（解析基准）。
        tokens: 要取的子树位置。
        declared: 秘密声明路径集合。

    Returns:
        子树（秘密已换成标记）；路径不存在时返回 ``MISSING``。
    """
    position = tuple(tokens)
    value = lookup_path(stored_root, position)
    if value is MISSING:
        return MISSING
    # origin_name 取该位置的所属表项名，让子树里的秘密占位仍然带得上 F3 认领要用的来源名
    return _redact(value, position, frozenset(declared), _origin_name_at(stored_root, position))


def _is_secret_path(tokens: Sequence[PathToken], key: str, declared: frozenset[str]) -> bool:
    """``_redact`` 内部用的适配器——判定统一走 ``is_secret_path``（单一口径）。"""
    del key  # 键名不再单独使用：``is_secret_path`` 自己会看末段
    return is_secret_path(tokens, declared)


def _origin_name_of(data: Mapping[Any, Any], inherited: str | None) -> str | None:
    """表项自身的 ``name``（非空字符串才算）——它是 F3"按名认领"的依据。"""
    name = data.get("name")
    if isinstance(name, str) and name.strip():
        return name.strip()
    return inherited


def _origin_name_at(stored_root: Any, tokens: Sequence[PathToken]) -> str | None:
    """从数据里现查某个路径所属表项的 ``name``（沿路径逐层看，取最近的一层）。"""
    current = stored_root
    origin: str | None = None
    for token in tokens:
        if isinstance(current, Mapping):
            name = current.get("name")
            if isinstance(name, str) and name.strip():
                origin = name.strip()
        if isinstance(token, int):
            if isinstance(current, (str, bytes)) or not isinstance(current, list) or token >= len(current):
                return origin
            current = current[token]
            continue
        if not isinstance(current, Mapping) or token not in current:
            return origin
        current = current[token]
    return origin


# ── 服务端自身的配置错误（不是客户端的错）────────────────────────────


class SecretDeclarationError(ValueError):
    """**服务端**的秘密声明表里有一条非法路径（F12）。

    为什么要单独一个类型，而不是复用 ``ConfigPathError``：``SECRET_FIELD_PATHS`` 是
    **服务端自己的数据**，它写错了是**我们的** bug；而 ``ConfigPathError`` 的语义是
    "客户端给的路径不合法"。两者混用会把服务端故障报成 400（客户端参数错），
    排障的人于是去查请求，而问题在代码/声明表里——这正是 F12。

    Attributes:
        declared_path: 出错的那条声明（报错要指名道姓，否则没法改）。
        cause: 原始解析异常。
    """

    def __init__(self, declared_path: str, cause: Exception) -> None:
        self.declared_path = declared_path
        self.cause = cause
        super().__init__(f"服务端秘密声明表里有非法路径 {declared_path!r}：{cause}")


# ── 写路径（认领规则 · F3）────────────────────────────────────────────


class SecretClaimError(ValueError):
    """秘密占位认不到来源（F3 规则③：拒绝整次写入，绝不按位置猜）。

    Attributes:
        location: 占位被提交到哪个路径（报错要指明位置）。
        recorded_path: 占位自称的来源路径（便于人判断是"改名"还是"乱构造"）。
    """

    def __init__(self, message: str, *, location: str, recorded_path: str = "") -> None:
        self.location = location
        self.recorded_path = recorded_path
        super().__init__(message)


def claim_secret_value(
    sentinel: Mapping[str, Any],
    stored_root: Any,
    *,
    target_path: str,
    declared: Iterable[str],
) -> Any:
    """按 F3 的两级规则认领占位所指的原值——**来源与靶子都必须是同一个秘密字段**。

    0. **靶子约束**（2026-10-16 对抗审查 F3 补上）：占位只能写回**它来源的那个秘密字段**
       （``to_declaration_key(来源根) == to_declaration_key(靶子根)``，下标可不同）。
       没有这条约束时，占位是一个**任意读**原语：把它 ``set`` 到任意可读的普通字段，
       原值就落盘了，再读那个字段就拿到明文——写一次、读一次，F2 的保密承诺整条作废。
    1. **名字唯一匹配**：占位带 ``origin_name``，且在**来源路径所在的数组**里恰好只有一个
       表项叫这个名字 ⇒ 认领该表项的对应字段（改名 + 换序都还认得出自己）。
    2. **占位自带来源路径**：按 ``path`` 直接取原值（含下标，所以换序也能认对）。
    3. 以上任一不成立 ⇒ 抛 ``SecretClaimError``，由调用方转成 400 并**拒绝整次写入**。

    ⚠️ **``set: false`` 的占位要拒绝**（F3 子观察，2026-10-16 定）：以前这个标志**从没被读过**
    ⇒ 一个"服务端说这里没值"的占位照样能认领。判别它的是**来源**（而不是标志本身）：

    - 来源**真的有值** ⇒ 这是"客户端拿着'没值'的标记去覆盖一个**有值**的位置"⇒ 写下去
      等于**删掉那份凭据**（占位不是值，落盘的就是"没有值"）。⇒ 拒绝并点名。危险形态在于
      来源路径不随元素移动而变化（改过的表单、换过序的表单都会碰到），静默接受 = 丢密钥。
    - 来源**本来就没值/不存在** ⇒ 照常认领（认领的结果就是"没值"），
      这正是"读一份没配密钥的配置、填了别的字段、再整体写回"的合法路径。**不能**一并拒掉。

    为什么不做"标记成了 set:false 就把这一项从结果里删掉"这种"更聪明"的处理：那会让
    ``set`` 标志对**落盘内容**产生副作用（同一份表单，改一个无关字段就可能删掉一个表项），
    比拒绝更难排障。**判据是：说清楚、不猜。**

    ⚠️ **已知局限（保留、不修 —— F3 明文要求）**：新建表项带着"别家"的占位、且其来源下标
    仍然有效时，会按规则②继承该位置的凭据。保留是因为改名/换序场景需要这条兜底
    （否则改名即丢密钥）；根治方向是占位强制带来源名。**不得对外表述成"增删换序都不会串"。**
    （靶子约束不影响这条：新建表项的靶子仍是同一个秘密字段，只是下标不同。）

    Args:
        sentinel: 客户端回发的秘密占位。
        stored_root: **已存储的那份**配置（解析基准，不是调用者上次读到的那份）。
        target_path: 占位被提交到的路径。
        declared: 该命名空间的秘密声明路径集合（来源/靶子都用它判身份）。

    Returns:
        认领到的原值（明文或 ``${VAR}`` 引用文本都原样返回——引用解析是 F4 的事）。
    """
    recorded_path = str(sentinel.get(SENTINEL_PATH_KEY, "")).strip()
    if not recorded_path:
        raise SecretClaimError(
            "秘密占位没有来源路径，无法认领（拒绝按位置猜）",
            location=target_path,
        )

    try:
        source_tokens = parse_path(recorded_path)
    except ValueError as error:
        raise SecretClaimError(
            f"秘密占位的来源路径 '{recorded_path}' 不合法：{error}",
            location=target_path,
            recorded_path=recorded_path,
        ) from error

    source_root = find_secret_root(source_tokens, declared)
    if source_root is None:
        raise SecretClaimError(
            f"秘密占位的来源 '{recorded_path}' 不是秘密字段，拒绝认领",
            location=target_path,
            recorded_path=recorded_path,
        )

    try:
        target_tokens = parse_path(target_path)
    except ValueError as error:  # pragma: no cover — 调用方已解析过一次，这里是兜底
        raise SecretClaimError(
            f"秘密占位的写入位置 '{target_path}' 不合法：{error}",
            location=target_path,
            recorded_path=recorded_path,
        ) from error

    target_root = find_secret_root(target_tokens, declared)
    if target_root is None or to_declaration_key(target_root) != to_declaration_key(source_root):
        raise SecretClaimError(
            f"秘密占位只能写回它来源的秘密字段（'{recorded_path}' ⇒ '{target_path}' 不是同一个字段）；"
            "把秘密搬到别的字段会绕过脱敏，已拒绝",
            location=target_path,
            recorded_path=recorded_path,
        )

    # 规则①：按名认领（名字在**来源数组**里唯一）
    origin_name = sentinel.get(SENTINEL_ORIGIN_NAME_KEY)
    if isinstance(origin_name, str) and origin_name.strip():
        claimed = _claim_by_origin_name(stored_root, source_tokens, origin_name.strip())
        if claimed is not MISSING:
            _refuse_claim_if_placeholder_says_unset(sentinel, claimed, target_path=target_path)
            return claimed

    # 规则②：按来源路径/下标认领
    claimed = lookup_path(stored_root, source_tokens)
    if claimed is not MISSING:
        _refuse_claim_if_placeholder_says_unset(sentinel, claimed, target_path=target_path)
        return claimed

    raise SecretClaimError(
        f"秘密占位认不到来源：来源路径 '{recorded_path}' 在已存储的配置里不存在",
        location=target_path,
        recorded_path=recorded_path,
    )


def _refuse_claim_if_placeholder_says_unset(
    sentinel: Mapping[str, Any],
    claimed_value: Any,
    *,
    target_path: str,
) -> None:
    """``set: false`` 的占位**不许**认领一个真值（F3 子观察的判据落点）。

    调用条件：来源与靶子都校验过、且**确实认到了值**。此时若占位自称"没值"（``set: false``）
    而来源里真有值，说明这份占位不是这个位置的（改过的表单 / 换过序 / 客户端自己构造的）。
    认领下去 = 把一份**存在的凭据换成"没有值"**——静默丢密钥，正是 F2 要防的事。

    ⚠️ 只在"**来源确实有值**"时拒绝：来源本来就没值（`set: false` 的合法来源）时不该拦，
    否则"读一份没配密钥的配置 → 填别的字段 → 整体写回"这条正常路径会被误伤。
    """
    if sentinel.get(SENTINEL_SET_KEY, True) is not False:
        return
    if not is_configured(claimed_value):
        return
    raise SecretClaimError(
        "秘密占位自称未配置（set=false），但它指向的来源位置上有值："
        "照写会把那份凭据换成'没有值'。请重新读取配置后再提交（占位可能来自改过/换序的表单）",
        location=target_path,
        recorded_path=str(sentinel.get(SENTINEL_PATH_KEY, "")),
    )


def _claim_by_origin_name(stored_root: Any, source_tokens: Sequence[PathToken], origin_name: str) -> Any:
    """规则①：在来源路径的**父数组**里找唯一同名表项，取它的对应字段。"""
    if len(source_tokens) < 2:
        return MISSING
    parent_tokens = source_tokens[:-1]
    field_token = source_tokens[-1]
    if isinstance(field_token, int):
        return MISSING

    container = lookup_path(stored_root, parent_tokens)
    if isinstance(container, (str, bytes)) or not isinstance(container, list):
        return MISSING

    matched = [
        item
        for item in container
        if isinstance(item, Mapping) and isinstance(item.get("name"), str) and item.get("name").strip() == origin_name
    ]
    if len(matched) != 1:
        # 0 个 → 没得认；多个 → 名字不唯一，"按名认领"失去依据 ⇒ 退回规则②
        return MISSING

    value = matched[0].get(field_token, MISSING)
    return value


def find_unresolved_sentinels(data: Any, *, path: str = "", declared: Iterable[str] | None = None) -> list[str]:
    """列出仍然残留的**秘密占位**路径（写路径还原失败的证据）。

    判断从严：宁可拒绝一次落盘，也不把占位写进配置文件。
    ``declared`` 给了就只认"来源确实是秘密"的占位（见 ``is_secret_claim``）——
    否则一张恰好长成 ``{path, set}`` 的**普通数据表**会被误报、连带整次保存被拒（F6）。
    报告位置优先用占位自带的来源路径（它说明密钥**本来在哪**），再附上提交位置。
    """
    if is_secret_claim(data, declared):
        recorded_path = str(data.get(SENTINEL_PATH_KEY, "")).strip()
        if recorded_path and path and recorded_path != path:
            return [f"{recorded_path}（提交于 {path}）"]
        return [recorded_path or path or "未知位置"]

    if isinstance(data, Mapping):
        unresolved: list[str] = []
        for key, value in data.items():
            key_text = str(key)
            child_path = f"{path}.{key_text}" if path else key_text
            unresolved.extend(find_unresolved_sentinels(value, path=child_path, declared=declared))
        return unresolved

    if isinstance(data, (list, tuple)):
        unresolved = []
        for index, item in enumerate(data):
            unresolved.extend(find_unresolved_sentinels(item, path=f"{path}[{index}]", declared=declared))
        return unresolved

    return []


def merge_payload_with_reference(payload: Any, reference: Any, *, declared: Iterable[str] | None = None) -> Any:
    """写路径保真：占位还原 + 未见字段保留（**遗留整份/整节端点在用**）。

    新的 ``mutate`` 走路径操作，不需要这一步（没被点名的路径根本不进写路径）；
    本函数保留是为了旧端点继续可用，直到 5 段把旧读路径拆掉。

    对齐规则：

    - ``{path, set}`` 占位 ⇒ 用参考里对应位置的原值（明文或 ``${VAR}`` 引用文本）还原；
      位置靠"名字 → 占位自带的来源下标"认领（见 ``_align_reference_item``），
      条目改名/增删/换序都不会把 A 提供商的密钥串到 B 上。
      ⚠️ 只认"来源确实是秘密"的占位（``is_secret_claim``）：传了 ``declared`` 之后，
      一张恰好长成 ``{path, set}`` 的**普通数据表**不会被当成占位吃掉（F6）。
    - 字典 ⇒ 逐键递归（payload 里没有的键不参与结果；顶层由 ``_update_toml_doc`` 的合并保住原值，
      表项内由下面的列表分支显式补回）。
    - 列表 ⇒ 逐项对齐后按"参考字段打底 + payload 覆盖"重建——列表整体替换时，
      页面上没展示的字段不会被吃掉。
    - 其他 ⇒ 用 payload（用户显式给的值优先）。

    Args:
        payload: 前端提交的数据（可能含 ``{path, set}`` 占位）。
        reference: 配置文件里的当前数据。
        declared: 秘密声明路径集合；``None`` 时退化成纯形状判断（旧调用方兼容）。

    Returns:
        还原后的数据。还原不出来的占位会**原样留在结果里**，由
        ``find_unresolved_sentinels`` 检出后拒绝落盘。
    """
    if is_secret_claim(payload, declared):
        return reference

    if isinstance(payload, Mapping):
        reference_mapping = reference if isinstance(reference, Mapping) else {}
        merged: dict[str, Any] = {}
        for key, value in payload.items():
            key_text = str(key)
            if key_text in reference_mapping:
                merged[key_text] = merge_payload_with_reference(
                    value, reference_mapping[key_text], declared=declared
                )
            elif is_secret_claim(value, declared):
                # 参考里压根没有这个密钥叶（本来就没配）⇒ 不落盘占位符
                continue
            else:
                merged[key_text] = value
        return merged

    if isinstance(payload, list):
        reference_list = reference if isinstance(reference, list) else []
        return [_merge_list_item(item, reference_list, declared) for item in payload]

    return payload


def _recorded_list_index(item: Any) -> int | None:
    """从表项里的占位反推它在原列表中的下标（占位路径自带来源）。"""
    for sentinel in _iter_sentinels(item):
        match = re.search(r"\[(\d+)\]", sentinel[SENTINEL_PATH_KEY])
        if match is not None:
            return int(match.group(1))
    return None


def _iter_sentinels(value: Any) -> list[Mapping[str, Any]]:
    """递归收集一个值里出现的全部占位。

    这里**保持纯形状判断**：它只用来"从表项里反推来源下标"，属于启发式，
    判断错了只是认领不到（会被拒），不会把普通数据当占位吃掉。
    """
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

    ⚠️ 已知局限（F3"已知局限"条目，交叉证伪实测）：**新建**表项（名字不在参考里）
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


def _merge_list_item(item: Any, reference_list: list[Any], declared: Iterable[str] | None = None) -> Any:
    """合并单个列表项：认领到参考项的表项按"参考打底 + payload 覆盖"，否则原样放行。"""
    reference_item = _align_reference_item(item, reference_list)
    if reference_item is None:
        return item

    if not isinstance(item, Mapping) or not isinstance(reference_item, Mapping):
        return merge_payload_with_reference(item, reference_item, declared=declared)

    merged: dict[str, Any] = {str(key): value for key, value in reference_item.items()}
    for key, value in item.items():
        key_text = str(key)
        if key_text in reference_item:
            merged[key_text] = merge_payload_with_reference(
                value, reference_item[key_text], declared=declared
            )
        elif is_secret_claim(value, declared):
            continue
        else:
            merged[key_text] = value
    return merged


# ── 派生通道的模型侧小工具（config_store 也用它做 schema 默认值解析） ─────


def element_model(annotation: Any) -> Any | None:
    """取出注解里的"配置模型类"：``T`` / ``Optional[T]`` / ``list[T]`` 都认，其余给 ``None``。"""
    if annotation is None:
        return None
    unwrapped = unwrap_optional(annotation)
    target = unwrapped[0] if unwrapped else annotation
    inner = sequence_element(target)
    if inner is not None:
        target = inner
    if isinstance(target, type) and isinstance(getattr(target, "model_fields", None), Mapping):
        return target
    return None


def unwrap_optional(annotation: Any) -> list[Any]:
    """展开 ``Optional[T]``（本仓配置类禁止其它 Union，所以最多两元）。"""
    origin = typing.get_origin(annotation)
    if origin not in {typing.Union, types.UnionType}:
        return []
    return [arg for arg in typing.get_args(annotation) if arg is not type(None)]


def sequence_element(annotation: Any) -> Any | None:
    """若注解是 ``list[T]`` / ``set[T]`` / ``tuple[T]``，返回 ``T``。"""
    if typing.get_origin(annotation) not in {list, set, tuple, typing.List, typing.Set, typing.Tuple}:
        return None
    args = typing.get_args(annotation)
    return args[0] if args else None
