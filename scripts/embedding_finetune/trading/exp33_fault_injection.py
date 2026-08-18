#!/usr/bin/env python3
"""exp33: 量子信道式故障注入——bitflip 混沌测试 sqlite 存储鲁棒性(ZG)

exp19 的 bitflip 信道模拟量子 X 门错误 = 真实硬件位翻转(宇宙射线/老化)。
本实验:对 sqlite 数据库文件做位翻转注入,测鲁棒性边界:
- 建测试库(relations 表 + 100 条数据)
- 注入 N 个随机 bit 翻转(文件层面)
- 测:能否打开?integrity_check 过不过?数据还能不能读?
- 参数扫描 N ∈ {1,4,16,64,256,1024} × 30 次;对比均匀翻转 vs 数据区集中翻转
"""

import os
import sqlite3
import tempfile
import numpy as np

rng = np.random.RandomState(20260818)


def build_db(path):
    """建测试库:relations 表 + 100 条数据(先删旧文件,防损坏库残留)。"""
    if os.path.exists(path):
        os.remove(path)
    conn = sqlite3.connect(path)
    conn.execute("""CREATE TABLE relations (
        hash TEXT PRIMARY KEY, subject TEXT, object TEXT,
        confidence REAL DEFAULT 1.0, metadata BLOB)""")
    for i in range(100):
        conn.execute("INSERT INTO relations VALUES (?,?,?,?,?)",
                     ('h%03d' % i, 'subject%d' % i, 'object%d' % (i % 10),
                      1.0 - i * 0.005, b'{"k": %d}' % i))
    conn.commit()
    conn.close()


def flip_bits(data, n_bits, mode='uniform'):
    """翻转 n_bits 个随机位;mode=uniform 均匀 / data 集中数据区(跳过页头 100 字节)。"""
    b = bytearray(data)
    size = len(b)
    if mode == 'uniform':
        idx = rng.randint(0, size * 8, n_bits)
    else:
        # 数据区:页头之外(前 100 字节是 sqlite 文件头,破坏它必挂——测数据区)
        start = 100 * 8
        idx = rng.randint(start, size * 8, n_bits)
    for pos in idx:
        byte_i = pos // 8
        bit_i = pos % 8
        b[byte_i] ^= (1 << bit_i)
    return bytes(b)


def test_db(path):
    """返回 0=完全可用 / 1=可开但损坏 / 2=打不开。"""
    try:
        conn = sqlite3.connect(path)
    except Exception:
        return 2
    try:
        cur = conn.cursor()
        cur.execute("PRAGMA integrity_check")
        status = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM relations")
        n = cur.fetchone()[0]
        if status == 'ok' and n == 100:
            return 0
        return 1
    except Exception:
        return 2
    finally:
        try:
            conn.close()
        except Exception:
            pass


if __name__ == '__main__':
    print('=== exp33: 量子信道式故障注入(bitflip 混沌测试 sqlite) ===')
    print('relations 表 100 条;注入位翻转 N ∈ {1,4,16,64,256,1024} × 30 次\n')

    tmp = tempfile.mkdtemp()
    dbpath = os.path.join(tmp, 'test.db')

    for mode, label in [('uniform', '均匀翻转(全文件)'), ('data', '数据区集中(跳过页头)')]:
        print('--- %s ---' % label)
        print('%-8s %12s %14s %12s' % ('翻转bit数', '完全可用%', '可开但损坏%', '打不开%'))
        for n_bits in [1, 4, 16, 64, 256, 1024]:
            results = [0, 0, 0]
            for _ in range(30):
                build_db(dbpath)
                with open(dbpath, 'rb') as f:
                    data = f.read()
                flipped = flip_bits(data, n_bits, mode)
                with open(dbpath, 'wb') as f:
                    f.write(flipped)
                results[test_db(dbpath)] += 1
            print('%-8d %12.0f %14.0f %12.0f' % (
                n_bits, results[0] / 30 * 100, results[1] / 30 * 100,
                results[2] / 30 * 100))
        print()

    # 附加:单 bit 翻转 1000 次的破坏率(最细粒度)
    print('--- 单 bit 翻转 × 1000 次(细粒度) ---')
    build_db(dbpath)
    with open(dbpath, 'rb') as f:
        data = f.read()
    ok = bad = dead = 0
    for _ in range(1000):
        with open(dbpath, 'wb') as f:
            f.write(flip_bits(data, 1, 'uniform'))
        r = test_db(dbpath)
        if r == 0: ok += 1
        elif r == 1: bad += 1
        else: dead += 1
    print('完全可用 %.1f%% / 可开但损坏 %.1f%% / 打不开 %.1f%%' % (
        ok / 10, bad / 10, dead / 10))

    print()
    print('=== 结论观察 ===')
    print('鲁棒性边界:多少位翻转内 sqlite 依然完全可用?')
    print('数据区 vs 页头:哪种翻转伤害大(验证"故障位置"与"故障数量"哪个是胜负手)?')
