from __future__ import annotations


def rerp_available() -> bool:
    # check if robotexclusionrulesparser is installed
    try:
        from robotexclusionrulesparser import (  # noqa: PLC0415
            RobotExclusionRulesParser,  # noqa: F401
        )
    except ImportError:
        return False
    return True
