#!/usr/bin/env python3
"""exp35: 量子 Hopfield 式记忆检索——残缺输入恢复 vs 相似度检索(ZH 候选2)

量子 Hopfield(2025 实验已证实 7 倍容量):联想记忆从残缺输入恢复完整记忆。
与 exp29 两能级遗忘同一物理家族(耗散=记忆)。本实验的"量子启发"核心:
**salience 加权 = 基态能量深浅**——高巩固模式 = 深势阱(能量低),低巩固 = 浅势阱。
从残缺输入出发,Hopfield 动力学收敛到"最近的深势阱" = 重要记忆优先恢复。

对比(MaiBot 记忆场景,20 条记忆 × N=80 特征):
- 经典 Hopfield(等权)
- salience 加权 Hopfield(高巩固模式优先)
- 相似度 top-1(现状 A_memorix 式检索基线)
指标:残缺恢复准确率(遮 10/30/50/70%)+ 容量(5~40 条)+ 噪声鲁棒性
"""

import math
import numpy as np

rng = np.random.RandomState(20260818)

N = 80          # 特征维度
M = 20          # 记忆条数


def make_patterns(m, n=N):
    """m 条 ±1 随机模式。"""
    return rng.choice([-1.0, 1.0], size=(m, n))


def classic_weights(patterns):
    """经典 Hopfield 权重(等权,对角归零)。"""
    W = patterns.T @ patterns / len(patterns)
    np.fill_diagonal(W, 0.0)
    return W


def weighted_weights(patterns, salience):
    """salience 加权 Hopfield:W = Σ c_m s_m s_m^T / Σ c。
    c = 巩固强度(exp29 的 c0 概念)——高巩固 = 深势阱。"""
    c = np.array(salience)
    W = np.zeros((N, N))
    for m in range(len(patterns)):
        W += c[m] * np.outer(patterns[m], patterns[m])
    W /= c.sum()
    np.fill_diagonal(W, 0.0)
    return W


def recall(W, x0, max_iter=50):
    """异步更新回忆:收敛到最近记忆(能量下降动力学)。"""
    x = x0.copy()
    for _ in range(max_iter):
        order = rng.permutation(len(x))
        changed = False
        for i in order:
            h = W[i] @ x
            new = 1.0 if h >= 0 else -1.0
            if new != x[i]:
                x[i] = new
                changed = True
        if not changed:
            break
    return x


def corrupt(x, mask_ratio):
    """残缺输入:随机遮掉 mask_ratio 比例的特征(置 0 = 信息缺失)。"""
    x = x.copy()
    mask = rng.random(len(x)) < mask_ratio
    x[mask] = 0.0
    return x


def noise_corrupt(x, noise_std):
    """噪声输入:特征加高斯噪声后重新符号化。"""
    x = x.copy()
    x = np.where(x + rng.normal(0, noise_std, len(x)) >= 0, 1.0, -1.0)
    return x


def similarity_retrieve(x, patterns):
    """现状检索:余弦相似度 top-1(不看残缺,直接找最近)。"""
    scores = patterns @ x / (np.linalg.norm(patterns, axis=1) * np.linalg.norm(x) + 1e-9)
    return int(np.argmax(scores))


def test_recovery(W, patterns, corrupt_fn, trials=50):
    """恢复准确率:残缺/噪声输入能否收敛回原记忆。"""
    ok = 0
    for _ in range(trials):
        m = rng.randint(len(patterns))
        x0 = corrupt_fn(patterns[m].copy())
        out = recall(W, x0)
        if np.array_equal(out, patterns[m]):
            ok += 1
    return ok / trials


if __name__ == '__main__':
    print('=== exp35: 量子 Hopfield 式记忆检索(salience=势阱深浅) ===')
    print('20 条 ±1 记忆 × N=80;残缺/噪声输入恢复 vs 相似度检索\n')

    patterns = make_patterns(M)
    salience = rng.uniform(0.3, 1.0, M)   # 每条记忆的巩固强度(exp29 c0)
    W_classic = classic_weights(patterns)
    W_weighted = weighted_weights(patterns, salience)

    print('--- 残缺恢复准确率(遮掉比例 vs 恢复率) ---')
    print('%-14s %10s %10s %10s %10s' % ('方法', '遮10%', '遮30%', '遮50%', '遮70%'))
    for name, W in [('经典Hopfield', W_classic), ('salience加权', W_weighted)]:
        row = []
        for r_ in [0.1, 0.3, 0.5, 0.7]:
            row.append(test_recovery(W, patterns, lambda x, r=r_: corrupt(x, r)))
        print('%-14s %10.2f %10.2f %10.2f %10.2f' % (name, *row))
    # 相似度基线(残缺时相似度检索也受影响)
    row = []
    for r_ in [0.1, 0.3, 0.5, 0.7]:
        ok = 0
        for _ in range(50):
            m = rng.randint(M)
            x0 = corrupt(patterns[m].copy(), r_)
            if similarity_retrieve(x0, patterns) == m:
                ok += 1
        row.append(ok / 50)
    print('%-14s %10.2f %10.2f %10.2f %10.2f' % ('相似度top-1', *row))

    print()
    print('--- 噪声鲁棒性(加噪强度 vs 恢复率) ---')
    print('%-14s %10s %10s %10s' % ('方法', '噪声0.3', '噪声0.6', '噪声1.0'))
    for name, W in [('经典Hopfield', W_classic), ('salience加权', W_weighted)]:
        row = []
        for ns in [0.3, 0.6, 1.0]:
            row.append(test_recovery(W, patterns, lambda x, s=ns: noise_corrupt(x, s)))
        print('%-14s %10.2f %10.2f %10.2f' % (name, *row))

    # 修正对比:翻转残缺(遮掉的特征随机翻转=错误信息,而非置0)
    def flip_corrupt(x, ratio):
        x = x.copy()
        mask = rng.random(len(x)) < ratio
        x[mask] = -x[mask]
        return x

    print('--- 翻转残缺恢复率(错误信息 vs 恢复率)——公平对比 ---')
    print('%-14s %10s %10s %10s %10s' % ('方法', '翻10%', '翻30%', '翻50%', '翻70%'))
    for name, W in [('经典Hopfield', W_classic), ('salience加权', W_weighted)]:
        row = []
        for r_ in [0.1, 0.3, 0.5, 0.7]:
            row.append(test_recovery(W, patterns, lambda x, r=r_: flip_corrupt(x, r)))
        print('%-14s %10.2f %10.2f %10.2f %10.2f' % (name, *row))
    row = []
    for r_ in [0.1, 0.3, 0.5, 0.7]:
        ok = 0
        for _ in range(50):
            m = rng.randint(M)
            x0 = flip_corrupt(patterns[m].copy(), r_)
            if similarity_retrieve(x0, patterns) == m:
                ok += 1
        row.append(ok / 50)
    print('%-14s %10.2f %10.2f %10.2f %10.2f' % ('相似度top-1', *row))

    print()
    print('--- 容量测试(记忆条数 vs 恢复率,遮30%) ---')
    print('%-10s %10s %10s' % ('条数', '经典', 'salience加权'))
    for m in [5, 10, 20, 30, 40]:
        pats = make_patterns(m)
        Wc = classic_weights(pats)
        Ww = weighted_weights(pats, rng.uniform(0.3, 1.0, m))
        rc = test_recovery(Wc, pats, lambda x: corrupt(x, 0.3), trials=30)
        rw = test_recovery(Ww, pats, lambda x: corrupt(x, 0.3), trials=30)
        print('%-10d %10.2f %10.2f' % (m, rc, rw))

    print()
    print('=== 结论观察 ===')
    print('salience 加权(势阱深浅)是否在残缺恢复上优于经典等权?')
    print('Hopfield 动力学 vs 相似度 top-1:恢复 vs 检索的差异(回忆 vs 匹配)')
