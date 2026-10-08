"""spread.dll ctypes 接口诊断：从最小用例逐步升到真实规模。

用法：python diag.py [dll路径]
  默认加载 spread_dbg.dll（-fcheck=all 调试版，会打印 Fortran 运行时错误）
"""
import ctypes
import os
import shutil
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))

# 调试版 DLL（-fcheck/-fbacktrace）会依赖 libgfortran-5.dll 等 mingw 运行时，
# 把 gfortran 所在 bin 目录加入 DLL 搜索路径。
_gf = shutil.which("gfortran")
if _gf:
    try:
        os.add_dll_directory(os.path.dirname(_gf))
    except (FileNotFoundError, OSError):
        pass


def bind(path):
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


def case(fn, name, n, esrc, edst, ew, erec, edet, seeds, depth, minw):
    esrc = np.ascontiguousarray(esrc, dtype=np.int32)
    edst = np.ascontiguousarray(edst, dtype=np.int32)
    ew = np.ascontiguousarray(ew, dtype=np.float64)
    erec = np.ascontiguousarray(erec, dtype=np.float64)
    edet = np.ascontiguousarray(edet, dtype=np.float64)
    seeds = np.ascontiguousarray(seeds, dtype=np.int32)
    act_full = np.zeros(n + 1, dtype=np.float64)
    actv = np.ascontiguousarray(act_full[1:])
    print(f"[{name}] n={n} ne={len(esrc)} nseed={len(seeds)} "
          f"actv.len={len(actv)} shares={np.shares_memory(act_full, actv)}")
    fn(n, len(esrc), esrc, edst, ew, erec, edet,
       len(seeds), seeds, depth, minw, actv)
    nz = int((act_full[1:] > 0).sum())
    print(f"    -> ok, 激活节点={nz}")
    return act_full


def main() -> int:
    dll = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "spread_dbg.dll")
    print(f"dll = {dll}")
    fn = bind(dll)

    # 1) 空边
    case(fn, "空图", 3,
         np.zeros(0), np.zeros(0), np.zeros(0), np.zeros(0), np.zeros(0),
         np.array([1]), 1, 0.05)

    # 2) 2 节点 1 边
    case(fn, "tiny", 2,
         np.array([1]), np.array([2]), np.array([0.5]), np.array([1.0]), np.array([1.0]),
         np.array([1]), 1, 0.05)

    # 3) 200 节点 800 边（真实分布）
    rng = np.random.default_rng(1)
    N = 200
    esrc = rng.integers(1, N + 1, 800, dtype=np.int32)
    edst = rng.integers(1, N + 1, 800, dtype=np.int32)
    case(fn, "mid", N, esrc, edst,
         rng.uniform(0.1, 1.0, 800), rng.uniform(1.0, 1.25, 800), rng.uniform(0.5, 1.0, 800),
         np.array([11, 22, 33, 44, 55]), 3, 0.05)

    # 4) 真实规模 2000 节点 8000 边（与 demo 相同的生成器）
    RNG = np.random.default_rng(20261008)
    N2, NE2 = 2000, 8000
    esrc = RNG.integers(1, N2 + 1, NE2, dtype=np.int32)
    edst = RNG.integers(1, N2 + 1, NE2, dtype=np.int32)
    keep = esrc != edst
    esrc, edst = esrc[keep], edst[keep]
    ew = RNG.uniform(0.1, 1.0, len(esrc))
    erec = RNG.uniform(1.0, 1.25, len(esrc))
    edet = RNG.uniform(0.5, 1.0, len(esrc))
    seeds = (RNG.choice(N2, 5, replace=False) + 1).astype(np.int32)
    case(fn, "full", N2, esrc, edst, ew, erec, edet, seeds, 3, 0.05)

    print("ALL OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
