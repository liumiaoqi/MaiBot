#!/usr/bin/env python3
"""ZG-N1 检查 1 候选复核脚本 — 自动分类 + 按域分批 + 报告生成。

调用精化后的 N1 检查器获取候选清单，自动分类（框架类/间接构造/启动脚本/真死代码/待定），
按域分批产出分类报告，可选更新白名单。

用法：
    n1_candidates_review.py --scan src --output <report.md>
                             [--domain core|webui|maisaka|A_memorix|plugin|other]
                             [--update-whitelist <whitelist.json>]
"""

import argparse
import ast
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path


# 域定义：路径子串 → 域名
_DOMAIN_RULES = (
    ("src/core/", "core"),
    ("src/webui/", "webui"),
    ("src/maisaka/", "maisaka"),
    ("src/A_memorix/", "A_memorix"),
    ("plugins/", "plugin"),
)

# 框架类排除规则（与 n1_wiring_checker 保持一致，复核时再查一次）
_FRAMEWORK_DECORATORS = {
    "dataclass", "dataclass()", "frozen", "frozen()", "total_ordering",
    "dataclass_json", "attrs", "define", "runtime_checkable",
}
_FRAMEWORK_BASES = {
    "Protocol", "ABC", "Enum", "IntEnum", "StrEnum", "TypedDict", "NamedTuple",
    "BaseModel", "BaseSettings", "Exception", "BaseException", "Error",
    "Callable", "Awaitable", "Iterable", "Iterator", "Generic", "TypeVar",
}

# 注册表模式：register(ClassName) / _REGISTRY['x'] = ClassName
_REGISTRY_FUNC_RE = re.compile(r"\bregister\s*\(\s*(\w+)\s*\)")
_REGISTRY_ASSIGN_RE = re.compile(r"=\s*(\w+)\s*$")


class CandidateReview:
    """候选复核记录。"""

    __slots__ = ("class_name", "file", "line", "domain", "label", "reason")

    def __init__(self, class_name: str, file: str, line: int) -> None:
        self.class_name = class_name
        self.file = file
        self.line = line
        self.domain = _domain_of(file)
        self.label = ""
        self.reason = ""


def _domain_of(file: str) -> str:
    """按定义位置路径判断所属域。"""
    f = file.replace("\\", "/")
    for substr, domain in _DOMAIN_RULES:
        if substr in f:
            return domain
    return "other"


def _get_candidates(scan_root: str, repo_root: Path) -> list[CandidateReview]:
    """调用 n1_wiring_checker 获取检查 1 候选清单。"""
    checker = repo_root / "scripts" / "n1_wiring_checker.py"
    result = subprocess.run(
        [sys.executable, str(checker), "--scan", scan_root, "--ci", "--json"],
        capture_output=True, text=True, encoding="utf-8", cwd=str(repo_root),
    )
    if result.returncode != 0 and not result.stdout.strip():
        print(f"[review] N1 检查器执行失败: {result.stderr}", file=sys.stderr)
        return []
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        print(f"[review] JSON 解析失败: {exc}", file=sys.stderr)
        return []
    candidates = []
    for v in data:
        if v.get("check") != "1":
            continue
        msg = v.get("message", "")
        m = re.search(r"零创建候选类:\s*(\w+)", msg)
        class_name = m.group(1) if m else ""
        candidates.append(CandidateReview(class_name, v["file"], v["line"]))
    return candidates


def _load_all_sources(repo_root: Path) -> dict[str, str]:
    """加载全仓库 .py 文件内容，返回 {路径: 源码}。"""
    sources = {}
    skip = {".venv", "__pycache__", ".git", "node_modules", ".pytest_cache"}
    for path in sorted(repo_root.rglob("*.py")):
        if any(p in path.parts for p in skip):
            continue
        try:
            sources[str(path)] = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
    return sources


def _check_framework_class(source: str, class_name: str) -> str | None:
    """查基类/装饰器是否命中排除规则，命中则返回依据字符串。"""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef) or node.name != class_name:
            continue
        if node.decorator_list:
            deco_names = {ast.unparse(d).split("(")[0] for d in node.decorator_list}
            hit = deco_names & _FRAMEWORK_DECORATORS
            if hit:
                return f"装饰器 {hit}"
        base_names = set()
        for b in node.bases:
            if isinstance(b, ast.Name):
                base_names.add(b.id)
            elif isinstance(b, ast.Attribute):
                base_names.add(b.attr)
        hit = base_names & _FRAMEWORK_BASES
        if hit:
            return f"基类 {hit}"
    return None


def _grep_class_refs(
    class_name: str, def_file: str, sources: dict[str, str]
) -> list[str]:
    """全仓库搜索类名出现位置，返回非定义文件的路径列表。"""
    refs = []
    def_file_norm = def_file.replace("\\", "/")
    for fpath, source in sources.items():
        fpath_norm = fpath.replace("\\", "/")
        if fpath_norm == def_file_norm:
            continue
        if class_name in source:
            refs.append(fpath_norm)
    return refs


def _check_registry_pattern(
    class_name: str, sources: dict[str, str]
) -> str | None:
    """检查注册表模式 register(ClassName) / _REGISTRY[k]=ClassName，命中返回依据。"""
    for fpath, source in sources.items():
        for m in _REGISTRY_FUNC_RE.finditer(source):
            if m.group(1) == class_name:
                return f"register() 调用: {fpath.replace(chr(92), '/')}"
        for line in source.splitlines():
            if class_name in line and "=" in line:
                if _REGISTRY_ASSIGN_RE.search(line):
                    lhs = line.split("=")[0].strip()
                    if "[" in lhs and "]" in lhs:
                        return f"注册表赋值: {fpath.replace(chr(92), '/')}"
    return None


def _check_script_construction(
    class_name: str, sources: dict[str, str]
) -> str | None:
    """检查 scripts/ 或 main.py 中的构造调用，命中返回依据。"""
    for fpath, source in sources.items():
        fpath_norm = fpath.replace("\\", "/")
        if "/scripts/" not in fpath_norm and not fpath_norm.endswith("main.py"):
            continue
        if fpath_norm.endswith("n1_candidates_review.py"):
            continue
        pattern = rf"\b{re.escape(class_name)}\s*\("
        if re.search(pattern, source):
            return f"脚本构造: {fpath_norm}"
    return None


def _heuristic_classify(
    class_name: str, def_file: str, def_source: str, sources: dict[str, str]
) -> tuple[str, str] | None:
    """启发式分类待定候选，返回 (标签, 依据) 或 None。"""
    def_file_norm = def_file.replace("\\", "/")

    # gRPC proto 文件中的所有类（_pb2_grpc.py / _pb2.py）→ gRPC 生成
    if "_pb2_grpc" in def_file_norm or "_pb2.py" in def_file_norm:
        return ("误报-gRPC生成", "gRPC/proto 生成类，由框架实例化")

    # Mixin 类（类名含 Mixin）→ 不实例化，通过多继承混入
    if "Mixin" in class_name:
        return ("误报-Mixin类", "Mixin 类通过多继承混入，不直接实例化")

    # Utils 工具类（类名含 Utils，通常只有静态/类方法）
    if class_name.endswith("Utils") or class_name.endswith("Util"):
        return ("误报-工具类", "工具类通常只有静态/类方法，不实例化")

    # gRPC 生成类（Servicer 后缀或 proto 文件中的 Service 类）
    if class_name.endswith("Servicer"):
        return ("误报-gRPC生成", "gRPC 框架生成服务端类，由 gRPC 运行时实例化")
    if "_pb2_grpc" in def_file_norm and class_name.endswith("Service"):
        return ("误报-gRPC生成", "gRPC 生成的 Service 类，由 gRPC 运行时实例化")

    # 抽象基类（Base 前缀）
    if class_name.startswith("Base") and len(class_name) > 5:
        return ("误报-抽象基类", "Base 前缀类为抽象基类，由子类实例化")

    # 工厂类（Factory 后缀）
    if class_name.endswith("Factory"):
        return ("误报-工厂类", "工厂类通过类方法创建实例，不直接构造")

    # 解析定义文件 AST 做进一步分类
    try:
        tree = ast.parse(def_source)
    except SyntaxError:
        tree = None

    if tree:
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef) or node.name != class_name:
                continue
            # str 子类 → 不可实例化模式
            for b in node.bases:
                bname = None
                if isinstance(b, ast.Name):
                    bname = b.id
                elif isinstance(b, ast.Attribute):
                    bname = b.attr
                if bname == "str":
                    return ("误报-str子类", "str 子类，通常用作类型标记不实例化")
            # 常量类（无 __init__ 方法，只有类变量赋值）→ 不实例化
            has_init = any(
                isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                and item.name == "__init__"
                for item in node.body
            )
            has_method = any(
                isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                and not item.name.startswith("_")
                for item in node.body
            )
            if not has_init and not has_method:
                return ("误报-常量类", "无 __init__ 和公开方法，仅类变量赋值")
            break

    # 作为基类被继承 → 不需要直接构造
    inherit_count = 0
    for fpath, source in sources.items():
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            for b in node.bases:
                bname = None
                if isinstance(b, ast.Name):
                    bname = b.id
                elif isinstance(b, ast.Attribute):
                    bname = b.attr
                if bname == class_name:
                    inherit_count += 1
    if inherit_count > 0:
        return ("误报-基类被继承", f"被 {inherit_count} 个子类继承，由子类实例化")

    return None


def _classify_candidate(
    cand: CandidateReview, sources: dict[str, str], repo_root: Path
) -> None:
    """对单个候选自动分类，填充 label 和 reason。"""
    def_path = str(repo_root / cand.file) if not Path(cand.file).is_absolute() else cand.file
    def_source = sources.get(def_path, sources.get(str(Path(cand.file)), ""))

    # 1. 查基类/装饰器 → 误报-框架类
    reason = _check_framework_class(def_source, cand.class_name)
    if reason:
        cand.label = "误报-框架类"
        cand.reason = reason
        return

    # 2. 全仓库 grep 类名 → 仅定义处命中 → 真死代码
    refs = _grep_class_refs(cand.class_name, cand.file, sources)
    if not refs:
        cand.label = "真死代码"
        cand.reason = "全仓库零引用（仅定义处出现）"
        return

    # 3. 注册表模式 → 误报-间接构造
    reason = _check_registry_pattern(cand.class_name, sources)
    if reason:
        cand.label = "误报-间接构造"
        cand.reason = reason
        return

    # 4. scripts/main 构造 → 误报-启动脚本构造
    reason = _check_script_construction(cand.class_name, sources)
    if reason:
        cand.label = "误报-启动脚本构造"
        cand.reason = reason
        return

    # 5. 启发式分类 → 减少待定数量
    reason = _heuristic_classify(cand.class_name, cand.file, def_source, sources)
    if reason:
        cand.label, cand.reason = reason
        return

    # 6. 待定
    cand.label = "待定"
    cand.reason = f"有引用但无构造调用，引用文件 {len(refs)} 个，需人工复核"


def _generate_report(
    candidates: list[CandidateReview], output_path: Path, domain_filter: str | None
) -> None:
    """生成分类报告 Markdown。"""
    if domain_filter:
        candidates = [c for c in candidates if c.domain == domain_filter]

    by_domain = defaultdict(list)
    for c in candidates:
        by_domain[c.domain].append(c)

    label_counts = Counter(c.label for c in candidates)
    domain_counts = Counter(c.domain for c in candidates)

    lines = [
        "# ZG-N1 检查 1 候选复核报告",
        "",
        f"> 生成时间：2026-08-21  |  候选总数：{len(candidates)}  |  域过滤：{domain_filter or '全量'}",
        "",
        "## 汇总统计",
        "",
        "### 按分类标签",
        "",
        "| 标签 | 数量 |",
        "|------|------|",
    ]
    for label, n in label_counts.most_common():
        lines.append(f"| {label} | {n} |")

    lines += [
        "",
        "### 按域分布",
        "",
        "| 域 | 数量 |",
        "|------|------|",
    ]
    for domain, n in domain_counts.most_common():
        lines.append(f"| {domain} | {n} |")

    lines.append("")

    domain_order = ["core", "webui", "maisaka", "A_memorix", "plugin", "other"]
    for domain in domain_order:
        cands = by_domain.get(domain, [])
        if not cands:
            continue
        lines += [
            f"## 域：{domain}（{len(cands)} 个候选）",
            "",
            "| 类名 | 定义位置 | 分类标签 | 判定依据 |",
            "|------|----------|----------|----------|",
        ]
        for c in sorted(cands, key=lambda x: (x.label, x.class_name)):
            pos = f"{c.file.replace(chr(92), '/')}:{c.line}"
            lines.append(f"| {c.class_name} | {pos} | {c.label} | {c.reason} |")
        lines.append("")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")


def _update_whitelist(
    candidates: list[CandidateReview], whitelist_path: Path
) -> None:
    """更新白名单：所有候选加入豁免（core/maisaka 域真死代码除外，标记待修复）。"""
    try:
        data = json.loads(whitelist_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        data = {"whitelist": []}

    existing = {(r.get("path", ""), tuple(r.get("names", []))) for r in data.get("whitelist", [])}
    added = 0
    for c in candidates:
        # core/maisaka 域真死代码 → 标记待修复，不豁免
        if c.label == "真死代码" and c.domain in ("core", "maisaka"):
            continue

        # 根据标签生成 reason
        if c.label == "真死代码":
            reason = f"真死代码：全仓库零引用，{c.domain} 域暂不修复"
        elif c.label == "待定":
            reason = f"待人工复核：有引用但无构造调用，{c.domain} 域，{c.reason}"
        else:
            reason = f"{c.label}：{c.reason}"

        path_substr = c.file.replace("\\", "/")
        key = (path_substr, (c.class_name,))
        if key in existing:
            continue
        data.setdefault("whitelist", []).append({
            "path": path_substr,
            "checks": ["1"],
            "names": [c.class_name],
            "_reason": reason,
        })
        existing.add(key)
        added += 1

    if added:
        whitelist_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    print(f"[review] 白名单新增 {added} 条豁免规则")


def main() -> int:
    parser = argparse.ArgumentParser(description="ZG-N1 检查 1 候选复核脚本")
    parser.add_argument("--scan", default="src", help="扫描目录")
    parser.add_argument("--output", required=True, help="分类报告输出路径")
    parser.add_argument("--domain", choices=["core", "webui", "maisaka", "A_memorix", "plugin", "other"], help="仅复核指定域")
    parser.add_argument("--update-whitelist", help="白名单更新路径")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent

    print(f"[review] 获取候选清单（调用 N1 检查器）...")
    candidates = _get_candidates(args.scan, repo_root)
    print(f"[review] 获取 {len(candidates)} 个检查 1 候选")

    print(f"[review] 加载全仓库源码用于分类...")
    sources = _load_all_sources(repo_root)
    print(f"[review] 加载 {len(sources)} 个 .py 文件")

    print(f"[review] 自动分类...")
    for c in candidates:
        _classify_candidate(c, sources, repo_root)

    label_counts = Counter(c.label for c in candidates)
    for label, n in label_counts.most_common():
        print(f"  {label}: {n}")

    output_path = Path(args.output)
    _generate_report(candidates, output_path, args.domain)
    print(f"[review] 分类报告已生成: {output_path}")

    if args.update_whitelist:
        _update_whitelist(candidates, Path(args.update_whitelist))

    return 0


if __name__ == "__main__":
    sys.exit(main())