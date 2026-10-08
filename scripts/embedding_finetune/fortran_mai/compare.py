"""对拍器：Fortran 版 vs Python 复刻版。

公式与事件表逐条复制自：
  - src/maisaka/agent/emotion.py（2026）
  - fortran_mai/mai.f90（本目录）

判据：逐值对比 #D 数据行，最大误差 < 1e-9 为 PASS。
"""

import math
import sys

NEMO = 7
NTICK = 120
BASE = [40.0, 10.0, 10.0, 8.0, 45.0, 30.0, 15.0]  # happy..lonely
RATE = 0.12  # per hour

# 与 mai.f90 `inject_event` 逐条一致（tick -> (1-based index, delta)）
EVENTS = {
    5: (1, 25.0),
    8: (6, 30.0),
    12: (2, 20.0),
    15: (7, 18.0),
    20: (5, 15.0),
    30: (4, 22.0),
    35: (1, 10.0),
    50: (3, 20.0),
    60: (6, 25.0),
    70: (2, 15.0),
    85: (1, 18.0),
    100: (7, 12.0),
}


def simulate():
    """Python 复刻：decay(toward baseline) -> trigger(clamp)。"""
    emo = list(BASE)
    rows = []
    for tick in range(1, NTICK + 1):
        emo = [b + (e - b) * math.exp(-RATE * 1.0) for b, e in zip(BASE, emo)]
        if tick in EVENTS:
            idx, delta = EVENTS[tick]
            emo[idx - 1] = max(0.0, min(100.0, emo[idx - 1] + delta))
        rows.append(list(emo))
    return rows


def read_fortran(path):
    rows = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("#D"):
                rows.append([float(x) for x in line.split()[1:]])
    return rows


def main() -> int:
    fortran = read_fortran("out.txt")
    python = simulate()

    if len(fortran) != len(python):
        print(f"FAIL: row count mismatch fortran={len(fortran)} python={len(python)}")
        return 1

    max_diff = 0.0
    for r, (fr, pr) in enumerate(zip(fortran, python), 1):
        for a, b in zip(fr, pr):
            d = abs(a - b)
            if d > max_diff:
                max_diff = d
            if d > 1e-6:
                print(f"DIFF tick={r}: fortran={a!r} python={b!r}")

    status = "PASS" if max_diff < 1e-9 else "CHECK"
    print(f"rows={len(fortran)}  values={len(fortran) * NEMO}  max_diff={max_diff:.3e}  -> {status}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
