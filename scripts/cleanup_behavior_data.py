#!/usr/bin/env python3
"""T-02 存量行为数据删除（行为学习激进档遗留）。

容器重启后 5 分钟内执行（MaiBot 尚未建立数据库连接时，跨文件系统 SQLite 写可用）。

用法（容器内）：
    python scripts/cleanup_behavior_data.py

删除：behavior_experience_paths / behavior_scene_clusters /
      behavior_scene_tag_clusters / behavior_actions / behavior_outcomes
不动：agent_interaction_relationships（关系网络 69 条）
"""

import sqlite3
import sys
from pathlib import Path

DB_PATH = Path("/MaiMBot/data/MaiBot.db")

TABLES = [
    "behavior_experience_paths",
    "behavior_scene_clusters",
    "behavior_scene_tag_clusters",
    "behavior_actions",
    "behavior_outcomes",
]


def main() -> int:
    if not DB_PATH.exists():
        print(f"数据库不存在: {DB_PATH}")
        return 1
    try:
        conn = sqlite3.connect(str(DB_PATH), timeout=10)
        cur = conn.cursor()
        for table in TABLES:
            try:
                n = cur.execute(f"SELECT COUNT(*) FROM [{table}]").fetchone()[0]
                cur.execute(f"DELETE FROM [{table}]")
                print(f"{table}: 删除 {n} 条")
            except Exception as e:
                print(f"{table}: ERR {type(e).__name__}: {e}")
                conn.rollback()
                return 2
        # 验证
        for table in TABLES:
            n = cur.execute(f"SELECT COUNT(*) FROM [{table}]").fetchone()[0]
            assert n == 0, f"{table} 未清空: {n}"
            print(f"验证 {table}: {n} ✅")
        # 关系网络不动（验证未受影响）
        n = cur.execute("SELECT COUNT(*) FROM agent_interaction_relationships").fetchone()[0]
        print(f"关系网络（不动）: {n} ✅")
        conn.commit()
        conn.close()
        print("T-02 数据删除完成")
        return 0
    except sqlite3.OperationalError as e:
        print(f"数据库打开失败（可能 MaiBot 已启动持锁）: {e}")
        print("提示：请在容器重启后 5 分钟内执行")
        return 3


if __name__ == "__main__":
    sys.exit(main())
