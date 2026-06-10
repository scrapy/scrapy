"""Boto/botocore helpers"""


def is_botocore_available() -> bool:
    try:
        import botocore  # noqa: F401,PLC0415

        return True
    except ImportError:
        return False
