#!/usr/bin/env python3
"""probe15_phase_audit.py -- exp34 QSNN 的相位/采样语义审计。

A) 三种动作语义对照（"量子测量"本义 vs 现实现 vs argmax）：
   - 本义：每路独立 Bernoulli(sin^2(phase))；但"多路同时发放"在原设计里没有定义（语义空白）
   - 现实现：ps = sin^2 + 噪声；>0.1 的候选；e^{ps} 归一后采样（softmax 压平？）
   - argmax：确定性竞争
B) 训练轨迹审计（插桩 601088 + 一个种子）：
   - phase 落在梯度死区（|sin 2*phase| 小）的比例
   - 动作分布 / 候选数分布（采样被压平的证据）
   - phi 贴 wrap 边界（|phi| 接近 pi）的比例
跑法: ../.venv/Scripts/python.exe probe15_phase_audit.py
"""
import math
import os
import random
import sys

import numpy as np

T = r"E:/Users/lmq/MaiBot/scripts/embedding_finetune/trading"
sys.path.insert(0, T)
import exp34_qsnn as E34  # noqa: E402


def semantics_sample(phases, rng, noise=0.1, thr=0.1):
    """三种语义各采一个动作，返回 (a_intrinsic, a_current, a_argmax, extras)"""
    p = [math.sin(x) ** 2 for x in phases]
    # --- 1) 本义：独立 Bernoulli；多路同时发放 => 随机取一个（原设计空白，此处补充） ---
    fires = [i for i in range(3) if rng.random() < p[i]]
    extras = len(fires)
    if not fires:
        a1 = 2
    elif len(fires) == 1:
        a1 = fires[0]
    else:
        a1 = rng.choice(fires)
    # --- 2) 现实现 ---
    ps = [p[i] + rng.uniform(-noise, noise) for i in range(3)]
    cand = [i for i in range(3) if ps[i] > thr]
    if not cand:
        a2 = 2
    else:
        e = [math.exp(ps[i]) for i in cand]
        tot = sum(e)
        r = rng.random() * tot
        acc = 0.0
        a2 = cand[-1]
        for i, ei in zip(cand, e, strict=True):
            acc += ei
            if r <= acc:
                a2 = i
                break
    # --- 3) argmax ---
    a3 = int(np.argmax(p))
    return a1, a2, a3, extras


def part_A():
    print('=== A. action semantics comparison (random phases) ===')
    rng = random.Random(7)
    n = 20000
    a1s = np.zeros(3); a2s = np.zeros(3); a3s = np.zeros(3)
    multi = 0
    for _ in range(n):
        phases = [rng.uniform(-math.pi, math.pi) for _ in range(3)]
        a1, a2, a3, ex = part_A_one(phases, rng)
        a1s[a1] += 1
        a2s[a2] += 1
        a3s[a3] += 1
        if ex >= 2:
            multi += 1
    print('action distribution  [buy   sell  hold]:')
    print('  intrinsic(bernoulli)  %s' % (a1s / n))
    print('  current (softmax+sam) %s' % (a2s / n))
    print('  argmax                %s' % (a3s / n))
    print('multi-fire rate (intrinsic, >=2 routes): %.3f' % (multi / n))
    # contrast of e^{ps}: max ratio when ps in [0,1]
    print('e^{ps} contrast with ps in [0,1]: max ratio = e^1 = %.2f' % math.e)
    # gradient dead zone: fraction of phase near k*pi/2 for random phase in [-pi,pi]
    ph = [rng.uniform(-math.pi, math.pi) for _ in range(200000)]
    dead = sum(1 for x in ph if abs(math.sin(2 * x)) < 0.1) / len(ph)
    print('random-phase dead-zone fraction (|sin 2x|<0.1): %.3f' % dead)


def part_A_one(phases, rng):
    return semantics_sample(phases, rng)


def run_phase_trace(code, seed):
    df = E34.load_stock(code)
    train, _ = E34.split_train_test(df)
    net = E34.QSNN(seed=seed)
    prices = train['close'].values
    rets = []; hist = []; h = False; c = 100.0; s = 0.0; prev = None
    rec = {'acts': [], 'phases': [], 'ncand': [], 'phimax': []}
    for p in prices:
        if prev is not None:
            rets.append(p / prev - 1)
            rets = rets[-E34.WINDOW:] if len(rets) > E34.WINDOW else rets
            hist.append(p); hist = hist[-40:] if len(hist) > 40 else hist
            ret1 = math.tanh(rets[-1] * 50)
            trend = math.tanh((p - hist[-21]) / hist[-21] * 20) if len(hist) >= 21 else 0.0
            feats = [ret1, trend, 0.0]
            # trace phases & candidates like act() but without consuming extra rng beyond act
            phases = [sum(net.phi[a][i] * feats[i] for i in range(3)) for a in range(3)]
            a = net.act(feats)
            rec['acts'].append(a)
            rec['phases'].append(phases)
            ps = [math.sin(x) ** 2 for x in phases]
            rec['ncand'].append(sum(1 for v in ps if v > 0.1))
            rec['phimax'].append(max(abs(v) for row in net.phi for v in row))
            if a == 0 and not h and c > 0:
                s = c / p * (1 - E34.COST); c = 0.0; h = True
            elif a == 1 and h:
                c = s * p * (1 - E34.COST); s = 0.0; h = False
            val = c + s * p
            if a in (0, 1):
                reward = 1.0 if val >= 100.0 * p / prices[0] else -1.0
                net.learn(reward, a, feats)
        else:
            hist.append(p)
        prev = p
    return rec


def part_B():
    print('=== B. training trace audit (601088, seed=254114614) ===')
    rec = run_phase_trace('601088', 254114614)
    acts = np.array(rec['acts'])
    n = len(acts)
    fr = [float(np.mean(acts == k)) for k in range(3)]
    print('action freq [buy sell hold]: %.3f %.3f %.3f  (n=%d)' % (fr[0], fr[1], fr[2], n))
    ph = np.array(rec['phases'])
    dead = float(np.mean(np.abs(np.sin(2 * ph)) < 0.1))
    print('dead-zone residence (|sin 2*phase|<0.1): %.3f' % dead)
    nc = np.array(rec['ncand'])
    print('candidates per step: 0:%.3f 1:%.3f 2:%.3f 3:%.3f' % (
        np.mean(nc == 0), np.mean(nc == 1), np.mean(nc == 2), np.mean(nc == 3)))
    pm = np.array(rec['phimax'])
    print('phi near wrap boundary (max|phi| > pi-0.1): %.3f   max|phi| reached: %.3f' % (
        np.mean(pm > math.pi - 0.1), pm.max()))


if __name__ == '__main__':
    part_A()
    print()
    part_B()
