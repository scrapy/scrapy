"""Boto/botocore helpers"""

from __future__ import absolute_import
import six

from scrapy.exceptions import NotConfigured


def is_botocore():
    try:
        import botocore
        return True
    except ImportError:
        if six.PY2:
            try:
                import boto
                return False
            except ImportError:
                raise NotConfigured('missing botocore or boto library')
        else:
            raise NotConfigured('missing botocore library')
