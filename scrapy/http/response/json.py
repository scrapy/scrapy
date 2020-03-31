"""
This module implements the JsonResponse class which adds encoding
discovering through JSON encoding declarations to the TextResponse class.

See documentation in docs/topics/request-response.rst
"""

import json

from scrapy.http.response.text import TextResponse


class JsonResponse(TextResponse):

    def __init__(self, *args, **kwargs):
        self._json = None
        super(JsonResponse, self).__init__(*args, **kwargs)

    def json(self):
        """Returns the JSON-encoded body deserialized into a Python object"""
        if self._json is None:
            self._json = json.loads(self.text)
        return self._json
