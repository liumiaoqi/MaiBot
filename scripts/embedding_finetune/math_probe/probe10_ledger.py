#!/usr/bin/env python3
"""probe10_ledger.py -- exp32 总饥饿积分的「账本分解」（逐位复刻 rng 流）。

恒等式（每步：先累积后服务，测量在累积后）：
    h_final = SUM(rates)*STEPS - clip_acc_total - serv_actual_total
    总饥饿积分 >= STEPS * SUM(rates)   (每步测量点至少含本步到达 —— 理论下界)

账本四件套: 到达 / 服务位(6*eff) / 实服务 / 空转浪费(服务位-实服务) / 截断
跑法: ../.venv/Scripts/python.exe probe10_ledger.py
"""
import math
import sys

import numpy as np

TRADING = r"E:/Users/lmq/MaiBot/scripts/embedding_finetune/trading"
sys.path.insert(0, TRADING)
import exp32_quantum_annealing_desire as E  # noqa: E402


def simulate_ledger(mode):
    h = np.zeros(E.N_DESIRES)
    current = 0
    total_hunger = 0.0
    max_hunger = 0.0
    switches = 0
    T = 10.0
    clip_acc = 0.0      # 累积截断损失（min(30) 截掉的）
    serv_actual = 0.0   # 实服务（真正减掉的量）
    serv_budget = 0.0   # 服务位（6*eff 的理论上限）

    for step in range(E.STEPS):
        h += np.array(E.RATES)
        raw = h.copy()
        h = np.minimum(h, 30.0)
        clip_acc += float((raw - h).sum())
        total_hunger += h.sum()
        max_hunger = max(max_hunger, h.max())

        if mode == 'greedy':
            nxt = int(np.argmax(h))
        elif mode == 'inertia':
            others = [i for i in range(E.N_DESIRES) if i != current]
            switch = any(h[i] > h[current] * E.INERTIA_BONUS + E.INERTIA_THRESHOLD
                         for i in others)
            nxt = max(others, key=lambda i: h[i]) if switch else current
        elif mode == 'anneal':
            others = [i for i in range(E.N_DESIRES) if i != current]
            gain = max((h[i] - h[current]) for i in others)
            if gain > 0 and E.rng.random() < math.exp(-E.SWITCH_COST / max(T, 0.1)):
                nxt = max(others, key=lambda i: h[i])
            else:
                nxt = current
            T *= 0.985
        elif mode == 'quantum':
            others = [i for i in range(E.N_DESIRES) if i != current]
            switch = any(h[i] > h[current] * E.INERTIA_BONUS + E.INERTIA_THRESHOLD
                         for i in others)
            if switch or E.rng.random() < E.TUNNEL_P:
                nxt = max(others, key=lambda i: h[i] / E.RATES[i])
            else:
                nxt = current

        if nxt != current:
            switches += 1
        eff = E.INERTIA_BONUS if nxt == current else (1.0 - E.SWITCH_COST)
        before = h[nxt]
        h[nxt] = max(0.0, h[nxt] - 6.0 * eff)
        serv_actual += before - h[nxt]
        serv_budget += 6.0 * eff
        current = nxt

    return total_hunger, max_hunger, switches, serv_actual, serv_budget, clip_acc, float(h.sum())


if __name__ == '__main__':
    arr = E.RATES
    print('=== probe10: hunger ledger (bit-exact replay of exp32 rng stream) ===')
    print('arrival/step = %.1f   theoretical floor = STEPS*sum = %.0f' % (sum(arr), E.STEPS*sum(arr)))
    print('')
    print('%-9s %10s %8s %6s %10s %10s %10s %10s %10s' % (
        'mode', 'hunger', 'max', 'sw', 'serv_act', 'serv_bud', 'idle_waste', 'clip', 'h_final'))
    for mode in ['greedy', 'inertia', 'anneal', 'quantum']:
        res = [simulate_ledger(mode) for _ in range(50)]
        th = np.mean([r[0] for r in res])
        mh = np.mean([r[1] for r in res])
        sw = np.mean([r[2] for r in res])
        sa = np.mean([r[3] for r in res])
        sb = np.mean([r[4] for r in res])
        cl = np.mean([r[5] for r in res])
        hf = np.mean([r[6] for r in res])
        print('%-9s %10.0f %8.1f %6.1f %10.1f %10.1f %10.1f %10.1f %10.2f' % (
            mode, th, mh, sw, sa, sb, sb - sa, cl, hf))
        # 恒等式核对: h_final = 252 - clip - serv_act  (对单次运行)
        r0 = res[0]
        rhs = E.STEPS*sum(arr) - r0[5] - r0[3]
        print('   identity check (run1): h_final %.4f  vs  252 - clip - serv = %.4f' % (r0[6], rhs))
