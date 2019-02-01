"""
This module implements the XmlResponse class which adds encoding
discovering through XML encoding declarations to the TextResponse class.

See documentation in docs/topics/request-response.rst
"""

from scrapy.http.response.text import TextResponse

class XmlResponse(TextResponse):
    """The :class:`XmlResponse` class is a subclass of :class:`TextResponse` which
    adds encoding auto-discovering support by looking into the XML declaration
    line.  See :attr:`TextResponse.encoding`."""
    pass
