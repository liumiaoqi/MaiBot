#!/usr/bin/env python3
"""exp0: LIF 神经元基础——累积-泄漏-阈值-放电（事件驱动的第一课）

对应认知（2026-08-17 聊的神经元机制）：
- 事件驱动：没输入就不放电，有输入才累积
- 泄漏：膜电位随时间衰减（beta < 1）——不持续的输入会漏掉
- 阈值放电：累积超过阈值 → 输出脉冲 → 电位复位

运行：scripts/embedding_finetune/.venv/Scripts/python snn_behavior/exp0_lif_basics.py
"""

import matplotlib
import matplotlib.pyplot as plt
import snntorch as snn
import torch

# 中文字体（Windows：微软雅黑——matplotlib 默认 DejaVu 无中文会乱码）
matplotlib.rcParams["font.sans-serif"] = ["Microsoft YaHei"]
matplotlib.rcParams["axes.unicode_minus"] = False  # 负号正常显示

def demo_single_neuron() -> None:
    """单个 LIF 神经元：不同输入强度下的放电行为。"""
    print("=" * 60)
    print("实验 0a：单个 LIF 神经元——输入强度 vs 放电频率")
    print("=" * 60)

    lif = snn.Leaky(beta=0.9, threshold=1.0)
    steps = 50
    t = list(range(steps))

    for strength in [0.2, 0.5, 1.2]:
        # 恒定输入脉冲序列
        inp = torch.ones(steps, 1, 1) * strength
        mem = lif.init_leaky()
        spikes = []
        for step in range(steps):
            spk, mem = lif(inp[step], mem)
            spikes.append(spk.item())
        fire_times = [i for i, s in enumerate(spikes) if s > 0]
        print(f"输入强度 {strength}: 放电 {len(fire_times)} 次，时刻 {fire_times[:8]}{'...' if len(fire_times) > 8 else ''}")

    print()
    print("观察：强度 0.2 不放电（累积不到阈值）；0.5 间歇放电；1.2 稳定放电")
    print("这就是'事件驱动'：输入弱 → 静默；输入强 → 放电（对应神经元六机制中的事件驱动）")


def demo_beta_effect() -> None:
    """beta（泄漏率）的影响：记忆 vs 遗忘。"""
    print("=" * 60)
    print("实验 0b：beta 泄漏率——记忆的遗忘曲线")
    print("=" * 60)

    steps = 30
    # 只在第 5 步给一个脉冲，然后看电位衰减
    inp = torch.zeros(steps, 1, 1)
    inp[5] = 1.5  # 单个强脉冲

    for beta in [0.5, 0.9, 0.99]:
        lif = snn.Leaky(beta=beta, threshold=100)  # 阈值设很大，只看电位衰减
        mem = lif.init_leaky()
        trace = []
        for step in range(steps):
            spk, mem = lif(inp[step], mem)
            trace.append(mem.item())
        print(f"beta={beta}: 第5步脉冲后，第15步电位={trace[14]:.3f}，第25步={trace[24]:.3f}")

    print()
    print("观察：beta 小（0.5）= 忘得快（泄漏快）；beta 大（0.99）= 记得久")
    print("这就是'积累性/遗忘'的神经元级实现——对应你 lab 里 forgetting_curve 实验的微观机制")


def demo_visual() -> None:
    """可视化：膜电位轨迹 + 放电脉冲。"""
    lif = snn.Leaky(beta=0.9, threshold=1.0)
    steps = 50
    inp = torch.zeros(steps, 1, 1)
    # 第 10-15 步连续输入（模拟持续刺激）
    inp[10:16] = 0.6

    mem = lif.init_leaky()
    mem_trace = []
    spike_trace = []
    for step in range(steps):
        spk, mem = lif(inp[step], mem)
        mem_trace.append(mem.item())
        spike_trace.append(spk.item())

    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(10, 8), sharex=True)
    ax1.plot(range(steps), [i.item() for i in inp], color="gray")
    ax1.set_ylabel("输入")
    ax1.set_title("LIF 神经元：输入 → 膜电位 → 放电")
    ax2.plot(range(steps), mem_trace, color="blue")
    ax2.axhline(1.0, color="red", linestyle="--", label="阈值 1.0")
    ax2.set_ylabel("膜电位")
    ax2.legend()
    ax3.stem(range(steps), spike_trace)
    ax3.set_ylabel("放电脉冲")
    ax3.set_xlabel("时间步")
    plt.tight_layout()
    plt.savefig("snn_behavior/exp0_visual.png", dpi=100)
    print()
    print("可视化已保存：snn_behavior/exp0_visual.png")
    print("看膜电位曲线：输入期间爬升 → 超阈值 → 放电 → 复位 → 泄漏下降")


if __name__ == "__main__":
    demo_single_neuron()
    print()
    demo_beta_effect()
    print()
    demo_visual()
    print()
    print("实验 0 完成——你已经亲手摸到了'事件驱动 + 泄漏 + 阈值放电'")
