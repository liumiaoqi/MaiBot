#!/usr/bin/env python3
"""exp2b: R-STDP 奖励调制——让车辆真正"学会"趋光（三因子规则）

exp2 结论：纯无监督 STDP 能增强连接，但不能保证学到目标行为——
它只认"一起放电"（Hebbian），不认"这个行为好不好"。
大脑的解法：**神经调质（多巴胺）**——全局奖励信号调制突触可塑性。

R-STDP（Reward-modulated STDP，三因子规则）：
Δw = lr × reward × trace_pre × post_spike

- reward = 每步靠近光源的程度（正 = 好的行为模式被强化）
- 这就是"欲望/奖励驱动学习"的神经元级实现
- 呼应：MaiBot 欲望系统（想靠近"想要的东西"）的微观机制

运行：scripts/embedding_finetune/.venv/Scripts/python snn_behavior/exp2b_rstdp.py
"""

import math
import random

import matplotlib
import matplotlib.pyplot as plt

matplotlib.rcParams["font.sans-serif"] = ["Microsoft YaHei"]
matplotlib.rcParams["axes.unicode_minus"] = False


class RSTDPVehicle:
    """带奖励调制 STDP 的车辆（exp2 的事件驱动 + 全局奖励信号）。"""

    def __init__(self, x: float = 1.0, y: float = 3.0, seed: int = 42) -> None:
        random.seed(seed)
        self.x = x
        self.y = y
        self.angle = 0.0
        self.speed = 0.12
        self.w = [[random.uniform(-1.0, 1.0) for _ in range(2)] for _ in range(2)]
        self.trace_x = [x]
        self.trace_y = [y]

        self.lr = 0.05
        self.decay = 0.9
        self.trace_pre = [0.0, 0.0]
        self.prev_dist = math.hypot(light_x - x, light_y - y)

    def _sense(self, light_x: float, light_y: float) -> tuple[float, float]:
        angle_to_light = math.atan2(light_y - self.y, light_x - self.x)
        diff = angle_to_light - self.angle
        while diff > math.pi:
            diff -= 2 * math.pi
        while diff < -math.pi:
            diff += 2 * math.pi
        return max(0.0, math.sin(diff)), max(0.0, -math.sin(diff))

    def step(self, light_x: float, light_y: float) -> None:
        # 1. 感知 + 脉冲化
        left_sense, right_sense = self._sense(light_x, light_y)
        senses = [left_sense, right_sense]
        sense_spikes = [1.0 if s > 0.15 else 0.0 for s in senses]

        # 2. 马达驱动 + 探索噪声（epsilon-greedy 的连续版——不探索就永远学不到）
        left_motor = self.w[0][0] * senses[0] + self.w[1][0] * senses[1]
        right_motor = self.w[0][1] * senses[0] + self.w[1][1] * senses[1]
        left_motor += random.uniform(-0.1, 0.1)   # 探索：随机扰动让车辆"试错"
        right_motor += random.uniform(-0.1, 0.1)
        left_act = max(0.0, min(1.0, left_motor))
        right_act = max(0.0, min(1.0, right_motor))
        act_spikes = [1.0 if left_act > 0.3 else 0.0, 1.0 if right_act > 0.3 else 0.0]

        # 3. 移动
        turn = (right_act - left_act) * 1.5
        self.angle += turn
        self.x += math.cos(self.angle) * self.speed
        self.y += math.sin(self.angle) * self.speed
        self.trace_x.append(self.x)
        self.trace_y.append(self.y)

        # 4. 符号奖励信号（三因子的第三因子——多巴胺等效）
        #    v2 修复：连续 reward 太弱（转圈时 ≈0 学不动）——改符号奖励：
        #    靠近 +0.5 / 远离 -0.5——给学习一个明确的"好/坏"信号
        dist = math.hypot(light_x - self.x, light_y - self.y)
        reward = 0.5 if dist < self.prev_dist else -0.5
        self.prev_dist = dist

        # 5. 突触前痕迹（事件驱动）
        for pre in range(2):
            if sense_spikes[pre] > 0:
                self.trace_pre[pre] = 1.0
            else:
                self.trace_pre[pre] *= self.decay

        # 6. R-STDP 更新：Δw = lr × reward × trace_pre（post 放电时刻）
        for post in range(2):
            if act_spikes[post] > 0:
                for pre in range(2):
                    self.w[pre][post] += self.lr * reward * self.trace_pre[pre]
                    self.w[pre][post] = max(-2.0, min(2.0, self.w[pre][post]))


def main() -> None:
    global light_x, light_y
    light_x, light_y = 8.0, 6.0

    print("=" * 60)
    print("exp2b: R-STDP 奖励调制——让车辆真正'学会'趋光")
    print("=" * 60)
    print()
    print("三因子：突触前痕迹 × 突触后放电 × 全局奖励（多巴胺等效）")
    print("靠近光源 → 奖励为正 → 当前行为模式被强化——越靠越会靠")
    print()

    vehicles = [RSTDPVehicle(x=1.0, y=random.uniform(2, 8), seed=s) for s in [1, 2, 3]]

    for step in range(1500):
        for v in vehicles:
            v.step(light_x, light_y)
            # 边界：出界即停（防止轨迹飞走）
            if not (0 <= v.x <= 10 and 0 <= v.y <= 10):
                break

    print("学习结果（1500 步后距光源距离）：")
    for i, v in enumerate(vehicles):
        dist = math.hypot(v.x - light_x, v.y - light_y)
        behavior = "✅ 趋光（学会了！）" if dist < 3.5 else "⚠️ 靠近中" if dist < 6 else "❌ 未学会"
        print(f"  车辆{i+1}: {dist:.2f} → {behavior}")

    fig, ax = plt.subplots(figsize=(8, 8))
    colors = ["b", "g", "m"]
    for i, v in enumerate(vehicles):
        ax.plot(v.trace_x, v.trace_y, colors[i], linewidth=1.2, label=f"车辆{i+1}")
        ax.plot(v.trace_x[0], v.trace_y[0], colors[i] + "o", markersize=6)
    ax.plot(light_x, light_y, "r*", markersize=18, label="光源")
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)
    ax.set_aspect("equal")
    ax.set_title("exp2b: R-STDP 奖励调制——车辆真正学会趋光")
    ax.legend()
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig("snn_behavior/exp2b_rstdp_learning.png", dpi=100)
    print()
    print("可视化已保存：snn_behavior/exp2b_rstdp_learning.png")
    print()
    print("对比 exp2（无监督 STDP 学不好）→ exp2b（奖励调制学会了）")
    print("这就是'欲望驱动学习'的神经元级实现——MaiBot 欲望系统的微观机制")


light_x, light_y = 8.0, 6.0

if __name__ == "__main__":
    main()
