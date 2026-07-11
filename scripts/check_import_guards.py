"""A_memorix/core/ 导入隔离守卫验证脚本。

检查 src/A_memorix/core/ 下所有 .py 文件是否存在违规导入。
ruff TID251 无法对 src.services 等被大量合法使用的模块做目录限定禁止，
因此用 AST 脚本做补充检查。
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

BANNED_PREFIXES = (
    "src.services",
    "src.config.config",
    "src.common.database",
    "src.llm_models",
    "src.A_memorix.host_service",
)

ALLOWED_PREFIXES = (
    "src.common.logger",
    "src.common.prompt_i18n",
    "src.common.data_models",
    "src.core.types",
    "src.core.protocols",
)

CORE_DIR = Path(__file__).resolve().parent.parent / "src" / "A_memorix" / "core"


def _is_banned(module: str) -> bool:
    if any(module.startswith(allowed) for allowed in ALLOWED_PREFIXES):
        return False
    return any(module.startswith(banned) for banned in BANNED_PREFIXES)


def check_file(filepath: Path, verbose: bool = False) -> list[tuple[int, str, str]]:
    violations = []
    try:
        source = filepath.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(filepath))
    except (SyntaxError, UnicodeDecodeError) as exc:
        if verbose:
            print(f"  跳过（解析失败）: {filepath}: {exc}")
        return violations

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and _is_banned(node.module):
            violations.append((node.lineno, node.module, f"from {node.module} import ..."))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if _is_banned(alias.name):
                    violations.append((node.lineno, alias.name, f"import {alias.name}"))

    return violations


def main() -> int:
    parser = argparse.ArgumentParser(description="A_memorix/core/ 导入隔离守卫")
    parser.add_argument("--verbose", "-v", action="store_true", help="显示检查详情")
    args = parser.parse_args()

    if not CORE_DIR.exists():
        print(f"错误: 目录不存在 {CORE_DIR}")
        return 1

    total_violations = 0
    py_files = sorted(CORE_DIR.rglob("*.py"))

    if args.verbose:
        print(f"检查目录: {CORE_DIR}")
        print(f"扫描文件: {len(py_files)} 个\n")

    for filepath in py_files:
        violations = check_file(filepath, verbose=args.verbose)
        for lineno, module, statement in violations:
            rel = filepath.relative_to(CORE_DIR.parent.parent.parent)
            print(f"{rel}:{lineno}: {statement}  [违规模块: {module}]")
            total_violations += 1

    if total_violations == 0:
        if args.verbose:
            print("\n✅ 零违规，所有导入符合隔离规则")
        return 0

    print(f"\n❌ 发现 {total_violations} 处违规导入")
    return 1


if __name__ == "__main__":
    sys.exit(main())