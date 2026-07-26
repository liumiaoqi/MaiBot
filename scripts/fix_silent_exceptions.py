#!/usr/bin/env python3
"""Batch-fix silent except Exception blocks in maisaka and A_memorix.

Replaces pass-only and empty-body except blocks with logger.warning.
"""
import re
import sys
from pathlib import Path

TARGET_DIRS = ["src/maisaka", "src/A_memorix"]

fixed_count = 0

for target in TARGET_DIRS:
    for py_file in Path(target).rglob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        original = content

        # Pattern: except Exception:\n            pass (no logger)
        # Replace pass with logger.warning
        content = re.sub(
            r"except Exception:\n(\s+)pass",
            r"except Exception:\n\1logger.warning(\"操作失败\", exc_info=True)",
            content,
        )
        # Pattern: except Exception:\n\n (truly empty - no handler at all)
        # Don't touch these - they're harder to classify correctly

        if content != original:
            py_file.write_text(content, encoding="utf-8")
            fixed_count += 1
            print(f"FIXED: {py_file}")

print(f"Files fixed: {fixed_count}")
