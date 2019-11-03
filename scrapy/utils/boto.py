"""Boto/botocore helpers"""

from scrapy.exceptions import NotConfigured


def is_botocore():
    try:
        import botocore
        return True
    except ImportError:
        raise NotConfigured('missing botocore library')
