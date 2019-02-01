"""
This module implements the HtmlResponse class which adds encoding
discovering through HTML encoding declarations to the TextResponse class.

See documentation in docs/topics/request-response.rst
"""

from scrapy.http.response.text import TextResponse

class HtmlResponse(TextResponse):
    """The :class:`HtmlResponse` class is a subclass of :class:`TextResponse`
    which adds encoding auto-discovering support by looking into the HTML `meta
    http-equiv`_ attribute.  See :attr:`TextResponse.encoding`.

    .. _meta http-equiv: https://www.w3schools.com/TAGS/att_meta_http_equiv.asp
    """
    pass
