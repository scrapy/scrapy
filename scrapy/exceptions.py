"""
Scrapy core exceptions

These exceptions are documented in docs/topics/exceptions.rst. Please don't add
new exceptions here without documenting them there.
"""

# Internal

class NotConfigured(Exception):
    """This exception can be raised by some components to indicate that they
    will remain disabled. Those components include:

    * Extensions
    * Item pipelines
    * Downloader middlewares
    * Spider middlewares

    The exception must be raised in the component's ``__init__`` method.
    """
    pass

# HTTP and crawling

class IgnoreRequest(Exception):
    """This exception can be raised by the Scheduler or any downloader
    middleware to indicate that the request should be ignored."""

class DontCloseSpider(Exception):
    """This exception can be raised in a :signal:`spider_idle` signal handler
    to prevent the spider from being closed."""
    pass

class CloseSpider(Exception):
    """This exception can be raised from a spider callback to request the
    spider to be closed/stopped. Supported arguments:

    :param reason: the reason for closing
    :type reason: str

    For example::

        def parse_page(self, response):
            if 'Bandwidth exceeded' in response.body:
                raise CloseSpider('bandwidth_exceeded')
    """

    def __init__(self, reason='cancelled'):
        super(CloseSpider, self).__init__()
        self.reason = reason

# Items

class DropItem(Exception):
    """The exception that must be raised by item pipeline stages to stop
    processing an Item. For more information see
    :ref:`topics-item-pipeline`."""
    pass

class NotSupported(Exception):
    """This exception is raised to indicate an unsupported feature."""
    pass

# Commands

class UsageError(Exception):
    """To indicate a command-line usage error"""
    def __init__(self, *a, **kw):
        self.print_help = kw.pop('print_help', True)
        super(UsageError, self).__init__(*a, **kw)

class ScrapyDeprecationWarning(Warning):
    """Warning category for deprecated features, since the default
    DeprecationWarning is silenced on Python 2.7+
    """
    pass

class ContractFail(AssertionError):
    """Error raised in case of a failing contract"""
    pass
