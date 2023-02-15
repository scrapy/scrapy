"""Boto/botocore helpers"""


def is_botocore_available():
    try:
        import botocore  # noqa: F401

        return True
    except ImportError:
        return False


def is_boto3_available():
    try:
        import boto3  # noqa: F401

        return True
    except ImportError:
        return False
