"""扩散激活 · 三路对拍与计时 —— "Spreading Activation, 1957 style"

参考源：src/A_memorix/core/connectionist/spreading_activation.py（2026）
复刻其 BFS 传播核心（边列表等价形式）：
  种子 act=1.0；每轮对 frontier 节点（act>=min_w）扫描双向边：
    spread = act * w * 0.85 * recency * (0.3 + 0.7*detail)
  严格大于才更新并进入下一轮 frontier；共 depth 轮。

⚠️ 语义说明：2026 原版在轮内 IN-PLACE 更新 `activated`（结果依赖 Python
set 迭代序 = 异步更新产物）。三路对拍统一定义为 **轮初快照（同步更新）**——
序无关、可复现；这是对原版语义的标准化，差异记录在 NOTES.md。

路线：
  A. python-loop : 纯 Python 循环
  B. numpy-vec   : numpy 向量化（maximum.at 折叠）
  C. fortran-cabi: Fortran 内核（spread.dll, ISO_C_BINDING / ctypes）

判据：三路激活数组逐值一致（容差 1e-9，实际预期 ~0）。
"""
import ctypes
import os
import sys
import time

import numpy as np

RNG = np.random.default_rng(20261008)
N = 2000
NE = 8000
DEPTH = 3
MINW = 0.05
NSEED = 5
DECAY = 0.85


def gen_graph():
    esrc = RNG.integers(1, N + 1, NE, dtype=np.int32)
    edst = RNG.integers(1, N + 1, NE, dtype=np.int32)
    keep = esrc != edst
    esrc, edst = esrc[keep], edst[keep]
    ew = RNG.uniform(0.1, 1.0, len(esrc))
    erec = RNG.uniform(1.0, 1.25, len(esrc))   # recency_factor（时间项预注入）
    edet = RNG.uniform(0.5, 1.0, len(esrc))
    seeds = (RNG.choice(N, NSEED, replace=False) + 1).astype(np.int32)
    return esrc, edst, ew, erec, edet, seeds


def ref_loop(esrc, edst, ew, erec, edet, seeds):
    """A：纯 Python 循环（快照语义）。"""
    ne = len(esrc)
    act = np.zeros(N + 1)
    frontier = set(int(s) for s in seeds)
    for s in frontier:
        act[s] = 1.0
    for _ in range(DEPTH):
        snap = act.copy()                      # 轮初快照
        nxt = set()
        for i in sorted(frontier):
            cur = snap[i]
            if cur < MINW:
                continue
            for e in range(ne):
                if esrc[e] == i:
                    nb = int(edst[e])
                elif edst[e] == i:
                    nb = int(esrc[e])
                else:
                    continue
                spread = cur * ew[e] * DECAY * erec[e] * (0.3 + 0.7 * edet[e])
                if spread >= MINW and spread > act[nb]:
                    act[nb] = spread
                    nxt.add(nb)
        frontier = nxt
        if not frontier:
            break
    return act


def ref_numpy(esrc, edst, ew, erec, edet, seeds):
    """B：numpy 向量化（天然快照语义）。"""
    act = np.zeros(N + 1)
    act[seeds] = 1.0
    front = np.zeros(N + 1, dtype=bool)
    front[seeds] = True
    factor = ew * DECAY * erec * (0.3 + 0.7 * edet)
    for _ in range(DEPTH):
        sa = np.where(front[esrc], act[esrc], 0.0)   # 轮初快照派生
        da = np.where(front[edst], act[edst], 0.0)
        sp1 = sa * factor
        sp2 = da * factor
        before = act.copy()
        m1 = sp1 >= MINW
        m2 = sp2 >= MINW
        if m1.any():
            np.maximum.at(act, edst[m1], sp1[m1])
        if m2.any():
            np.maximum.at(act, esrc[m2], sp2[m2])
        nxt = np.zeros(N + 1, dtype=bool)
        nxt[np.nonzero(act > before)[0]] = True
        front = nxt
        if not front.any():
            break
    return act


def load_lib(path=None):
    """加载 spread.dll。

    ⚠️ 坑（已实证）：CPython 3.8+ / Windows 下，ctypes.CDLL 传**裸文件名**
    （如 'spread.dll'，不含目录分隔符）时按「默认目录搜索」规则解析，
    **不会搜索当前工作目录** —— 会误报 FileNotFoundError。
    必须传带路径的形式（'./spread.dll' 或绝对路径）。
    """
    if path is None:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "spread.dll")
    lib = ctypes.CDLL(path)
    fn = lib.spread_recall
    i32p = np.ctypeslib.ndpointer(dtype=np.int32, flags="C_CONTIGUOUS")
    f64p = np.ctypeslib.ndpointer(dtype=np.float64, flags="C_CONTIGUOUS")
    fn.argtypes = [
        ctypes.c_int, ctypes.c_int,
        i32p, i32p,
        f64p, f64p, f64p,
        ctypes.c_int, i32p,
        ctypes.c_int, ctypes.c_double,
        f64p,
    ]
    fn.restype = None
    return fn


def run_fortran(fn, esrc, edst, ew, erec, edet, seeds):
    act_full = np.zeros(N + 1, dtype=np.float64)
    act_view = np.ascontiguousarray(act_full[1:])   # 1-based 视图
    fn(N, len(esrc), esrc, edst, ew, erec, edet,
       len(seeds), seeds, DEPTH, MINW, act_view)
    return act_full


def main() -> int:
    esrc, edst, ew, erec, edet, seeds = gen_graph()
    ne = len(esrc)
    print(f"=== 扩散激活三路对拍（n={N}, e={ne}, depth={DEPTH}, seeds={len(seeds)}）===")

    fn = load_lib()

    t0 = time.perf_counter()
    a_loop = ref_loop(esrc, edst, ew, erec, edet, seeds)
    t_loop = time.perf_counter() - t0

    t0 = time.perf_counter()
    a_np = ref_numpy(esrc, edst, ew, erec, edet, seeds)
    t_np = time.perf_counter() - t0

    t_f = float("inf")
    for _ in range(5):
        t0 = time.perf_counter()
        a_f = run_fortran(fn, esrc, edst, ew, erec, edet, seeds)
        t_f = min(t_f, time.perf_counter() - t0)

    d1 = float(np.max(np.abs(a_loop - a_f)))
    d2 = float(np.max(np.abs(a_np - a_f)))
    ok = d1 < 1e-9 and d2 < 1e-9

    print(f"[对拍] python-loop  vs fortran : max_diff={d1:.3e}")
    print(f"[对拍] numpy-vec    vs fortran : max_diff={d2:.3e}")
    print(f"[结果] {'PASS' if ok else 'FAIL'}   激活节点数={int((a_f[1:] > 0).sum())}")
    print(f"[计时] python-loop {t_loop * 1e3:9.1f} ms")
    print(f"[计时] numpy-vec   {t_np * 1e3:9.2f} ms")
    print(f"[计时] fortran     {t_f * 1e3:9.2f} ms  (min of 5)")

    top = np.argsort(-a_f[1:])[:10] + 1
    print("[top10] " + "  ".join(f"{int(i)}:{a_f[i]:.4f}" for i in top))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
