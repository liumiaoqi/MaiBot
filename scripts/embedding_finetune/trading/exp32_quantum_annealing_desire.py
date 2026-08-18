#!/usr/bin/env python3
"""exp32: 量子退火欲望演化——隧穿跳出局部最优(ZH ㉓)

⑫ 已验证类型化欲望动力学。本实验:欲望选择从"惯性贪心"(可能卡在
局部最优:一直打游戏,其他欲望累积成大坑)升级为量子退火式:
- 能量景观 = 欲望满足度(切换欲望有成本 = 能量壁垒)
- 经典模拟退火:温度高探索/温度低冻结——后期卡死
- 量子退火:隧穿率 ∝ exp(-壁垒/隧穿强度),与温度无关——低温也保持探索
  ("突然想做别的"——即使当前欲望还行)

3 欲望(生理快累积/社会中/冲动慢)× 168 步(7天×24h)× 50 次模拟:
指标:总饥饿积分(越低越好)/最大峰值(有没有欲望饿成坑)/切换次数
对比:贪心(追最高)/惯性贪心(局部最优陷阱)/模拟退火(后期冻结)/量子退火(隧穿)
"""

import math
import numpy as np

rng = np.random.RandomState(20260818)

STEPS = 168          # 7 天 × 24 小时
N_DESIRES = 3
RATES = [0.8, 0.4, 0.3]     # 生理/社会/冲动 累积率
INERTIA_BONUS = 1.2         # 连续满足同一欲望的效率加成(惯性快乐)
SWITCH_COST = 0.2           # 切换欲望的效率损失(能量壁垒)
INERTIA_THRESHOLD = 5.0     # 惯性贪心:其他欲望超过当前+阈值才切换
TUNNEL_P = 0.05             # 量子隧穿概率(低温也探索)


def simulate(mode):
    h = np.zeros(N_DESIRES)       # 饥饿度
    current = 0
    total_hunger = 0.0
    max_hunger = 0.0
    switches = 0
    T = 10.0                      # 模拟退火温度(线性衰减)

    for step in range(STEPS):
        # 累积饥饿
        h += np.array(RATES)
        h = np.minimum(h, 30.0)   # 饥饿上限
        total_hunger += h.sum()
        max_hunger = max(max_hunger, h.max())

        # 选择欲望
        if mode == 'greedy':
            nxt = int(np.argmax(h))
        elif mode == 'inertia':
            # 惯性贪心:当前欲望 + 惯性收益后仍低于其他欲望-阈值才切换
            others = [i for i in range(N_DESIRES) if i != current]
            switch = any(h[i] > h[current] * INERTIA_BONUS + INERTIA_THRESHOLD
                         for i in others)
            nxt = max(others, key=lambda i: h[i]) if switch else current
        elif mode == 'anneal':
            # 模拟退火:切换概率 exp(-切换成本/T),T 衰减——后期冻结
            others = [i for i in range(N_DESIRES) if i != current]
            gain = max((h[i] - h[current]) for i in others)
            if gain > 0 and rng.random() < math.exp(-SWITCH_COST / max(T, 0.1)):
                nxt = max(others, key=lambda i: h[i])
            else:
                nxt = current
            T *= 0.985              # 降温
        elif mode == 'quantum':
            # 量子退火:惯性规则 + 隧穿(与温度无关的探索)——"突然想做别的"
            # 隧穿目标 = 被冷落最久(h/rate 归一化:饥饿÷累积率 = 多久没满足)
            others = [i for i in range(N_DESIRES) if i != current]
            switch = any(h[i] > h[current] * INERTIA_BONUS + INERTIA_THRESHOLD
                         for i in others)
            if switch or rng.random() < TUNNEL_P:
                nxt = max(others, key=lambda i: h[i] / RATES[i])
            else:
                nxt = current

        # 执行满足
        if nxt != current:
            switches += 1
        eff = INERTIA_BONUS if nxt == current else (1.0 - SWITCH_COST)
        h[nxt] = max(0.0, h[nxt] - 6.0 * eff)   # 满足:饥饿下降(效率加权)
        current = nxt

    return total_hunger, max_hunger, switches


if __name__ == '__main__':
    print('=== exp32: 量子退火欲望演化——隧穿跳出局部最优 ===')
    print('3 欲望(生理0.8/社会0.4/冲动0.3) × 168 步(7天) × 50 次模拟\n')

    print('%-18s %12s %10s %10s' % ('策略', '总饥饿积分', '最大峰值', '切换次数'))
    print('-' * 52)
    for mode, name in [('greedy', '贪心(追最高)'),
                       ('inertia', '惯性贪心(局部陷阱)'),
                       ('anneal', '模拟退火(后期冻结)'),
                       ('quantum', '量子退火(隧穿)')]:
        res = [simulate(mode) for _ in range(50)]
        th = np.mean([r[0] for r in res])
        mh = np.mean([r[1] for r in res])
        sw = np.mean([r[2] for r in res])
        print('%-18s %12.0f %10.1f %10.1f' % (name, th, mh, sw))

    print()
    print('=== 结论观察 ===')
    print('量子退火是否在"总饥饿 × 峰值"上优于惯性贪心(卡死)和模拟退火(冻结)?')
    print('隧穿 = 低温也探索:不牺牲稳定性的多样性')
