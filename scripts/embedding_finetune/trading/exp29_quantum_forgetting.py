#!/usr/bin/env python3
"""exp29: 量子遗忘曲线——振幅阻尼/两能级 vs 现状 granular_decay vs 复习强化

问题(ZH ⑱):人类遗忘是 Ebbinghaus 曲线(先快后慢,双指数),现状 granular_decay
是纯指数衰减(每单位时间固定比例)+ 地板。量子物理提供两个自然模型:
- 振幅阻尼信道(|1>→|0> 衰减):P(1) 按 (1-p)^t 指数衰减——纯指数,和现状同构?
- 两能级系统(短期态 S 快衰减 + 长期态 L 慢衰减,复习=巩固 S→L):天然双指数——
  短期记忆快速蒸发(海马体),长期记忆慢速保留(皮层),复习=巩固(海马体→皮层)——
  这个模型天然产生 Ebbinghaus 形状!

对照:
1. granular 现状: 指数 + 地板(base·exp(-t/S),floor)
2. quantum_ampdamp: P(1)=(1-p)^t 指数(振幅阻尼)
3. quantum_2level: S=base·exp(-t/τs) + L(巩固累积,慢衰减 τl)——无复习时 S 蒸发 L 保留
4. 复习变体: 间隔复习(在 S 将尽未尽时复习,加固 L)

指标:无复习遗忘曲线 vs Ebbinghaus 参考拟合 + 复习留存 + 重要记忆长期留存。
"""

import math
import numpy as np

# 经典 Ebbinghaus 遗忘数据点(小时, 保留率)
EBB = [(0, 1.00), (0.33, 0.58), (1, 0.44), (9, 0.36),
       (24, 0.33), (48, 0.28), (144, 0.25), (744, 0.21)]

DAYS = 31
HOURS = np.array([h for h, _ in EBB])


def granular(s0, S=24.0, floor=0.2, days=DAYS):
    """现状:纯指数衰减 + 地板,无复习。"""
    curve = []
    for t in range(days + 1):
        curve.append(max(floor, s0 * math.exp(-t / S)))
    return curve


def quantum_ampdamp(s0, p=0.05, floor=0.2, days=DAYS):
    """量子振幅阻尼:P(1) 按 (1-p)^t 衰减(等效指数),0 是基态(地板)。"""
    curve = []
    for t in range(days + 1):
        curve.append(max(floor, s0 * (1.0 - p) ** t))
    return curve


def quantum_2level(s0, tau_s=1.0, tau_l=200.0, c0=0.1, days=DAYS):
    """量子两能级:S 短期态快衰减(τs 天),L 长期态慢衰减(τl 天)。
    初始巩固 c0(首次学习时已有部分长期痕迹),无复习时 S 蒸发 L 保留。
    """
    S = s0 * 0.7
    L = s0 * c0
    curve = []
    for t in range(days + 1):
        curve.append(S * math.exp(-t / tau_s) + L * math.exp(-t / tau_l))
    return curve


def quantum_2level_review(s0, review_days, tau_s=1.0, tau_l=200.0,
                          c0=0.1, consolidate=0.5, days=DAYS):
    """两能级 + 间隔复习:复习日 S 重置(重新激发)+ 巩固增量(consolidate)。
    总强度 = S + L;复习在 S 将尽未尽时进行(间隔效应)。
    """
    S = s0 * 0.7
    L = s0 * c0
    curve = []
    for t in range(days + 1):
        if t in review_days:
            S = s0 * 0.7          # 复习:重新激发短期态
            L += s0 * consolidate  # 复习:巩固到长期态
        curve.append(S * math.exp(-t / tau_s) + L * math.exp(-t / tau_l))
    return curve


def fit_ebbinghaus(curve_fn, **kw):
    """取曲线在 Ebbinghaus 时间点的值,算与参考的 MAE。"""
    vals = []
    for h, ref in EBB:
        day = h / 24.0
        # 线性插值取曲线值
        i0 = int(day)
        i1 = min(i0 + 1, len(curve_fn) - 1)
        frac = day - i0
        v = curve_fn[i0] * (1 - frac) + curve_fn[i1] * frac
        vals.append((v, ref))
    return sum(abs(v - r) for v, r in vals) / len(vals)


if __name__ == '__main__':
    print('=== exp29: 量子遗忘曲线(振幅阻尼/两能级 vs 现状 vs 复习) ===')
    print('参考:Ebbinghaus 遗忘数据(1h 44% / 1d 33% / 6d 25% / 31d 21%)\n')

    # 1. 无复习遗忘曲线拟合
    s0 = 1.0
    g_curve = granular(s0)
    qa_curve = quantum_ampdamp(s0)
    q2_curve = quantum_2level(s0)
    print('--- 无复习:遗忘曲线 vs Ebbinghaus 拟合(MAE 越低越像人) ---')
    for name, curve in [('granular 现状(指数+地板)', g_curve),
                        ('quantum 振幅阻尼(指数)', qa_curve),
                        ('quantum 两能级(S快+L慢)', q2_curve)]:
        mae = fit_ebbinghaus(curve)
        print('%-28s MAE = %.4f   31天留存 %.2f%%' % (name, mae,
              curve[31] * 100))

    print()
    print('--- 各模型 31 天曲线采样 ---')
    print('%-28s %8s %8s %8s %8s' % ('模型', '1天', '2天', '6天', '31天'))
    for name, curve in [('granular 现状', g_curve), ('ampdamp', qa_curve),
                        ('两能级', q2_curve)]:
        print('%-28s %8.3f %8.3f %8.3f %8.3f' % (
            name, curve[1], curve[2], curve[6], curve[31]))

    # 2. 复习效果(间隔复习 vs 无复习)
    print()
    print('--- 复习效果(两能级:复习 = 重新激发 S + 巩固 L) ---')
    no_review = quantum_2level(s0)
    review_1 = quantum_2level_review(s0, review_days={1}, consolidate=0.3)
    review_spaced = quantum_2level_review(s0, review_days={1, 3, 7, 14},
                                          consolidate=0.3)
    print('%-28s %8s %8s' % ('策略', '7天留存', '31天留存'))
    for name, c in [('无复习', no_review), ('复习1次(第1天)', review_1),
                    ('间隔复习(1/3/7/14天)', review_spaced)]:
        print('%-28s %8.3f %8.3f' % (name, c[7], c[31]))

    # 3. 重要记忆长期留存(不提及但高 salience——⑨ 的诉求)
    print()
    print('--- 重要记忆(salience=1.0)不提及 100 天的留存 ---')
    # 两能级:初始巩固高(重要记忆学习时巩固更多);用 days=100 的曲线
    important = quantum_2level(s0, c0=0.5, days=100)
    normal = quantum_2level(s0, c0=0.1, days=100)
    print('普通记忆(c0=0.1) 100天: %.2f%%' % (normal[100] * 100))
    print('重要记忆(c0=0.5) 100天: %.2f%%' % (important[100] * 100))
    print('现状 granular(地板0.2) 100天: %.2f%%' % (granular(s0, days=100)[100] * 100))

    print()
    print('=== 结论观察 ===')
    print('两能级(S快+L慢)天然产生 Ebbinghaus 先快后慢;复习=巩固到 L;'
          '重要记忆靠初始巩固(c0)而非提及频率——三个诉求一次满足')
