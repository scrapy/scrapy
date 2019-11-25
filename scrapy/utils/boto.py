"""Boto/botocore helpers"""

from __future__ import absolute_import

from scrapy.exceptions import NotConfigured


def is_botocore():
    try:
        import botocore  # noqa: F401
        return True
    except ImportError:
        raise NotConfigured('missing botocore library')
