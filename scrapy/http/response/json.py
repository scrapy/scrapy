"""
This module implements the JsonResponse class which adds encoding
discovering through JSON encoding declarations to the TextResponse class.

See documentation in docs/topics/request-response.rst
"""

import json
from scrapy.http.response.text import TextResponse


class JsonResponse(TextResponse):

    def json(self):
        """Return body as JSON"""
        return json.loads(self.text)
