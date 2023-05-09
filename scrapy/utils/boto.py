"""Boto/botocore helpers"""


def is_botocore_available():
    try:
        import botocore  # noqa: F401

        return True
    except ImportError:
        return False
