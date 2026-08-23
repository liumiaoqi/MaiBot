#!/usr/bin/env python3
"""ZG-N4 安全门禁检查器 — WebUI 路由安全静态 AST 扫描。

检查 5 类安全模式（认证缺失/SSRF/XFF 伪造/信息泄露/api_key 空切片），输出 JSON 报告。
CI 模式：发现 P0 违反即 exit(1) 拦截；P1 候选仅报告不阻断。

用法：
    n4_security_checker.py [--scan src/webui/routers [--scan ...]]
                           [--whitelist whitelist.json] [--ci] [--json]
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path

# ───────────────────────────── 检查项 N4-1~5 ─────────────────────────────

# 认证函数名（端点函数体内调用即视为有认证）
_AUTH_CALL_NAMES = {"require_auth", "require_plugin_token", "verify_auth_token", "verify_auth_token_from_cookie"}

# 认证依赖名（router 级 dependencies=[Depends(xxx)] 即视为有认证）
_AUTH_DEPEND_NAMES = {"require_auth", "require_plugin_token", "verify_auth_token"}

# 外部 HTTP 请求模块/方法（SSRF 候选）
_HTTP_CLIENT_ATTRS = {"get", "post", "put", "delete", "patch", "head", "request"}

# X-Forwarded-For 头名变体
_XFF_KEYS = {"x-forwarded-for", "x_forwarded_for", "X-Forwarded-For"}


class SecurityViolation:
    __slots__ = ("check_id", "file", "line", "message", "severity", "whitelisted")

    def __init__(
        self,
        check_id: str,
        file: str,
        line: int,
        message: str,
        severity: str = "P1",
        whitelisted: bool = False,
    ) -> None:
        self.check_id = check_id
        self.file = file
        self.line = line
        self.message = message
        self.severity = severity
        self.whitelisted = whitelisted

    def to_dict(self) -> dict:
        return {
            "check": self.check_id,
            "file": self.file,
            "line": self.line,
            "message": self.message,
            "severity": self.severity,
            "whitelisted": self.whitelisted,
        }


# ──────────────────────────────────────────── 白名单 ────────────────────────────────────────────

class WhitelistRule:
    """单条白名单规则：路径子串 + 可选检查/函数名集合 + _reason，命中即豁免。"""

    __slots__ = ("path_substr", "checks", "names", "reason")

    def __init__(
        self,
        path_substr: str,
        checks: list[str] | None = None,
        names: list[str] | None = None,
        reason: str = "",
    ) -> None:
        self.path_substr = path_substr
        self.checks = set(checks or [])
        self.names = set(names or [])
        self.reason = reason

    def matches(self, file: str, name: str | None, check_id: str) -> bool:
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
        print(f"[n4] 白名单加载失败: {exc}", file=sys.stderr)
        return []
    rules = []
    for raw in data.get("whitelist", []):
        rules.append(
            WhitelistRule(
                path_substr=raw.get("path", ""),
                checks=raw.get("checks"),
                names=raw.get("names"),
                reason=raw.get("_reason", ""),
            )
        )
    return rules


# ──────────────────────────────────────────── AST 辅助 ────────────────────────────────────────────

def _get_call_name(node: ast.Call) -> str:
    """提取 Call 节点的函数名（支持 require_auth / obj.method 等形式，返回末段名）。"""
    f = node.func
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute):
        return f.attr
    return ""


def _get_kwarg_names(call: ast.Call) -> set[str]:
    """提取 Call 节点的关键字参数名集合。"""
    return {kw.arg for kw in call.keywords if kw.arg}


def _find_router_defs(tree: ast.AST) -> list[tuple[ast.Call, int]]:
    """找所有 APIRouter(...) 调用，返回 (call_node, lineno) 列表。"""
    result = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for val in [node.value]:
                if isinstance(val, ast.Call) and _get_call_name(val) == "APIRouter":
                    result.append((val, node.lineno))
    return result


def _router_has_auth(router_call: ast.Call) -> bool:
    """检查 APIRouter() 调用是否含 dependencies=[Depends(require_auth)] 等认证依赖。"""
    for kw in router_call.keywords:
        if kw.arg == "dependencies" and isinstance(kw.value, ast.List):
            for elt in kw.value.elts:
                if isinstance(elt, ast.Call) and _get_call_name(elt) == "Depends":
                    for arg in elt.args:
                        if isinstance(arg, ast.Name) and arg.id in _AUTH_DEPEND_NAMES:
                            return True
                        if isinstance(arg, ast.Attribute) and arg.attr in _AUTH_DEPEND_NAMES:
                            return True
    return False


def _find_endpoint_funcs(tree: ast.AST) -> list[tuple[str, ast.FunctionDef | ast.AsyncFunctionDef]]:
    """找所有路由端点函数（@router.get/post/... 装饰），返回 (http_method, func_node) 列表。"""
    endpoints = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for deco in node.decorator_list:
                if isinstance(deco, ast.Call):
                    name = _get_call_name(deco)
                    if name in {"get", "post", "put", "delete", "patch", "head", "websocket"}:
                        endpoints.append((name, node))
                        break
                if isinstance(deco, ast.Attribute):
                    if deco.attr in {"get", "post", "put", "delete", "patch", "head", "websocket"}:
                        endpoints.append((deco.attr, node))
                        break
    return endpoints


def _func_body_has_auth_call(func: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """检查端点函数体是否含 require_plugin_token/verify_auth_token 等认证调用。"""
    for node in ast.walk(func):
        if isinstance(node, ast.Call):
            if _get_call_name(node) in _AUTH_CALL_NAMES:
                return True
    return False


def _func_has_url_param(func: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """检查端点函数是否有 url/URL 参数（SSRF 候选）。"""
    for arg in func.args.args:
        if arg.arg in {"url", "URL", "target_url", "endpoint", "uri"}:
            return True
    return False


def _func_body_has_http_call(func: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """检查函数体是否含 requests.get/post、httpx.get/post、client.get/post 等外部 HTTP 调用。"""
    for node in ast.walk(func):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute) and node.func.attr in _HTTP_CLIENT_ATTRS:
                # requests.get / httpx.post / session.get 等
                if isinstance(node.func.value, ast.Name) and node.func.value.id in {"requests", "httpx", "aiohttp"}:
                    return True
                # client.get / session.post 等（属性链）
                return True
    return False


def _func_body_has_allowlist(func: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """启发式检查函数体是否有 allowlist/whitelist/URL 校验（有则不报 SSRF）。"""
    _allowlist_names = {"allowlist", "whitelist", "ALLOWLIST", "WHITELIST", "safe_hosts", "SAFE_HOSTS"}
    _url_check_funcs = {"is_safe_url", "validate_url", "check_url", "is_allowed_host"}
    for node in ast.walk(func):
        if isinstance(node, ast.Name) and (node.id in _allowlist_names or node.id in _url_check_funcs):
            return True
        if isinstance(node, ast.Attribute) and node.attr in _url_check_funcs:
            return True
    return False


def _func_body_has_xff(func: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """检查函数体是否读取 X-Forwarded-For 头（用于限流/鉴权 = XFF 伪造风险）。"""
    for node in ast.walk(func):
        # request.headers["X-Forwarded-For"] 或 request.headers.get("X-Forwarded-For")
        if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Attribute):
            if node.value.attr == "headers":
                if isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str):
                    if node.slice.value.lower() in _XFF_KEYS:
                        return True
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "get" and isinstance(node.func.value, ast.Attribute):
                if node.func.value.attr == "headers":
                    for arg in node.args:
                        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                            if arg.value.lower() in _XFF_KEYS:
                                return True
    return False


def _func_body_has_info_leak(func: ast.FunctionDef | ast.AsyncFunctionDef) -> list[int]:
    """检查 except handler 是否含 HTTPException(detail=str(e)) 或 return dict 含 str(e)。

    返回违反行号列表。
    """
    leak_lines = []
    for node in ast.walk(func):
        if isinstance(node, ast.Try):
            for handler in node.handlers:
                for body_node in ast.walk(handler):
                    if isinstance(body_node, ast.Call) and _get_call_name(body_node) == "HTTPException":
                        for kw in body_node.keywords:
                            if kw.arg == "detail":
                                if _expr_contains_str_of_exception(kw.value):
                                    leak_lines.append(body_node.lineno)
                    if isinstance(body_node, ast.Return) and isinstance(body_node.value, ast.Dict):
                        for v in body_node.value.values:
                            if _expr_contains_str_of_exception(v):
                                leak_lines.append(body_node.lineno)
    return leak_lines


def _expr_contains_str_of_exception(expr: ast.AST) -> bool:
    """检查表达式是否含 str(e)/f"...{e}..."/e.args 等异常信息泄露。"""
    for node in ast.walk(expr):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "str":
            for arg in node.args:
                if isinstance(arg, ast.Name) and arg.id in {"e", "exc", "err", "error", "exception"}:
                    return True
        if isinstance(node, ast.FormattedValue):
            if isinstance(node.value, ast.Name) and node.value.id in {"e", "exc", "err", "error", "exception"}:
                return True
    return False


def _find_apikey_slices(source: str) -> list[tuple[int, str]]:
    """找 api_key[:N] 切片行（grep 快速层），返回 (line_no, line_text) 列表。"""
    import re
    pattern = re.compile(r"\b(api_key|apikey|token|secret)\s*\[\s*:")
    result = []
    for line_no, line in enumerate(source.splitlines(), 1):
        if pattern.search(line):
            result.append((line_no, line))
    return result


def _line_has_length_guard(source_lines: list[str], slice_line_no: int) -> bool:
    """启发式检查切片行前 5 行是否有 if api_key / api_key or "" / len(api_key) 长度判断。"""
    import re
    start = max(0, slice_line_no - 6)
    for line in source_lines[start:slice_line_no - 1]:
        if re.search(r"\bif\s+(not\s+)?(api_key|apikey|token|secret)\b", line):
            return True
        if re.search(r"\b(api_key|apikey|token|secret)\s+or\s+", line):
            return True
        if re.search(r"\blen\s*\(\s*(api_key|apikey|token|secret)", line):
            return True
    return False


# ──────────────────────────────────────────── 5 类检查 ────────────────────────────────────────────

def _check_no_auth(source: str, path: Path, violations: list, whitelisted) -> None:
    """检查 N4-1：端点无认证（router 级无 dependencies + 端点函数体无认证调用 = P0）。"""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return
    routers = _find_router_defs(tree)
    if not routers:
        return
    # 任一 router 有认证则视为全文件有 router 级认证（保守不报）
    any_router_auth = any(_router_has_auth(rc) for rc, _ in routers)
    if any_router_auth:
        return
    endpoints = _find_endpoint_funcs(tree)
    for method, func in endpoints:
        if _func_body_has_auth_call(func):
            continue
        if whitelisted("n4-no-auth", func.name, func.lineno):
            continue
        violations.append(
            SecurityViolation(
                "n4-no-auth",
                str(path),
                func.lineno,
                f"端点无认证: {method} {func.name}（router 级无 dependencies + 函数体无认证调用）",
                severity="P0",
            )
        )


def _check_ssrf(source: str, path: Path, violations: list, whitelisted) -> None:
    """检查 N4-2：SSRF 候选（端点有 url 参数 + 函数体有外部 HTTP 调用 + 无 allowlist 校验 = P1）。"""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return
    endpoints = _find_endpoint_funcs(tree)
    for method, func in endpoints:
        if not _func_has_url_param(func):
            continue
        if not _func_body_has_http_call(func):
            continue
        if _func_body_has_allowlist(func):
            continue
        if whitelisted("n4-ssrf", func.name, func.lineno):
            continue
        violations.append(
            SecurityViolation(
                "n4-ssrf",
                str(path),
                func.lineno,
                f"SSRF 候选: {method} {func.name}（url 参数 + 外部 HTTP 调用 + 无 allowlist 校验）",
                severity="P1",
            )
        )


def _check_xff(source: str, path: Path, violations: list, whitelisted) -> None:
    """检查 N4-3：X-Forwarded-For 伪造风险（端点函数体读 XFF 用于限流/鉴权 = P1）。"""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return
    endpoints = _find_endpoint_funcs(tree)
    for method, func in endpoints:
        if not _func_body_has_xff(func):
            continue
        if whitelisted("n4-xff", func.name, func.lineno):
            continue
        violations.append(
            SecurityViolation(
                "n4-xff",
                str(path),
                func.lineno,
                f"XFF 伪造风险: {method} {func.name}（读 X-Forwarded-For 用于限流/鉴权）",
                severity="P1",
            )
        )


def _check_info_leak(source: str, path: Path, violations: list, whitelisted) -> None:
    """检查 N4-4：异常信息泄露（except handler 含 HTTPException(detail=str(e)) 或 return dict 含 str(e) = P1）。"""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return
    endpoints = _find_endpoint_funcs(tree)
    for method, func in endpoints:
        leak_lines = _func_body_has_info_leak(func)
        for line in leak_lines:
            if whitelisted("n4-info-leak", func.name, line):
                continue
            violations.append(
                SecurityViolation(
                    "n4-info-leak",
                    str(path),
                    line,
                    f"异常信息泄露: {method} {func.name}（except handler 含 str(e)/f'...{{e}}'）",
                    severity="P1",
                )
            )


def _check_apikey_empty(source: str, path: Path, violations: list, whitelisted) -> None:
    """检查 N4-5：api_key 空切片（api_key[:N] 前无长度判断 = P1）。"""
    slices = _find_apikey_slices(source)
    if not slices:
        return
    source_lines = source.splitlines()
    for line_no, line_text in slices:
        if _line_has_length_guard(source_lines, line_no):
            continue
        if whitelisted("n4-apikey-empty", None, line_no):
            continue
        violations.append(
            SecurityViolation(
                "n4-apikey-empty",
                str(path),
                line_no,
                f"api_key 空切片候选: {line_text.strip()}（前无长度判断）",
                severity="P1",
            )
        )


# ──────────────────────────────────────────── 扫描分发 ────────────────────────────────────────────

_CHECK_MAP = {
    "n4-no-auth": _check_no_auth,
    "n4-ssrf": _check_ssrf,
    "n4-xff": _check_xff,
    "n4-info-leak": _check_info_leak,
    "n4-apikey-empty": _check_apikey_empty,
}

_ALL_CHECKS = set(_CHECK_MAP.keys())


def _scan_file_n4(
    path: Path,
    checks: set[str],
    whitelist: list[WhitelistRule],
) -> list[SecurityViolation]:
    """扫描单文件，返回安全违反列表。"""
    violations: list[SecurityViolation] = []
    source = path.read_text(encoding="utf-8", errors="replace")

    def _whitelisted(check_id: str, name: str | None, line: int) -> bool:
        return any(rule.matches(str(path), name, check_id) for rule in whitelist)

    for check_id in checks:
        if check_id in _CHECK_MAP:
            _CHECK_MAP[check_id](source, path, violations, _whitelisted)
    return violations


def _scan_dir(root: Path, checks: set[str], whitelist: list[WhitelistRule]) -> list[SecurityViolation]:
    """扫描目录，聚合所有安全违反项。"""
    all_violations = []
    for path in sorted(root.rglob("*.py")):
        if ".venv" in path.parts or "__pycache__" in path.parts or ".git" in path.parts:
            continue
        try:
            all_violations.extend(_scan_file_n4(path, checks, whitelist))
        except (SyntaxError, UnicodeDecodeError) as exc:
            print(f"[n4] 分析跳过 {path}: {exc}", file=sys.stderr)
    return all_violations


def _dedup(vc: list[SecurityViolation]) -> list[SecurityViolation]:
    """按 (file, line, check, message) 去重。"""
    seen = set()
    result = []
    for x in vc:
        key = (str(x.file), x.line, x.check_id, x.message)
        if key not in seen:
            seen.add(key)
            result.append(x)
    return result


# ──────────────────────────────────────────── CLI 入口 ────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="N4 安全门禁检查器")
    parser.add_argument("--scan", nargs="+", default=["src/webui/routers"], help="扫描目录")
    parser.add_argument("--whitelist", default="scripts/.n4_whitelist.json", help="白名单文件路径")
    parser.add_argument("--ci", action="store_true", help="CI 模式：P0 违反即 exit(1)")
    parser.add_argument("--json", action="store_true", help="JSON 报告输出")
    args = parser.parse_args()

    whitelist = _load_whitelist(Path(args.whitelist))
    checks = _ALL_CHECKS

    violations = []
    for scan in args.scan:
        root = Path(scan)
        if not root.exists():
            print(f"[n4] 扫描目录不存在: {root}", file=sys.stderr)
            return 1
        violations.extend(_scan_dir(root, checks, whitelist))

    violations = _dedup(violations)

    if args.json:
        print(json.dumps([v.to_dict() for v in violations], ensure_ascii=False, indent=2))
    else:
        for v in violations:
            print(f"[N4·{v.check_id}|{v.severity}] {v.file}:{v.line}: {v.message}")
        p0_count = sum(1 for v in violations if v.severity == "P0")
        p1_count = sum(1 for v in violations if v.severity == "P1")
        if args.ci and p0_count > 0:
            print(f"[n4] 安全门禁失败：{p0_count} 个 P0 违反 + {p1_count} 个 P1 候选", file=sys.stderr)
            return 1
        print(f"[n4] 安全门禁通过：{p0_count} 个 P0 + {p1_count} 个 P1 候选 / 扫描 {len(list(root.rglob('*.py')))} 个文件")

    return 0


if __name__ == "__main__":
    sys.exit(main())