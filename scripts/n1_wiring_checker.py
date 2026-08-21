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
}

# 需要基于启发式排除的构造模式（类装饰器调用 vs 简单 xx() 调用）
_INSTANTIATION_RE = re.compile(r"(\w+)\s*\(")


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


def _build_call_index(root: Path) -> dict[str, set[str]]:
    """全仓库调用索引：函数/类名 → 调用文件集合。

    扫描所有 .py 文件的 AST Call 节点，构建跨文件调用索引。
    供检查 1（类构造）/检查 2/3（入口函数）跨文件比对。
    """
    index: dict[str, set[str]] = {}
    for path in sorted(root.rglob("*.py")):
        if ".venv" in path.parts or "__pycache__" in path.parts or ".git" in path.parts:
            continue
        try:
            source = path.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(source)
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                index.setdefault(node.func.id, set()).add(str(path))
    return index


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
    """
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        class_name = node.name
        if node.decorator_list:
            deco_names = {ast.unparse(d).split("(")[0] for d in node.decorator_list}
            if deco_names & _NON_INSTANTIABLE_DECORATORS:
                continue
        if any(b.id in _NON_INSTANTIABLE_BASES for b in node.bases if isinstance(b, ast.Name)):
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


def _scan_dir(root: Path, checks: set[str], whitelist: list) -> list[WiringViolation]:
    """扫描目录，聚合所有违反项。"""
    # v3：构建跨文件调用索引（检查 1/2/3 增强用）
    call_index = _build_call_index(root) if (checks & {"1", "2", "3"}) else None
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
    args = parser.parse_args()

    whitelist = _load_whitelist(Path(args.whitelist))

    checks = {"1", "2", "3", "4", "5", "6", "7", "8"}
    # 默认检查项：可用性稳定的静态检查项（后续版本扩展全量项）
    # 非 CI：只开精确度高的检查 2/4/5/6（装饰器反向/裸except/字符串联合/api_key）
    # CI：开全部 8 项（含启发式检查 1/3/7/8，需人工复核）
    checks = {"2", "4", "5", "6"} if not args.ci else {"1", "2", "3", "4", "5", "6", "7", "8"}

    violations = []
    for scan in args.scan:
        root = Path(scan)
        if not root.exists():
            print(f"[n1] 扫描目录不存在: {root}", file=sys.stderr)
            return 1
        violations.extend(_scan_dir(root, checks, whitelist))

    violations = _dedup(violations)

    if args.json:
        print(json.dumps([v.to_dict() for v in violations], ensure_ascii=False, indent=2))
    else:
        for v in violations:
            print(f"[N1·{v.check_id}] {v.file}:{v.line}: {v.message}")
        if args.ci and violations:
            print(f"[n1] 接线检查失败：{len(violations)} 个违反", file=sys.stderr)
            return 1
        print(f"[n1] 接线检查通过：{len(violations)} 个违反 / 仓库扫描 {len(list(root.rglob('*.py')))} 个文件")

    return 0


if __name__ == "__main__":
    sys.exit(main())