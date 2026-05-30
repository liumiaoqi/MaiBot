from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections import Counter
from pathlib import Path

import sqlite3


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "MaiBot.db"

COUNT_BUCKETS = (
    ("0", 0, 0),
    ("1-3", 1, 3),
    ("4-7", 4, 7),
    ("8-24", 8, 24),
    ("25-99", 25, 99),
    ("100+", 100, None),
)


def connect_readonly(db_path: Path) -> sqlite3.Connection:
    if not db_path.exists():
        raise FileNotFoundError(f"数据库文件不存在: {db_path}")

    database_uri = f"file:{db_path.as_posix()}?mode=ro"
    connection = sqlite3.connect(database_uri, uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout=5000")
    return connection


def ensure_jargons_table(connection: sqlite3.Connection) -> None:
    table_exists = connection.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table'
          AND name = 'jargons'
        """
    ).fetchone()
    if table_exists is None:
        raise RuntimeError("当前数据库没有 jargons 表")

    columns = {str(row["name"]) for row in connection.execute("PRAGMA table_info(jargons)").fetchall()}
    if "count" not in columns:
        raise RuntimeError("jargons 表没有 count 字段")


def fetch_jargon_rows(db_path: Path) -> list[sqlite3.Row]:
    with connect_readonly(db_path) as connection:
        ensure_jargons_table(connection)
        return connection.execute(
            """
            SELECT
                COALESCE(count, 0) AS count,
                is_jargon,
                is_complete,
                is_global
            FROM jargons
            ORDER BY count
            """
        ).fetchall()


def percentile(sorted_values: list[int], percent: float) -> float:
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return float(sorted_values[0])

    position = (len(sorted_values) - 1) * percent
    lower_index = int(position)
    upper_index = min(lower_index + 1, len(sorted_values) - 1)
    fraction = position - lower_index
    return sorted_values[lower_index] * (1 - fraction) + sorted_values[upper_index] * fraction


def status_label(value: object) -> str:
    if value is None:
        return "待判定"
    return "黑话" if bool(value) else "非黑话"


def bool_label(value: object) -> str:
    return "是" if bool(value) else "否"


def bucket_label(count_value: int) -> str:
    for label, lower_bound, upper_bound in COUNT_BUCKETS:
        if count_value < lower_bound:
            continue
        if upper_bound is None or count_value <= upper_bound:
            return label
    return "unknown"


def print_counter(title: str, counter: Counter[str], total: int) -> None:
    print(title)
    if total == 0:
        print("  无数据")
        return

    label_width = max(len("分组"), *(len(label) for label in counter))
    count_width = max(len("数量"), *(len(str(count)) for count in counter.values()))
    print(f"  {'分组':<{label_width}}  {'数量':>{count_width}}  占比")
    print(f"  {'-' * label_width}  {'-' * count_width}  ------")
    for label, count in counter.items():
        percent = count / total * 100
        print(f"  {label:<{label_width}}  {count:>{count_width}}  {percent:>5.1f}%")


def print_distribution(rows: list[sqlite3.Row], exact_limit: int) -> None:
    counts = [int(row["count"] or 0) for row in rows]
    total = len(counts)
    print(f"记录总数: {total}")
    if not counts:
        return

    sorted_counts = sorted(counts)
    average = sum(sorted_counts) / total
    print(
        "count 概览: "
        f"min={sorted_counts[0]}, "
        f"p25={percentile(sorted_counts, 0.25):.1f}, "
        f"median={percentile(sorted_counts, 0.50):.1f}, "
        f"p75={percentile(sorted_counts, 0.75):.1f}, "
        f"p90={percentile(sorted_counts, 0.90):.1f}, "
        f"p95={percentile(sorted_counts, 0.95):.1f}, "
        f"max={sorted_counts[-1]}, "
        f"avg={average:.2f}"
    )
    print()

    bucket_counter = Counter(bucket_label(count) for count in sorted_counts)
    ordered_bucket_counter = Counter({label: bucket_counter.get(label, 0) for label, _low, _high in COUNT_BUCKETS})
    print_counter("按推断阈值分桶", ordered_bucket_counter, total)
    print()

    status_counter = Counter(status_label(row["is_jargon"]) for row in rows)
    print_counter("按判定状态", status_counter, total)
    print()

    complete_counter = Counter(bool_label(row["is_complete"]) for row in rows)
    print_counter("按是否完成推断", complete_counter, total)
    print()

    global_counter = Counter(bool_label(row["is_global"]) for row in rows)
    print_counter("按是否全局黑话", global_counter, total)
    print()

    exact_counter = Counter(sorted_counts)
    exact_items = sorted(exact_counter.items(), key=lambda item: (-item[1], item[0]))
    if exact_limit > 0:
        exact_items = exact_items[:exact_limit]

    exact_label = f"出现最多的 count 值 Top {exact_limit}" if exact_limit > 0 else "所有 count 值分布"
    print(exact_label)
    count_width = max(len("count"), *(len(str(count_value)) for count_value, _row_count in exact_items))
    rows_width = max(len("记录数"), *(len(str(row_count)) for _count_value, row_count in exact_items))
    print(f"  {'count':>{count_width}}  {'记录数':>{rows_width}}  占比")
    print(f"  {'-' * count_width}  {'-' * rows_width}  ------")
    for count_value, row_count in exact_items:
        percent = row_count / total * 100
        print(f"  {count_value:>{count_width}}  {row_count:>{rows_width}}  {percent:>5.1f}%")


def parse_args() -> Namespace:
    parser = ArgumentParser(description="分析 jargons 表的 count 分布。")
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB_PATH,
        help=f"SQLite 数据库路径，默认: {DEFAULT_DB_PATH}",
    )
    parser.add_argument(
        "--exact-limit",
        type=int,
        default=30,
        help="按记录数排序展示多少个具体 count 值；设为 0 展示全部。",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rows = fetch_jargon_rows(args.db)
    print(f"数据库: {args.db}")
    print_distribution(rows, args.exact_limit)


if __name__ == "__main__":
    main()
