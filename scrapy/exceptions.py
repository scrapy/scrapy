"""
Scrapy core exceptions

These exceptions are documented in docs/topics/exceptions.rst. Please don't add
new exceptions here without documenting them there.
"""
from typing import Any

# Internal


class NotConfigured(Exception):
    """Indicates a missing configuration situation"""

    pass


class _InvalidOutput(TypeError):
    """
    Indicates an invalid value has been returned by a middleware's processing method.
    Internal and undocumented, it should not be raised or caught by user code.
    """

    pass


# HTTP and crawling


class IgnoreRequest(Exception):
    """Indicates a decision was made not to process a request"""


class DontCloseSpider(Exception):
    """Request the spider not to be closed yet"""

    pass


class CloseSpider(Exception):
    """Raise this from callbacks to request the spider to be closed"""

    def __init__(self, reason: str = "cancelled"):
        super().__init__()
        self.reason = reason


class StopDownload(Exception):
    """
    Stop the download of the body for a given response.
    The 'fail' boolean parameter indicates whether or not the resulting partial response
    should be handled by the request errback. Note that 'fail' is a keyword-only argument.
    """

    def __init__(self, *, fail: bool = True):
        super().__init__()
        self.fail = fail


# Items


class DropItem(Exception):
    """Drop item from the item pipeline"""

    pass


class NotSupported(Exception):
    """Indicates a feature or method is not supported"""

    pass


# Commands


class UsageError(Exception):
    """To indicate a command-line usage error"""

    def __init__(self, *a: Any, **kw: Any):
        self.print_help = kw.pop("print_help", True)
        super().__init__(*a, **kw)


class ScrapyDeprecationWarning(Warning):
    """Warning category for deprecated features, since the default
    DeprecationWarning is silenced on Python 2.7+
    """

    pass


class ContractFail(AssertionError):
    """Error raised in case of a failing contract"""

    pass
