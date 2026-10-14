#!/usr/bin/env python3
"""hard_random.py — 硬件真随机源（RDSEED/RDRAND 直读，机器码注入，零编译依赖）

用途：probe27 普适性分析的「硬随机 × 伪随机」双源对照——随机实现（run）的
种子改由 CPU 芯片内的物理熵源提供（热噪声/亚稳态），而非算法伪随机。

层次：
  RDSEED  —— 原始熵输出（慢、可失败）；首选
  RDRAND  —— 经片内 DRBG 调理的硬件随机（快）；RDSEED 不可用时回退
  （对照层：os.urandom = OS 系统熵池 CSPRNG；np.random = 纯算法 MT/PCG）

实现：机器码注入（无需编译器）——
    xor rax,rax          ; 48 31 C0   fail sentinel = 0
    mov ecx, 64          ; B9 40 00 00 00   retry budget
    rdseed rax           ; 48 0F C7 F8      (offset 8)
    jnc  +4 -> ret       ; 73 04
    dec  ecx             ; FF C9
    jnz  -10 -> rdseed   ; 75 F6
    ret                  ; C3
  RDRAND 版同构，仅换指令字节 F0。失败（64 次重试耗尽）返回 0。
  64 位地址经 ctypes c_void_p restype 正确处理（历史坑：默认 c_int 截断）。

自测：python hard_random.py
"""

import ctypes
import os

__all__ = ["hw_u64", "hw_seed_sequence", "source_name", "audit", "read_stats"]

_kernel32 = ctypes.windll.kernel32
_kernel32.VirtualAlloc.restype = ctypes.c_void_p
_kernel32.VirtualAlloc.argtypes = [ctypes.c_void_p, ctypes.c_size_t,
                                   ctypes.c_ulong, ctypes.c_ulong]
_kernel32.VirtualProtect.restype = ctypes.c_int
_kernel32.VirtualProtect.argtypes = [ctypes.c_void_p, ctypes.c_size_t,
                                     ctypes.c_ulong, ctypes.POINTER(ctypes.c_ulong)]

_DEBUG = os.environ.get("HW_RAND_DEBUG") == "1"

# RDSEED: 48 0F C7 F8 | RDRAND: 48 0F C7 F0
_RDSEED_CODE = bytes([
    0x48, 0x31, 0xC0,              # xor rax, rax
    0xB9, 0x40, 0x00, 0x00, 0x00,  # mov ecx, 64
    0x48, 0x0F, 0xC7, 0xF8,        # rdseed rax
    0x73, 0x04,                    # jnc +4 -> ret
    0xFF, 0xC9,                    # dec ecx
    0x75, 0xF6,                    # jnz -10 -> rdseed
    0xC3,                          # ret
])
_RDRAND_CODE = bytes([
    0x48, 0x31, 0xC0,
    0xB9, 0x40, 0x00, 0x00, 0x00,
    0x48, 0x0F, 0xC7, 0xF0,        # rdrand rax
    0x73, 0x04,
    0xFF, 0xC9,
    0x75, 0xF6,
    0xC3,
])


def _make_fn(code: bytes):
    """把机器码写入 RX 内存并包装成 uint64(void) 函数。"""
    size = len(code)
    MEM_COMMIT_RESERVE = 0x1000 | 0x2000
    PAGE_READWRITE = 0x04
    PAGE_EXECUTE_READ = 0x20
    addr = _kernel32.VirtualAlloc(None, size, MEM_COMMIT_RESERVE, PAGE_READWRITE)
    if _DEBUG:
        print(f"[hw-rand] VirtualAlloc -> {hex(addr) if addr else 'FAIL'}, "
              f"GetLastError={_kernel32.GetLastError()}")
    if not addr:
        raise OSError("VirtualAlloc failed")
    ctypes.memmove(addr, code, size)
    old = ctypes.c_ulong(0)
    ok = _kernel32.VirtualProtect(addr, size, PAGE_EXECUTE_READ, ctypes.byref(old))
    if _DEBUG:
        print(f"[hw-rand] VirtualProtect -> {ok}, old={hex(old.value)}")
    if not ok:
        raise OSError("VirtualProtect failed")
    return ctypes.CFUNCTYPE(ctypes.c_uint64)(int(addr))


_fn_rdseed = None
_fn_rdrand = None
source_name = "unavailable"


def _looks_random(vals):
    return len(set(vals)) >= 6 and all(v != 0 for v in vals)


def _init():
    global _fn_rdseed, _fn_rdrand, source_name
    if source_name != "unavailable":
        return
    for code, name in ((_RDSEED_CODE, "rdseed"), (_RDRAND_CODE, "rdrand")):
        try:
            fn = _make_fn(code)
            vals = [fn() for _ in range(8)]
            if _DEBUG:
                print(f"[hw-rand] {name} sample: {[hex(v) for v in vals[:3]]}")
            if _looks_random(vals):
                if name == "rdseed":
                    _fn_rdseed = fn
                else:
                    _fn_rdrand = fn
                source_name = name
                return
        except OSError as e:
            if _DEBUG:
                print(f"[hw-rand] {name} init failed: {e}")
    source_name = "unavailable"


def hw_u64():
    """单次 64 位硬件随机数（RDSEED 优先，RDRAND 回退）。0 = 重试耗尽。"""
    if source_name == "unavailable":
        _init()
    if _fn_rdseed is not None:
        return int(_fn_rdseed())
    if _fn_rdrand is not None:
        return int(_fn_rdrand())
    raise RuntimeError("no hardware RNG available")


def hw_seed_sequence(n):
    """n 个硬件随机种子（int 列表），供 np.random.SeedSequence(entropy=...)。"""
    return [hw_u64() for _ in range(n)]


def read_stats(trials=20000):
    """返回 (fails, dupes, popcount_mean, low_byte_mean)，供审计用。"""
    vals = [hw_u64() for _ in range(trials)]
    fails = sum(1 for v in vals if v == 0)
    bits = sum(bin(v).count("1") for v in vals)
    low = sum(v & 0xFF for v in vals) / trials
    return fails, trials - len(set(vals)), bits / trials, low


def audit(trials=20000):
    """自测报告：可用性 / 速度 / 基本均匀性 sanity。"""
    import time
    _init()
    print(f"hardware source: {source_name}")
    if source_name == "unavailable":
        print("RDSEED/RDRAND unavailable (VM or security policy?) "
              "-- fallback: os.urandom (OS entropy pool)")
        return
    t0 = time.perf_counter()
    fails, dupes, pc, low = read_stats(trials)
    dt = time.perf_counter() - t0
    print(f"{trials} draws in {dt*1000:.1f} ms  ({dt/trials*1e6:.2f} us/draw)")
    print(f"fail(0-sentinel): {fails} | duplicates: {dupes}")
    print(f"popcount mean: {pc:.2f} (expect ~32) | low byte mean: {low:.1f} (expect ~127.5)")


if __name__ == "__main__":
    audit()
