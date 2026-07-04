"""C 扩展兼容性评估报告。

扫描 pyproject.toml 中的所有依赖，按自由线程 Python 3.14 兼容性分级：
- A: 已支持自由线程
- B: 部分支持或待验证
- C: 不支持，需降级方案

生成时间: 2026-07-04
"""

from __future__ import annotations

C_EXTENSION_ASSESSMENT: dict[str, dict[str, str]] = {
    # A级：已支持自由线程
    "numpy": {"level": "A", "note": "NumPy 2.x 已支持自由线程构建，需安装 numpy-freethreading 或从源码编译"},
    "pandas": {"level": "A", "note": "Pandas 2.x 依赖 NumPy，随 NumPy 自由线程版本可用"},
    "scipy": {"level": "A", "note": "SciPy 1.14+ 已支持自由线程构建"},
    "pyarrow": {"level": "A", "note": "PyArrow 已支持自由线程"},
    "pillow": {"level": "A", "note": "Pillow 已支持自由线程"},
    "pydantic": {"level": "A", "note": "Pydantic V2 核心为 Rust 实现，无 GIL 依赖"},
    "sqlalchemy": {"level": "A", "note": "纯 Python 实现，无 C 扩展"},
    "sqlmodel": {"level": "A", "note": "纯 Python 实现，无 C 扩展"},
    "aiohttp": {"level": "A", "note": "核心为 C 扩展但已支持自由线程"},
    "httpx": {"level": "A", "note": "纯 Python 实现，无 C 扩展"},
    "openai": {"level": "A", "note": "纯 Python 实现，无 C 扩展"},
    "fastapi": {"level": "A", "note": "纯 Python 实现，无 C 扩展"},
    "uvicorn": {"level": "A", "note": "纯 Python 实现（uvloop 为可选 C 加速）"},
    "rich": {"level": "A", "note": "纯 Python 实现，无 C 扩展"},
    "msgpack": {"level": "A", "note": "C 扩展可选，有纯 Python fallback"},
    "pyyaml": {"level": "A", "note": "LibYAML 绑定可选，有纯 Python fallback"},

    # B级：部分支持或待验证
    "rapidfuzz": {"level": "B", "note": "C++ 扩展，需验证自由线程构建；有纯 Python fallback 但性能差"},
    "jieba": {"level": "B", "note": "纯 Python 实现，但依赖可选的 C 扩展加速"},
    "pypinyin": {"level": "B", "note": "纯 Python 实现，无 C 扩展，但需验证线程安全性"},
    "colorama": {"level": "B", "note": "纯 Python，但 Windows API 调用需验证线程安全"},
    "watchfiles": {"level": "B", "note": "Rust 扩展，需验证自由线程兼容性"},
    "playwright": {"level": "B", "note": "Node.js 子进程通信，不直接涉及 GIL，但需验证并发安全性"},
    "structlog": {"level": "B", "note": "纯 Python，但需验证线程安全的日志输出"},
    "tomlkit": {"level": "B", "note": "纯 Python，无 C 扩展"},
    "Babel": {"level": "B", "note": "纯 Python，无 C 扩展"},
    "google-genai": {"level": "B", "note": "纯 Python SDK，需验证线程安全性"},
    "json-repair": {"level": "B", "note": "纯 Python，无 C 扩展"},
    "mcp": {"level": "B", "note": "纯 Python SDK，需验证线程安全性"},
    "python-multipart": {"level": "B", "note": "纯 Python，无 C 扩展"},
    "typing-extensions": {"level": "B", "note": "纯 Python，无 C 扩展"},
    "certifi": {"level": "B", "note": "纯 Python（CA 证书包），无 C 扩展"},

    # C级：不支持自由线程
    "faiss-cpu": {
        "level": "C",
        "note": "Facebook FAISS C++ 库绑定，不支持自由线程",
        "fallback": "使用 numpy 手动实现简单向量搜索，或降级为单线程模式使用 faiss-cpu",
    },
    "ahocorasick-rs": {
        "level": "C",
        "note": "Rust 实现的 Aho-Corasick 自动机，不支持自由线程",
        "fallback": "使用纯 Python 的 pyahocorasick 替代，或降级为单线程模式使用 ahocorasick-rs",
    },
}

# 项目自有包（无兼容性问题）
_INTERNAL_PACKAGES = [
    "maim-message",
    "maibot-dashboard",
    "maibot-plugin-sdk",
]

# 开发依赖
_DEV_PACKAGES = {
    "pytest": {"level": "A", "note": "纯 Python，无 C 扩展"},
    "pytest-asyncio": {"level": "A", "note": "纯 Python，无 C 扩展"},
    "ruff": {"level": "A", "note": "Rust 实现，无 GIL 依赖"},
    "zstandard": {"level": "B", "note": "C 扩展，需验证自由线程构建"},
}


def get_assessment() -> dict[str, dict[str, str]]:
    """返回完整的 C 扩展兼容性评估。"""
    return C_EXTENSION_ASSESSMENT


def get_c_level_packages() -> dict[str, dict[str, str]]:
    """返回 C 级（不支持自由线程）的包及其降级方案。"""
    return {k: v for k, v in C_EXTENSION_ASSESSMENT.items() if v["level"] == "C"}


def get_summary() -> dict[str, int]:
    """返回兼容性分级汇总。"""
    counts = {"A": 0, "B": 0, "C": 0}
    for v in C_EXTENSION_ASSESSMENT.values():
        level = v["level"]
        if level in counts:
            counts[level] += 1
    return counts