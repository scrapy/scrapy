"""Boto/botocore helpers"""

from __future__ import absolute_import
import warnings
import six

from scrapy.exceptions import NotConfigured
from scrapy.exceptions import ScrapyDeprecationWarning


def is_botocore():
    try:
        import botocore
        return True
    except ImportError:
        if six.PY2:
            try:
                import boto
                message = (
                    'Usage of boto in Scrapy is deprecated. '
                    'Consider installing botocore for a stable and recommended way to access AWS.'
                )
                warnings.warn(message, category=ScrapyDeprecationWarning, stacklevel=2)
                return False
            except ImportError:
                raise NotConfigured('missing botocore or boto library')
        else:
            raise NotConfigured('missing botocore library')
