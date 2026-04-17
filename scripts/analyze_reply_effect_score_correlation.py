from pathlib import Path
from typing import Any

from scipy import stats

import argparse
import csv
import json
import math


DEFAULT_LOG_DIR = Path("logs") / "maisaka_reply_effect"
DEFAULT_MANUAL_DIR = Path("logs") / "maisaka_reply_effect_manual"


METRIC_SPECS = [
    ("总分", "asi", "ASI 自动总分"),
    ("大项", "behavior_score", "行为满意度 B"),
    ("大项", "relational_score", "感知质量 R"),
    ("大项", "friction_score", "摩擦风险 F"),
    ("大项", "friction_quality_score", "低摩擦质量分"),
    ("行为子项", "behavior_signals.continue_2turns", "继续两轮"),
    ("行为子项", "behavior_signals.next_user_sentiment", "后续情绪"),
    ("行为子项", "behavior_signals.user_expansion", "用户展开"),
    ("行为子项", "behavior_signals.no_correction", "没有纠正"),
    ("行为子项", "behavior_signals.no_abort", "没有放弃"),
    ("rubric 子项", "rubric_scores.social_presence.normalized_score", "社交临场感"),
    ("rubric 子项", "rubric_scores.warmth.normalized_score", "温暖感"),
    ("rubric 子项", "rubric_scores.competence.normalized_score", "能力/有用性"),
    ("rubric 子项", "rubric_scores.appropriateness.normalized_score", "合适程度"),
    ("rubric 子项", "rubric_scores.uncanny_risk.normalized_score", "违和风险 judge"),
    ("摩擦子项", "friction_signals.explicit_negative", "明确负反馈"),
    ("摩擦子项", "friction_signals.repair_loop", "修复循环"),
    ("摩擦子项", "friction_signals.uncanny_risk", "违和风险"),
]


def normalize_name(value: str) -> str:
    normalized = "".join(char if char.isalnum() or char in "._-" else "_" for char in str(value or "").strip())
    normalized = normalized.strip("._")
    return normalized or "unknown"


def load_json_file(file_path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(file_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def to_float(value: Any) -> float | None:
    if value in {None, ""}:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def get_nested(payload: dict[str, Any], dotted_path: str) -> Any:
    current: Any = payload
    for key in dotted_path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def annotation_path(manual_dir: Path, chat_id: str, effect_id: str) -> Path:
    return manual_dir / normalize_name(chat_id) / f"{normalize_name(effect_id)}.json"


def iter_records(
    log_dir: Path,
    manual_dir: Path,
    *,
    chat_id: str,
    include_pending: bool,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if not log_dir.exists():
        return records

    chat_dirs = [log_dir / normalize_name(chat_id)] if chat_id else [path for path in log_dir.iterdir() if path.is_dir()]
    for chat_dir in sorted(chat_dirs):
        if not chat_dir.exists() or not chat_dir.is_dir():
            continue
        for record_file in sorted(chat_dir.glob("*.json")):
            effect_record = load_json_file(record_file)
            if not effect_record:
                continue
            if not include_pending and effect_record.get("status") != "finalized":
                continue

            effect_id = str(effect_record.get("effect_id") or record_file.stem)
            manual_record = load_json_file(annotation_path(manual_dir, chat_dir.name, effect_id))
            manual_score = to_float(manual_record.get("manual_score"))
            if manual_score is None:
                manual_score_5 = to_float(manual_record.get("manual_score_5"))
                if manual_score_5 is not None:
                    manual_score = (manual_score_5 - 1) / 4 * 100
            if manual_score is None:
                continue

            raw_scores = effect_record.get("scores") if isinstance(effect_record.get("scores"), dict) else {}
            scores = dict(raw_scores)
            friction_score = to_float(scores.get("friction_score"))
            if friction_score is not None:
                scores["friction_quality_score"] = 1 - friction_score
            records.append(
                {
                    "chat_id": chat_dir.name,
                    "effect_id": effect_id,
                    "manual_score": manual_score,
                    "manual_score_5": manual_record.get("manual_score_5"),
                    "scores": scores,
                    "status": effect_record.get("status"),
                    "created_at": effect_record.get("created_at"),
                    "record_file": str(record_file),
                }
            )
    return records


def calculate_metric_stats(records: list[dict[str, Any]], metric_path: str, min_n: int) -> dict[str, Any]:
    pairs: list[tuple[float, float]] = []
    for record in records:
        x_value = to_float(get_nested(record["scores"], metric_path))
        y_value = to_float(record["manual_score"])
        if x_value is None or y_value is None:
            continue
        pairs.append((x_value, y_value))

    x_values = [pair[0] for pair in pairs]
    y_values = [pair[1] for pair in pairs]
    result: dict[str, Any] = {
        "n": len(pairs),
        "pearson_r": None,
        "pearson_p": None,
        "spearman_r": None,
        "spearman_p": None,
        "kendall_tau": None,
        "kendall_p": None,
        "note": "",
    }
    if len(pairs) < min_n:
        result["note"] = f"样本数少于 {min_n}"
        return result
    if len(set(x_values)) < 2:
        result["note"] = "自动评分没有变化，无法计算相关"
        return result
    if len(set(y_values)) < 2:
        result["note"] = "人工评分没有变化，无法计算相关"
        return result

    pearson = stats.pearsonr(x_values, y_values)
    spearman = stats.spearmanr(x_values, y_values)
    kendall = stats.kendalltau(x_values, y_values)
    result.update(
        {
            "pearson_r": round_float(pearson.statistic),
            "pearson_p": round_float(pearson.pvalue),
            "spearman_r": round_float(spearman.statistic),
            "spearman_p": round_float(spearman.pvalue),
            "kendall_tau": round_float(kendall.statistic),
            "kendall_p": round_float(kendall.pvalue),
        }
    )
    return result


def round_float(value: Any) -> float | None:
    number = to_float(value)
    if number is None:
        return None
    return round(number, 6)


def significance_label(p_value: float | None) -> str:
    if p_value is None:
        return ""
    if p_value < 0.001:
        return "***"
    if p_value < 0.01:
        return "**"
    if p_value < 0.05:
        return "*"
    if p_value < 0.1:
        return "."
    return "ns"


def build_report(records: list[dict[str, Any]], min_n: int) -> list[dict[str, Any]]:
    report: list[dict[str, Any]] = []
    for group, metric_path, label in METRIC_SPECS:
        metric_stats = calculate_metric_stats(records, metric_path, min_n)
        report.append(
            {
                "group": group,
                "metric": metric_path,
                "label": label,
                **metric_stats,
                "pearson_sig": significance_label(metric_stats["pearson_p"]),
                "spearman_sig": significance_label(metric_stats["spearman_p"]),
                "kendall_sig": significance_label(metric_stats["kendall_p"]),
            }
        )
    return report


def print_report(records: list[dict[str, Any]], report: list[dict[str, Any]]) -> None:
    chats = sorted({record["chat_id"] for record in records})
    print("\nMaisaka 回复效果评分相关性分析")
    print("=" * 96)
    print(f"已匹配人工评分记录数: {len(records)}")
    print(f"聊天流数量: {len(chats)}")
    if chats:
        print(f"聊天流: {', '.join(chats[:8])}{' ...' if len(chats) > 8 else ''}")
    print("人工分使用 manual_score，若只有 manual_score_5，则换算到 0-100 后参与计算。")
    print("显著性: *** p<0.001, ** p<0.01, * p<0.05, . p<0.1, ns 不显著")
    print("-" * 96)

    header = (
        f"{'分组':<14} {'指标':<34} {'n':>4} "
        f"{'Pearson r':>10} {'p':>10} {'sig':>4} "
        f"{'Spearman r':>11} {'p':>10} {'sig':>4} "
        f"{'Kendall':>9} {'p':>10} {'说明'}"
    )
    print(header)
    print("-" * 96)
    for item in report:
        print(
            f"{item['group']:<14} "
            f"{item['label']:<34} "
            f"{item['n']:>4} "
            f"{format_number(item['pearson_r']):>10} "
            f"{format_number(item['pearson_p']):>10} "
            f"{item['pearson_sig']:>4} "
            f"{format_number(item['spearman_r']):>11} "
            f"{format_number(item['spearman_p']):>10} "
            f"{item['spearman_sig']:>4} "
            f"{format_number(item['kendall_tau']):>9} "
            f"{format_number(item['kendall_p']):>10} "
            f"{item['note']}"
        )

    total = next((item for item in report if item["metric"] == "asi"), None)
    if total:
        print("-" * 96)
        print(
            "总分 ASI 与人工分的 Pearson 相关: "
            f"r={format_number(total['pearson_r'])}, "
            f"p={format_number(total['pearson_p'])}, "
            f"显著性={total['pearson_sig'] or 'N/A'}"
        )


def format_number(value: Any) -> str:
    if value is None:
        return "N/A"
    number = to_float(value)
    if number is None:
        return "N/A"
    if abs(number) < 0.000001:
        return "0"
    return f"{number:.4g}"


def write_csv(file_path: Path, report: list[dict[str, Any]]) -> None:
    file_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "group",
        "metric",
        "label",
        "n",
        "pearson_r",
        "pearson_p",
        "pearson_sig",
        "spearman_r",
        "spearman_p",
        "spearman_sig",
        "kendall_tau",
        "kendall_p",
        "kendall_sig",
        "note",
    ]
    with file_path.open("w", encoding="utf-8-sig", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(report)


def write_json(file_path: Path, records: list[dict[str, Any]], report: list[dict[str, Any]]) -> None:
    file_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "matched_record_count": len(records),
        "chat_count": len({record["chat_id"] for record in records}),
        "report": report,
    }
    file_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="分析 Maisaka 回复效果自动评分与人工评分的相关性和显著性。")
    parser.add_argument("--log-dir", type=Path, default=DEFAULT_LOG_DIR, help="自动评分 JSON 目录")
    parser.add_argument("--manual-dir", type=Path, default=DEFAULT_MANUAL_DIR, help="人工评分 JSON 目录")
    parser.add_argument("--chat-id", default="", help="只分析某个 platform_type_id，例如 qq_group_1028699246")
    parser.add_argument("--include-pending", action="store_true", help="包含尚未 finalized 的记录")
    parser.add_argument("--min-n", type=int, default=3, help="计算相关性需要的最小样本数，默认 3")
    parser.add_argument("--csv", type=Path, default=None, help="把统计结果另存为 CSV")
    parser.add_argument("--json", type=Path, default=None, help="把统计结果另存为 JSON")
    args = parser.parse_args()

    records = iter_records(
        args.log_dir,
        args.manual_dir,
        chat_id=args.chat_id,
        include_pending=args.include_pending,
    )
    report = build_report(records, max(2, args.min_n))
    print_report(records, report)

    if args.csv:
        write_csv(args.csv, report)
        print(f"\nCSV 已保存: {args.csv}")
    if args.json:
        write_json(args.json, records, report)
        print(f"JSON 已保存: {args.json}")


if __name__ == "__main__":
    main()
