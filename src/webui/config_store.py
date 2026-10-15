"""配置命名空间存储（2 段接缝的读写基座）：命名空间 → 文件 · revision 乐观锁 · schema 默认值。

**命名空间粒度 = 配置平面**（F1 实作口径，2026-10-16 lead 裁定）：
``bot`` = ``bot_config.toml``，``model`` = ``model_config.toml``；section（``chat``/``maim_message``…）
**不是**命名空间，它只是路径前缀（``chat.max_tokens``）。

理由：**写冲突发生在文件粒度**——两个写者改同一文件的不同 section，最终仍是"后写覆盖先写"；
把锁切到 section 级只会**放过**这种真冲突。锁的粒度和"会互相踩"的粒度必须是同一个。

**revision 怎么算**（不匹配 ⇒ 拒绝，见 ``commit``）：

- 每个命名空间一个**单调递增**整数 + 该文件内容的指纹（sha256）。
- 取号时先比指纹：**文件被本层之外的东西改了**（raw 端点 / 手工编辑 / 别的进程）⇒ 也算新版本，
  revision 前进一格。否则锁是假的——"别人刚改过"会看起来像"没人动过"。
- 指纹没变就返回原号 ⇒ 客户端连读两次拿到同一个 revision，不会假冲突。

⚠️ **诚实边界**：revision 状态在**进程内存**里（MaiBot 的 WebUI 是单进程，够用）。
多进程/多实例同时写同一个配置文件**不在本机制的覆盖范围**——那种部署下两个进程各自
维护一份计数，锁会失效。跨重启不会误放行：重启后计数从 1 重新开始，而指纹比对仍会
把"文件变过"识别出来（计数变小只会让老 ``expectedRevision`` 更容易被拒，方向是安全的）。
"""

from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable, Mapping, Sequence
import copy
import hashlib
import threading

import tomlkit
from pydantic_core import PydanticUndefined

from src.common.logger import get_logger
from src.common.utils.toml_utils import save_toml_with_format
from src.config.config import CONFIG_DIR, Config, ModelConfig  # noqa: TID251 — 配置面读写配置
from src.config.config_base import AttributeData, ConfigBase
from src.webui.config_paths import MISSING, PathToken, to_plain
from src.webui.config_secrets import collect_secret_field_paths, element_model

logger = get_logger("webui")


__all__ = [
    "NAMESPACES",
    "NAMESPACE_BOT",
    "NAMESPACE_MODEL",
    "NamespaceSpec",
    "RevisionConflictError",
    "UnknownNamespaceError",
    "commit",
    "config_file_path",
    "current_revision",
    "load_document",
    "load_stored",
    "namespace_spec",
    "schema_default",
    "schema_field_info",
    "secret_field_paths",
]

NAMESPACE_BOT = "bot"
NAMESPACE_MODEL = "model"


@dataclass(frozen=True)
class NamespaceSpec:
    """一个配置平面：文件 + 根模型。

    Attributes:
        name: 命名空间名（``bot`` / ``model``）。
        filename: 该平面的配置文件名（相对 ``CONFIG_DIR``）。
        model: 根配置模型类（schema 默认值、秘密派生、写入校验都用它）。
    """

    name: str
    filename: str
    model: type[ConfigBase]


NAMESPACES: Mapping[str, NamespaceSpec] = MappingProxyType(
    {
        NAMESPACE_BOT: NamespaceSpec(name=NAMESPACE_BOT, filename="bot_config.toml", model=Config),
        NAMESPACE_MODEL: NamespaceSpec(name=NAMESPACE_MODEL, filename="model_config.toml", model=ModelConfig),
    }
)

# 配置目录。**模块级名字（不是直接引用导入值）**：测试要能 monkeypatch 它指向 tmp_path，
# 调用时现读全局，别在 import 期把它烧进闭包。
CONFIG_DIR = CONFIG_DIR

_INITIAL_REVISION = 1

_REVISION_LOCK = threading.Lock()
_REVISION_STATES: dict[str, "_RevisionState"] = {}


class UnknownNamespaceError(ValueError):
    """命名空间不存在（客户端传了 ``bot``/``model`` 之外的名字）。"""

    def __init__(self, namespace: str) -> None:
        self.namespace = namespace
        known = "、".join(sorted(NAMESPACES))
        super().__init__(f"未知的配置命名空间 '{namespace}'（可用：{known}）")


class ConfigFileMissingError(FileNotFoundError):
    """命名空间对应的配置文件不存在。"""

    def __init__(self, namespace: str, path: Path) -> None:
        self.namespace = namespace
        self.path = path
        super().__init__(f"配置文件不存在：{path}")


class RevisionConflictError(Exception):
    """``expectedRevision`` 不是当前版本 ⇒ 拒绝写入（F5：不自动合并、不静默覆盖）。

    Attributes:
        namespace: 冲突的命名空间。
        expected: 客户端带的 revision。
        current: 服务端当前的 revision。
    """

    def __init__(self, *, namespace: str, expected: int, current: int) -> None:
        self.namespace = namespace
        self.expected = expected
        self.current = current
        super().__init__(
            f"配置 '{namespace}' 已被其他改动推进（当前 revision={current}，"
            f"你带的是 {expected}）；请重新读取后再提交"
        )


@dataclass
class _RevisionState:
    """命名空间的 revision 状态（进程内，锁内访问）。"""

    revision: int
    fingerprint: str


def namespace_spec(namespace: str) -> NamespaceSpec:
    """取命名空间定义；不存在 ⇒ ``UnknownNamespaceError``。"""
    spec = NAMESPACES.get(namespace)
    if spec is None:
        raise UnknownNamespaceError(namespace)
    return spec


def config_file_path(namespace: str) -> Path:
    """命名空间对应的配置文件路径（现读模块级 ``CONFIG_DIR``，便于测试隔离）。"""
    return Path(CONFIG_DIR) / namespace_spec(namespace).filename


def load_document(namespace: str) -> Any:
    """读原始 ``tomlkit`` 文档（保注释、保格式、可真删键）。

    Raises:
        ConfigFileMissingError: 文件不存在。
    """
    path = config_file_path(namespace)
    if not path.exists():
        raise ConfigFileMissingError(namespace, path)
    with open(path, "r", encoding="utf-8") as file:
        return tomlkit.load(file)


def load_stored(namespace: str) -> Any:
    """读**已存储的那份**为纯 Python 结构——这就是 F1 说的"解析基准"。"""
    return to_plain(load_document(namespace))


def secret_field_paths(namespace: str) -> frozenset[str]:
    """该命名空间的秘密声明路径全集（声明表 ∪ 字段声明派生）。"""
    spec = namespace_spec(namespace)
    return collect_secret_field_paths(namespace, spec.model)


def current_revision(namespace: str) -> int:
    """读当前 revision；读配置**之前**先拿它，写的时候原样带回来。"""
    namespace_spec(namespace)  # 先校验命名空间，再动锁
    with _REVISION_LOCK:
        return _refresh_locked(namespace).revision


def commit(
    namespace: str,
    expected_revision: int,
    apply: Callable[[Any, Any], None],
    *,
    validate: Callable[[Any], None] | None = None,
) -> int:
    """乐观锁保护的配置写入：**校验 → 落盘 → 推进 revision**。

    顺序是判据的一部分：

    1. 刷新 revision（文件被外部改过也算新版本）；与 ``expected_revision`` 不等 ⇒
       ``RevisionConflictError``，**在动任何数据之前**就把这次写入挡掉。
    2. 重新读**已存储的那份**文档，把 ``apply(document, baseline)`` 作用在它上面
       —— 解析基准是存储，不是"调用者上次读到的那份"（F1）。
       ``baseline`` 是**同一把锁里**取出来的变更前快照：秘密占位的认领基准必须是它，
       不能在锁外先读一遍（那中间会漏进别人的写入）。
    3. ``validate`` 不通过 ⇒ 异常上抛，**文件一个字节不动、revision 不前进**。
    4. 落盘（``save_toml_with_format`` 内部是原子写）后才推进 revision。

    Args:
        namespace: 命名空间。
        expected_revision: 客户端读到的 revision。
        apply: 在 ``tomlkit`` 文档上就地实施变更；第二参数是**变更前**的纯 Python 快照
            （认领秘密原值用）。
        validate: 写入前的整体校验（收纯 Python 结构）；``None`` = 用根模型 ``from_dict``。

    Returns:
        写入后的新 revision。

    Raises:
        UnknownNamespaceError: 命名空间不存在。
        ConfigFileMissingError: 配置文件不存在。
        RevisionConflictError: ``expected_revision`` 过期。
        FileNotFoundError: 并发下文件被删。
    """
    spec = namespace_spec(namespace)
    path = config_file_path(namespace)
    validator = validate if validate is not None else _default_validator(spec)

    with _REVISION_LOCK:
        state = _refresh_locked(namespace)
        if state.revision != expected_revision:
            raise RevisionConflictError(
                namespace=namespace,
                expected=expected_revision,
                current=state.revision,
            )

        document = load_document(namespace)
        baseline = to_plain(document)
        apply(document, baseline)
        validator(to_plain(document))

        save_toml_with_format(document, str(path))
        state.fingerprint = _fingerprint(path)
        state.revision += 1
        return state.revision


def schema_field_info(namespace: str, tokens: Sequence[PathToken]) -> Any | None:
    """沿路径在模型里找字段，返回末段的 ``FieldInfo``；找不到给 ``None``。

    数组下标不改变所属模型（``api_providers[0].api_key`` 与 ``api_providers[1].api_key``
    落在同一个 ``APIProvider`` 上），所以下标被跳过。
    """
    current: Any = namespace_spec(namespace).model
    info: Any = None
    for token in tokens:
        if isinstance(token, int):
            continue
        fields = getattr(current, "model_fields", None)
        if not isinstance(fields, Mapping) or token not in fields:
            return None
        info = fields[token]
        current = element_model(getattr(info, "annotation", None))
    return info


def schema_default(namespace: str, tokens: Sequence[PathToken]) -> Any:
    """取该路径的 schema 默认值；没有默认值（或路径根本没有对应字段）⇒ ``MISSING``。

    ``unset(path)`` 之后读回来的 ``value`` 就是从这里来的——**"重置为继承"不是"写一个
    恰好等于默认值的值"**（F5）：前者文件里没有这个键、``inherited=true``；后者文件里有键、
    ``inherited=false``，而且从今往后 schema 默认值再变，它也跟不上了。
    """
    if not tokens or isinstance(tokens[-1], int):
        # 数组元素没有"元素级默认值"这回事（默认值属于字段，不属于第 n 个表项）
        return MISSING

    info = schema_field_info(namespace, tokens)
    if info is None:
        return MISSING

    if getattr(info, "default", PydanticUndefined) is not PydanticUndefined:
        return _jsonable(info.default)

    factory = getattr(info, "default_factory", None)
    if factory is not None:
        try:
            return _jsonable(factory())
        except Exception as error:  # noqa: BLE001 — 默认值是只读查询，坏一个字段不该炸整个读接口
            _report_internal_error(
                "计算配置字段默认值失败",
                error,
                detail=f"（{namespace}:{_path_text(tokens)}）",
            )
            return MISSING

    return MISSING


def _default_validator(spec: NamespaceSpec) -> Callable[[Any], None]:
    """默认校验：按根模型 ``from_dict`` 走一遍（不通过就抛，调用方不再落盘）。"""

    def _validate(plain: Any) -> None:
        spec.model.from_dict(AttributeData(), copy.deepcopy(plain))

    return _validate


def _refresh_locked(namespace: str) -> _RevisionState:
    """锁内刷新 revision（调用方必须已持锁）。"""
    fingerprint = _fingerprint(config_file_path(namespace))
    state = _REVISION_STATES.get(namespace)
    if state is None:
        state = _RevisionState(revision=_INITIAL_REVISION, fingerprint=fingerprint)
        _REVISION_STATES[namespace] = state
        return state

    if state.fingerprint != fingerprint:
        # 本层之外有人改了文件（raw 端点 / 手工编辑 / 别的进程）
        # ⇒ 从乐观锁的角度这**必须**是一次新版本，否则老 expectedRevision 会被误判成最新
        state.revision += 1
        state.fingerprint = fingerprint
    return state


def _fingerprint(path: Path) -> str:
    """文件内容指纹；文件不存在给空串（"不存在"本身也是一种状态）。"""
    if not path.exists():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _jsonable(value: Any) -> Any:
    """把模型实例转成可进 JSON 的形态（默认值可能是 ``ConfigBase`` 实例）。"""
    dump = getattr(value, "model_dump", None)
    if callable(dump):
        return dump()
    return value


def _path_text(tokens: Sequence[PathToken]) -> str:
    """仅用于日志：把 token 拼回大致可读的路径（不 import format_path 以避循环风险为零，直接内联）。"""
    parts: list[str] = []
    for token in tokens:
        if isinstance(token, int):
            parts.append(f"[{token}]")
        else:
            parts.append(f".{token}" if parts else str(token))
    return "".join(parts)


def _report_internal_error(message: str, error: Exception, *, detail: str = "") -> None:
    """内部异常**双通道**上报（logger + 上报口）——AGENTS §七 缺陷模式 7。"""
    logger.error(f"{message}{detail}: {error}", exc_info=True)

    from src.core.error_escalation.types import ErrorLevel
    from src.core.error_escalation_port_registry import get_error_escalation_port

    port = get_error_escalation_port()
    if port is not None:
        port.report(ErrorLevel.ERROR, message, exception=error)
