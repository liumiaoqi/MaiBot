#!/usr/bin/env python3
"""exp51b: 多 seed 稳定性验证——5 个 seed 重复对照"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from exp51_role_drift_chat import (run_experiment, init_params, diversity,
                                   N_CHARS, PARAM_NAMES, PARAM_RANGES)

seeds = [7, 11, 23, 42, 99]
print("seed | 固定差异度 | 漂移差异度 | Δ差异 | 固定适应度 | 漂移适应度 | 漂移增益%")
print("-----|-----------|-----------|-------|-----------|-----------|----------")
tot_d = tot_f = 0.0
for s in seeds:
    np.random.seed(s)
    base = init_params()
    fixed = run_experiment(drift=False, seed=s)
    drift = run_experiment(drift=True, seed=s)
    d0 = diversity(base)
    df = diversity(fixed['params_final'])
    dd = diversity(drift['params_final'])
    mf = fixed['fitness'].mean()
    md = drift['fitness'].mean()
    gain = (md / mf - 1) * 100
    tot_d += (dd - d0)
    tot_f += gain
    print(f"{s:4d} | {df:.3f}      | {dd:.3f}      | {dd-d0:+.3f} | {mf:6.1f}    | {md:6.1f}    | {gain:+5.1f}%")
print(f"-----|-----------|-----------|-------|-----------|-----------|----------")
print(f"平均 |           |           | {tot_d/len(seeds):+.3f} |           |           | {tot_f/len(seeds):+.1f}%")
