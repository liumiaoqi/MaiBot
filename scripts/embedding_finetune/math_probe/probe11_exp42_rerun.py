#!/usr/bin/env python3
"""probe11_exp42_rerun.py -- 重跑 exp42 拿全 50 代曲线（不碰原存档）。

- 复用 exp42 的全部机制函数（load_worm/phenotype/run_life/mutate/crossover）
- 主循环照抄 exp42（同 seed、同顺序）→ 期望 avg 曲线与原版 print 对拍一致
- 存档改写到 math_probe/data_exp42/（每代 best/avg/champion 基因全记录）

跑法: ../.venv/Scripts/python.exe probe11_exp42_rerun.py
"""
import json
import os
import sys

import numpy as np

TRADING = r"E:/Users/lmq/MaiBot/scripts/embedding_finetune/trading"
sys.path.insert(0, TRADING)
import exp42_worm_evolution as E  # noqa: E402

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data_exp42")
os.makedirs(out, exist_ok=True)

rng = E.rng  # 与 exp42 同一 RandomState（seed 20260818）

W_real, groups = E.load_worm()
prices_all = E.load_prices()
print("connectome: 279 neurons | price series: %d" % len(prices_all))

# --- 初始种群（照抄 exp42）---
pop = []
base = np.array([1.0] * 10)
base[0] = rng.uniform(-1, 1)
pop.append(base)
for _ in range(E.N_POP - 1):
    pop.append(E.mutate(base, rate=0.5, sigma=0.5))

curve = []   # gen, best, avg
champs = []  # gen + 10 genes
for gen in range(E.N_GENS):
    fitness = []
    for worm in pop:
        W = E.phenotype(worm, W_real, groups)
        prices = prices_all[rng.randint(len(prices_all))]
        fitness.append(E.run_life(W, groups, worm, prices))
    fitness = np.array(fitness)
    best_i = int(np.argmax(fitness))
    curve.append((gen, float(fitness[best_i]), float(fitness.mean())))
    champs.append([float(v) for v in pop[best_i]])
    if gen % 10 == 0 or gen == E.N_GENS - 1:
        print("gen %2d: avg %7.2f | best %7.2f" % (gen, fitness.mean(), fitness[best_i]))

    order = np.argsort(fitness)[::-1]
    survivors = [pop[i] for i in order[:max(2, E.N_POP // 5)]]
    new_pop = [survivors[0].copy()]
    while len(new_pop) < E.N_POP:
        a, b = rng.choice(len(survivors), 2, replace=False)
        child = E.crossover(survivors[a], survivors[b])
        child = E.mutate(child)
        new_pop.append(child)
    pop = new_pop

np.savetxt(os.path.join(out, "curve.csv"), np.array(curve), fmt="%.4f", delimiter=",", header="gen,best,avg", comments="")
np.savetxt(os.path.join(out, "champs.csv"), np.array(champs), fmt="%.6f", delimiter=",")
with open(os.path.join(out, "gene_names.json"), "w", encoding="utf-8") as f:
    json.dump(E.GENE_NAMES, f, ensure_ascii=False)

print("=== 曲线（每10代）===")
arr = np.array(curve)
for g in list(range(0, E.N_GENS, 10)) + [E.N_GENS - 1]:
    row = arr[arr[:, 0] == g][0]
    print("gen %2d: best %9.2f  avg %9.2f" % (g, row[1], row[2]))
print("curves -> data_exp42/curve.csv ; champions -> champs.csv")
