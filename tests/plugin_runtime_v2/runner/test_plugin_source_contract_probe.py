"""P0-c 常驻探针：**插件源码 ↔ 宿主契约**的源级对拍（跨仓，但跑在我们的 CI 里）。

为什么放我们仓：插件仓的测试不会被我们的 CI 跑到（`docs/pitfalls.md` #33 也把插件目录列为
"新 worktree 必补的三类资源"之一）。探针读插件源码、断言契约，跨边界的两侧就在同一条判据上。

探针三件（对应判据门③"必须证明红得起来"）：
1. 正向：真实适配器的 @Tool 声明必须与处理器实际读取的键**完全对齐**；
2. 自检：扫描不到任何 @Tool ⇒ **报错**（"扫描器自己瞎了"不许当通过——照 dsh
   `scripts/gen-cordis-catalog.ts:929-931` 的做法）；
3. 鉴别力：合成三种坏样本（漏 required / 多 required / 无声明）必须**各自红**。
"""

import ast
from pathlib import Path
from typing import Any

ADAPTER_PLUGIN = (
    Path(__file__).resolve().parents[3] / "plugins" / "maibot-team.napcat-adapter" / "plugin.py"
)
TOOL_PREFIX = "napcat."


def _tool_declarations(source: str) -> list[tuple[ast.AST, str, dict[str, Any] | None]]:
    """抽出 `@Tool(...)` 声明：返回 (函数节点, 工具名, parameters_schema)。"""
    found: list[tuple[ast.AST, str, dict[str, Any] | None]] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call) or getattr(decorator.func, "id", "") != "Tool":
                continue
            keywords = {kw.arg: kw.value for kw in decorator.keywords}
            name_node = keywords.get("name")
            tool_name = str(ast.literal_eval(name_node)) if name_node is not None else node.name
            schema_node = keywords.get("parameters_schema")
            schema = ast.literal_eval(schema_node) if schema_node is not None else None
            found.append((node, tool_name, schema))
    return found


def _hard_read_keys(func: ast.AST) -> set[str]:
    """处理器**硬索引**读的键：`args["k"]`（缺了就是 KeyError）。"""
    keys: set[str] = set()
    for node in ast.walk(func):
        if (
            isinstance(node, ast.Subscript)
            and isinstance(node.value, ast.Name)
            and node.value.id == "args"
            and isinstance(node.slice, ast.Constant)
            and isinstance(node.slice.value, str)
        ):
            keys.add(node.slice.value)
    return keys


def find_schema_contract_violations(source: str) -> list[str]:
    """源级契约对拍：`parameters_schema.required` ⟺ 处理器硬索引的键。"""
    declarations = _tool_declarations(source)
    if not declarations:
        return ["扫描不到任何 @Tool 声明——探针自己瞎了（扫描失败不许当通过）"]

    violations: list[str] = []
    for func, tool_name, schema in declarations:
        if not tool_name.startswith(TOOL_PREFIX):
            continue
        hard_keys = _hard_read_keys(func)
        if schema is None:
            violations.append(f"{tool_name}: 没有 parameters_schema ⇒ 宿主侧校验不会执行")
            continue
        required = {str(key) for key in (schema.get("required") or [])}
        properties = {str(key) for key in (schema.get("properties") or {})}
        for key in sorted(hard_keys - required):
            violations.append(
                f"{tool_name}: 处理器硬索引 args[{key!r}]，schema 却没把它列入 required（缺参会炸在运行时）"
            )
        for key in sorted(required - hard_keys):
            violations.append(
                f"{tool_name}: schema 把 {key!r} 标成 required，处理器并不硬读它（会误拒合法调用）"
            )
        for key in sorted(required - properties):
            violations.append(f"{tool_name}: required 里的 {key!r} 不在 properties 里")
    return violations


def test_adapter_tool_schemas_match_handler_reads() -> None:
    """正向：真实适配器的每个发送工具，声明与读取必须对齐（== 无违规）。"""
    assert ADAPTER_PLUGIN.exists(), f"插件源码不在（见 docs/pitfalls.md #33）: {ADAPTER_PLUGIN}"
    violations = find_schema_contract_violations(ADAPTER_PLUGIN.read_text(encoding="utf-8"))
    assert violations == [], "插件声明与处理器读取对不上：\n" + "\n".join(violations)


def test_probe_sees_the_send_tools() -> None:
    """自检的第二半：真源码里确实扫到了 N 个发送工具（防"扫了个空"也算过）。"""
    tools = [
        name
        for _func, name, _schema in _tool_declarations(ADAPTER_PLUGIN.read_text(encoding="utf-8"))
        if name.startswith(TOOL_PREFIX)
    ]
    assert len(tools) >= 5, f"只扫到 {tools}——扫描器可能瞎了"


def test_probe_goes_red_when_required_key_missing() -> None:
    """鉴别力①：处理器硬读 `session_id` 却漏写 required ⇒ 必须红。"""
    bad = '''
class P:
    @Tool(name="napcat.send_text", description="x", parameters_schema={
        "type": "object", "properties": {"session_id": {"type": "string"}}, "required": [],
    })
    async def tool_send_text(self, args):
        return args["session_id"]
'''
    violations = find_schema_contract_violations(bad)
    assert violations and "session_id" in violations[0], f"漏写 required 没被抓到: {violations}"


def test_probe_goes_red_when_required_key_absent_from_properties() -> None:
    """鉴别力②：required 里的键不在 properties ⇒ 必须红（schema 自相矛盾）。"""
    bad = '''
class P:
    @Tool(name="napcat.send_image", description="x", parameters_schema={
        "type": "object", "properties": {}, "required": ["session_id"],
    })
    async def tool_send_image(self, args):
        return args["session_id"]
'''
    violations = find_schema_contract_violations(bad)
    assert any("不在 properties" in item for item in violations), f"自相矛盾没被抓到: {violations}"


def test_probe_goes_red_on_missing_declaration() -> None:
    """鉴别力③：工具没声明 schema ⇒ 必须红（它就是"写了也校不到"的入口）。"""
    bad = '''
class P:
    @Tool(name="napcat.send_emoji", description="x")
    async def tool_send_emoji(self, args):
        return args["emoji_base64"]
'''
    violations = find_schema_contract_violations(bad)
    assert any("没有 parameters_schema" in item for item in violations), f"未声明没被抓到: {violations}"


def test_probe_goes_red_when_scanner_sees_nothing() -> None:
    """鉴别力④：源码里没有任何 @Tool ⇒ 报"扫描器瞎了"，不许静默通过。"""
    violations = find_schema_contract_violations("x = 1\n")
    assert violations and "扫描不到" in violations[0], f"空扫描没被抓到: {violations}"
