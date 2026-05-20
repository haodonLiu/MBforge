import sys
from pathlib import Path

# 确保 src 在路径最前面
src_path = str(Path(__file__).parent.parent / "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)
