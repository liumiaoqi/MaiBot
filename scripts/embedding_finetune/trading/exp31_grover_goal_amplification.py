#!/usr/bin/env python3
"""exp31: Grover 式目标放大——概率放大 vs 确定性贪心(ZH ㉑)

⑭ 目标槽已验证(建立/推进/受挫2次重规划/完成)。本实验:目标选择从
"确定性排序选 top-1"升级为"Grover 式振幅放大":
- 目标池 = 叠加态,每个目标振幅 a_i ∝ √score_i(概率 = |a_i|² = score_i 的线性)
- 振幅放大 ≈ 概率指数化 P(i) ∝ score_i^k(k=2 平方放大 = Grover 一次迭代的近似)
- 受挫目标反相(score×-1)→ 测量概率大降(对应 Grover 标记错误答案)
对比 k=1(线性采样)/ k=2(Grover 平方)/ k=8(强放大)/ 贪心(确定性 top-1):
- 主目标完成速度 / 次目标推进度(偶尔想起别的事)/ 总完成率 / 受挫处理
"""

import math
import numpy as np

rng = np.random.RandomState(20260818)

N_ROUNDS = 120
N_TARGETS = 5
PROGRESS_STEP = 0.08
FRUSTRATE_PROB = 0.08   # 每轮受挫概率(陷阱)
FRUSTRATE_LIMIT = 2     # ⑭ 结论:受挫 2 次重规划


def make_targets():
    """5 个目标,强度各异(0.5-1.0),初始进度随机。"""
    targets = []
    for i in range(N_TARGETS):
        targets.append({
            'id': i,
            'strength': rng.uniform(0.5, 1.0),
            'progress': rng.uniform(0.0, 0.3),
            'frust': 0,
            'done': False,
        })
    return targets


def score(t):
    if t['done']:
        return 0.0
    # 当前紧迫度 = 强度 × 剩余进度
    return t['strength'] * (1.0 - t['progress'])


def pick_grover(targets, k):
    """概率放大选择:k=1 线性采样 / k=2 平方放大(Grover) / k=8 强放大。
    受挫≥2 的目标反相(score 为负 → 概率≈0)。"""
    scores = np.array([score(t) for t in targets])
    # 反相:受挫目标被抑制(标记为"错误答案")
    for i, t in enumerate(targets):
        if t['frust'] >= FRUSTRATE_LIMIT and not t['done']:
            scores[i] = -abs(scores[i])
    # 概率放大:负数归零,再 k 次幂
    probs = np.clip(scores, 0.0, None) ** k
    total = probs.sum()
    if total <= 0:
        return None
    probs = probs / total
    return int(rng.choice(len(targets), p=probs))


def pick_greedy(targets):
    """确定性贪心:直接选最高分(受挫目标已放弃)。"""
    best = None
    best_s = -1
    for i, t in enumerate(targets):
        if t['done']:
            continue
        if t['frust'] >= FRUSTRATE_LIMIT:
            continue
        s = score(t)
        if s > best_s:
            best_s = s
            best = i
    return best


def simulate(strategy, k=None, verbose=False):
    targets = make_targets()
    rounds = 0
    secondary = 0.0  # 次目标推进度累计(非最高初始强度目标)
    main_done_round = None
    main_idx = max(range(N_TARGETS), key=lambda i: targets[i]['strength'])
    for r in range(N_ROUNDS):
        if strategy == 'greedy':
            idx = pick_greedy(targets)
        else:
            idx = pick_grover(targets, k)
        if idx is None:
            break
        t = targets[idx]
        t['progress'] = min(1.0, t['progress'] + PROGRESS_STEP)
        if idx != main_idx:
            secondary += PROGRESS_STEP
        # 受挫事件
        if rng.random() < FRUSTRATE_PROB:
            t['frust'] += 1
        if t['progress'] >= 1.0:
            t['done'] = True
            if idx == main_idx and main_done_round is None:
                main_done_round = r
        rounds += 1
    done_count = sum(1 for t in targets if t['done'])
    return done_count, main_done_round, secondary, rounds


if __name__ == '__main__':
    print('=== exp31: Grover 式目标放大 vs 确定性贪心 ===')
    print('5 目标 × 120 轮 × 50 次模拟;受挫概率 8%,受挫 2 次反相/放弃\n')

    strategies = [
        ('k=1 线性采样', 'grover', 1),
        ('k=2 Grover平方', 'grover', 2),
        ('k=8 强放大', 'grover', 8),
        ('贪心(确定性top-1)', 'greedy', None),
    ]
    print('%-22s %10s %12s %12s %12s' % (
        '策略', '平均完成', '主目标完成轮', '次目标推进', '受挫放弃'))
    print('-' * 70)
    for name, strat, k in strategies:
        res = [simulate(strat, k) for _ in range(50)]
        done = np.mean([r[0] for r in res])
        main_r = np.mean([r[1] for r in res if r[1] is not None])
        sec = np.mean([r[2] for r in res])
        # 受挫放弃数
        abandon = 0
        for _ in range(50):
            ts = make_targets()
            for r in range(N_ROUNDS):
                if strat == 'greedy':
                    idx = pick_greedy(ts)
                else:
                    idx = pick_grover(ts, k)
                if idx is None:
                    break
                if rng.random() < FRUSTRATE_PROB:
                    ts[idx]['frust'] += 1
                if ts[idx]['progress'] >= 1.0:
                    ts[idx]['done'] = True
                if ts[idx]['frust'] >= FRUSTRATE_LIMIT and not ts[idx]['done']:
                    abandon += 1
                    break
        print('%-22s %8.1f %12.1f %12.2f %10d' % (
            name, done, main_r, sec, abandon))

    print()
    print('=== 结论观察 ===')
    print('k=2(Grover 平方)是否在"主目标速度 × 次目标推进"上优于贪心?')
    print('概率放大让低优先目标"偶尔被想起"(人味),贪心永远只做一件事')
