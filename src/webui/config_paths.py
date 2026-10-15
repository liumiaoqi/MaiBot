"""配置路径操作（2 段接缝的解析基座）。

**为什么需要它**：本轮把配置读/写接缝从"整份文件进出"改成"路径操作"——
`get(paths)` 按路径读、`mutate(ns, ops)` 按路径写。整份进出有两个结构性问题：

① 没读到的字段也会参与写（表项整段 replace 会把页面上没展示的字段吃掉）；
② 没有"这个字段动没动过"的概念（`inherited` 无从表达）。

路径操作把这两个问题一起解掉：**没被点名的路径根本不进写路径**。

**路径语法**（本模块是唯一解析入口）：``a.b[0].c``

- 键用 ``.`` 分隔，下标用 ``[n]``（非负整数）；根必须是键（配置文件根是表，不是数组）。
- 声明表里的 ``[]``（"任意下标"，见 ``config_secrets.SECRET_FIELD_PATHS``）是**声明语法**，
  ``parse_path`` 不接受它——运行时路径的石下标必须具体。

**边界**：本模块只做路径代数（解析 / 查 / 改 / 删 / 列叶），**不碰文件、不认 schema**。
"缺省值是多少""这是不是秘密字段"属于 ``config_store`` / ``config_secrets`` 的职责。

与 tomlkit 的关系：本模块只依赖"像 dict / 像 list"这一层公共协议
（``tomlkit.items.Table`` / ``AoT`` / ``Array`` 都满足）——所以同一套代码既能作用在
``tomlkit`` 文档上（保注释、保格式、能真删键），也能作用在纯 Python 结构上（测试对账）。
"""

from typing import Any, Iterator, Mapping, Sequence
import re

from src.common.logger import get_logger

logger = get_logger("webui")


__all__ = [
    "ConfigPathError",
    "MISSING",
    "WILDCARD",
    "PathToken",
    "assign_path",
    "expand_declaration",
    "format_path",
    "iter_leaf_paths",
    "lookup_path",
    "lookup_parent",
    "parse_declaration",
    "parse_path",
    "remove_index",
    "remove_path",
    "to_declaration_key",
    "to_plain",
]


class ConfigPathError(ValueError):
    """路径语法错误，或路径在数据上走不通（越界 / 类型不符）。

    Attributes:
        path: 出错的原始路径文本（便于 400 响应直接引用）。
    """

    def __init__(self, message: str, *, path: str = "") -> None:
        self.path = path
        super().__init__(f"{message}（路径：{path}）" if path else message)


class _MissingType:
    """"路径不存在"的单例哨兵。

    不用 ``None``：``None`` 是 TOML 里合法的空值语义，两者混起来会让
    "没配" 与 "显式配成空" 无法区分——而 ``inherited`` 恰恰要区分这两件事。
    """

    _instance: "_MissingType | None" = None

    def __new__(cls) -> "_MissingType":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __bool__(self) -> bool:
        return False

    def __repr__(self) -> str:
        return "MISSING"


MISSING = _MissingType()
"""路径不存在的哨兵；``lookup_path`` 查不到时返回它。"""


class _WildcardType:
    """声明路径里的 ``[]``（"任意下标"）的单例标记。

    只出现在**声明**里（``SECRET_FIELD_PATHS`` 这种"所有 api_providers 的 api_key
    都是秘密"的写法）；运行时路径的石下标必须具体，两套语法刻意分开。
    """

    _instance: "_WildcardType | None" = None

    def __new__(cls) -> "_WildcardType":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "WILDCARD"


WILDCARD = _WildcardType()
"""声明路径里表示"任意下标"的标记。"""

PathToken = str | int

# 键名字符集：``\w`` 含下划线与 Unicode 字母（配置键实际是 ASCII snake_case，
# 这里放宽不至于误判成下标即可）；``-`` 单独列出因为 ``\w`` 不含它。
_KEY_PATTERN = re.compile(r"[\w\-]+")


def parse_path(path: str) -> tuple[PathToken, ...]:
    """把路径文本解析成 token 元组：``"api_providers[1].api_key"`` ⇒ ``("api_providers", 1, "api_key")``。

    Args:
        path: 路径文本。

    Returns:
        token 元组（``str`` 为键、``int`` 为下标）。

    Raises:
        ConfigPathError: 语法不合法（空 / 缺 ``]`` / 下标非数字 / 多余分隔符 / 以 ``[`` 开头等）。
    """
    tokens = _scan_path(path, allow_wildcard=False)
    if isinstance(tokens[0], int):
        raise ConfigPathError("路径的根必须是键名（配置文件根是表，不是数组）", path=path)
    return tokens


def parse_declaration(path: str) -> tuple[PathToken | _WildcardType, ...]:
    """解析**声明**路径：与 ``parse_path`` 同语法，但允许 ``[]`` 表示"任意下标"。

    例：``"api_providers[].api_key"`` ⇒ ``("api_providers", WILDCARD, "api_key")``。
    """
    tokens = _scan_path(path, allow_wildcard=True)
    if isinstance(tokens[0], int):
        raise ConfigPathError("声明路径的根必须是键名", path=path)
    return tokens


def to_declaration_key(tokens: Sequence[PathToken]) -> str:
    """把**具体**路径归一成**声明**键文本：下标一律写成 ``[]``。

    ``("api_providers", 3, "api_key")`` ⇒ ``"api_providers[].api_key"``
    ⇒ 判定"某条具体路径算不算秘密"退化成一次集合查询（O(1)，且不引入正则）。
    """
    parts: list[str] = []
    for token in tokens:
        if isinstance(token, int):
            if not parts:
                raise ConfigPathError("路径的根不能是下标")
            parts[-1] = f"{parts[-1]}[]"
        else:
            parts.append(str(token))
    return ".".join(parts)


def expand_declaration(
    declared: Sequence[PathToken | _WildcardType],
    root: Any,
    prefix: Sequence[PathToken] = (),
) -> Iterator[tuple[PathToken, ...]]:
    """把声明路径按 ``root`` 里的实际下标展开成若干具体路径。

    用途：读路径要给**未配置**的秘密字段也发一个 ``set: false`` 标记（F2 三态的中间态），
    而"哪些下标真实存在"只有数据知道（``api_providers[]`` ⇒ ``api_providers[0]``/``[1]``…）。

    两条语义刻意不同：

    - **``[]`` 需要真实表项**：数组是空的 / 压根没有这个数组 ⇒ 一条都不产出
      （没有表项，就没有"某个表项的密钥没配"这回事）。
    - **普通键不需要存在**：``maim_message.auth_token`` 就算文件里没写，
      也要产出这条路径——"这个秘密没配"本身就是要报告的状态（F2 中间态）。
      所以中途取不到值只会让**后面的 ``[]``** 无表项可枚举，不会吞掉末段路径。
    """
    if not declared:
        yield tuple(prefix)
        return

    head, rest = declared[0], declared[1:]

    if isinstance(head, _WildcardType):
        if isinstance(root, (str, bytes)) or not isinstance(root, list):
            return
        for index, item in enumerate(root):
            yield from expand_declaration(rest, item, (*prefix, index))
        return

    yield from expand_declaration(rest, _declaration_child(root, head), (*prefix, head))


def _declaration_child(root: Any, token: PathToken) -> Any:
    """按声明 token 取下一层；取不到给 ``MISSING``（"取不到"不等于"路径不存在"，见上）。"""
    if isinstance(token, int):
        if isinstance(root, (str, bytes)) or not isinstance(root, list) or token >= len(root):
            return MISSING
        return root[token]
    if isinstance(root, Mapping):
        return root.get(token, MISSING)
    return MISSING


def _scan_path(path: str, *, allow_wildcard: bool) -> tuple[PathToken | _WildcardType, ...]:
    """路径扫描器：``parse_path`` 与 ``parse_declaration`` 共用的唯一实现。"""
    if not isinstance(path, str) or not path.strip():
        raise ConfigPathError("配置路径不能为空", path=str(path))

    text = path.strip()
    length = len(text)
    tokens: list[PathToken | _WildcardType] = []
    cursor = 0
    # 每读到一个元素后置 True：下一个位置必须是 ``.`` / ``[`` / 结尾，不能再直接接键名
    expecting_separator = False

    while cursor < length:
        char = text[cursor]

        if char == ".":
            if not expecting_separator:
                raise ConfigPathError("路径里出现多余的分隔符 '.'", path=path)
            cursor += 1
            expecting_separator = False
            if cursor >= length:
                raise ConfigPathError("路径不能以 '.' 结尾", path=path)
            continue

        if char == "[":
            if not expecting_separator:
                raise ConfigPathError("下标 '[' 只能跟在键名或另一个下标之后", path=path)
            closing = text.find("]", cursor)
            if closing < 0:
                raise ConfigPathError("下标缺少配对的 ']'", path=path)
            raw_index = text[cursor + 1 : closing]
            if not raw_index:
                if not allow_wildcard:
                    raise ConfigPathError("运行时路径的下标不能留空（'[]' 只用于声明）", path=path)
                tokens.append(WILDCARD)
            elif not raw_index.isdigit():
                raise ConfigPathError(f"下标必须是非负整数，收到 '{raw_index}'", path=path)
            else:
                tokens.append(int(raw_index))
            cursor = closing + 1
            continue

        if expecting_separator:
            raise ConfigPathError(f"位置 {cursor} 缺少分隔符 '.' 或下标", path=path)

        matched = _KEY_PATTERN.match(text, cursor)
        if matched is None:
            raise ConfigPathError(f"位置 {cursor} 不是合法的键名", path=path)
        tokens.append(matched.group(0))
        cursor = matched.end()
        expecting_separator = True

    if not tokens:
        raise ConfigPathError("配置路径不能为空", path=path)
    return tuple(tokens)


def format_path(tokens: Sequence[PathToken]) -> str:
    """token 元组还原成路径文本（``parse_path`` 的逆）。"""
    parts: list[str] = []
    for token in tokens:
        if isinstance(token, int):
            if not parts:
                raise ConfigPathError("路径的根不能是下标")
            parts[-1] = f"{parts[-1]}[{token}]"
        else:
            parts.append(str(token))
    return ".".join(parts)


def lookup_path(root: Any, tokens: Sequence[PathToken]) -> Any:
    """按 token 走一遍数据，查不到返回 ``MISSING``（不抛异常——读路径要能问"在不在"）。

    规则：键只认 Mapping / 下标只认 Sequence（字符串除外）；类型不符或下标越界都算"没有"。
    """
    current = root
    for token in tokens:
        if isinstance(token, int):
            if isinstance(current, (str, bytes)) or not isinstance(current, Sequence):
                return MISSING
            if token < 0 or token >= len(current):
                return MISSING
            current = current[token]
            continue

        if not isinstance(current, Mapping) or token not in current:
            return MISSING
        current = current[token]
    return current


def lookup_parent(root: Any, tokens: Sequence[PathToken]) -> tuple[Any, PathToken]:
    """定位末段 token 的父容器。

    Returns:
        ``(父容器, 末段 token)``。

    Raises:
        ConfigPathError: 父路径不存在（父路径**不自动创建**——写错一层就静默造出一棵新子树，
            那是难查的脏数据）。
    """
    if not tokens:
        raise ConfigPathError("配置路径不能为空")
    parent = lookup_path(root, tokens[:-1])
    if parent is MISSING:
        raise ConfigPathError(f"父路径不存在：{format_path(tokens[:-1])}")
    return parent, tokens[-1]


def assign_path(root: Any, tokens: Sequence[PathToken], value: Any) -> None:
    """按路径写入（``set`` op 的实现）。

    中间层**自动补齐**：缺字典就补字典、缺数组就补数组（那是"造容器"）；
    下标等于当前长度时**追加这个值本身**（那是"加一条数据"）——这两件事必须分清。
    下标大于长度直接报错——不做"空洞填充"（TOML 数组不允许空洞）。

    Args:
        root: 根容器（tomlkit 文档或纯 Python dict 均可）。
        tokens: 路径 token。
        value: 要写入的值。

    Raises:
        ConfigPathError: 路径走不通（下标越界 / 类型不符 / 无可写父层）。
    """
    if not tokens:
        raise ConfigPathError("配置路径不能为空")

    parent, last_token = _ensure_parent(root, tokens)
    if isinstance(last_token, int):
        if isinstance(parent, (str, bytes)) or not isinstance(parent, list):
            raise ConfigPathError("下标只能作用在数组上", path=format_path(tokens))
        if last_token > len(parent):
            raise ConfigPathError(
                f"下标 {last_token} 越界（当前长度 {len(parent)}）；追加只能用等于长度的下标",
                path=format_path(tokens),
            )
        if last_token == len(parent):
            # ⚠️ 必须 append **值本身**：曾误写成 `_as_container(value)`（把值当"下一段 token"
            # 去造容器）⇒ 追加了个空表、用户的值被丢掉，而报错落在"配置数据验证失败"上，
            # 合法操作永远无法成功（2026-10-16 对抗审查 F2）。
            parent.append(value)
            return
        parent[last_token] = value
        return

    if not isinstance(parent, Mapping) or not _is_mutable(parent):
        raise ConfigPathError("键只能写进表（Mapping）里", path=format_path(tokens))
    parent[last_token] = value


def remove_path(root: Any, tokens: Sequence[PathToken]) -> None:
    """按路径删除键（``unset`` op 的实现——**真删**，不是写默认值）。

    **幂等**（F9，2026-10-16 定）：键**本来就不存在**时**不算失败**——"重置为继承"的目标
    是"这个键不在文件里"，而它已经在那个状态了。旧行为是抛 ``ConfigPathError`` ⇒ 400，
    ⇒ 批量重试（第一次成功、重发同一批）会卡在这一条上，把"已经是想要的状态"报成错误。

    ⚠️ 幂等**只覆盖"键不存在"这一种**，别的照旧报错：
      - 路径**走不通**（父层类型不符 / 中间段不存在 / 下标越界）⇒ 仍然 ``ConfigPathError``:
        "文件里根本没有这条路径"是**别的错**（拼错路径、对着旧版本的表单操作），
        悄悄放过等于把用户的错误吃掉；
      - 数组元素要用 ``remove_at``（下标删除）⇒ 仍然拒绝。

    只删键，不清理变成空表的父层：TOML 里空表是合法的，而"顺手删掉空表"会让
    ``[chat]`` 这类节连同注释一起消失，超出用户点"重置"的意图。

    Raises:
        ConfigPathError: 父容器不可写 / 目标不是键（是数组元素）/ 路径走不通。
    """
    if not tokens:
        raise ConfigPathError("配置路径不能为空")
    parent, last_token = lookup_parent(root, tokens)
    if isinstance(last_token, int):
        raise ConfigPathError("数组元素要用 remove_at（下标删除），不能用 unset", path=format_path(tokens))
    if not isinstance(parent, Mapping):
        raise ConfigPathError("路径不存在，无法重置", path=format_path(tokens))
    if last_token not in parent:
        # F9：幂等分支——键已经在"不在文件里"这个状态，重复 unset 不改语义
        return
    if not _is_mutable(parent):
        raise ConfigPathError("父容器不可写", path=format_path(tokens))
    del parent[last_token]


def remove_index(root: Any, tokens: Sequence[PathToken], index: int) -> None:
    """删除数组里指定下标的元素（``remove_at`` op；**不用 set null 代替**）。

    Raises:
        ConfigPathError: 目标不是数组，或下标越界。
    """
    if not tokens:
        raise ConfigPathError("配置路径不能为空")
    if index < 0:
        raise ConfigPathError("下标不能为负数", path=format_path(tokens))
    container = lookup_path(root, tokens)
    if container is MISSING:
        raise ConfigPathError("路径不存在，无法删除数组元素", path=format_path(tokens))
    if isinstance(container, (str, bytes)) or not isinstance(container, list):
        raise ConfigPathError("remove_at 的目标必须是数组", path=format_path(tokens))
    if index >= len(container):
        raise ConfigPathError(
            f"下标 {index} 越界（当前长度 {len(container)}）",
            path=format_path(tokens),
        )
    del container[index]


def to_plain(data: Any) -> Any:
    """把 ``tomlkit`` 容器递归转成纯 Python 结构（dict / list / 标量）。

    为什么要转：``ConfigBase.from_dict`` 会对数据做 ``pop`` / 赋值，直接喂 ``tomlkit``
    的 ``Table`` 会触发它的 ``__setitem__``（把注释乱掉、甚至改动原文档）；
    纯结构则是可以随便动的副本。
    """
    if isinstance(data, Mapping):
        return {str(key): to_plain(value) for key, value in data.items()}
    if isinstance(data, (list, tuple)) and not isinstance(data, (str, bytes)):
        return [to_plain(item) for item in data]
    return data


def iter_leaf_paths(root: Any, prefix: Sequence[PathToken] = ()) -> Iterator[tuple[PathToken, ...]]:
    """列出一棵配置树里的全部**叶**路径（空表 / 空数组也算叶——它们本身就是"值")。

    给 ``get(paths)`` 的"整命名空间"模式用：不传 paths 时列出已存储的全部叶路径。
    顺序 = 文档顺序（dict 保序），所以客户端拿到的顺序是稳定的。
    """
    if isinstance(root, Mapping):
        if not root:
            if prefix:
                yield tuple(prefix)
            return
        for key, value in root.items():
            yield from iter_leaf_paths(value, (*prefix, str(key)))
        return

    if isinstance(root, (list, tuple)) and not isinstance(root, (str, bytes)):
        if not root:
            if prefix:
                yield tuple(prefix)
            return
        for index, value in enumerate(root):
            yield from iter_leaf_paths(value, (*prefix, index))
        return

    if prefix:
        yield tuple(prefix)


def _ensure_parent(root: Any, tokens: Sequence[PathToken]) -> tuple[Any, PathToken]:
    """走到末段的父容器，沿途把缺的容器补齐（``assign_path`` 的自动补齐）。"""
    current = root
    for depth, token in enumerate(tokens[:-1]):
        next_token = tokens[depth + 1]
        current = _ensure_child(current, token, next_token, tokens)
    return current, tokens[-1]


def _ensure_child(current: Any, token: PathToken, next_token: PathToken, tokens: Sequence[PathToken]) -> Any:
    """取出（必要时创建）一个中间层容器。"""
    placeholder = "" if isinstance(next_token, int) else None

    if isinstance(token, int):
        if isinstance(current, (str, bytes)) or not isinstance(current, list):
            raise ConfigPathError("下标只能作用在数组上", path=format_path(tokens))
        if token > len(current):
            raise ConfigPathError(f"下标 {token} 越界（当前长度 {len(current)}）", path=format_path(tokens))
        if token == len(current):
            current.append(_as_container(placeholder))
        elif not _is_container(current[token]):
            # 中间层已经存在但不是容器（例如它是个字符串）⇒ 再往下走必炸，提前报清楚
            raise ConfigPathError("路径中间层不是表/数组", path=format_path(tokens))
        return current[token]

    if not isinstance(current, Mapping):
        raise ConfigPathError("键只能作用在表（Mapping）上", path=format_path(tokens))
    if token not in current:
        if not _is_mutable(current):
            raise ConfigPathError("父容器不可写", path=format_path(tokens))
        current[token] = _as_container(placeholder)
    elif not _is_container(current[token]):
        raise ConfigPathError(f"中间层 '{token}' 不是表/数组", path=format_path(tokens))
    return current[token]


def _is_container(value: Any) -> bool:
    """是不是可继续下钻的容器（表 / 数组；字符串是 Sequence 但要排除）。"""
    if isinstance(value, (str, bytes)):
        return False
    return isinstance(value, (Mapping, list, tuple))


def _as_container(next_token: PathToken) -> Any:
    """按"下一段是下标还是键"造空容器。

    ``next_token`` 为 ``""`` 表示下一段是下标 ⇒ 造数组；否则造表。
    返回纯 Python 结构——tomlkit 会在赋值时把它转成对应 Item，注释与格式由 tomlkit 管。
    """
    if next_token == "":
        return []
    return {}


def _is_mutable(value: Any) -> bool:
    """能不能往里写（tomlkit 的 Table / 纯 dict 都行；只读映射不行）。"""
    return hasattr(value, "__setitem__") and hasattr(value, "__delitem__")
