"""绊线的**鉴别力**判据：合成一个"确实写了配置"的写者 ⇒ 绊线必须红。

绊线本体在 `pytests/conftest.py`（`_guard_live_config_untouched`，会话级 autouse）：
整条 pytests 跑完后，**活配置必须逐字节未变**（sha256 + 字节数 + mtime_ns）。

为什么用 tmp 路径做鉴别力：会话级绊线在**会话结束**才断言，直接拿真文件试会
①不能在同一用例里断言它红 ②还真的会弄脏活配置。⇒ 这里对**辅助函数本身**做鉴别力，
真文件只由会话级绊线守（这是等价的：判据逻辑同一份代码）。
"""

import os
from pathlib import Path

import pytest

from pytests.conftest import assert_config_untouched, snapshot_config


def _fake_live_config(tmp_path: Path) -> Path:
    """造一个"活配置"（内容与真实配置同形，但落在 tmp 里）。"""

    path = tmp_path / "bot_config.toml"
    path.write_text('[inner]\nversion = "8.29.0"\n', encoding="utf-8")
    return path


def test_guard_passes_when_config_untouched(tmp_path: Path) -> None:
    """对照臂：没写 ⇒ 不抛（否则绊线是"永远红"，等于没有判据）。"""

    live = _fake_live_config(tmp_path)
    before = snapshot_config(live)

    assert_config_untouched(live, before)  # 不该抛


def test_guard_discriminates_a_real_writeback(tmp_path: Path) -> None:
    """**鉴别力**：合成"生产路径升级写回"（内容变了 + 盘被动过）⇒ 必须红。"""

    live = _fake_live_config(tmp_path)
    before = snapshot_config(live)

    # 合成写者：等价于 config.py:1110-1114 的写回（版本被升级后 os.replace 落盘）
    live.write_text('[inner]\nversion = "8.29.1"\n', encoding="utf-8")

    with pytest.raises(AssertionError, match="测试写了\\*\\*活配置\\*\\*"):
        assert_config_untouched(live, before)


def test_guard_discriminates_mtime_only_change(tmp_path: Path) -> None:
    """**鉴别力（更严的一档）**：内容等值、只是**动过盘** ⇒ 也要红。

    为什么需要这一档：写回可能刚好写出等值内容（比如升级链只补注释/仅 touch），
    那时只看 sha256 会漏，靠 mtime_ns 咬住。
    """

    live = _fake_live_config(tmp_path)
    before = snapshot_config(live)

    os.utime(live, ns=(before[2] + 10**9, before[2] + 10**9))  # 只改 mtime

    with pytest.raises(AssertionError, match="测试写了\\*\\*活配置\\*\\*"):
        assert_config_untouched(live, before)


def test_guard_discriminates_equal_length_content_change(tmp_path: Path) -> None:
    """**鉴别力（同长度替换）**：字节数不变、内容变了 ⇒ 靠 sha256 咬住。"""

    live = _fake_live_config(tmp_path)
    before = snapshot_config(live)

    text = live.read_text(encoding="utf-8")
    live.write_text(text.replace("8.29.0", "9.29.0"), encoding="utf-8")  # 同长度
    assert live.stat().st_size == before[1], "本用例前提：长度不变"

    with pytest.raises(AssertionError, match="测试写了\\*\\*活配置\\*\\*"):
        assert_config_untouched(live, before)
