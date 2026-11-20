"""插件集成测试的 collection 守卫。

`plugins/` 是被 `.gitignore` 忽略的独立插件仓（第 365 行 `/plugins/*`）：本机有挂载，
CI 里没有。而本目录几个用例在**模块级**调用 `import_plugin_module(...)`，插件缺失时
collection 阶段就抛 `FileNotFoundError`，把整轮 pytest 打断在 collecting 阶段。

所以这里按插件目录是否存在决定是否收集——本地照常跑，CI 里跳过这三个文件。

用绝对路径的 `collect_ignore` 而不是 `collect_ignore_glob`：后者相对 conftest 目录做
glob，在 `--import-mode=importlib` 下实测未生效（CI run 44809767036 仍然报错）。
`collect_ignore` 接受绝对路径，不依赖匹配语义。

注意这是静默的（不会报 skip 原因），因为要在 import 前生效，pytest 只提供这一种机制。
"""

from pathlib import Path

_HERE = Path(__file__).resolve().parent
_PLUGINS_ROOT = _HERE.parents[1] / "plugins"

# 依赖具体插件目录的用例 → 该目录不在时跳过收集
_REQUIRES = {
    "test_napcat_v4.py": "maibot-team.napcat-adapter",
    "test_v1_compat.py": "maibot-team.v1-compat",
    "test_zg16_1_e2e.py": "maibot-team.napcat-adapter",
}

collect_ignore = [
    str(_HERE / filename)
    for filename, plugin in _REQUIRES.items()
    if not (_PLUGINS_ROOT / plugin).is_dir()
]
