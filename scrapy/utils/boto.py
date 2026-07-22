"""Boto/botocore helpers"""

from importlib.util import find_spec


def is_botocore_available() -> bool:
    return find_spec("botocore") is not None
