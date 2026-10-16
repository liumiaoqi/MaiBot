#!/usr/bin/env python3
"""ZG-N1 反射接线检查器 — 静态 AST 接线门禁。

检查 8 类历史债模式（接线四问自动化），输出 JSON 报告。
CI 模式：发现问题即 exit(1) 拦截。

用法：
    n1_wiring_checker.py [--scan src [--scan ...]] [--engine auto|rg|py]
                           [--whitelist whitelist.json] [--ci] [--json]
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path

# ───────────────────────────── 检查项 1-8 ─────────────────────────────

# 检查项 1：零创建点 — 类定义必须有构造调用（排除 dataclass/protocol/Enum/Exception/TypedDict/ABC）
_NON_INSTANTIABLE_DECORATORS = {
    "dataclass",
    "dataclass()",
    "frozen",
    "frozen()",
    "total_ordering",
    "dataclass_json",
    "attrs",
    "define",
    "runtime_checkable",
}

_NON_INSTANTIABLE_BASES = {
    "Protocol",
    "ABC",
    "Enum",
    "IntEnum",
    "StrEnum",
    "TypedDict",
    "NamedTuple",
    "BaseModel",
    "BaseSettings",
    "Exception",
    "BaseException",
    "Error",
    "Callable",
    "Awaitable",
    "Iterable",
    "Iterator",
    "Generic",
    "TypeVar",
    # 项目特定框架/数据类基类
    "ConfigBase",
    "SQLModel",
    "_StrictManifestModel",
    "BaseDatabaseDataModel",
    "BaseMigrationProgressReporter",
    "MemoryServiceError",
    "BaseOrchestratorStrategy",
    "BaseHTTPMiddleware",
}

# 需要基于启发式排除的构造模式（类装饰器调用 vs 简单 xx() 调用）
_INSTANTIATION_RE = re.compile(r"(\w+)\s*\(")

# 间接构造识别：注册函数白名单（register(ClassName) → ClassName 被索引）
_REGISTRY_FUNCTIONS = {"register"}

# 插件目录整体排除（插件内部构造由插件运行时管理，不由主程序直接构造）
_PLUGIN_DIRS = ("plugins",)


# 检查 2：@startup_item 装饰器 — 装饰器签名 vs 调用点参数
START_ITEM_DECORATOR = "startup_item"


# 检查 3：入口函数零调用 — init_*/start_* 无生产调用点（get_* 多为查询函数非入口，不查）
ZERO_CALL_PREFIXES = ("init_", "start_")

# 检查 4：裸 except pass（多行）
EXCEPT_PASS_RE = re.compile(r"^\s*except\s+(Exception|BaseException|OSError|RuntimeError)?\s*:\s*$", re.MULTILINE)

# 检查项 5：字符串联合 "X" | None — protocols.py 回归
STRING_UNION_RE = re.compile(r'"([A-Za-z_][A-Za-z0-9_]*)"\s*\|\s*None')

# 检查项 6：api_key 完整打印
API_KEY_LEAK_RE = re.compile(r'(api_key|apikey|token|secret|password)\s*[:=]\s*["\'][^"\']{20,}')

# 检查项 8：私有属性类外访问 — self._xxx
PRIVATE_MEMBER_RE = re.compile(r"\.(_[a-zA-Z_]\w*)\s*=")


class WiringViolation:
    __slots__ = ("check_id", "file", "line", "message")

    def __init__(self, check_id: str, file: str, line: int, message: str) -> None:
        self.check_id = check_id
        self.file = file
        self.line = line
        self.message = message

    def to_dict(self) -> dict:
        return {"check": self.check_id, "file": self.file, "line": self.line, "message": self.message}


# ──────────────────────────────────────────── UI 白名单 ────────────────────────────────────────────

class WhitelistRule:
    """单条白名单规则：路径子串 + 可选函数/类名集合，命中即豁免。"""

    __slots__ = ("path_substr", "checks", "names")

    def __init__(self, path_substr: str, checks: list[str] | None = None, names: list[str] | None = None) -> None:
        self.path_substr = path_substr
        self.checks = set(checks or [])
        self.names = set(names or [])

    def matches(self, file: str, name: str | None, check_id: str) -> bool:
        # 路径分隔符归一化（Windows 反斜杠 → 正斜杠）
        file_norm = file.replace("\\", "/")
        if self.path_substr not in file_norm:
            return False
        if self.checks and check_id not in self.checks:
            return False
        if name and self.names and name not in self.names:
            return False
        return True


def _load_whitelist(path: Path) -> list[WhitelistRule]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        print(f"[n1] 白名单加载失败: {exc}", file=sys.stderr)
        return []
    rules = []
    for raw in data.get("whitelist", []):
        rules.append(
            WhitelistRule(
                path_substr=raw.get("path", ""),
                checks=raw.get("checks"),
                names=raw.get("names"),
            )
        )
    return rules


def _build_call_index(
    root: Path,
    extra_roots: list[Path] | None = None,
    stats: dict[str, int] | None = None,
) -> dict[str, set[str]]:
    """全仓库调用索引：函数/类名 → 调用文件集合。

    扫描所有 .py 文件的 AST Call 节点，构建跨文件调用索引。
    供检查 1（类构造）/检查 2/3（入口函数）跨文件比对。

    v3 精化：extra_roots 支持扫描 src/ 外的目录（如 scripts/）。
    stats（可选出参）：回填 scanned_files / call_nodes 两个计数，供空数据源断言用。
    """
    index: dict[str, set[str]] = {}
    call_nodes = 0
    # ⚠️ root_* 只数**主根**：extra_roots（scripts/）里必然一堆调用，
    # 拿"全局计数"当空数据源判据会被 scripts/ 直接喂饱 ⇒ 闸永远不响（假阴性）。
    root_call_nodes = 0
    root_scanned_files = 0
    scanned_files = 0
    scan_roots = [root]
    if extra_roots:
        scan_roots.extend(extra_roots)
    for scan_root in scan_roots:
        # ⚠️ 必须比 **resolve 后**的路径：rglob 在绝对 root 上返回绝对路径、
        # 在相对 root 上返回相对路径，而调用方可能混着传 ⇒ 直接 `==` 会悄悄判错。
        root_resolved = root.resolve()
        is_root = scan_root.resolve() == root_resolved
        for path in sorted(scan_root.rglob("*.py")):
            if ".venv" in path.parts or "__pycache__" in path.parts or ".git" in path.parts or "node_modules" in path.parts:
                continue
            scanned_files += 1
            if is_root:
                root_scanned_files += 1
            try:
                source = path.read_text(encoding="utf-8", errors="replace")
                tree = ast.parse(source)
            except (SyntaxError, UnicodeDecodeError):
                continue
            for node in ast.walk(tree):
                # 直接调用：ClassName() 或 func()
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    call_nodes += 1
                    if is_root:
                        root_call_nodes += 1
                    index.setdefault(node.func.id, set()).add(str(path))
                    # 注册函数：register(ClassName) → 索引 ClassName
                    if node.func.id in _REGISTRY_FUNCTIONS and node.args:
                        first_arg = node.args[0]
                        if isinstance(first_arg, ast.Name) and first_arg.id not in ("self", "cls"):
                            index.setdefault(first_arg.id, set()).add(str(path))
                # 属性调用：obj.method() → 索引 method（供检查 9 set_* 跨文件调用检测）
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                    call_nodes += 1
                    if is_root:
                        root_call_nodes += 1
                    index.setdefault(node.func.attr, set()).add(str(path))
                # 注册表赋值：_REGISTRY['foo'] = ClassName → 索引 ClassName
                # ⚠️ 同时认 `ast.AnnAssign`（2026-10-17 修）：注解式写法
                # `_REGISTRY['foo']: type = FooClass` 只有 AnnAssign 节点，
                # 旧版只认 Assign ⇒ 这类间接构造**整个索引不到** ⇒ 检查 1 误报
                # 零创建（或反过来，把有构造的类看漏）——"抽取器太窄"那族。
                if isinstance(node, ast.Assign):
                    for t in node.targets:
                        _index_registry_target(t, node.value, index, str(path))
                elif isinstance(node, ast.AnnAssign):
                    # AnnAssign 的 value 可能是 None（纯注解 `x: int`）——必须挡掉
                    if node.value is not None:
                        _index_registry_target(node.target, node.value, index, str(path))
    # 空数据源自检：扫了主根文件、却一个调用节点都没抽到 ⇒ 主根索引面失效，
    # 跨文件判定全都会"没查到 ⇒ 不报"（静默绿）。索引空不是"仓库没调用"，是抽取器没在看。
    if root_scanned_files > 0 and root_call_nodes == 0:
        print(
            f"[n1] 空数据源告警：主根扫了 {root_scanned_files} 个 .py，"
            "调用节点抽取为 0 条（跨文件接线判定因此全部失效）",
            file=sys.stderr,
        )
    if stats is not None:
        stats["scanned_files"] = scanned_files
        stats["call_nodes"] = call_nodes
        stats["root_call_nodes"] = root_call_nodes
        stats["root_scanned_files"] = root_scanned_files
    return index


def _index_registry_target(
    target: ast.AST, value: ast.AST, index: dict[str, set[str]], path_str: str,
) -> None:
    """把 `TARGET[...] = ClassName` 里的 ClassName 记进调用索引。

    供 `ast.Assign` / `ast.AnnAssign` 两种赋值共用（注解式写法越来越多，
    抽取器只认一种就会静默漏掉另一种）。
    """
    if not (isinstance(target, ast.Subscript) and isinstance(target.value, ast.Name)):
        return
    if isinstance(value, ast.Name) and value.id not in ("self", "cls"):
        index.setdefault(value.id, set()).add(path_str)


def _scan_file(
    path: Path,
    checks: set[str],
    whitelist: list[WhitelistRule],
    call_index: dict[str, set[str]] | None = None,
) -> list[WiringViolation]:
    """扫描单文件，返回违反列表。"""
    violations = []
    source = path.read_text(encoding="utf-8", errors="replace")

    def _whitelisted(check_id: str, name: str | None, line: int) -> bool:
        return any(rule.matches(str(path), name, check_id) for rule in whitelist)

    # ── 检查 1：零创建点（类定义 vs 构造调用） ──────
    if "1" in checks:
        _scan_class_check(source, path, violations, _whitelisted, call_index)

    # ── 检查 2：@startup_item 装饰器反向验证 ──────
    if "2" in checks:
        _check_startup_decorator(source, path, violations, _whitelisted, call_index)

    # ── 检查 3：入口零调用（init_*/get_*/start_*） ──────
    if "3" in checks:
        _check_entry_zero_calls(source, path, violations, _whitelisted, call_index)

    # ── 检查 4：裸 except pass ──────────
    if "4" in checks:
        _check_except_pass(source, path, violations, _whitelisted)

    # ── 检查 5：字符串联合 "X" | None ──────
    if "5" in checks:
        _check_string_union(source, path, violations, _whitelisted)

    # ── 检查 6：api_key 完整打印 ──────
    if "6" in checks:
        _check_api_key(source, path, violations, _whitelisted)

    # ── 检查 7：import logging 缺失（模块用 print 不用 log） ──────
    if "7" in checks:
        _check_missing_logging(source, path, violations, _whitelisted)

    # ── 检查 8：私有属性类外访问 ──────
    if "8" in checks:
        _check_private_access(source, path, violations, _whitelisted)

    # ── 检查 9：set_* 配置注入点零调用（功能静默禁用） ──────
    if "9" in checks:
        _check_setter_zero_call(source, path, violations, _whitelisted, call_index)

    return violations


def _check_startup_decorator(source: str, path: Path, violations: list, whitelisted, call_index=None) -> None:
    """检查 2：反向验证 — 入口函数有生产调用点但缺 @startup_item 装饰器 = 接线违规。

    v3 增强：跨文件调用搜索——跨文件有调用视为有生产接线，不报。
    正向（装饰器存在但无调用点）由检查 3 覆盖。
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return
    # 先收集本文件所有顶层函数名 + 是否有 @startup_item
    func_has_decorator: dict[str, bool] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            deco_names = {ast.unparse(d).split("(")[0] for d in node.decorator_list}
            func_has_decorator[node.name] = START_ITEM_DECORATOR in deco_names
    # 收集本文件所有 Call 的被调函数名
    called_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            called_names.add(node.func.id)
    # 反向：函数被调用 + 名字像入口 + 无 @startup_item → 候选违规
    for name, has_deco in func_has_decorator.items():
        if has_deco:
            continue
        if not name.startswith(("init_", "start_")):
            continue
        if name not in called_names:
            continue
        # v3：跨文件有调用 → 有生产接线 → 不报
        if call_index and name in call_index:
            continue
        if whitelisted("2", name, 0):
            continue
        # 找到函数定义行号
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
                violations.append(
                    WiringViolation("2", str(path), node.lineno, f"入口有生产调用点但缺 @startup_item: {name}")
                )
                break


def _check_missing_logging(source: str, path: Path, violations: list, whitelisted) -> None:
    """检查 7：模块用 print 调试但缺 import logging（启发式，需人工复核）。"""
    if "import logging" in source or "from logging" in source or "getLogger" in source:
        return
    # 仅当文件含 print( 且看起来是模块（>50 行）才报
    if "print(" not in source:
        return
    line_count = source.count("\n")
    if line_count < 50:
        return
    if whitelisted("7", None, 0):
        return
    # 找第一个 print( 行号
    for line_no, line in enumerate(source.splitlines(), 1):
        if "print(" in line:
            violations.append(WiringViolation("7", str(path), line_no, f"模块用 print 但缺 import logging ({line_count} 行)"))
            break


def _check_private_access(source: str, path: Path, violations: list, whitelisted) -> None:
    """检查 8：私有属性类外访问（启发式，需人工复核）。

    匹配 `. _xxx =` 模式（类外赋值私有属性），排除 self._xxx / cls._xxx。
    """
    for line_no, line in enumerate(source.splitlines(), 1):
        for m in PRIVATE_MEMBER_RE.finditer(line):
            prefix = line[: m.start()]
            # 排除 self._xxx / cls._xxx / type._xxx 等合法类内访问
            if prefix.rstrip().endswith(("self", "cls", "type", "this")):
                continue
            attr = m.group(1)
            if whitelisted("8", attr, line_no):
                continue
            violations.append(WiringViolation("8", str(path), line_no, f"私有属性类外访问候选: {attr}"))
            break  # 每行只报一次


def _scan_class_check(source, path, violations, whitelisted, call_index=None):
    """检查 1/3：类定义 vs 构造调用（零创建点）。

    v3 增强：跨文件构造调用检查——类名在 call_index 中（全仓库有构造调用）则不报。
    v3 精化：plugins/ 目录整体排除（插件内部构造由插件运行时管理）。
    """
    # plugins/ 目录整体排除
    path_norm = str(path).replace("\\", "/")
    if any(f"/{d}/" in path_norm for d in _PLUGIN_DIRS):
        return
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        class_name = node.name
        if node.decorator_list:
            deco_names = {ast.unparse(d).split("(")[0] for d in node.decorator_list}
            if deco_names & _NON_INSTANTIABLE_DECORATORS:
                continue
        # v3 精化：基类检查扩展为同时解析 ast.Attribute 末段（如 pydantic.BaseModel → "BaseModel"）
        # v3 精化：ast.Subscript 泛型基类（如 BaseDatabaseDataModel[T] → "BaseDatabaseDataModel"）
        base_names: set[str] = set()
        for b in node.bases:
            if isinstance(b, ast.Name):
                base_names.add(b.id)
            elif isinstance(b, ast.Attribute):
                base_names.add(b.attr)
            elif isinstance(b, ast.Subscript):
                if isinstance(b.value, ast.Name):
                    base_names.add(b.value.id)
                elif isinstance(b.value, ast.Attribute):
                    base_names.add(b.value.attr)
        if base_names & _NON_INSTANTIABLE_BASES:
            continue
        # v3：跨文件构造调用检查——有调用则不报
        if call_index and class_name in call_index:
            continue
        if not whitelisted("1", None, 0):
            violations.append(WiringViolation("1", str(path), node.lineno, f"零创建候选类: {class_name}"))

def _check_except_pass(source: str, path: Path, violations: list, whitelisted) -> None:
    """检查 4：裸 except: pass（AST 精确解析 + 全国 grep 增强）。"""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Try):
            for handler in node.handlers:
                if handler.type is None and handler.body:
                    only_pass = (len(handler.body) == 1 and isinstance(handler.body[0], ast.Pass))
                    if only_pass:
                        name = ""
                        if not whitelisted("4", None, 0):
                            violations.append(WiringViolation("4", str(path), node.lineno, "裸 except: pass"))
                    else:
                        # except Exception: pass 带异常类型但吞掉 —— 降级不报（B29 10 处为裸 except 已单独计）
                        pass

def _check_entry_zero_calls(source: str, path: Path, violations: list, whitelisted, call_index=None) -> None:
    """检查 3：入口函数零调用（init_*/get_*/start_* 无生产调用）。

    v3 增强：跨文件调用搜索——跨文件有调用则不报（有生产调用点）。
    """
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for deco in node.decorator_list:
                if isinstance(deco, ast.Name) and deco.id == START_ITEM_DECORATOR:
                    break
            else:
                name = node.name
                if name.startswith(("init_", "start_")):
                    # v3：跨文件有调用 → 有生产调用点 → 不报
                    if call_index and name in call_index:
                        continue
                    if not whitelisted("3", name, 0):
                        violations.append(WiringViolation("3", str(path), node.lineno, f"入口零调用候选: {name}"))

def _check_string_union(source: str, path: Path, violations: list, whitelisted) -> None:
    """检查5：`"X" | None` 字符串联合模式（grep 快速层）。"""
    for line_no, line in enumerate(source.splitlines(), 1):
        m = STRING_UNION_RE.search(line)
        if m and not whitelisted("5", m.group(1), 0):
            violations.append(WiringViolation("5", str(path), line_no, f"字符串联合: {m.group(1)!r} | None"))

def _check_api_key(source: str, path: Path, violations: list, whitelisted) -> None:
    """检查6：api_key 完整打印泄漏。"""
    for line_no, line in enumerate(source.splitlines(), 1):
        m = API_KEY_LEAK_RE.search(line)
        if m and not whitelisted("6", m.group(1), 0):
            violations.append(WiringViolation("6", str(path), line_no, f"api_key 泄漏: {m.group(1)!r}"))


# 检查项 9：set_* 配置注入点零调用 — docstring 声明注入但零生产调用点
_SETTER_INJECTION_KEYWORDS = ("由 main.py 调用", "注入", "配置注入", "inject", "inject by main.py")


def _check_setter_zero_call(source: str, path: Path, violations: list, whitelisted, call_index=None) -> None:
    """检查 9：set_* 配置注入点零调用（功能静默禁用）。

    扫描 set_* 前缀方法定义，检查 docstring 是否含注入声明（"由 main.py 调用"/"注入"/"配置"），
    复用 call_index 查跨文件调用，排除测试文件引用，零生产调用则报。
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        name = node.name
        if not name.startswith("set_"):
            continue
        docstring = ast.get_docstring(node) or ""
        if not any(kw in docstring for kw in _SETTER_INJECTION_KEYWORDS):
            continue
        if call_index and name in call_index:
            non_test_callers = {f for f in call_index[name] if "test_" not in Path(f).name}
            if non_test_callers:
                continue
        if whitelisted("9", name, 0):
            continue
        violations.append(
            WiringViolation("9", str(path), node.lineno, f"set_* 配置注入点零调用: {name}（docstring 声明注入但零生产调用点）")
        )


def _scan_dir(root: Path, checks: set[str], whitelist: list) -> list[WiringViolation]:
    """扫描目录，聚合所有违反项。"""
    # v3 精化：构建跨文件调用索引，extra_roots 覆盖 scripts/
    call_index = _build_call_index(root, extra_roots=[Path("scripts")]) if (checks & {"1", "2", "3", "9"}) else None
    all_violations = []
    for path in sorted(root.rglob("*.py")):
        if ".venv" in path.parts or "__pycache__" in path.parts or ".git" in path.parts:
            continue
        try:
            all_violations.extend(_scan_file(path, checks, whitelist, call_index))
        except (SyntaxError, UnicodeDecodeError) as exc:
            print(f"[n1] 分析跳过 {path}: {exc}", file=sys.stderr)
    return all_violations


def _dedup(vc: list[WiringViolation]) -> list[WiringViolation]:
    """按 (file, line, check, message) 去重。"""
    seen = set()
    result = []
    for x in vc:
        key = (str(x.file), x.line, x.check_id, x.message)
        if key not in seen:
            seen.add(key)
            result.append(x)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="N1 反射接线检查器")
    parser.add_argument("--scan", nargs="+", default=["src"], help="扫描目录")
    parser.add_argument("--engine", choices=("auto", "rg", "py"), default="auto")
    parser.add_argument("--whitelist", default="scripts/.n1_whitelist.json", help="白名单文件路径")
    parser.add_argument("--ci", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="空数据源断言：扫了 .py 却没抽到任何调用节点即 exit(1)",
    )
    args = parser.parse_args()

    whitelist = _load_whitelist(Path(args.whitelist))

    checks = {"1", "2", "3", "4", "5", "6", "7", "8"}
    # 默认检查项：可用性稳定的静态检查项（后续版本扩展全量项）
    # 非 CI：只开精确度高的检查 2/4/5/6（装饰器反向/裸except/字符串联合/api_key）
    # CI：开全部 8 项（含启发式检查 1/3/7/8，需人工复核）
    checks = {"2", "4", "5", "6"} if not args.ci else {"1", "2", "3", "4", "5", "6", "7", "8", "9"}

    violations = []
    file_total = 0
    empty_index_roots: list[str] = []
    for scan in args.scan:
        root = Path(scan)
        if not root.exists():
            print(f"[n1] 扫描目录不存在: {root}", file=sys.stderr)
            return 1
        violations.extend(_scan_dir(root, checks, whitelist))
        file_total += len(list(root.rglob("*.py")))
        if args.strict:
            stats: dict[str, int] = {}
            _build_call_index(root, extra_roots=[Path("scripts")], stats=stats)
            if stats.get("root_scanned_files", 0) > 0 and stats.get("root_call_nodes", 0) == 0:
                empty_index_roots.append(str(root))
                print(
                    f"[n1] 空数据源：{root} 主根扫了 {stats['root_scanned_files']} 个 .py，"
                    "调用节点 0 条",
                    file=sys.stderr,
                )

    violations = _dedup(violations)

    if args.json:
        print(json.dumps([v.to_dict() for v in violations], ensure_ascii=False, indent=2))
    else:
        for v in violations:
            print(f"[N1·{v.check_id}] {v.file}:{v.line}: {v.message}")
        if args.ci and violations:
            print(f"[n1] 接线检查失败：{len(violations)} 个违反", file=sys.stderr)
            return 1
        if args.strict and empty_index_roots:
            print("[n1] 接线检查失败：调用索引为空（抽取器没在看 ≠ 接线正常）", file=sys.stderr)
            return 1
        print(f"[n1] 接线检查通过：{len(violations)} 个违反 / 仓库扫描 {file_total} 个文件")

    return 0


if __name__ == "__main__":
    sys.exit(main())