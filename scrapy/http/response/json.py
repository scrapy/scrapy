"""
This module implements the JsonResponse class that is used when the response
has a JSON MIME type in its Content-Type header.

See documentation in docs/topics/request-response.rst
"""

from scrapy.http.response.text import TextResponse


class JsonResponse(TextResponse):
    pass
