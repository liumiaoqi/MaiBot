"""插件运行时测试的统一跳过条件。

`plugins/maibot-team.*` 在 git 里是 **gitlink**（mode 160000），但仓库没有 `.gitmodules`
——它们没有可 clone 的来源，CI 检出后是空目录。本地有内容是因为手动放进去的。

所以这里按「插件清单文件是否存在」判断：本地照常跑，CI 整目录 skip。
注意判据必须是 `_manifest.json` 而不是目录本身——gitlink 会让空目录也 `is_dir()` 为真。
"""

from pathlib import Path

import pytest

_PLUGIN_MANIFEST = Path(__file__).resolve().parents[2] / "plugins" / "maibot-team.napcat-adapter" / "_manifest.json"


def pytest_collection_modifyitems(config, items):
    if _PLUGIN_MANIFEST.is_file():
        return
    skip = pytest.mark.skip(reason="plugins/ 未就绪（gitlink 无 .gitmodules，CI 检出为空壳）")
    for item in items:
        item.add_marker(skip)
