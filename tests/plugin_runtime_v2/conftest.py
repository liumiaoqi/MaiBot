"""插件集成测试的 collection 守卫。

`plugins/` 是被 `.gitignore` 忽略的独立插件仓（第 365 行 `/plugins/*`）：本机有挂载，
CI 里没有。而本目录几个用例在**模块级**调用 `import_plugin_module(...)`，插件缺失时
collection 阶段就抛 `FileNotFoundError`，把整轮 pytest 打断在 collecting 阶段。

所以这里按插件目录是否存在决定是否收集——本地照常跑，CI 里跳过这三个文件。
注意 `collect_ignore` 是静默的（不会报 skip 原因），这是唯一能在 import 前生效的机制；
如需可见性，请看 CI 日志里本目录收集到的条数。
"""

from pathlib import Path

_PLUGINS_ROOT = Path(__file__).resolve().parents[2] / "plugins"

# 依赖具体插件目录的用例 → 该目录不在时跳过收集
_REQUIRES = {
    "test_napcat_v4.py": "maibot-team.napcat-adapter",
    "test_v1_compat.py": "maibot-team.v1-compat",
    "test_zg16_1_e2e.py": "maibot-team.napcat-adapter",
}

collect_ignore_glob = [
    filename for filename, plugin in _REQUIRES.items() if not (_PLUGINS_ROOT / plugin).is_dir()
]
