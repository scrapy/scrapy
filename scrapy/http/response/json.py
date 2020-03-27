"""
This module implements the JsonResponse class which adds encoding
discovering through JSON encoding declarations to the TextResponse class.

See documentation in docs/topics/request-response.rst
"""

from scrapy.http.response.text import TextResponse


class JsonResponse(TextResponse):
    pass
