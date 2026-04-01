import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
SDK_SRC = ROOT / "packages" / "integration-sdk" / "src"
PACKAGES_DIR = ROOT / "packages"

if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))
if str(SDK_SRC) not in sys.path:
    sys.path.append(str(SDK_SRC))
if str(PACKAGES_DIR) not in sys.path:
    sys.path.append(str(PACKAGES_DIR))
