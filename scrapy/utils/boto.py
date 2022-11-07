"""Boto/botocore helpers"""
import warnings

from scrapy.exceptions import NotConfigured, ScrapyDeprecationWarning


def is_botocore():
    """ Returns True if botocore is available, otherwise raises NotConfigured. Never returns False.

    Previously, when boto was supported in addition to botocore, this returned False if boto was available
    but botocore wasn't.
    """
    message = (
        'is_botocore() is deprecated and always returns True or raises an Exception, '
        'so it cannot be used for checking if boto is available instead of botocore. '
        'You can use scrapy.utils.boto.is_botocore_available() to check if botocore '
        'is available.'
    )
    warnings.warn(message, ScrapyDeprecationWarning, stacklevel=2)
    try:
        import botocore  # noqa: F401
        return True
    except ImportError:
        raise NotConfigured('missing botocore library')


def is_botocore_available():
    try:
        import botocore  # noqa: F401
        return True
    except ImportError:
        return False
