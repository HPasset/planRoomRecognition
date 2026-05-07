"""Root conftest for pytest path configuration."""
import sys
from pathlib import Path

root = Path(__file__).parent
if str(root) not in sys.path:
    sys.path.insert(0, str(root))
