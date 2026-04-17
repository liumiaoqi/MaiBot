import sys
from pathlib import Path

# Add project root to Python path so src imports work
project_root = Path(__file__).parent.parent.absolute()
src_root = project_root / "src"
if str(src_root) not in sys.path:
    sys.path.insert(0, str(src_root))
if str(project_root) not in sys.path:
    sys.path.insert(1, str(project_root))
