"""x61_python_ref: exp61 交叉验证参照（numpy 侧）

2D 周期格 CTQW，源 = 节点 0，t = 8 的概率分布。
用于与 x61_crosscheck.wl（Wolfram 侧）逐值对拍。
"""

import numpy as np

side = 8
n = side * side
W = np.zeros((n, n))
for r in range(side):
    for c in range(side):
        i = r * side + c
        for dr, dc in ((0, 1), (1, 0)):
            j = ((r + dr) % side) * side + (c + dc) % side
            W[i, j] = W[j, i] = 1.0

vals, vecs = np.linalg.eigh(W)
psi0 = np.zeros(n)
psi0[0] = 1.0
coef = vecs.T @ psi0
t = 8.0
psi = vecs @ (np.exp(-1j * vals * t) * coef)
p = np.abs(psi) ** 2

print("eig:", " ".join(f"{v:.10f}" for v in vals[:5]))
print("p08:", " ".join(f"{x:.10f}" for x in p[:8]))
print("p37:", f"{p[36]:.10f}")
print("sum:", f"{p.sum():.10f}")
