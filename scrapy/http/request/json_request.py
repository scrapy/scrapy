"""
This module implements the JSONRequest class which is a more convenient class
(than Request) to generate JSON Requests.

See documentation in docs/topics/request-response.rst
"""

import json

from scrapy.http.request import Request


class JSONRequest(Request):
    def __init__(self, *args, **kwargs):
        data = kwargs.pop('data', None)
        if data:
            kwargs['body'] = json.dumps(data)

            if 'method' not in kwargs:
                kwargs['method'] = 'POST'

        super(JSONRequest, self).__init__(*args, **kwargs)
        self.headers.setdefault('Content-Type', 'application/json')
        self.headers.setdefault('Accept', 'application/json, text/javascript, */*; q=0.01')
