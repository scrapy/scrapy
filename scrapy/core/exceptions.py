"""
Scrapy core exceptions

These exceptions are documented in docs/ref/exceptions.rst. Please don't add
new exceptions here without documenting them there.
"""

# Internal

class NotConfigured(Exception):
    """Indicates a missing configuration situation"""
    pass

# HTTP and crawling

class IgnoreRequest(Exception):
    """Indicates a decision was made not to process a request"""
    pass

class DontCloseDomain(Exception):
    """Request the domain not to be closed yet"""
    pass

class HttpException(Exception):
    def __init__(self, status, message, response):
        if not message:
            from twisted.web import http
            message = http.responses.get(int(status))

        self.status = int(status)
        self.message = message
        self.response = response
        Exception.__init__(self, status, message, response)

    def __str__(self):
        return '%s %s' % (self.status, self.message)

# Items

class DropItem(Exception):
    """Drop item from the item pipeline"""
    pass

class NotSupported(Exception):
    """Indicates a feature or method is not supported"""
    pass
