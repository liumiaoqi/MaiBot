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

**锁里放什么**（F13，2026-10-16）：``_REVISION_LOCK`` 只覆盖"**一致性必需**"的那点活——
读字节 + sha256、revision 校验、以及**替换文件 + 推进 revision**（后者必须是一个原子步，
否则读者会看到"新内容 + 旧 revision"）。解析 TOML、``to_plain``、``apply``、
pydantic 全模型校验**一律在锁外**：它们曾是 248ms 里的大头（校验 161ms / 解析 27.5ms），
而它们既不读共享状态也不需要被串行化。写侧与读侧（``read_snapshot``）是同一条原则。
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
    "read_snapshot",
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
        reason: 可选的补充说明（用于"快照内容变了"这一类——此时 expected 与 current 可能相等，
            基础消息里的"被其他改动推进"说不清现场，必须补一句实话）。
    """

    def __init__(self, *, namespace: str, expected: int, current: int, reason: str = "") -> None:
        self.namespace = namespace
        self.expected = expected
        self.current = current
        self.reason = reason
        base = (
            f"配置 '{namespace}' 已被其他改动推进（当前 revision={current}，"
            f"你带的是 {expected}）"
        )
        detail = f"——{reason}" if reason else ""
        super().__init__(f"{base}{detail}；请重新读取后再提交")


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
    """读当前 revision；读配置**之前**先拿它，写的时候原样带回来。

    ⚠️ 单读 revision 是安全的；但**"读内容 + 读 revision"必须走 ``read_snapshot``**——
    分两次调用会在中间留下撕裂窗口（见该函数的说明，F11）。
    """
    namespace_spec(namespace)  # 先校验命名空间，再动锁
    with _REVISION_LOCK:
        return _refresh_locked(namespace).revision


def read_snapshot(namespace: str) -> tuple[Any, int]:
    """**一次取回 ``(内容, revision)`` 且两者同源**——读接缝唯一该用的取数口（F11）。

    **为什么必须是一个口**：读接缝原先分两步调 ``load_stored()`` 与 ``current_revision()``，
    两次各自进出锁。写者插在中间，客户端就拿到 **(旧内容, 新 revision)**——它以为自己是
    最新的，带着这个 revision 去 ``mutate`` 会**被接受** ⇒ 乐观锁的保护失效
    （基于旧内容算出来的写被当成最新写）。窗口不小：``load_stored`` 既不持锁、
    又做文件 I/O，正好把 GIL 让出去。**实测：双线程下 40 次读 ⇒ 40 次撕裂**。
    生产上具备双线程条件：``src/main.py`` 里 WebUI 跑在**独立线程**（``ThreadedWebUIServer``）。

    **锁只覆盖"一致性所需的最小范围"**（F13 的教训：别持锁做重活）：
    锁内只做 **读字节 + sha256**（实测 0.28ms），**解析 TOML 与 ``to_plain`` 都在锁外**。
    能这么做的原因：revision 是由**内容指纹**派生的，而这一版把指纹**算在同一批字节上**，
    于是 "内容 ↔ revision" 由构造保证同源，不需要靠"把解析也锁住"来换。作为对照，
    若把 ``load_stored`` 也塞进锁内，锁的持有时长会从 0.3ms 涨到 ~30ms（bot 平面实测
    解析 27.5ms）——那正是 F13 抱怨的那类写法。

    **残余边界（如实说，不假装闭合）**：本锁只序列化**经过 config_store 的**读写。
    ``chat_session_service_web.py`` 等处直接调 ``save_toml_with_format`` 写同一份配置，
    它们**不持这把锁** ⇒ 仍有一个"读文件本身"级别的窄窗口（微秒量级，且方向保守：
    客户端会拿到比 revision 更新的内容，带旧 revision 去写会被 409 拒）。要彻底闭合得让那些
    写者也走本锁，属"删旧写路径"那一批（待 lmq 拍板），不在本段。

    Args:
        namespace: 命名空间。

    Returns:
        ``(已存储的纯 Python 结构, 与这份内容同源的 revision)``。

    Raises:
        UnknownNamespaceError: 命名空间不存在。
        ConfigFileMissingError: 配置文件不存在。
    """
    namespace_spec(namespace)  # 先校验命名空间，再动锁
    path = config_file_path(namespace)
    if not path.exists():
        raise ConfigFileMissingError(namespace, path)

    with _REVISION_LOCK:
        raw = path.read_bytes()
        revision = _refresh_locked(namespace, fingerprint=hashlib.sha256(raw).hexdigest()).revision

    # 锁外解析：重活不占锁
    return to_plain(tomlkit.loads(_decode_config_bytes(raw))), revision


def _decode_config_bytes(raw: bytes) -> str:
    """配置文件字节 → 文本，**与 ``open(..., "r", encoding="utf-8")`` 的换行语义对齐**。

    为什么要显式折行：本仓 ``config/bot_config.toml`` 是 **CRLF**（实测 661 个 CRLF），
    而 ``open(..., "r")`` 默认做 universal newlines（``\\r\\n`` → ``\\n``），
    ``read_bytes().decode()`` **不做**。两条路解出来的文本如果在多行字符串上分叉，
    就成了"读接缝看到的配置与写路径看到的配置不是同一份"——那是最难查的一类不一致。
    这里把 ``open`` 的语义显式复刻一遍，并有用例在真配置上对拍两条路的结果。
    """
    return raw.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")


def commit(
    namespace: str,
    expected_revision: int,
    apply: Callable[[Any, Any], None],
    *,
    validate: Callable[[Any], None] | None = None,
) -> int:
    """乐观锁保护的配置写入：**校验 revision → 落盘 → 推进 revision**（F13：重活在锁外）。

    顺序是判据的一部分：

    1. **临界区一**（实测 ~0.3ms）：读字节 + sha256 + 刷新 revision + 与 ``expected_revision``
       比对；不等 ⇒ ``RevisionConflictError``，**在动任何数据之前**就把这次写入挡掉。
       指纹**取自同一批字节**并当场登记为当前状态 ⇒ "内容 ↔ revision" 由构造保证同源（F11 的口径）。
    2. **锁外重活**（实测 ~0.4s，一秒都不占锁）：解析 TOML、转纯结构、``apply(document, baseline)``、
       ``validate``。这一步是 F13 要解决的问题所在——旧实现把它整段塞在锁里。
    3. **临界区二**（实测 ~落盘量级）：复核 revision 与快照指纹未被改动 → ``save_toml_with_format``
       → 重算指纹 → revision 前进。

    **为什么"落盘"与"推进 revision"必须共享同一个临界区**（本函数最容易被后人误拆的一处）：
    读者（``read_snapshot``）是**在锁内**读字节并**当场**登记指纹的，所以它眼中的
    "内容 ↔ revision" 是否同源，**完全**取决于这两件事是不是被同一把锁包住：

    - 拆开（例如为"再省几毫秒"把 ``save_toml_with_format`` 或 ``state.revision += 1`` 挪出 ``with``）
      ⇒ 读者可以在中间插进来：拿到**旧内容 + 新 revision**（乐观锁失效、基于旧内容的写会被误接受）
      或**新内容 + 旧 revision**（客户端以为过期、白拒一次）。这正是 F11 修掉的撕裂。
    - 两个并发 commit 交错落盘（"谁都对不上"）也是这一条的下半段。

    ⇒ 这一段是 **F11 不变式的结构保证**，不是"顺手写在一起"：
    ``pytests/webui/test_config_seam.py::TestReadSnapshotAtomicity`` 的零撕裂断言**靠它成立**。
    要再拆锁范围，先看那条用例——它红得起来是**好事**，别改断言（2026-10-16 与 `fu-xuan` 对齐）。

    **为什么锁外重活是安全的**（这是本函数唯一需要论证的地方，别只看结论）：

    - ``apply`` / ``validate`` 作用的那份 ``document`` 派生自**临界区一里读到的字节**，而临界区一
      把那批字节的指纹登记成了命名空间的当前指纹 ⇒ 此后**任何**内容变化都会让 revision 前进
      （``_refresh_locked`` 的既有语义："本层之外有人改了文件 ⇒ 从乐观锁角度这必须是一次新版本"）。
      于是临界区二的 revision 比对**等价于**"内容自快照以来没变过"——不需要把解析也锁住来换。
    - ``baseline``（秘密占位认领基准）因此也合法：它同样是那批字节的纯结构，而它"不会漏进别人的
      写入"这一点由上述同源保证，**不再**依赖"必须在锁里读一遍"（旧实现的理由，F13 起由指纹复核
      承担同一职责）。
    - 快照在锁内读（不是锁外）是有意的：若在锁外读、再拿旧指纹去登记，就会把**过期指纹**写成当前
      状态（盘上已是新内容、状态却说是旧的）。锁内读+当场登记把这个窗口消掉；代价是 0.3ms。

    ⚠️ **不得**为了"少做一次 I/O"把快照读挪到锁外——那正是上面那条失效的形态。

    Args:
        namespace: 命名空间。
        expected_revision: 客户端读到的 revision。
        apply: 在 ``tomlkit`` 文档上就地实施变更；第二参数是**变更前**的纯 Python 快照
            （认领秘密原值用），与写入的基准同源。
        validate: 写入前的整体校验（收纯 Python 结构）；``None`` = 用根模型 ``from_dict``。

    Returns:
        写入后的新 revision。

    Raises:
        UnknownNamespaceError: 命名空间不存在。
        ConfigFileMissingError: 配置文件不存在。
        RevisionConflictError: ``expected_revision`` 过期，或（防御分支）快照内容已被改动。
    """
    spec = namespace_spec(namespace)
    path = config_file_path(namespace)
    validator = validate if validate is not None else _default_validator(spec)

    # ── 临界区一：同源快照 + 过期写入早退（约 0.3ms）────────────────────────────
    with _REVISION_LOCK:
        if not path.exists():
            raise ConfigFileMissingError(namespace, path)
        raw = path.read_bytes()
        snapshot_fingerprint = hashlib.sha256(raw).hexdigest()
        state = _refresh_locked(namespace, fingerprint=snapshot_fingerprint)
        if state.revision != expected_revision:
            raise RevisionConflictError(
                namespace=namespace,
                expected=expected_revision,
                current=state.revision,
            )

    # ── 锁外重活：解析 / 转纯结构 / 变更 / 全模型校验（约 0.4s）────────────────
    # 解析走 `_decode_config_bytes`：与 `read_snapshot` 同一套换行语义，两条路看到的配置必须
    # 逐字段一致（真配置是 CRLF，`read_bytes().decode()` 与 `open(..., "r")` 会分叉）。
    document = tomlkit.loads(_decode_config_bytes(raw))
    baseline = to_plain(document)
    apply(document, baseline)
    validator(to_plain(document))

    # ── 临界区二：复核 → 落盘 → 推进 revision（约落盘量级）──────────────────────
    with _REVISION_LOCK:
        state = _refresh_locked(namespace)
        if state.revision != expected_revision:
            raise RevisionConflictError(
                namespace=namespace,
                expected=expected_revision,
                current=state.revision,
            )
        _assert_snapshot_unchanged(namespace, state, snapshot_fingerprint, expected_revision)

        save_toml_with_format(document, str(path))
        state.fingerprint = _fingerprint(path)
        state.revision += 1
        return state.revision


def _assert_snapshot_unchanged(
    namespace: str,
    state: _RevisionState,
    snapshot_fingerprint: str,
    expected_revision: int,
) -> None:
    """复核"盘上内容还是我们快照的那份"——**不变量的自检**，不是常规判据。

    为什么**推理上不可达**（写清楚，免得后人以为漏了用例）：临界区一刚把
    ``state.fingerprint`` 置为快照指纹；而 ``state.fingerprint`` 只在锁内被改，且
    ``_refresh_locked`` 每次把指纹从"快照那份"改成别的，**同一次调用里必然让 revision 前进**
    ⇒ "内容变了"一定先被上面的 revision 比对拦下（``expected`` 那份号已经过期）。

    那它为什么还留着：它是"内容 ↔ revision 同源"这条不变量的**最后一道自检**。哪天有人把快照读
    挪到锁外、或让 ``_REVISION_STATES`` 绕过锁更新，revision 比对会**静默通过**并按旧内容落盘，
    而这一行会当场出声。行为由注入式用例锁定（``pytests/webui/test_config_commit_lock_scope.py``）。

    Raises:
        RevisionConflictError: 快照指纹与当前状态不符（正常情况下永不触发）。
    """
    if state.fingerprint == snapshot_fingerprint:
        return
    raise RevisionConflictError(
        namespace=namespace,
        expected=expected_revision,
        current=state.revision,
        reason=(
            "盘上内容在你读出快照之后被改动过（本次写入基于过期内容，已放弃而不是重算覆盖）"
        ),
    )


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


def _refresh_locked(namespace: str, *, fingerprint: str | None = None) -> _RevisionState:
    """锁内刷新 revision（调用方必须已持锁）。

    Args:
        namespace: 命名空间。
        fingerprint: 已算好的内容指纹。``read_snapshot`` 会传进来——它必须在**锁内**读字节、
            又不想读两遍（读+哈希实测 0.28ms，是锁可以覆盖的最小代价）。
            ``None`` = 自己现算（``commit`` / ``current_revision`` 走这条）。
    """
    if fingerprint is None:
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
