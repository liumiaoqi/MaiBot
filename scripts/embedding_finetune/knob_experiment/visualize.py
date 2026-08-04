"""旋钮实验第二步：可视化 α/β 参数终值。

输出：
    output/param_space.png   参数空间散点图（x=α, y=β）
    output/heatmap_alpha.png α 每层参数热力图
    output/heatmap_beta.png  β 每层参数热力图
"""

import json
from pathlib import Path
from typing import Dict, List, Tuple

try:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
except ModuleNotFoundError as exc:
    raise SystemExit("缺少依赖 matplotlib：请先执行 pip install matplotlib") from exc

THRESHOLD = 0.05
OUTPUT_DIR = Path(__file__).resolve().parent / "output"
WEIGHT_SHAPES = {
    "fc1.weight": (8, 64),
    "fc2.weight": (8, 8),
    "fc3.weight": (2, 8),
}


def load_json(name: str) -> Dict[str, list]:
    """读取 output 下的 JSON 文件。"""
    return json.loads((OUTPUT_DIR / name).read_text(encoding="utf-8"))


def compute_pointing_stats(
    alpha: Dict[str, list],
    beta: Dict[str, list],
    track_a: Dict[str, list],
) -> Tuple[int, int, int]:
    """统计指向 A / 指向 B / 中立的参数个数。

    指向 A：|α-初始| > 阈值 且 |β-初始| < 阈值；
    指向 B：|β-初始| > 阈值 且 |α-初始| < 阈值。
    """
    pointing_a = 0
    pointing_b = 0
    neutral = 0
    for name in alpha:
        initial = track_a[name][0]
        for alpha_value, beta_value, init_value in zip(
            alpha[name], beta[name], initial, strict=True
        ):
            delta_a = abs(alpha_value - init_value)
            delta_b = abs(beta_value - init_value)
            if delta_a > THRESHOLD and delta_b < THRESHOLD:
                pointing_a += 1
            elif delta_b > THRESHOLD and delta_a < THRESHOLD:
                pointing_b += 1
            else:
                neutral += 1
    return pointing_a, pointing_b, neutral


def plot_param_space(
    alpha: Dict[str, list],
    beta: Dict[str, list],
    track_a: Dict[str, list],
) -> None:
    """绘制参数空间散点图：每个参数一个点，x=α、y=β，按指向方向着色。"""
    points: Dict[str, Tuple[List[float], List[float]]] = {
        "pointing A": ([], []),
        "pointing B": ([], []),
        "neutral": ([], []),
    }
    for name in alpha:
        initial = track_a[name][0]
        for alpha_value, beta_value, init_value in zip(
            alpha[name], beta[name], initial, strict=True
        ):
            delta_a = abs(alpha_value - init_value)
            delta_b = abs(beta_value - init_value)
            if delta_a > THRESHOLD and delta_b < THRESHOLD:
                category = "pointing A"
            elif delta_b > THRESHOLD and delta_a < THRESHOLD:
                category = "pointing B"
            else:
                category = "neutral"
            points[category][0].append(alpha_value)
            points[category][1].append(beta_value)

    fig, ax = plt.subplots(figsize=(8, 8))
    colors = {"pointing A": "red", "pointing B": "blue", "neutral": "gray"}
    for category, (xs, ys) in points.items():
        ax.scatter(xs, ys, s=8, alpha=0.7, color=colors[category], label=category)
    all_values = [
        value for values in alpha.values() for value in values
    ] + [value for values in beta.values() for value in values]
    axis_min = min(all_values)
    axis_max = max(all_values)
    ax.plot([axis_min, axis_max], [axis_min, axis_max], "k--", linewidth=0.8, label="y=x")
    ax.set_xlabel("alpha (A training)")
    ax.set_ylabel("beta (B training)")
    ax.set_title("Parameter space: one dot per parameter")
    ax.legend()
    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "param_space.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


def plot_heatmap(values: Dict[str, list], title: str, filename: str) -> None:
    """按模型结构绘制参数热力图：三个权重矩阵 + 全部 bias。"""
    fig, axes = plt.subplots(1, 4, figsize=(17, 4))
    panels = (
        ("fc1.weight", "fc1.weight (8x64)"),
        ("fc2.weight", "fc2.weight (8x8)"),
        ("fc3.weight", "fc3.weight (2x8)"),
    )
    for ax, (name, panel_title) in zip(axes, panels, strict=False):
        rows, cols = WEIGHT_SHAPES[name]
        matrix = [values[name][index * cols:(index + 1) * cols] for index in range(rows)]
        image = ax.imshow(matrix, aspect="auto", cmap="RdBu_r")
        fig.colorbar(image, ax=ax, fraction=0.046, pad=0.04)
        ax.set_title(panel_title)

    bias_ax = axes[3]
    bias_values = values["fc1.bias"] + values["fc2.bias"] + values["fc3.bias"]
    bias_labels = (
        [f"fc1.b{i}" for i in range(8)]
        + [f"fc2.b{i}" for i in range(8)]
        + [f"fc3.b{i}" for i in range(2)]
    )
    bias_image = bias_ax.imshow([[value] for value in bias_values], aspect="auto", cmap="RdBu_r")
    fig.colorbar(bias_image, ax=bias_ax, fraction=0.046, pad=0.04)
    bias_ax.set_yticks(range(len(bias_values)))
    bias_ax.set_yticklabels(bias_labels, fontsize=6)
    bias_ax.set_title("biases")
    bias_ax.set_xticks([])

    fig.suptitle(title)
    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / filename, dpi=150, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    """读取 α/β/轨迹并输出统计与 PNG。"""
    missing = [name for name in ("alpha.json", "beta.json", "track_a.json")
               if not (OUTPUT_DIR / name).exists()]
    if missing:
        raise SystemExit(f"缺少输出文件 {missing}，请先运行 train_track.py")

    alpha = load_json("alpha.json")
    beta = load_json("beta.json")
    track_a = load_json("track_a.json")

    pointing_a, pointing_b, neutral = compute_pointing_stats(alpha, beta, track_a)
    total = pointing_a + pointing_b + neutral
    print(f"指向 A 的参数数：{pointing_a}")
    print(f"指向 B 的参数数：{pointing_b}")
    print(f"中立参数数：{neutral}")
    print(f"（阈值 |Δ| = {THRESHOLD}，参数总数 = {total}）")

    plot_param_space(alpha, beta, track_a)
    plot_heatmap(alpha, "Alpha (trained on A)", "heatmap_alpha.png")
    plot_heatmap(beta, "Beta (trained on B)", "heatmap_beta.png")
    print("PNG 已保存到 output/：param_space.png / heatmap_alpha.png / heatmap_beta.png")


if __name__ == "__main__":
    main()
