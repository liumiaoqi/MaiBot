"""旋钮实验：XOR 逻辑推理——让极小模型"会逻辑"。

经典问题：XOR（异或）是单层感知机学不会的（卡在 50% 猜硬币），
加一个隐藏层就学会——本脚本直观展示"隐藏层就是干这个的"。

能力：输入两个二进制位 (x1, x2)，输出异或结果——
  00→0、01→1、10→1、11→0（"两个不一样就是 1"）

包含：
1. 单层 vs 双层对比：单层卡 50%，双层学会（隐藏层的作用）
2. 推理过程可视化：输入 01 → 隐藏层 4 个神经元激活 → 输出
3. 真值表：4 种输入全测

用法：
  python xor_logic.py
输出：output/xor_inference.png（推理过程图）
"""

from pathlib import Path
from typing import List, Tuple

import torch

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

SEED = 42
EPOCHS = 3000
LEARNING_RATE = 0.3
OUTPUT_DIR = Path(__file__).resolve().parent / "output"

# XOR 真值表：输入 (x1, x2) -> 期望输出
XOR_DATA: List[Tuple[List[float], float]] = [
    ([0.0, 0.0], 0.0),
    ([0.0, 1.0], 1.0),
    ([1.0, 0.0], 1.0),
    ([1.0, 1.0], 0.0),
]


class XORNet(torch.nn.Module):
    """双层 XOR 网络：2 -> 4 -> 1（sigmoid）。

    隐藏层 4 个神经元——XOR 的可分性靠隐藏层实现
    （单层感知机线性可分不了 XOR）。
    """

    def __init__(self, hidden: int = 4, single_layer: bool = False) -> None:
        super().__init__()
        if single_layer:
            self.hidden = None
            self.out = torch.nn.Linear(2, 1)
        else:
            self.hidden = torch.nn.Linear(2, hidden)
            self.out = torch.nn.Linear(hidden, 1)
        self.sigmoid = torch.nn.Sigmoid()

    def forward(self, x: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor | None]:
        """前向传播，返回 (输出, 隐藏层激活或 None)。"""
        if self.hidden is None:
            return self.sigmoid(self.out(x)), None
        hidden_act = self.sigmoid(self.hidden(x))
        out = self.sigmoid(self.out(hidden_act))
        return out, hidden_act


def train(model: torch.nn.Module) -> List[float]:
    """在 4 个 XOR 样本上训练，返回每轮损失。"""
    x = torch.tensor([[a, b] for (a, b), _ in XOR_DATA], dtype=torch.float32)
    y = torch.tensor([[label] for _, label in XOR_DATA], dtype=torch.float32)
    optimizer = torch.optim.SGD(model.parameters(), lr=LEARNING_RATE)
    criterion = torch.nn.BCELoss()
    losses: List[float] = []
    for _ in range(EPOCHS):
        optimizer.zero_grad()
        out, _ = model(x)
        loss = criterion(out, y)
        loss.backward()
        optimizer.step()
        losses.append(loss.item())
    return losses


def truth_table(model: torch.nn.Module) -> List[Tuple[List[float], float, float]]:
    """测 4 种输入，返回 (输入, 期望, 模型输出)。"""
    results: List[Tuple[List[float], float, float]] = []
    model.eval()
    with torch.no_grad():
        for inputs, expected in XOR_DATA:
            x = torch.tensor([inputs], dtype=torch.float32)
            out, _ = model(x)
            results.append((inputs, expected, out.item()))
    return results


def plot_inference(model: torch.nn.Module) -> None:
    """可视化 XOR 推理过程：输入 → 隐藏层激活 → 输出。"""
    fig, axes = plt.subplots(1, 4, figsize=(14, 3.6))
    fig.suptitle("XOR inference — hidden layer maps 4 inputs to separable activation patterns", fontsize=12)

    for ax, (inputs, expected) in zip(axes, XOR_DATA, strict=True):
        x = torch.tensor([inputs], dtype=torch.float32)
        with torch.no_grad():
            out, hidden = model(x)

        # 左侧：输入两位
        ax.barh([0, 1], inputs, color=["#3498db", "#3498db"])
        ax.set_yticks([0, 1])
        ax.set_yticklabels(["x1", "x2"])
        ax.set_xlim(0, 1.2)
        ax.set_title(f"输入 {int(inputs[0])}{int(inputs[1])}\n期望={int(expected)}")

        # 中间：隐藏层激活（4 个神经元）
        if hidden is not None:
            hidden_values = hidden[0].numpy()
            for i, value in enumerate(hidden_values):
                ax.text(1.05, i - 0.3, f"{value:.2f}", fontsize=8)
            ax.barh([i + 2.5 for i in range(4)], hidden_values,
                    color=["#e74c3c" if v > 0.5 else "#95a5a6" for v in hidden_values])
            ax.text(1.05, 6.2, "hidden act", fontsize=8)

        # 右侧：输出
        ax.text(1.05, -1.2, f"输出={out.item():.2f}\n→ {int(round(out.item()))}",
                fontsize=10, color="#2ecc71" if round(out.item()) == expected else "#e74c3c")
        ax.set_xlim(0, 2.2)

    out_path = OUTPUT_DIR / "xor_inference.png"
    plt.tight_layout(rect=(0, 0, 1, 0.92))
    fig.savefig(out_path, dpi=130)
    plt.close(fig)
    print(f"XOR 推理过程图已保存: {out_path}")


def main() -> None:
    """训练单层/双层对比 + 打印真值表 + 推理可视化。"""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    torch.manual_seed(SEED)

    print("=" * 60)
    print("XOR 逻辑推理实验")
    print("=" * 60)

    # 1. 单层感知机（无隐藏层）——经典失败
    single = XORNet(single_layer=True)
    train(single)
    table = truth_table(single)
    correct = sum(1 for _, expected, out in table if round(out) == expected)
    print("\n① 单层感知机（2 → 1，无隐藏层）：")
    for inputs, expected, out in table:
        mark = "✅" if round(out) == expected else "❌"
        print(f"   {int(inputs[0])}{int(inputs[1])} → 模型输出 {out:.2f}（期望 {int(expected)}）{mark}")
    print(f"   正确率 {correct}/4——单层学不会 XOR（线性不可分），这是神经网络教科书经典结论")

    # 2. 双层网络（2 → 4 → 1）——学会
    net = XORNet(hidden=4)
    train(net)
    table = truth_table(net)
    correct = sum(1 for _, expected, out in table if round(out) == expected)
    print("\n② 双层网络（2 → 4 → 1，含隐藏层）：")
    for inputs, expected, out in table:
        mark = "✅" if round(out) == expected else "❌"
        print(f"   {int(inputs[0])}{int(inputs[1])} → 模型输出 {out:.2f}（期望 {int(expected)}）{mark}")
    print(f"   正确率 {correct}/4——加隐藏层就学会（隐藏层 = 把线性不可分变成可分）")

    # 3. 推理过程可视化
    plot_inference(net)

    print("\n结论：XOR 的『智能』来自隐藏层——")
    print("  隐藏层把 4 个输入映射成 4 个神经元的激活模式，")
    print("  输出层只需要在激活模式上做一条简单分割线。")


if __name__ == "__main__":
    main()
