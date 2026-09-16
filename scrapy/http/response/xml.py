"""
This module implements the :class:`XmlResponse` class which is used as a
content type marker by :class:`~scrapy.selector.Selector` and can be used in
``isinstance()`` checks.

See documentation in docs/topics/request-response.rst
"""

from scrapy.http.response.text import TextResponse


class XmlResponse(TextResponse):
    __slots__ = ()
