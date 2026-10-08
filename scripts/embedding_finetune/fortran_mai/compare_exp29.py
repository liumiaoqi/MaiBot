"""对拍器：exp29 Fortran 版 vs Python 源码复刻。

Python 侧函数逐字复制自 trading/exp29_quantum_forgetting.py（2026），
只做一件事：算出与 exp29_forgetting.f90 相同的 25 个关键值，比对 #N 行。

判据：最大误差 < 1e-12（输出精度 15 位，量化误差 ~5e-16）。
"""

import math
import sys

NDAY = 31
S0 = 1.0
EBB_H = [0.0, 0.33, 1.0, 9.0, 24.0, 48.0, 144.0, 744.0]
EBB_R = [1.00, 0.58, 0.44, 0.36, 0.33, 0.28, 0.25, 0.21]


def granular(s0, nd=NDAY):
    return [max(0.2, s0 * math.exp(-t / 24.0)) for t in range(nd + 1)]


def ampdamp(s0, nd=NDAY):
    return [max(0.2, s0 * (1.0 - 0.05) ** t) for t in range(nd + 1)]


def two_level(s0, c0=0.1, nd=NDAY):
    s_ = s0 * 0.7
    l_ = s0 * c0
    return [s_ * math.exp(-t / 1.0) + l_ * math.exp(-t / 200.0) for t in range(nd + 1)]


def two_level_review(s0, mode, nd=NDAY):
    s_ = s0 * 0.7
    l_ = s0 * 0.1
    out = []
    for t in range(nd + 1):
        if mode == 1 and t == 1:
            s_ = s0 * 0.7
            l_ += s0 * 0.3
        if mode == 2 and t in (1, 3, 7, 14):
            s_ = s0 * 0.7
            l_ += s0 * 0.3
        out.append(s_ * math.exp(-t / 1.0) + l_ * math.exp(-t / 200.0))
    return out


def fit_mae(curve):
    total = 0.0
    for h, ref in zip(EBB_H, EBB_R):
        day = h / 24.0
        i0 = int(day)
        i1 = min(i0 + 1, NDAY)
        frac = day - i0
        v = curve[i0] * (1 - frac) + curve[i1] * frac
        total += abs(v - ref)
    return total / 8.0


def expected():
    g = granular(S0)
    qa = ampdamp(S0)
    q2 = two_level(S0, 0.1)
    nr = two_level_review(S0, 0)
    r1 = two_level_review(S0, 1)
    rs = two_level_review(S0, 2)
    imp = two_level(S0, 0.5, 100)
    norm = two_level(S0, 0.1, 100)
    g100 = granular(S0, 100)
    return {
        "mae_granular": fit_mae(g),
        "mae_ampdamp": fit_mae(qa),
        "mae_2level": fit_mae(q2),
        "g_d1": g[1], "g_d2": g[2], "g_d6": g[6], "g_d31": g[31],
        "qa_d1": qa[1], "qa_d2": qa[2], "qa_d6": qa[6], "qa_d31": qa[31],
        "q2_d1": q2[1], "q2_d2": q2[2], "q2_d6": q2[6], "q2_d31": q2[31],
        "nr_d7": nr[7], "nr_d31": nr[31],
        "r1_d7": r1[7], "r1_d31": r1[31],
        "rs_d7": rs[7], "rs_d31": rs[31],
        "imp100": imp[100], "norm100": norm[100], "g100": g100[100],
    }


def read_fortran(path):
    out = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("#N "):
                parts = line.split()
                out[parts[1]] = float(parts[2])
    return out


def main() -> int:
    exp = expected()
    got = read_fortran("out29.txt")

    missing = set(exp) - set(got)
    if missing:
        print(f"FAIL: fortran output missing labels: {sorted(missing)}")
        return 1

    max_diff = 0.0
    for label, v in exp.items():
        d = abs(got[label] - v)
        if d > max_diff:
            max_diff = d
        if d > 1e-9:
            print(f"DIFF {label}: fortran={got[label]!r} python={v!r}")

    status = "PASS" if max_diff < 1e-12 else "CHECK"
    print(f"labels={len(exp)}  max_diff={max_diff:.3e}  -> {status}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
