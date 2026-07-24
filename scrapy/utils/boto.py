"""Boto/botocore helpers"""

from importlib.util import find_spec


def is_botocore_available() -> bool:
    return find_spec("botocore") is not None


def is_aiobotocore_available() -> bool:
    return find_spec("aiobotocore") is not None


def is_aioboto3_available() -> bool:
    return find_spec("aioboto3") is not None
