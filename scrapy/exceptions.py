"""
Scrapy core exceptions

These exceptions are documented in docs/topics/exceptions.rst. Please don't add
new exceptions here without documenting them there.
"""

from scrapy import log

# Internal

class NotConfigured(Exception):
    """Indicates a missing configuration situation"""
    pass

# HTTP and crawling

class IgnoreRequest(Exception):
    """Indicates a decision was made not to process a request"""

    def __init__(self, msg='', level=log.ERROR):
        self.msg = msg
        self.level = level

    def __str__(self):
        return self.msg

class DontCloseSpider(Exception):
    """Request the spider not to be closed yet"""
    pass

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
    def __init__(self, *a, **kw):
        self.print_help = kw.pop('print_help', True)
        super(UsageError, self).__init__(*a, **kw)
