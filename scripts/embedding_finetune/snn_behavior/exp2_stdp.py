#!/usr/bin/env python3
"""exp2: STDP 可塑性——让车辆"学会"趋光（积累性机制落地）

STDP（Spike-Timing-Dependent Plasticity，脉冲时序依赖可塑性）：
- 突触前神经元先放电 → 突触后神经元随后放电 → 该连接**增强**（长时程增强 LTP）
- 突触后先放电 → 突触前后放电 → 该连接**减弱**（长时程抑制 LTD）
- 一句话："一起放电的神经元连在一起"（fire together, wire together——Hebbian 规则）

对应神经元六机制中的"积累性"：用过的连接自动变强——越用越熟。
本实验：初始随机连接权重 → 车辆乱走 → STDP 学习 → 学会趋光。
"""

import math
import random

import matplotlib
import matplotlib.pyplot as plt

# 中文字体（Windows：微软雅黑）
matplotlib.rcParams["font.sans-serif"] = ["Microsoft YaHei"]
matplotlib.rcParams["axes.unicode_minus"] = False


class STDPVehicle:
    """带 STDP 可塑性的 Braitenberg 车辆。

    与 exp1 的区别：4 条连接的权重不是固定的（0 或 1），
    而是**学习出来的**——从随机权重开始，STDP 规则逐步调整。
    """

    def __init__(self, x: float = 1.0, y: float = 3.0, seed: int = 42) -> None:
        random.seed(seed)
        self.x = x
        self.y = y
        self.angle = 0.0
        self.speed = 0.12

        # 4 条连接权重：w[传感器][马达]——初始随机（-1..1）
        # 正权重 = 兴奋性连接；负权重 = 抑制性连接
        self.w = [[random.uniform(-1.0, 1.0) for _ in range(2)] for _ in range(2)]
        self.w_history = []  # 记录权重演化（学完之后看）

        self.trace_x = [x]
        self.trace_y = [y]

        # STDP 参数
        self.lr = 0.05      # 学习率
        self.decay = 0.9    # 突触前/后痕迹的衰减（短期记忆）
        self.trace_pre = [0.0, 0.0]    # 传感器（突触前）放电痕迹
        self.trace_post = [0.0, 0.0]   # 马达（突触后）放电痕迹

    def _sense(self, light_x: float, light_y: float) -> tuple[float, float]:
        """同 exp1：光源相对角度差 → 左右传感器强度。"""
        angle_to_light = math.atan2(light_y - self.y, light_x - self.x)
        diff = angle_to_light - self.angle
        while diff > math.pi:
            diff -= 2 * math.pi
        while diff < -math.pi:
            diff += 2 * math.pi
        left_sense = max(0.0, math.sin(diff))
        right_sense = max(0.0, -math.sin(diff))
        return left_sense, right_sense

    def step(self, light_x: float, light_y: float) -> None:
        """一步：感知 → 脉冲化 → 加权驱动 → 移动 → 事件驱动 STDP 更新。

        v2 修复（2026-08-17，dsh 诊断）：
        - v1 bug：连续值 STDP 在稳态时数学自相抵消（trace ≈ sense/(1-decay)，
          两项相减恒为 0）——权重永不变化，"学习"不成立
        - v2：脉冲化（阈值放电 0/1）+ 事件驱动（只有 post 放电时刻才更新权重）
          ——这才是真实 STDP 的形态，也呼应"神经元六机制"中的事件驱动
        """

        # 1. 感知（传感器连续强度 → 阈值脉冲化）
        left_sense, right_sense = self._sense(light_x, light_y)
        senses = [left_sense, right_sense]
        # 阈值放电：强度超过阈值 → 发一个脉冲（1），否则静默（0）
        sense_spikes = [1.0 if s > 0.25 else 0.0 for s in senses]

        # 2. 马达驱动 = 权重 × 传感器强度（加权求和，连续值驱动运动）
        left_motor = self.w[0][0] * senses[0] + self.w[1][0] * senses[1]
        right_motor = self.w[0][1] * senses[0] + self.w[1][1] * senses[1]
        left_act = max(0.0, min(1.0, left_motor))
        right_act = max(0.0, min(1.0, right_motor))
        act_spikes = [1.0 if left_act > 0.5 else 0.0, 1.0 if right_act > 0.5 else 0.0]

        # 3. 移动（差速转向）
        turn = (right_act - left_act) * 1.5
        self.angle += turn
        self.x += math.cos(self.angle) * self.speed
        self.y += math.sin(self.angle) * self.speed
        self.trace_x.append(self.x)
        self.trace_y.append(self.y)

        # 4. 事件驱动 STDP（核心：只有"放电事件"时刻才更新）
        #    突触前痕迹：pre 放电 → 痕迹置 1；否则衰减（短期记忆）
        for pre in range(2):
            if sense_spikes[pre] > 0:
                self.trace_pre[pre] = 1.0
            else:
                self.trace_pre[pre] *= self.decay

        #    突触后放电时刻：看 pre 的痕迹——pre 刚放电过 → 该连接增强
        #    （fire together, wire together——一起放电的神经元连在一起）
        for post in range(2):
            if act_spikes[post] > 0:
                for pre in range(2):
                    self.w[pre][post] += self.lr * self.trace_pre[pre]
                    # 权重夹在 [-2, 2]（防爆）
                    self.w[pre][post] = max(-2.0, min(2.0, self.w[pre][post]))
                self.trace_post[post] = 1.0
            else:
                self.trace_post[post] *= self.decay

    def weight_snapshot(self) -> tuple[float, float, float, float]:
        """返回 4 条连接权重的快照。"""
        return (self.w[0][0], self.w[1][0], self.w[0][1], self.w[1][1])


def main() -> None:
    print("=" * 60)
    print("exp2: STDP 可塑性——让车辆'学会'趋光")
    print("=" * 60)
    print()

    light_x, light_y = 8.0, 6.0

    # 三辆车：随机起点权重，跑学习
    vehicles = []
    for seed in [1, 2, 3]:
        v = STDPVehicle(x=1.0, y=random.uniform(2, 8), seed=seed)
        vehicles.append(v)

    # 学习阶段：跑 600 步（每 150 步记录一次权重快照）
    print("权重演化（w_左传左马达, w_右传左马达, w_左传右马达, w_右传右马达）：")
    for step in range(600):
        for v in vehicles:
            v.step(light_x, light_y)
        if step in [0, 149, 299, 599]:
            for i, v in enumerate(vehicles):
                w = v.weight_snapshot()
                print(f"  车辆{i+1} 第{step+1}步: {w[0]:+.2f} {w[1]:+.2f} | {w[2]:+.2f} {w[3]:+.2f}")

    # 结果：看每辆车最终离光源多远（学到趋光了没）
    print()
    print("学习结果（600 步后距光源距离）：")
    for i, v in enumerate(vehicles):
        dist = math.sqrt((v.x - light_x) ** 2 + (v.y - light_y) ** 2)
        behavior = "趋光（学会了）" if dist < 4 else "未学会（还在游荡）"
        print(f"  车辆{i+1}: {dist:.2f} → {behavior}")

    # 可视化：三条学习轨迹
    fig, ax = plt.subplots(figsize=(8, 8))
    colors = ["b", "g", "m"]
    for i, v in enumerate(vehicles):
        ax.plot(v.trace_x, v.trace_y, colors[i], linewidth=1.2, label=f"车辆{i+1}")
        ax.plot(v.trace_x[0], v.trace_y[0], colors[i] + "o", markersize=6)
    ax.plot(light_x, light_y, "r*", markersize=18, label="光源")
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)
    ax.set_aspect("equal")
    ax.set_title("exp2: STDP 学习后的轨迹——从乱走到趋光")
    ax.legend()
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig("snn_behavior/exp2_stdp_learning.png", dpi=100)
    print()
    print("可视化已保存：snn_behavior/exp2_stdp_learning.png")
    print()
    print("关键认知：权重不是设计出来的，是'用'出来的——")
    print("一起放电的连接自动变强（积累性）——这就是'越用越熟'的神经元级实现")


if __name__ == "__main__":
    main()
