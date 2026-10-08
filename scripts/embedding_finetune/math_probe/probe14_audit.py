#!/usr/bin/env python3
"""probe14_audit.py -- exp36 对抗审计。

来源发现（见 NOTES）：
1. adversary_predict() 是空函数（两次 return None）；"对抗" = slippage() 的硬编码
2. slippage 符号反向：buy 打 0.995 折、sell 加价 —— "被利用"实为"被补贴"（基准数字为证：
   mt 有对抗 416.4 > mt 无对抗 377.5）
3. 噪声 n 平移不变（三个动作同加一个 n）=> 动作方向不受噪声影响

本脚本做四件事：
A) mt 确定性重放（同 seed 两次动作序列一致率）+ hw 变异率
B) "无种子预言"命中率：去噪动作 vs 真实动作（mt / hw）
C) 动作差异归因：方向翻转 vs 触发翻转
D) 滑点符号修正版的三场景收益（"真的被利用"长什么样）
跑法: ../.venv/Scripts/python.exe probe14_audit.py
"""
import os
import sys

import numpy as np

T = r"E:/Users/lmq/MaiBot/scripts/embedding_finetune/trading"
sys.path.insert(0, T)
import exp36_intrinsic_randomness as E  # noqa: E402


def run_audit(noise_src):
    df = E.load_stock(E.STOCK)
    train, test = E.split_train_test(df)
    t = E.TraderAdv(seed=E.SEED, noise_src=noise_src)
    rec = {"a": [], "a0": []}

    def decide_rec(feats):
        n = t._noise()
        sv = [sum(t.w[i][j] * feats[i] for i in range(3)) + n for j in range(3)]
        sv0 = [sum(t.w[i][j] * feats[i] for i in range(3)) for j in range(3)]

        def act(s):
            if s[0] > 0.1 and s[0] > s[1] and s[0] > s[2]:
                return 0
            if s[1] > 0.1 and s[1] > s[0] and s[1] > s[2]:
                return 1
            return 2

        a, a0 = act(sv), act(sv0)
        rec["a"].append(a)
        rec["a0"].append(a0)
        return a

    # --- train (照抄 run_stock，decide 换 decide_rec) ---
    prices = train["close"].values
    rets = []; hist = []; h = False; c = 100.0; s = 0.0; prev = None
    for p in prices:
        if prev is not None:
            rets.append(p / prev - 1)
            rets = rets[-E.WINDOW:] if len(rets) > E.WINDOW else rets
            hist.append(p); hist = hist[-40:] if len(hist) > 40 else hist
            ret1 = rets[-1] * 100
            trend = (p - hist[-21]) / hist[-21] * 100 if len(hist) >= 21 else 0.0
            feats = [ret1, trend, 0.0]
            a = decide_rec(feats)
            if a == 0 and not h and c > 0:
                s = c / p * (1 - E.COST); c = 0.0; h = True
            elif a == 1 and h:
                c = s * p * (1 - E.COST); s = 0.0; h = False
            val = c + s * p
            if a in (0, 1):
                reward = 1.0 if val >= 100.0 * p / prices[0] else -1.0
                t.learn(reward, a, feats)
        else:
            hist.append(p)
        prev = p
    # --- test (照抄) ---
    tp = test["close"].values
    rets3 = []; hist3 = []; prev3 = None
    for p in tp:
        if prev3 is not None:
            rets3.append(p / prev3 - 1)
            rets3 = rets3[-E.WINDOW:] if len(rets3) > E.WINDOW else rets3
            hist3.append(p); hist3 = hist3[-40:] if len(hist3) > 40 else hist3
            ret1 = rets3[-1] * 100
            trend = (p - hist3[-21]) / hist3[-21] * 100 if len(hist3) >= 21 else 0.0
            feats = [ret1, trend, 0.0]
            decide_rec(feats)
        else:
            hist3.append(p)
        prev3 = p
    return rec


def run_fixed(noise_src, adversarial):
    """滑点符号修正版：买入付 +SLIP（追高）、卖出收 -SLIP（压价）。"""
    df = E.load_stock(E.STOCK)
    train, test = E.split_train_test(df)
    t = E.TraderAdv(seed=E.SEED, noise_src=noise_src)

    def slip(a):
        if not adversarial or noise_src != 'mt':
            return 0.0
        return +E.SLIP if a == 0 else (-E.SLIP if a == 1 else 0.0)

    prices = train["close"].values
    rets = []; hist = []; h = False; c = 100.0; s = 0.0; prev = None
    for p in prices:
        if prev is not None:
            rets.append(p / prev - 1)
            rets = rets[-E.WINDOW:] if len(rets) > E.WINDOW else rets
            hist.append(p); hist = hist[-40:] if len(hist) > 40 else hist
            feats = [rets[-1] * 100,
                     (p - hist[-21]) / hist[-21] * 100 if len(hist) >= 21 else 0.0, 0.0]
            a, _ = t.decide(feats)
            exec_p = p * (1 + slip(a))
            if a == 0 and not h and c > 0:
                s = c / exec_p * (1 - E.COST); c = 0.0; h = True
            elif a == 1 and h:
                c = s * exec_p * (1 - E.COST); s = 0.0; h = False
            val = c + s * p
            if a in (0, 1):
                reward = 1.0 if val >= 100.0 * p / prices[0] else -1.0
                t.learn(reward, a, feats)
        else:
            hist.append(p)
        prev = p
    tp = test["close"].values
    rets3 = []; hist3 = []; h3 = False; c3 = 100.0; s3 = 0.0; prev3 = None
    for p in tp:
        if prev3 is not None:
            rets3.append(p / prev3 - 1)
            rets3 = rets3[-E.WINDOW:] if len(rets3) > E.WINDOW else rets3
            hist3.append(p); hist3 = hist3[-40:] if len(hist3) > 40 else hist3
            feats = [rets3[-1] * 100,
                     (p - hist3[-21]) / hist3[-21] * 100 if len(hist3) >= 21 else 0.0, 0.0]
            a, _ = t.decide(feats)
            exec_p = p * (1 + slip(a))
            if a == 0 and not h3 and c3 > 0:
                s3 = c3 / exec_p * (1 - E.COST); c3 = 0.0; h3 = True
            elif a == 1 and h3:
                c3 = s3 * exec_p * (1 - E.COST); s3 = 0.0; h3 = False
        else:
            hist3.append(p)
        prev3 = p
    return c3 + s3 * tp[-1]


if __name__ == '__main__':
    print('=== probe14: exp36 adversarial audit ===')
    recs = {}
    for src in ['mt', 'hw']:
        recs[src] = [run_audit(src) for _ in range(2)]

    print('--- A/B/C: replay, clean-prediction, attribution ---')
    for src in ['mt', 'hw']:
        r1, r2 = recs[src]
        n = len(r1['a'])
        disagree = sum(1 for x, y in zip(r1['a'], r2['a']) if x != y)
        agree = 1.0 - disagree / n
        hit = np.mean([a == a0 for a, a0 in zip(r1['a'], r1['a0'])])
        dirflip = 0; trigflip = 0
        for a, a0 in zip(r1['a'], r1['a0']):
            if a != a0:
                if a == 2 or a0 == 2:
                    trigflip += 1
                else:
                    dirflip += 1
        print('%s: two-run agreement %.6f (disagree %d) | clean-predict hit %.4f | flips dir %d / trig %d (n=%d)'
              % (src, agree, disagree, hit, dirflip, trigflip, n))

    print('--- D: corrected-sign slippage (buy pays +, sell receives -, i.e. really exploited) ---')
    for name, src, adv in [('mt clean', 'mt', False),
                           ('mt adv (true sign)', 'mt', True),
                           ('hw adv (true sign)', 'hw', True)]:
        vals = [run_fixed(src, adv) for _ in range(5)]
        print('%-22s %8.1f' % (name, np.mean(vals)))
