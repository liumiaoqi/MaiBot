#!/usr/bin/env python3
"""probe18_jump_diag.py -- exp46「资产失控」诊断：跨世界估值跳变的采样佐证。

机制：幸存者 Worm 跨纪元复用（shares 持股数保留），而 make_world 每纪元重抽
「股票×窗口」；value = Σ(cash + shares_i * p_i[-1]) 按索引与新区价格相乘
=> 持股数不变、价格换世界，估值被乘上「跨窗末价比」。
本脚本采样该比值的分布（末价池两两随机比），佐证「45 倍/纪元」在分布内。
跑法: ../.venv/Scripts/python.exe probe18_jump_diag.py
"""
import sys

import numpy as np

sys.path.insert(0, r'E:/Users/lmq/MaiBot/scripts/embedding_finetune/trading')
import exp46_worm_reproduction as E46  # noqa: E402

ps = E46.load_all_prices()
print('loaded price series:', len(ps))
ends = []
for p in ps:
    if len(p) > 101:
        ends.append(p[99:])  # 所有 100 天窗口的末价
alle = np.concatenate(ends)
print('window-end price pool: n=%d  min=%.2f  max=%.2f  median=%.2f' % (
    len(alle), alle.min(), alle.max(), np.median(alle)))

rng = np.random.RandomState(7)
a = rng.choice(alle, 300000)
b = rng.choice(alle, 300000)
ratio = b / a
print('random cross-window end-price ratio:')
print('  P(>100)=%.4f  P(>40)=%.4f  P(>10)=%.3f  P(>3)=%.3f' % (
    (ratio > 100).mean(), (ratio > 40).mean(), (ratio > 10).mean(), (ratio > 3).mean()))
print('  P(<0.1)=%.3f  P(<0.025)=%.4f  median=%.3f' % (
    (ratio < 0.1).mean(), (ratio < 0.025).mean(), np.median(ratio)))
print('reading: exp46 observed per-epoch jump x45 is well inside P(>40)=15%;')
print('combined with value-ranked truncation (ratchet) and free 100-capital newborns,')
print('average assets explode without any trading edge.')
