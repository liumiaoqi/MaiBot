"""旋钮实验：训练动画——50 轮训练中参数热力图逐帧变化（旋钮在转动）。

输出：output/train_anim_<arch>_<kind>.gif（A 或 B 训练）

用法：
  python train_anim.py --arch mlp2 --kind A
  python train_anim.py --arch mlp2 --kind B
"""

import argparse
from pathlib import Path
from typing import Dict, List

import torch

from train_track import (
    ARCHITECTURES,
    EPOCHS,
    SEED,
    OUTPUT_DIR,
    init_model,
    make_datasets,
    train_and_track,
)

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


def _param_heatmap(model: torch.nn.Module) -> Dict[str, torch.Tensor]:
    """把模型全部参数展平成热力图所需的块。"""
    blocks: Dict[str, torch.Tensor] = {}
    for name, param in model.named_parameters():
        blocks[name] = param.detach().cpu().clone()
    return blocks


def render_frame(blocks: Dict[str, torch.Tensor], epoch: int, kind: str,
                 ax: plt.Axes) -> None:
    """绘制单帧：全部参数按块排布的热力图。"""
    ax.clear()
    total_rows = sum(max(1, b.shape[0]) for b in blocks.values())
    canvas = torch.full((total_rows, 1), float("nan"))
    row = 0
    labels: List[str] = []
    for name, block in blocks.items():
        flat = block.reshape(block.shape[0], -1).mean(dim=1)
        canvas[row:row + flat.shape[0], 0] = flat
        labels.append(name)
        row += flat.shape[0]
    im = ax.imshow(canvas, cmap="RdBu_r", vmin=-0.6, vmax=0.6, aspect="auto")
    ax.set_yticks([])
    ax.set_title(f"{kind}-training epoch {epoch}/{EPOCHS} — each stripe = one knob", fontsize=12)
    return im


def main() -> None:
    """生成训练动画 GIF。"""
    parser = argparse.ArgumentParser(description="训练过程动画")
    parser.add_argument("--arch", type=str, default="mlp2",
                        help=f"架构: {sorted(ARCHITECTURES)}（默认 mlp2）")
    parser.add_argument("--kind", type=str, default="A", choices=["A", "B"],
                        help="训练数据：A=横条纹，B=竖条纹")
    parser.add_argument("--step", type=int, default=2,
                        help="每 N 轮取一帧（默认 2 = 25 帧）")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    datasets = make_datasets()
    model = init_model(SEED, args.arch)
    x, y = datasets[f"train_{args.kind.lower()}"]
    track = train_and_track(model, x, y, EPOCHS)

    # 用轨迹重建每帧的参数块
    frames: List[Dict[str, torch.Tensor]] = []
    for epoch in range(0, EPOCHS + 1, args.step):
        blocks: Dict[str, torch.Tensor] = {}
        for name, trajectory in track.items():
            values = trajectory[epoch]
            shape = dict(model.named_parameters())[name].shape
            blocks[name] = torch.tensor(values).reshape(shape)
        frames.append(blocks)

    fig, ax = plt.subplots(figsize=(6, max(3, len(frames[0]) * 0.12)))
    rendered = []
    for epoch_idx, blocks in enumerate(frames):
        epoch = epoch_idx * args.step
        im = render_frame(blocks, epoch, args.kind, ax)
        fig.canvas.draw()
        # 转 RGB 数组存帧
        import numpy as np

        rendered.append(np.frombuffer(fig.canvas.buffer_rgba(), dtype=np.uint8)
                        .reshape(fig.canvas.get_width_height()[::-1] + (4,))[:, :, :3])

    # 合成 GIF
    try:
        import imageio.v2 as imageio
    except ImportError:
        raise SystemExit("缺少 imageio：pip install imageio") from None
    out_path = OUTPUT_DIR / f"train_anim_{args.arch}_{args.kind}.gif"
    imageio.mimsave(out_path, rendered, duration=0.25)
    plt.close(fig)
    print(f"训练动画已保存: {out_path}（{len(rendered)} 帧）")


if __name__ == "__main__":
    main()
