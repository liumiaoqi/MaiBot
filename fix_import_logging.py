"""CQ-2 T1: maisaka 下 import logging → get_logger 机械替换脚本。"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent / "src" / "maisaka"

A_CLASS = [
    "agent/registry.py",
    "agent/router.py",
    "agent_autonomy/reminder.py",
    "agent_interaction/engine.py",
    "agent_interaction/monologue_engine.py",
    "agent_interaction/scheduler.py",
    "agent_interaction/memory/adapter.py",
    "agent_interaction/memory/profile.py",
    "subagent/fork_context.py",
    "subagent/agents/checkpoint_writer.py",
    "subagent/agents/dream_trigger.py",
    "time_awareness/lunar.py",
]

B_CLASS = [
    "agent/config.py",
    "agent/config_loader/loader.py",
    "agent_autonomy/log_utils.py",
    "agent_interaction/bootstrap.py",
    "agent_interaction/cooldown.py",
    "agent_interaction/echo_detector.py",
    "agent_interaction/event_store.py",
    "agent_interaction/trigger_scheduler.py",
    "agent_interaction/triggers/memory_driven.py",
    "consolidation/distill.py",
    "consolidation/knowledge_store.py",
    "consolidation/scheduler.py",

    "event_sensor/priority.py",
    "event_sensor/reaction.py",
    "event_sensor/sensor.py",
    "goal/judge.py",
    "goal/manager.py",
    "goal/scheduler.py",
    "migration/coordinator.py",
    "subagent/interactive_gate.py",
    "subagent/lifecycle.py",
    "subagent/parallel.py",
    "subagent/scheduler.py",
    "subagent/agents/compaction.py",
    "subagent/agents/compaction_trigger.py",
    "subagent/agents/dream.py",
    "time_awareness/context_builder.py",
    "time_awareness/scheduler.py",
    "time_awareness/service.py",
]


def process_a_class(fp: Path) -> bool:
    """A 类：已有 get_logger，仅删 import logging + logging.getLogger 行。"""
    lines = fp.read_text(encoding="utf-8").splitlines(keepends=True)
    new_lines = []
    changed = False
    for line in lines:
        stripped = line.strip()
        if stripped == "import logging":
            changed = True
            continue
        if re.match(r"^logger\s*=\s*logging\.getLogger\s*\(", stripped):
            changed = True
            continue
        new_lines.append(line)
    if changed:
        fp.write_text("".join(new_lines), encoding="utf-8")
    return changed


def process_b_class(fp: Path) -> bool:
    """B 类：需添加 get_logger import + 替换 logger = + 删 import logging。"""
    content = fp.read_text(encoding="utf-8")
    lines = content.splitlines(keepends=True)
    original = content

    has_import_logging = False
    has_get_logger_import = False
    get_logger_line = "from src.common.logger import get_logger\n"
    last_stdlib_import_idx = -1

    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped == "import logging":
            has_import_logging = True
        if "from src.common.logger import get_logger" in stripped:
            has_get_logger_import = True
        if re.match(r"^from __future__", stripped):
            last_stdlib_import_idx = i
            continue
        if re.match(r"^import \w", stripped) and not stripped.startswith("import logging"):
            last_stdlib_import_idx = i
            continue
        if re.match(r"^from \w", stripped) and "src." not in stripped and "local" not in stripped:
            last_stdlib_import_idx = i

    if not has_import_logging:
        return False

    new_lines = []
    added_get_logger = False

    for i, line in enumerate(lines):
        stripped = line.strip()

        if stripped == "import logging":
            continue

        logger_match = re.match(r"^logger\s*=\s*logging\.getLogger\s*\((.+)\)\s*$", stripped)
        if logger_match:
            arg = logger_match.group(1)
            new_lines.append(f"logger = get_logger({arg})\n")
            continue

        if not added_get_logger and not has_get_logger_import and i == last_stdlib_import_idx + 1:
            new_lines.append(get_logger_line)
            added_get_logger = True

        new_lines.append(line)

    if not added_get_logger and not has_get_logger_import:
        for j, line in enumerate(new_lines):
            if line.strip().startswith("from __future__"):
                new_lines.insert(j + 1, "\n")
                new_lines.insert(j + 2, get_logger_line)
                break

    new_content = "".join(new_lines)
    if new_content != original:
        fp.write_text(new_content, encoding="utf-8")
        return True
    return False


def main() -> None:
    changed_files = []

    for rel in A_CLASS:
        fp = ROOT / rel
        if not fp.exists():
            print(f"SKIP (not found): {rel}")
            continue
        if process_a_class(fp):
            changed_files.append(f"A: {rel}")
            print(f"OK (A-class): {rel}")
        else:
            print(f"NOOP: {rel}")

    for rel in B_CLASS:
        fp = ROOT / rel
        if not fp.exists():
            print(f"SKIP (not found): {rel}")
            continue
        if process_b_class(fp):
            changed_files.append(f"B: {rel}")
            print(f"OK (B-class): {rel}")
        else:
            print(f"NOOP: {rel}")

    print(f"\n=== Summary: {len(changed_files)} files changed ===")
    for f in changed_files:
        print(f"  {f}")


if __name__ == "__main__":
    main()
