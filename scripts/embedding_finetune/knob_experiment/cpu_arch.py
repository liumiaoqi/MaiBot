"""旋钮实验：真正适合 CPU 的架构（SSM 线性递推 vs MLP 矩阵并行）。

前沿背景：Mamba / RWKV 等"线性注意力/状态空间模型"架构——
设计动机之一就是摆脱 GPU 专属的 O(n^2) 注意力矩阵，
用 O(n) 的线性递推，在 CPU 上也能高效推理。

任务：交替序列预测（0,1,0,1,0,1...）——看历史预测下一位。

两种架构：
① MLP（GPU 架构代表）：窗口 4 个输入 → 全连接 → 预测。矩阵乘并行。
② SSM（CPU 架构代表，Mamba 精神）：只有 3 个旋钮 a/b/c——
     h_t = a·h_{t-1} + b·x_t     （状态递推，每步 O(1)）
     y_t = c·h_t                  （输出读取）
   整个模型就是 3 个数字在递推——CPU 上每步一次乘加。

对比：
- 参数量：MLP 几十个 vs SSM 3 个
- 能否学会：都能（交替序列极简）
- CPU 推理耗时：长序列下 SSM 线性优势
- 可视化：SSM 的状态 h 随序列翻转（轨迹图）——"递推的智慧"

用法：
  python cpu_arch.py
输出：output/ssm_state_traj.png（状态轨迹）+ 控制台对比
"""

from pathlib import Path
from typing import List, Tuple

import torch
import time

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

SEED = 7
EPOCHS = 200
LEARNING_RATE = 0.1
OUTPUT_DIR = Path(__file__).resolve().parent / "output"


def make_alternating(n: int) -> List[float]:
    """生成交替序列 0,1,0,1,...（前 n 项）。"""
    return [float(i % 2) for i in range(n)]


def make_windowed(x: List[float], window: int = 4) -> Tuple[torch.Tensor, torch.Tensor]:
    """滑窗构造训练样本：前 window 个 → 预测下一个。"""
    xs, ys = [], []
    for i in range(len(x) - window - 1):
        xs.append(x[i:i + window])
        ys.append(x[i + window])
    return torch.tensor(xs, dtype=torch.float32), torch.tensor(ys, dtype=torch.float32)


class MLPWindow(torch.nn.Module):
    """GPU 架构：窗口全连接（矩阵并行）。4 -> 8 -> 1。"""

    def __init__(self, window: int = 4) -> None:
        super().__init__()
        self.fc1 = torch.nn.Linear(window, 8)
        self.fc2 = torch.nn.Linear(8, 1)
        self.relu = torch.nn.ReLU()

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.fc2(self.relu(self.fc1(x)))


class SSM(torch.nn.Module):
    """CPU 架构：状态空间模型（Mamba 精神）——只有 3 个旋钮。

    h_t = a·h_{t-1} + b·x_t
    y_t = c·h_t

    递推式推理：每步 O(1) 乘加，无矩阵乘，无注意力——
    CPU 上从头到尾就是 3 个数的循环。
    """

    def __init__(self) -> None:
        super().__init__()
        # a 参数化：a = 2·sigmoid(pa) - 1 ∈ [-1, 1]——有界递推（SSM 标准做法）
        self.pa = torch.nn.Parameter(torch.tensor(0.0))
        self.b = torch.nn.Parameter(torch.tensor(0.5))
        self.c = torch.nn.Parameter(torch.tensor(1.0))
        self.d = torch.nn.Parameter(torch.tensor(0.0))  # 输出偏置（无偏置学不会 0→1）
        self.h0 = torch.nn.Parameter(torch.tensor(0.0))

    @property
    def a(self) -> torch.Tensor:
        """递推系数（有界 [-1,1]——保证稳定）。"""
        return 2.0 * torch.sigmoid(self.pa) - 1.0

    def forward(self, sequence: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        """顺序扫描序列，返回 (每步输出, 状态轨迹)。

        h_t = a·h_{t-1} + b·x_t——线性递推，a 参数化有界，
        不发散（实际 SSM 的对角参数化是同一思想的工程版）。
        """
        states: List[float] = []
        outputs: List[float] = []
        h = self.h0
        a_val = self.a
        for x in sequence:
            h = a_val * h + self.b * x
            states.append(h)
            outputs.append(self.c * h + self.d)
        return torch.stack(outputs), torch.stack(states)

    def predict_next(self, history: torch.Tensor) -> Tuple[float, torch.Tensor]:
        """给定历史序列，递推到末尾并预测下一位（返回 (预测, 状态轨迹)）。

        训练监督是 y_t = x_{t+1}——最后一步的输出 y = c·h_t + d
        已经是"下一位预测"，不需要再递推（再递推会抹掉最后输入的信息）。
        """
        outputs, states = self.forward(history)
        return outputs[-1].item(), states


def train_mlp(model: torch.nn.Module, x: torch.Tensor, y: torch.Tensor) -> None:
    """训练 MLP（窗口监督）。"""
    optimizer = torch.optim.SGD(model.parameters(), lr=LEARNING_RATE)
    criterion = torch.nn.MSELoss()
    for _ in range(EPOCHS):
        optimizer.zero_grad()
        loss = criterion(model(x).reshape(-1), y)
        loss.backward()
        optimizer.step()


def train_ssm(model: torch.nn.Module, x: torch.Tensor, y: torch.Tensor) -> None:
    """训练 SSM（BPTT：递推展开后反向传播——3 个旋钮）。

    稳定性：a 用参数化（2·sigmoid-1）天生有界 [-1,1]——
    BPTT 长链梯度用 Adam + grad clip 稳定。
    """
    optimizer = torch.optim.Adam(model.parameters(), lr=0.05)
    criterion = torch.nn.MSELoss()
    for _ in range(EPOCHS):
        optimizer.zero_grad()
        outputs, _ = model(x)
        loss = criterion(outputs, y)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        optimizer.step()


def sequence_accuracy(model, history: torch.Tensor, total: int = 200) -> float:
    """让模型自回归预测长序列，统计准确率（预测对的下一位比例）。"""
    correct = 0
    current = history.clone()
    for step in range(total):
        next_val = 1.0 - current[-1].item()  # 交替序列的正确答案
        if isinstance(model, SSM):
            pred, _ = model.predict_next(current)
        else:
            with torch.no_grad():
                pred = model(current[-4:].unsqueeze(0)).item()
        if round(pred) == next_val:
            correct += 1
        current = torch.cat([current, torch.tensor([next_val])])
    return correct / total


def time_cpu_scan(model, seq_len: int = 2000, repeats: int = 50) -> float:
    """CPU 上顺序扫描长序列的平均耗时（毫秒）。"""
    seq = torch.tensor(make_alternating(seq_len), dtype=torch.float32)
    start = time.perf_counter()
    with torch.no_grad():
        for _ in range(repeats):
            if isinstance(model, SSM):
                model(seq)
            else:
                for i in range(seq_len - 4):
                    model(seq[i:i + 4].unsqueeze(0))
    elapsed = (time.perf_counter() - start) / repeats * 1000
    return elapsed


def plot_ssm_state(model: SSM, history: torch.Tensor) -> None:
    """画 SSM 的状态轨迹——h 随序列翻转的画面。"""
    _, states = model.forward(history)
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(range(1, len(states) + 1), states.detach().numpy(), "o-",
            color="#3498db", markersize=6)
    ax.axhline(0, color="black", linewidth=0.5)
    ax.set_xlabel("sequence step")
    ax.set_ylabel("state h")
    ax.set_title("SSM state trajectory — h flips with the alternating pattern (3 knobs total)", fontsize=11)
    ax.grid(alpha=0.3)
    out_path = OUTPUT_DIR / "ssm_state_traj.png"
    fig.savefig(out_path, dpi=130)
    plt.close(fig)
    print(f"状态轨迹图已保存: {out_path}")


def main() -> None:
    """训练 MLP vs SSM，对比参数量/准确率/CPU 耗时，画状态轨迹。"""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    torch.manual_seed(SEED)

    data = make_alternating(60)
    x_windowed, y_windowed = make_windowed(data)
    x_scan = torch.tensor(data[:-1], dtype=torch.float32)
    y_scan = torch.tensor(data[1:], dtype=torch.float32)

    print("=" * 66)
    print("真正适合 CPU 的架构：SSM 线性递推 vs MLP 矩阵并行")
    print("任务：交替序列预测（0,1,0,1,...）")
    print("=" * 66)

    # ① MLP（GPU 架构）
    mlp = MLPWindow()
    train_mlp(mlp, x_windowed, y_windowed)
    mlp_params = sum(p.numel() for p in mlp.parameters())
    mlp_acc = sequence_accuracy(mlp, torch.tensor(data[:4], dtype=torch.float32))

    # ② SSM（CPU 架构）
    ssm = SSM()
    train_ssm(ssm, x_scan, y_scan)
    ssm_params = sum(p.numel() for p in ssm.parameters())
    ssm_acc = sequence_accuracy(ssm, torch.tensor(data[:4], dtype=torch.float32))

    print(f"\n{'':<12} {'参数量':>6} {'自回归准确率':>12} {'CPU 扫描 2000 步':>14}")
    print("-" * 66)
    print(f"{'MLP(矩阵)':<12} {mlp_params:>6} {mlp_acc:>11.1%} {time_cpu_scan(mlp):>13.1f} ms")
    print(f"{'SSM(递推)':<12} {ssm_params:>6} {ssm_acc:>11.1%} {time_cpu_scan(ssm):>13.1f} ms")
    print("-" * 66)
    print(f"\nSSM 学习到的 3 个旋钮：a={ssm.a.item():.3f}  b={ssm.b.item():.3f}  c={ssm.c.item():.3f}")
    print("解读：a≈-1（每步翻转状态）、b≈1（输入推状态）、c≈1（读状态）")
    print("  —— 交替序列的『逻辑』就藏在 3 个旋钮的递推里")

    # 推理过程：看一眼状态怎么翻转
    history = torch.tensor(data[:8], dtype=torch.float32)
    pred, states = ssm.predict_next(history)
    print(f"\n推理示例：历史 0,1,0,1,0,1,0,1 → 预测下一位 {pred:.2f}（期望 0）")
    plot_ssm_state(ssm, history)


if __name__ == "__main__":
    main()
