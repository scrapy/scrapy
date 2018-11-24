"""
This module implements the JSONRequest class which is a more convenient class
(than Request) to generate JSON Requests.

See documentation in docs/topics/request-response.rst
"""

import json

from scrapy.http.request import Request


class JSONRequest(Request):
    def __init__(self, *args, **kwargs):
        if 'method' not in kwargs:
            kwargs['method'] = 'POST'

        data = kwargs.pop('data', {})
        kwargs['body'] = json.dumps(data)
        super(JSONRequest, self).__init__(*args, **kwargs)
        self.headers.setdefault(b'Content-Type', b'application/json')

    def replace(self, *args, **kwargs):
        """ Create a new Request with the same attributes except for those
            given new values. """

        kwargs.pop('body', None)
        return super(JSONRequest, self).replace(*args, **kwargs)
