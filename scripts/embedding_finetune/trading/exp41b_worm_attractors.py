#!/usr/bin/env python3
"""exp41b: 线虫连接组自发吸引子——真实结构的"行为守则"实证

exp41 教训:真实连接不是 Hopfield 外积权重,外部定义的社区模式不是吸引子。
正确问题:**网络自由收敛到哪些状态?**——随机输入 -> 动力学 -> 收敛状态,
看收敛状态是否对应真实行为神经元组(AVA 后退/AVB 前进/DB-VB 运动等)。

方法:
1. W = 对称化真实连接(归一化)
2. 100 次随机初始化 -> 同步/异步更新 -> 收敛状态
3. 统计:收敛状态与行为神经元激活的相关性:
   - AVAL/AVAR(后退命令)+ DD(抑制性中间)
   - AVBL/AVBR/PVCL/PVCR(前进)+ DB(运动)
   - RIVL/RIVR(头部转向)
   - 感觉:IL2/URX/BAG(氧/CO2 感觉)
4. 对照:随机权重(同密度)——收敛状态是否还有行为相关性
"""

import json
import os
import numpy as np

rng = np.random.RandomState(42)
DATA = r'E:\Users\lmq\MaiBot\scripts\embedding_finetune\snn_behavior\worm_data'


def load_connectome():
    Gs = np.load(os.path.join(DATA, 'Gs.npy'))
    chem = json.load(open(os.path.join(DATA, 'chem.json'), encoding='utf-8'))
    names = [n.get('name') or str(n.get('id')) for n in chem['nodes']]
    return Gs, names


def sym_normalize(G):
    W = (G + G.T) / 2.0
    np.fill_diagonal(W, 0.0)
    maxw = np.abs(W).max()
    return W / maxw if maxw > 0 else W


def converge(W, x0, max_iter=200):
    """同步更新收敛(所有神经元同时更新,直到稳定)。"""
    x = x0.copy()
    for _ in range(max_iter):
        h = W @ x
        new = np.where(h >= 0, 1.0, -1.0)
        if np.array_equal(new, x):
            break
        x = new
    return x


# 行为神经元组(线虫文献已知)
BEHAVIOR = {
    '后退(AVA+DD)': ['AVAL', 'AVAR', 'DD01', 'DD02'],
    '前进(AVB+DB)': ['AVBL', 'AVBR', 'DB01', 'DB02', 'DB03'],
    '头部转向(RIV)': ['RIVL', 'RIVR', 'SMDDL'],
    '运动命令(PVC)': ['PVCL', 'PVCR'],
    '感觉(IL2/URX)': ['IL2DL', 'IL2VL', 'URXL', 'URXR'],
}


if __name__ == '__main__':
    print('=== exp41b: 线虫连接组自发吸引子——结构承载行为守则 ===')
    Gs, names = load_connectome()
    name2idx = {n: i for i, n in enumerate(names)}
    W_real = sym_normalize(Gs)
    print('真实 W 就绪(%d 神经元,非零边 %d)' % (len(names), int((W_real != 0).sum())))

    # 行为组索引
    bg = {}
    for label, group in BEHAVIOR.items():
        idx = [name2idx[n] for n in group if n in name2idx]
        bg[label] = idx
        print('  %s: %d 个神经元' % (label, len(idx)))

    # 100 次随机初始 -> 收敛 -> 统计每组的平均激活(+1/-1 均值)
    print()
    print('--- 自发吸引子与行为组激活(均值>0=该组激活,-1~+1) ---')
    print('%-22s %12s %12s' % ('行为组', '真实连接', '随机权重'))
    print('-' * 48)
    real_acts = {k: [] for k in bg}
    rand_acts = {k: [] for k in bg}
    # 随机权重(同密度)
    mask = W_real != 0
    n_edges = int(mask.sum())
    idxs = [(i, j) for i in range(len(W_real)) for j in range(i + 1, len(W_real))]
    W_rand = np.zeros_like(W_real)
    for t in rng.choice(len(idxs), n_edges // 2, replace=False):
        i, j = idxs[t]
        w = rng.uniform(-1, 1)
        W_rand[i][j] = W_rand[j][i] = w

    for _ in range(100):
        x0 = rng.choice([-1.0, 1.0], len(names))
        xr = converge(W_real, x0)
        xr2 = converge(W_rand, x0)
        for label, idx in bg.items():
            if idx:
                real_acts[label].append(xr[idx].mean())
                rand_acts[label].append(xr2[idx].mean())

    for label in bg:
        rm = np.mean(real_acts[label])
        rnd = np.mean(rand_acts[label])
        print('%-22s %12.3f %12.3f' % (label, rm, rnd))

    # 行为组间相关性(真实 W 收敛状态里,后退组和前进组是否负相关=互斥)
    print()
    print('--- 行为组互斥性(后退 vs 前进在收敛状态的相关性) ---')
    pairs = [('后退(AVA+DD)', '前进(AVB+DB)'),
             ('后退(AVA+DD)', '头部转向(RIV)'),
             ('前进(AVB+DB)', '运动命令(PVC)')]
    print('%-30s %12s %12s' % ('行为对', '真实连接', '随机权重'))
    print('-' * 56)
    # 重新跑并记录配对激活
    real_pair = {p: [] for p in pairs}
    rand_pair = {p: [] for p in pairs}
    for _ in range(100):
        x0 = rng.choice([-1.0, 1.0], len(names))
        xr = converge(W_real, x0)
        xr2 = converge(W_rand, x0)
        for a, b in pairs:
            va = xr[bg[a]].mean() if bg[a] else 0
            vb = xr[bg[b]].mean() if bg[b] else 0
            real_pair[(a, b)].append(va * vb)  # 同号=正相关(共激活),异号=负(互斥)
            va2 = xr2[bg[a]].mean() if bg[a] else 0
            vb2 = xr2[bg[b]].mean() if bg[b] else 0
            rand_pair[(a, b)].append(va2 * vb2)
    for a, b in pairs:
        print('%-30s %12.3f %12.3f' % (a + ' x ' + b, np.mean(real_pair[(a, b)]),
                                        np.mean(rand_pair[(a, b)])))

    print()
    print('=== 结论观察 ===')
    print('真实连接:行为组激活是否非随机(偏离0)?互斥性(后退x前进<0)?')
    print('随机权重:是否无结构(全部≈0)?——结构承载行为守则的直接对比')
