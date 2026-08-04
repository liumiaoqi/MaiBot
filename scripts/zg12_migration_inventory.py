"""ZG-12 迁移清单生成/审计（T54-T55）。

生成 task_name 字符串引用清单 CSV（迁移面审计用）：
- 按 src/ 出现行数统计（244 口径）
- 每行：file:line / task_name / 用途分类（调用点/配置键/fallback/同名异义）

用法（容器内）：
  cd /MaiMBot && uv run python scripts/zg12_migration_inventory.py [--csv out.csv] [--audit]
"""

import argparse
import re
import sys
from pathlib import Path

SRC_ROOT = Path("src")

TASK_NAMES = (
    "replyer", "planner", "utils", "memory", "mid_memory",
    "expression_use", "learner", "emoji", "vlm", "voice", "embedding",
)

# 同名异义（非模型任务语义）——审计时排除
NON_TASK_SEMANTICS = {
    "logger", "message component", "db enum", "resource type",
    "reasoning stage", "prompt category", "module/plugin name",
    "emoji storage", "intent/stage", "config section",
}


def scan() -> list[tuple[str, int, str, str]]:
    """扫描 src/ 下 task_name 字符串引用。返回 (file, line, task_name, 用途)。"""
    rows: list[tuple[str, int, str, str]] = []
    for path in sorted(SRC_ROOT.rglob("*.py")):
        if "__pycache__" in str(path):
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (UnicodeDecodeError, OSError):
            continue
        for lineno, line in enumerate(lines, 1):
            for task_name in TASK_NAMES:
                if re.search(rf'["\']{task_name}["\']', line):
                    rows.append((str(path), lineno, task_name, _classify(line)))
                    break
    return rows


def _classify(line: str) -> str:
    """按行内容粗分类引用用途。"""
    if "task_name" in line or "generate_response" in line or "LLMServiceClient" in line:
        return "调用点"
    if "model_task_config" in line or "TaskConfig" in line or "DEFAULT_TASK_CONFIG" in line:
        return "配置键"
    if "fallback" in line or "preferred" in line or "PRIORITY" in line:
        return "fallback/优先级"
    if "logger" in line.lower() or "get_logger" in line:
        return "logger 名"
    if "component_type" in line or "seg" in line or "Seg" in line:
        return "消息组件类型"
    if "prompt_category" in line or "request_kind" in line:
        return "prompt 类别"
    return "其他/待审"


def main() -> int:
    parser = argparse.ArgumentParser(description="ZG-12 迁移清单生成/审计")
    parser.add_argument("--csv", type=str, default="", help="输出 CSV 路径")
    parser.add_argument("--audit", action="store_true", help="审计模式：统计口径 + 分类汇总")
    args = parser.parse_args()

    rows = scan()
    line_count = len(rows)
    file_count = len({r[0] for r in rows})
    occurrence_count = sum(1 for _ in rows)

    if args.csv:
        import csv

        with open(args.csv, "w", encoding="utf-8", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(["file", "line", "task_name", "classify"])
            writer.writerows(rows)
        print(f"CSV 已写入: {args.csv}（{line_count} 行 / {file_count} 文件）")

    if args.audit or args.csv == "":
        print("=" * 60)
        print("ZG-12 迁移清单")
        print("=" * 60)
        print(f"按行统计: {line_count} 处 / {file_count} 个文件")
        by_name: dict[str, int] = {}
        for _, _, name, _ in rows:
            by_name[name] = by_name.get(name, 0) + 1
        print("按任务名分布:", dict(sorted(by_name.items(), key=lambda kv: -kv[1])))
        by_class: dict[str, int] = {}
        for _, _, _, cls in rows:
            by_class[cls] = by_class.get(cls, 0) + 1
        print("按用途分类:", dict(sorted(by_class.items(), key=lambda kv: -kv[1])))
        print(f"总出现次数（含同名异义）: {occurrence_count}")
        print("审计提示: 迁移目标 = '调用点' + '配置键' + 'fallback/优先级' 三类；")
        print("          'logger 名'/'消息组件类型'/'prompt 类别' 为同名异义，不在迁移范围。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
