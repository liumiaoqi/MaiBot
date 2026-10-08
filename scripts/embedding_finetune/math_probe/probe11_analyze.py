#!/usr/bin/env python3
"""probe11_analyze.py -- exp42 重跑数据的分析：适应度轨迹 + 基因贴界统计。
跑法: ../.venv/Scripts/python.exe probe11_analyze.py
"""
import json
import os

import numpy as np

d = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data_exp42")
curve = np.loadtxt(os.path.join(d, "curve.csv"), delimiter=",", skiprows=1)
champs = np.loadtxt(os.path.join(d, "champs.csv"), delimiter=",")
names = json.load(open(os.path.join(d, "gene_names.json"), encoding="utf-8"))
ranges = [(-1.0, 1.0), (0.1, 3.0), (0.1, 3.0), (0.1, 3.0), (0.1, 3.0),
          (0.1, 3.0), (0.1, 3.0), (0.0, 1.0), (0.0, 0.5), (-0.5, 0.5)]

gens, best, avg = curve[:, 0], curve[:, 1], curve[:, 2]

print("=== A. fitness trajectory (50 gens) ===")
print("best: gen0 %8.1f -> gen10 %8.1f (x%.1f) -> gen49 %8.1f (gen10-49 x%.2f)" % (
    best[0], best[10], best[10]/best[0], best[-1], best[-1]/best[10]))
print("avg : gen0 %8.1f -> gen10 %8.1f -> gen49 %8.1f (gen10-49 x%.2f)" % (
    avg[0], avg[10], avg[-1], avg[-1]/max(avg[10], 1e-9)))
sl = np.polyfit(gens[20:], best[20:], 1)[0]
print("late linear slope (gen20-49): %+.1f per gen  (vs gen0-10 %+.0f per gen)" % (
    sl, (best[10]-best[0])/10))
df = np.diff(best)
print("best per-gen change: std %.1f, max |jump| %.1f" % (df.std(), np.abs(df).max()))

print()
print("=== B. gene wall-hitting (champions, 50 gens) ===")
print("%-10s %14s %8s %8s %10s %10s" % ("gene", "range", "at_lo", "at_hi", "late_lo", "late_hi"))
for i, nm in enumerate(names):
    lo, hi = ranges[i]
    span = hi - lo
    v = champs[:, i]
    at_lo = (v < lo + 0.02*span).mean()
    at_hi = (v > hi - 0.02*span).mean()
    v_late = v[25:]
    late_lo = (v_late < lo + 0.02*span).mean()
    late_hi = (v_late > hi - 0.02*span).mean()
    print("%-10s [%5.1f,%5.1f] %7.0f%% %7.0f%% %9.0f%% %9.0f%%" % (
        nm, lo, hi, at_lo*100, at_hi*100, late_lo*100, late_hi*100))

print()
print("=== C. late-stage dispersion (champions gen25-49) ===")
v_late = champs[25:, :]
for i, nm in enumerate(names):
    tag = ""
    lo, hi = ranges[i]
    if v_late[:, i].std() < 0.03:
        tag = "  <- pinned"
    print("%-10s late std = %.4f%s" % (nm, v_late[:, i].std(), tag))

n_pinned = 0
for i, nm in enumerate(names):
    v_late = champs[25:, i]
    lo, hi = ranges[i]
    span = hi - lo
    if (v_late < lo + 0.02*span).mean() > 0.8 or (v_late > hi - 0.02*span).mean() > 0.8:
        n_pinned += 1
print()
print("genes pinned at a wall in late stage: %d / 10" % n_pinned)
