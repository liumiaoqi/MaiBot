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


@pytest.fixture(autouse=True, scope="session")
def _mark_test_mode() -> None:
    """ZG-7 接线：测试运行标记 TAINT_TEST_MODE（registry 未注册时透明跳过）。"""
    try:
        from src.core.tainted_mask.mark import mark_taint
        from src.core.tainted_mask.taint_flag import TaintFlag

        mark_taint(TaintFlag.TAINT_TEST_MODE)
    except Exception:
        pass
