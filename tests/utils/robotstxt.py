from __future__ import annotations

from importlib.util import find_spec


def rerp_available() -> bool:
    return find_spec("robotexclusionrulesparser") is not None
