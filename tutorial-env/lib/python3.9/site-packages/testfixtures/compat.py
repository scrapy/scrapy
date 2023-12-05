# compatibility module for different python versions
import sys
from typing import Tuple

PY_VERSION: Tuple[int, int] = sys.version_info[:2]

PY_37_PLUS: bool = PY_VERSION >= (3, 7)
PY_310_PLUS: bool = PY_VERSION >= (3, 10)
