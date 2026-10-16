import hashlib
import sys
from pathlib import Path

import pytest

# Add project root to Python path so src imports work
project_root = Path(__file__).parent.parent.absolute()
src_root = project_root / "src"
if str(src_root) not in sys.path:
    sys.path.insert(0, str(src_root))
if str(project_root) not in sys.path:
    sys.path.insert(1, str(project_root))


def snapshot_config(path: Path) -> tuple[str, int, int]:
    """活配置的指纹：``(sha256, 字节数, mtime_ns)``。

    三样一起才咬得住三类写入：改内容（sha256）、同长度替换（字节数）、
    **内容等值但确实动过盘**（mtime_ns）。
    """

    stat = path.stat()
    return (hashlib.sha256(path.read_bytes()).hexdigest(), stat.st_size, stat.st_mtime_ns)


def assert_config_untouched(path: Path, before: tuple[str, int, int]) -> None:
    """`before` 之后活配置必须**逐字节未变**；变了就红（带可归因的对比）。

    Raises:
        AssertionError: 文件内容或 mtime 变了（跑测试写了仓库配置）。
    """

    after = snapshot_config(path)
    assert after == before, (
        f"测试写了**活配置**：{path}\n"
        f"  跑前 sha256={before[0][:12]}… size={before[1]} mtime_ns={before[2]}\n"
        f"  跑后 sha256={after[0][:12]}… size={after[1]} mtime_ns={after[2]}\n"
        "  跑测试不该写回仓库配置：用**生产路径**初始化配置的用例（initialize_config → "
        "ConfigManager 读 config/bot_config.toml）在 CONFIG_VERSION 高于盘上版本时会触发"
        "**正常升级写回**（留档 config/old/ + os.replace 原子写）。"
        "把路径换成 tmp 副本即可（先例见 pytests/common_test/test_chat_config_utils.py 的 _init_config）。"
    )


@pytest.fixture(autouse=True, scope="session")
def _guard_live_config_untouched() -> None:
    """绊线（2026-10-17）：**整条 pytests 跑完后，活配置必须逐字节未变**。

    背景（实测）：某条用例的 autouse fixture 用**生产路径** `initialize_config()`，
    而 `CONFIG_VERSION`（8.29.1）高于盘上（8.29.0）⇒ 触发正常升级写回：
    活配置被改成 8.29.1，并在 `config/old/` 留下留档（一次全量跑下来 17 份）。

    这条绊线**不阻止写入**（那是写者自己的事，见 `_init_config` 的路径重定向），
    而是在会话结束时**出声**：让"跑测试写仓库配置"这件事无处可藏。
    鉴别力（合成写者必须让它红）见 `pytests/common_test/test_config_writeback_guard.py`。
    """

    from src.config.config import BOT_CONFIG_PATH

    if not BOT_CONFIG_PATH.exists():
        yield
        return
    before = snapshot_config(BOT_CONFIG_PATH)
    yield
    assert_config_untouched(BOT_CONFIG_PATH, before)


@pytest.fixture(autouse=True, scope="session")
def _mark_test_mode() -> None:
    """ZG-7 接线：测试运行标记 TAINT_TEST_MODE（registry 未注册时透明跳过）。"""
    try:
        from src.core.tainted_mask.mark import mark_taint
        from src.core.tainted_mask.taint_flag import TaintFlag

        mark_taint(TaintFlag.TAINT_TEST_MODE)
    except Exception:
        pass
