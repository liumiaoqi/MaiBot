"""P0-c① 常驻探针：**插件配置的声明面 ⊇ 读取面**（跨仓，但跑在我们的 CI 里）。

为什么放我们仓：插件仓的测试不会被我们的 CI 跑到（`docs/pitfalls.md` #33 也把插件目录列为
"新 worktree 必补的三类资源"之一）。探针读插件源码、断言契约，跨边界的两侧就在同一条判据上。
（同款先例：`tests/plugin_runtime_v2/runner/test_plugin_source_contract_probe.py`。）

**这一条对的是哪个真机事故**：`transport.py:148` 曾读 `server_config.action_timeout_sec`，
而 `NapCatServerConfig` **没有**这个字段 ⇒ 每次发送都在 `AttributeError` 上失败
（"能听不能说"的第五层，插件仓 `cf2f59c` 修）。当时**同仓两个文件都没对上，任何单侧测试都不会红**
——正是路线图 P0 要消灭的形状。

**两处必须记住的坑**（写错就出假阳性/假阴性）：

1. **方法要算进声明集**：`server_config.build_ws_url()` 读的是**方法**，只比 `AnnAssign` 字段
   会把 `build_ws_url` 报成"读了未声明的成员"——那是假阳性。
2. **读取面不止那一个**：`transport` 还读 `heartbeat_interval` / `reconnect_delay_sec` / `token`
   （`token` 出现 4 次），以及 `self._server_config` 这条别名链。漏掉它们，探针就只剩"看起来绿"。

探针三件（对应判据门③"必须证明红得起来"）：
1. 正向：真实源码上"读取面 ⊆ 声明面 ∪ 方法"**零违规**；
2. 自检：两侧任一扫空 ⇒ **报错**（"扫描器自己瞎了"不许当通过——照 dsh
   `scripts/gen-cordis-catalog.ts:929-931` 的做法）；
3. 鉴别力：合成坏样本（读一个不存在的字段 / 空扫描 / 只有写入）必须**各自红**。
"""

import ast
from pathlib import Path

ADAPTER_DIR = Path(__file__).resolve().parents[3] / "plugins" / "maibot-team.napcat-adapter"
DECLARATION_FILE = ADAPTER_DIR / "config.py"
READ_FILE = ADAPTER_DIR / "transport.py"
TARGET_CLASS = "NapCatServerConfig"
#: 读取侧的两种写法：`server_config.x`（本地别名）与 `self._server_config.x`
READ_ALIASES = ("server_config",)


def _declared_members(source: str, class_name: str = TARGET_CLASS) -> set[str]:
    """类里**可被属性访问到**的名字 = 带注解的字段 ∪ 带注解的赋值 ∪ 方法名。

    `AnnAssign` 是 dataclass 字段（有/无默认值都算）；`Assign` 覆盖非 dataclass 的类属性；
    `FunctionDef`/`AsyncFunctionDef` 是方法——**方法必须算**（`build_ws_url` 那类读取的落点）。
    """
    members: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.ClassDef) or node.name != class_name:
            continue
        for item in node.body:
            if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                members.add(item.target.id)
            elif isinstance(item, ast.Assign):
                for target in item.targets:
                    if isinstance(target, ast.Name):
                        members.add(target.id)
            elif isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                members.add(item.name)
    return members


def _read_attributes(source: str) -> set[str]:
    """读到的属性名集合。

    只收 **Load 上下文**：`server_config.x = 1`（Store）是写，不是读——
    把写当读会让探针看着更严，实际是在报假阳性。
    """
    reads: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Attribute) or not isinstance(node.ctx, ast.Load):
            continue
        # server_config.<attr>
        if isinstance(node.value, ast.Name) and node.value.id in READ_ALIASES:
            reads.add(node.attr)
            continue
        # self._server_config.<attr>
        inner = node.value
        if (
            isinstance(inner, ast.Attribute)
            and isinstance(inner.value, ast.Name)
            and inner.value.id == "self"
            and inner.attr.startswith("_server_config")
        ):
            reads.add(node.attr)
    return reads


def find_config_contract_violations(declaration_source: str, read_source: str) -> list[str]:
    """源级契约对拍：`server_config.<attr>` 的读取集必须 ⊆ 声明集（字段 ∪ 方法）。"""
    declared = _declared_members(declaration_source)
    reads = _read_attributes(read_source)

    blind: list[str] = []
    if not declared:
        blind.append(f"扫描不到 {TARGET_CLASS} 的声明——探针自己瞎了（扫描失败不许当通过）")
    if not reads:
        blind.append("扫不到任何 server_config.<attr> 读取——探针自己瞎了（扫描失败不许当通过）")
    if blind:
        return blind

    return [
        f"读取了未声明的成员：server_config.{name}（声明面：{TARGET_CLASS}.{name} 不存在）"
        for name in sorted(reads - declared)
    ]


def _real_pair() -> tuple[str, str]:
    for path in (DECLARATION_FILE, READ_FILE):
        assert path.exists(), f"插件源码不在（见 docs/pitfalls.md #33）: {path}"
    return (
        DECLARATION_FILE.read_text(encoding="utf-8"),
        READ_FILE.read_text(encoding="utf-8"),
    )


def test_adapter_server_config_reads_are_declared() -> None:
    """正向：真实适配器上，读取面 ⊆ 声明面 ∪ 方法（== 无违规）。"""
    violations = find_config_contract_violations(*_real_pair())
    assert violations == [], "配置声明与读取对不上：\n" + "\n".join(violations)


def test_probe_sees_the_known_reads() -> None:
    """自检①：真源码里确实扫到了那几个已知读取（防"扫了个空"也算过）。"""
    _declaration, read_source = _real_pair()
    reads = _read_attributes(read_source)
    missing = {"action_timeout_sec", "build_ws_url", "heartbeat_interval", "reconnect_delay_sec", "token"} - reads
    assert not missing, f"漏扫了这些读取 {sorted(missing)}——扫描器可能瞎了（实扫到 {sorted(reads)}）"


def test_probe_counts_methods_as_declared() -> None:
    """自检②：**方法要算进声明集**——`build_ws_url` 是方法不是字段。

    只比 `AnnAssign` 字段会把 `build_ws_url` 报成违规（假阳性）；这条用例把它钉住。
    """
    declaration_source, _read_source = _real_pair()
    declared = _declared_members(declaration_source)
    assert "build_ws_url" in declared, f"方法没被算进声明集（假阳性的来源）：{sorted(declared)}"
    assert "action_timeout_sec" in declared, f"字段没被扫到：{sorted(declared)}"


def test_probe_goes_red_when_reading_undeclared_field() -> None:
    """鉴别力①：读一个类里没有的字段 ⇒ 必须红（这就是 `action_timeout_sec` 那次事故的形状）。"""
    declaration = '''
class NapCatServerConfig:
    ws_url: str = "ws://127.0.0.1:3001"

    def build_ws_url(self) -> str:
        return self.ws_url
'''
    bad_read = '''
async def call(server_config):
    return server_config.action_timeout_sec
'''
    violations = find_config_contract_violations(declaration, bad_read)
    assert violations and "action_timeout_sec" in violations[0], f"未声明字段没被抓到: {violations}"


def test_probe_goes_red_when_reads_scanned_nothing() -> None:
    """鉴别力②：读取侧扫不到任何读取 ⇒ 报"扫描器瞎了"，不许静默通过。"""
    violation_source = "x = 1\n"
    declaration = "class NapCatServerConfig:\n    ws_url: str = 'x'\n"
    violations = find_config_contract_violations(declaration, violation_source)
    assert violations and "扫不到任何" in violations[0], f"空扫描没被抓到: {violations}"


def test_probe_goes_red_when_declaration_scanned_nothing() -> None:
    """鉴别力③：声明侧找不到目标类 ⇒ 必须红（类被改名/挪走时不许当通过）。"""
    violations = find_config_contract_violations("class Other:\n    x: int = 1\n", "y = server_config.ws_url\n")
    assert violations and "扫描不到" in violations[0], f"类不见了没被抓到: {violations}"


def test_probe_ignores_writes() -> None:
    """假阳性防线：`server_config.x = 1`（Store）不是"读"，不该被算进读取面。"""
    declaration = "class NapCatServerConfig:\n    ws_url: str = 'x'\n"
    write_only = "def f(server_config):\n    server_config.never_declared = 1\n"
    assert _read_attributes(write_only) == set()
    # 只有写入 ⇒ 读取面为空 ⇒ 触发"扫描器瞎了"的自检，而不是静默通过
    assert find_config_contract_violations(declaration, write_only) != []
