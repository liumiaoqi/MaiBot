"""容器资源约束适配模块。

自动检测 Docker cgroups 的 CPU 和内存限制，调整线程池大小和运行时参数。
"""

from __future__ import annotations

import os

from src.common.logger import get_logger

logger = get_logger("container_resource_adapter")


def get_cpu_limit() -> int:
    """获取容器可用的 CPU 核心数。

    优先读取 cgroups v2 的 cpu.max，然后 cgroups v1 的 cpu.cfs_quota_us，
    最后回退到 os.cpu_count()。
    """
    try:
        cpu_max_path = "/sys/fs/cgroup/cpu.max"
        if os.path.exists(cpu_max_path):
            with open(cpu_max_path) as f:
                content = f.read().strip()
            parts = content.split()
            if len(parts) == 2 and parts[0] != "max":
                quota = int(parts[0])
                period = int(parts[1])
                if period > 0:
                    return max(1, int(quota / period))
    except Exception:
        pass

    try:
        quota_path = "/sys/fs/cgroup/cpu/cpu.cfs_quota_us"
        period_path = "/sys/fs/cgroup/cpu/cpu.cfs_period_us"
        if os.path.exists(quota_path) and os.path.exists(period_path):
            with open(quota_path) as f:
                quota = int(f.read().strip())
            with open(period_path) as f:
                period = int(f.read().strip())
            if quota > 0 and period > 0:
                return max(1, int(quota / period))
    except Exception:
        pass

    return os.cpu_count() or 2


def get_memory_limit_mb() -> int:
    """获取容器的内存限制（MB）。

    优先读取 cgroups v2 的 memory.max，然后 cgroups v1 的 memory.limit_in_bytes，
    最后回退到系统可用内存。
    """
    try:
        mem_max_path = "/sys/fs/cgroup/memory.max"
        if os.path.exists(mem_max_path):
            with open(mem_max_path) as f:
                content = f.read().strip()
            if content != "max":
                limit_bytes = int(content)
                if limit_bytes > 0:
                    return limit_bytes // (1024 * 1024)
    except Exception:
        pass

    try:
        mem_limit_path = "/sys/fs/cgroup/memory/memory.limit_in_bytes"
        if os.path.exists(mem_limit_path):
            with open(mem_limit_path) as f:
                limit_bytes = int(f.read().strip())
            if 0 < limit_bytes < 2**63:
                return limit_bytes // (1024 * 1024)
    except Exception:
        pass

    return 0


def is_running_in_container() -> bool:
    """检测是否运行在容器中。"""
    indicators = [
        "/.dockerenv",
        "/run/.containerenv",
    ]
    for path in indicators:
        if os.path.exists(path):
            return True

    try:
        cgroup_path = "/proc/1/cgroup"
        if os.path.exists(cgroup_path):
            with open(cgroup_path) as f:
                content = f.read()
            if "docker" in content or "containerd" in content:
                return True
    except Exception:
        pass

    return False


def get_recommended_thread_pool_size() -> int:
    """根据容器资源约束推荐线程池大小。"""
    cpu_limit = get_cpu_limit()
    mem_limit_mb = get_memory_limit_mb()

    if mem_limit_mb > 0 and mem_limit_mb <= 512:
        return max(1, cpu_limit)
    if mem_limit_mb > 0 and mem_limit_mb <= 2048:
        return max(1, cpu_limit * 2)

    return max(2, cpu_limit * 2)


def log_resource_info() -> None:
    """记录容器资源信息。"""
    in_container = is_running_in_container()
    cpu_limit = get_cpu_limit()
    mem_limit_mb = get_memory_limit_mb()
    thread_pool_size = get_recommended_thread_pool_size()

    logger.info(
        f"运行环境: {'容器' if in_container else '宿主机'}, "
        f"CPU限制: {cpu_limit}核, "
        f"内存限制: {mem_limit_mb}MB" if mem_limit_mb > 0 else f"运行环境: {'容器' if in_container else '宿主机'}, CPU限制: {cpu_limit}核, 内存限制: 未检测到",
    )
    logger.info(f"推荐线程池大小: {thread_pool_size}")