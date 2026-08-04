"""旋钮实验：跨架构对比——不同架构下参数指向性的表现差异。

对每个架构（mlp1/mlp2/mlp3/wide/cnn）：
1. 同一初始参数 → A/B 分别训练 → 记录终值 α/β
2. 指向统计：指向 A（|Δα|>阈值 且 |Δβ|<阈值）/ 指向 B / 中立
3. 手动拧旋钮：把"指向 A"的 Top5 参数拉回初始与 α 的中间 → A/B 准确率变化
4. 灵敏度集中度：Top10 |Δ| 占总 |Δ| 的比例（越大 = 参数越局部化，越小 = 越分布式）

输出：output/compare_archs.json + 控制台对比表。
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

import torch

from train_track import (
    ARCHITECTURES,
    EPOCHS,
    SEED,
    TOP_K,
    OUTPUT_DIR,
    evaluate,
    final_values,
    init_model,
    make_datasets,
    top_parameter_changes,
    train_and_track,
)

DIRECTION_THRESHOLD = 0.05
MANUAL_TOP_N = 5
PULL_RATIO = 0.5  # 拉回初始与 α 的中间（50%）

# 与 visualize.py 一致的指向判定
def direction_stats(alpha: Dict[str, List[float]], beta: Dict[str, List[float]],
                    initial: Dict[str, List[float]]) -> Dict[str, int]:
    """统计指向 A / 指向 B / 中立 的参数数量。

    指向 A：|α-初始| > 阈值 且 |β-初始| < 阈值
    指向 B：反之；中立：两者都 < 阈值（或都不显著）
    """
    toward_a = toward_b = neutral = 0
    for name in alpha:
        for idx, (a_val, b_val) in enumerate(zip(alpha[name], beta[name], strict=True)):
            init_val = initial[name][idx]
            delta_a = abs(a_val - init_val)
            delta_b = abs(b_val - init_val)
            if delta_a > DIRECTION_THRESHOLD and delta_b <= DIRECTION_THRESHOLD:
                toward_a += 1
            elif delta_b > DIRECTION_THRESHOLD and delta_a <= DIRECTION_THRESHOLD:
                toward_b += 1
            else:
                neutral += 1
    return {"指向A": toward_a, "指向B": toward_b, "中立": neutral}


def sensitivity_concentration(track: Dict[str, List[List[float]]]) -> float:
    """Top10 |Δ| 占总 |Δ| 的比例——参数指向的集中度。"""
    changes: List[float] = []
    for name, trajectory in track.items():
        initial = trajectory[0]
        final = trajectory[-1]
        for before, after in zip(initial, final, strict=True):
            changes.append(abs(after - before))
    total = sum(changes)
    if total <= 0:
        return 0.0
    top = sum(sorted(changes, reverse=True)[:TOP_K])
    return top / total


def manual_pull_effect(arch: str, alpha: Dict[str, List[float]],
                       beta: Dict[str, List[float]], initial: Dict[str, List[float]],
                       datasets: Dict[str, Tuple[Any, Any]]) -> Tuple[float, float]:
    """把"指向 A"的 Top5 参数拉回初始与 α 的中间，测 A/B 准确率变化。

    Returns:
        (A 准确率变化, B 准确率变化)——正数 = 该旋钮组影响对应任务
    """
    import torch

    # 选出"指向 A"且 |Δα| 最大的参数
    candidates: List[Tuple[str, int, float]] = []
    for name in alpha:
        for idx, (a_val, b_val) in enumerate(zip(alpha[name], beta[name], strict=True)):
            init_val = initial[name][idx]
            delta_a = abs(a_val - init_val)
            delta_b = abs(b_val - init_val)
            if delta_a > DIRECTION_THRESHOLD and delta_b <= DIRECTION_THRESHOLD:
                candidates.append((name, idx, delta_a))
    candidates.sort(key=lambda item: item[2], reverse=True)
    picked = candidates[:MANUAL_TOP_N]

    # 基准准确率（α 模型）
    model = init_model(SEED, arch)  # 重新初始化（同架构）
    _load_values(model, alpha)
    acc_a0 = evaluate(model, *datasets["test_a"])
    acc_b0 = evaluate(model, *datasets["test_b"])

    # 拉回 50%
    for name, idx, _ in picked:
        param = dict(model.named_parameters())[name].data
        flat = param.reshape(-1)
        init_val = initial[name][idx]
        current = flat[idx].item()
        flat[idx] = init_val + (current - init_val) * (1.0 - PULL_RATIO)

    acc_a1 = evaluate(model, *datasets["test_a"])
    acc_b1 = evaluate(model, *datasets["test_b"])
    return acc_a1 - acc_a0, acc_b1 - acc_b0


def _load_values(model: torch.nn.Module, values: Dict[str, List[float]]) -> None:
    """把参数值字典加载进模型（用于手动修改实验）。"""
    with torch.no_grad():
        for name, param in model.named_parameters():
            data = values.get(name)
            if data is not None:
                param.data = torch.tensor(data, dtype=torch.float32).reshape(param.shape)


def main() -> None:
    """跑全部架构的对比，输出对比表 + summary JSON。"""
    import torch

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    datasets = make_datasets()
    summary: Dict[str, Any] = {}

    print("=" * 78)
    print("旋钮实验：跨架构对比")
    print("=" * 78)
    header = (f"{'架构':<8} {'参数数':>6} {'指向A':>6} {'指向B':>6} {'中立':>6} "
              f"{'集中度':>7} {'手动拧ΔA':>8} {'手动拧ΔB':>8} {'描述'}")
    print(header)
    print("-" * 78)

    for arch, (_, desc) in ARCHITECTURES.items():
        model_a = init_model(SEED, arch)
        track_a = train_and_track(model_a, *datasets["train_a"], EPOCHS)
        alpha = final_values(track_a)
        model_b = init_model(SEED, arch)
        track_b = train_and_track(model_b, *datasets["train_b"], EPOCHS)
        beta = final_values(track_b)
        initial = {name: traj[0] for name, traj in track_a.items()}

        stats = direction_stats(alpha, beta, initial)
        concentration = sensitivity_concentration(track_a)
        delta_a, delta_b = manual_pull_effect(
            arch, alpha, beta, initial, datasets,
        )
        param_count = sum(len(values) for values in alpha.values())

        print(f"{arch:<8} {param_count:>6} {stats['指向A']:>6} {stats['指向B']:>6} "
              f"{stats['中立']:>6} {concentration:>7.1%} "
              f"{delta_a:>+8.1%} {delta_b:>+8.1%} {desc}")
        summary[arch] = {
            "param_count": param_count,
            "direction": stats,
            "concentration_top10": round(concentration, 4),
            "manual_pull_delta_a": round(delta_a, 4),
            "manual_pull_delta_b": round(delta_b, 4),
            "description": desc,
        }

    print("-" * 78)
    print("解读：")
    print("  指向A/B = 参数被对应数据拉走的数量（指向性统计）")
    print("  集中度 = Top10 灵敏参数占总变化的比例（越高越局部化，越低越分布式）")
    print("  手动拧ΔA/ΔB = 把指向A的Top5参数拉回中间后，A/B准确率变化（正=该组旋钮影响此任务）")

    out_path = OUTPUT_DIR / "compare_archs.json"
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n对比数据已保存: {out_path}")


if __name__ == "__main__":
    main()
