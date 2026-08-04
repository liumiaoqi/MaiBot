"""旋钮实验：推理过程可视化——让"推理"变成看得见的画面。

输入一张条纹图，逐步展示信息如何流过模型：
1. 输入像素图（8x8）
2. 每层神经元的激活值（条形图——哪个神经元被点亮）
3. 输出层置信度（横/竖概率）

用法：
  python inference_show.py --arch mlp2 --image A     # 横条纹图
  python inference_show.py --arch mlp2 --image B     # 竖条纹图
  python inference_show.py --arch mlp2 --image noise # 带噪图

输出：output/inference_<arch>_<image>.png
"""

import argparse
from pathlib import Path
from typing import Any, Dict, List

import torch

from train_track import (
    ARCHITECTURES,
    SEED,
    OUTPUT_DIR,
    init_model,
    make_stripe_data,
)

# matplotlib 无显示环境时用 Agg 后端（只保存文件）
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


def load_alpha(arch: str) -> Dict[str, List[float]]:
    """从 output/alpha_<arch>.json 加载 A 训练后的参数终值。"""
    path = OUTPUT_DIR / f"alpha_{arch}.json"
    if not path.exists():
        raise SystemExit(
            f"缺少 {path.name}——请先运行: python train_track.py --arch {arch}"
        )
    import json

    return json.loads(path.read_text(encoding="utf-8"))


def build_model(arch: str) -> torch.nn.Module:
    """构建指定架构并加载 A 训练后的参数。"""
    model = init_model(SEED, arch)
    alpha = load_alpha(arch)
    with torch.no_grad():
        for name, param in model.named_parameters():
            data = alpha.get(name)
            if data is not None:
                param.data = torch.tensor(data, dtype=torch.float32).reshape(param.shape)
    return model


def capture_activations(model: torch.nn.Module, x: torch.Tensor) -> Dict[str, Any]:
    """前向传播并捕获每一层的激活值。"""
    hooks: Dict[str, List[float]] = {}
    handles = []
    for name, module in model.named_modules():
        if isinstance(module, (torch.nn.Linear, torch.nn.Conv2d)):
            handle = module.register_forward_hook(
                lambda m, i, o, n=name: hooks.update(
                    {n: o.detach().cpu().numpy().reshape(-1).tolist()}
                )
            )
            handles.append(handle)
    model.eval()
    with torch.no_grad():
        logits = model(x)
        probs = torch.softmax(logits, dim=1)[0]
    for handle in handles:
        handle.remove()
    return {
        "activations": hooks,
        "logits": logits[0].detach().cpu().numpy().tolist(),
        "probs": probs.detach().cpu().numpy().tolist(),
    }


def plot_inference(arch: str, image_kind: str) -> None:
    """绘制推理过程：输入图 → 各层激活 → 输出置信度。"""
    model = build_model(arch)
    # 生成一张测试图（无噪声，保证清晰）
    image_tensor, _ = make_stripe_data(image_kind, 1, seed=SEED)
    x = image_tensor[0]
    captured = capture_activations(model, x.unsqueeze(0))

    activations = captured["activations"]
    probs = captured["probs"]
    layer_names = list(activations.keys())
    n_layers = len(layer_names)

    # 布局：输入图 + 每层激活 + 输出
    total_panels = 1 + n_layers + 1
    fig, axes = plt.subplots(1, total_panels, figsize=(3.2 * total_panels, 3.2))
    fig.suptitle(
        f"推理过程可视化：{arch} 判断『{('横条纹' if image_kind == 'A' else '竖条纹')}』",
        fontsize=14,
    )

    # 1. 输入图
    ax = axes[0]
    ax.imshow(x.reshape(8, 8), cmap="gray", vmin=0, vmax=1)
    ax.set_title("输入\n(8x8 像素)")
    ax.set_xticks([])
    ax.set_yticks([])

    # 2. 每层激活
    for idx, name in enumerate(layer_names, start=1):
        ax = axes[idx]
        values = activations[name]
        if isinstance(values, list) and len(values) > 0:
            colors = ["#e74c3c" if v > 0 else "#3498db" for v in values]
            ax.bar(range(len(values)), values, color=colors)
            ax.axhline(0, color="black", linewidth=0.5)
        ax.set_title(f"{name}\n({len(values)} 个神经元)")
        ax.set_xticks([])

    # 3. 输出置信度
    ax = axes[-1]
    labels = ["横条纹", "竖条纹"]
    colors = ["#2ecc71" if i == int(image_kind == "B") else "#95a5a6" for i in range(2)]
    bars = ax.bar(labels, probs, color=colors)
    ax.set_ylim(0, 1)
    ax.set_title("输出置信度")
    for bar, prob in zip(bars, probs, strict=True):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.02,
                f"{prob:.2f}", ha="center", fontsize=11)

    verdict = "横条纹" if probs[0] > probs[1] else "竖条纹"
    correct = verdict == ("横条纹" if image_kind == "A" else "竖条纹")
    fig.text(
        0.5, 0.01,
        f"模型判断: {verdict}（{'✅ 正确' if correct else '❌ 错误'}）",
        ha="center", fontsize=13,
        color="#2ecc71" if correct else "#e74c3c",
    )

    out_path = OUTPUT_DIR / f"inference_{arch}_{image_kind}.png"
    plt.tight_layout(rect=(0, 0.04, 1, 0.94))
    fig.savefig(out_path, dpi=130)
    plt.close(fig)
    print(f"推理过程图已保存: {out_path}")


def main() -> None:
    """按参数绘制推理过程图。"""
    parser = argparse.ArgumentParser(description="推理过程可视化")
    parser.add_argument("--arch", type=str, default="mlp2",
                        help=f"架构: {sorted(ARCHITECTURES)}（默认 mlp2）")
    parser.add_argument("--image", type=str, default="A", choices=["A", "B"],
                        help="输入图类型：A=横条纹，B=竖条纹")
    args = parser.parse_args()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    plot_inference(args.arch, args.image)


if __name__ == "__main__":
    main()
