#!/usr/bin/env python3
"""exp1: Braitenberg 车辆——最简单的行为涌现（趋光 vs 避光）v2

v2 修复（2026-08-17，dsh 诊断）：
- v1 bug：传感器按 y 方向上下排列，光源在 x 方向时左右强度几乎相等
  → 马达等速 → 车辆直走 → 穿过光源出界 → 两个连接都"避光"
- v2：传感器按"光源相对车辆的角度差"计算——光源在左/右的偏差驱动转向

Braitenberg 车辆（Valentino Braitenberg, 1984）：
- 2 个传感器（左/右，探测光源方向偏差）
- 2 个马达（左/右轮）
- 连接方式决定行为：
  * 交叉连接（左传感器→右马达）：趋光（vehicle 2a）
  * 直连（左传感器→左马达）：避光（vehicle 2b）

关键认知：**没有"趋光"的代码**——行为从连接结构里涌现出来。
"""

import math

import matplotlib
import matplotlib.pyplot as plt

# 中文字体（Windows：微软雅黑——matplotlib 默认 DejaVu 无中文会乱码）
matplotlib.rcParams["font.sans-serif"] = ["Microsoft YaHei"]
matplotlib.rcParams["axes.unicode_minus"] = False  # 负号正常显示


class LightSource:
    """固定光源。"""

    def __init__(self, x: float = 8.0, y: float = 6.0) -> None:
        self.x = x
        self.y = y


class Vehicle:
    """Braitenberg 车辆 v2。

    wiring: "cross" = 交叉（趋光）/ "direct" = 直连（避光）
    """

    def __init__(self, wiring: str = "cross", x: float = 1.0, y: float = 3.0) -> None:
        self.x = x
        self.y = y
        self.angle = 0.0  # 朝向（弧度，0 = 向右）
        self.speed = 0.12
        self.wiring = wiring
        self.trace_x = [x]
        self.trace_y = [y]

    def _sense(self, light: LightSource) -> tuple[float, float]:
        """传感器：光源相对车辆的角度差（-pi..pi）。

        diff > 0：光源在车辆左侧；diff < 0：光源在右侧。
        返回 (左传感器强度, 右传感器强度)——光源在左时左强，在右时右强。
        """
        angle_to_light = math.atan2(light.y - self.y, light.x - self.x)
        diff = angle_to_light - self.angle
        # 归一化到 [-pi, pi]
        while diff > math.pi:
            diff -= 2 * math.pi
        while diff < -math.pi:
            diff += 2 * math.pi
        # 左传感器 = 光源偏左的程度（diff > 0 时大）；右传感器反之
        left_sense = max(0.0, math.sin(diff))
        right_sense = max(0.0, -math.sin(diff))
        return left_sense, right_sense

    def step(self, light: LightSource) -> None:
        left_sense, right_sense = self._sense(light)

        if self.wiring == "cross":
            # 交叉：左传感器 → 右马达（光源在左 → 右轮快 → 左转 → 追光）
            left_motor = right_sense
            right_motor = left_sense
        else:
            # 直连：左传感器 → 左马达（光源在左 → 左轮快 → 右转 → 远离光）
            left_motor = left_sense
            right_motor = right_sense

        # 差速转向：右轮快 → 左转（angle 增）
        turn = (right_motor - left_motor) * 1.5
        self.angle += turn

        self.x += math.cos(self.angle) * self.speed
        self.y += math.sin(self.angle) * self.speed
        self.trace_x.append(self.x)
        self.trace_y.append(self.y)


def run_simulation(wiring: str, steps: int = 300) -> tuple[list[float], list[float], LightSource]:
    light = LightSource(x=8.0, y=6.0)
    v = Vehicle(wiring=wiring, x=1.0, y=3.0)
    for _ in range(steps):
        v.step(light)
        # 边界：出界就停（防止轨迹飞走）
        if not (0 <= v.x <= 10 and 0 <= v.y <= 10):
            break
    return v.trace_x, v.trace_y, light


def main() -> None:
    print("=" * 60)
    print("exp1 v2: Braitenberg 车辆——行为从连接结构涌现（bug 修复版）")
    print("=" * 60)
    print()
    print("4 个神经元（2 传感器 + 2 马达），没有'趋光'或'避光'的代码——")
    print("只有 4 条连接线的接法不同，行为完全不同。")
    print()

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))

    for i, wiring in enumerate(["cross", "direct"]):
        tx, ty, light = run_simulation(wiring)
        ax = ax1 if i == 0 else ax2
        ax.plot(tx, ty, "b-", linewidth=1.5)
        ax.plot(light.x, light.y, "r*", markersize=18, label="光源")
        ax.plot(tx[0], ty[0], "go", markersize=8, label="起点")
        ax.set_xlim(0, 10)
        ax.set_ylim(0, 10)
        ax.set_aspect("equal")
        ax.set_title("vehicle 2a: 交叉连接 → 趋光" if wiring == "cross" else "vehicle 2b: 直连 → 避光")
        ax.legend()
        ax.grid(True, alpha=0.3)

        final_dist = math.sqrt((tx[-1] - light.x) ** 2 + (ty[-1] - light.y) ** 2)
        behavior = "趋光（靠近光源）" if final_dist < 3 else "避光（远离光源）"
        print(f"{wiring:>6} 连接: 终点距光源 {final_dist:.2f} → {behavior}")

    plt.tight_layout()
    plt.savefig("snn_behavior/exp1_braitenberg.png", dpi=100)
    print()
    print("可视化已保存：snn_behavior/exp1_braitenberg.png")
    print()
    print("关键认知：趋光/避光没有写在代码里——是'连接结构'涌现的")
    print("下一步：加 STDP 可塑性（exp2）——让车辆'学会'趋光")


if __name__ == "__main__":
    main()
