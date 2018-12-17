"""
This module implements the JSONRequest class which is a more convenient class
(than Request) to generate JSON Requests.

See documentation in docs/topics/request-response.rst
"""

import json
import warnings

from scrapy.http.request import Request


class JSONRequest(Request):
    def __init__(self, *args, **kwargs):
        dumps_kwargs = kwargs.pop('dumps_kwargs', {})
        body_passed = kwargs.get('body', None) is not None
        data = kwargs.pop('data', None)
        data_passed = data is not None

        if body_passed and data_passed:
            warnings.warn('Both body and data passed. data will be ignored')

        elif not body_passed and data_passed:
            kwargs['body'] = self.dump(data, **dumps_kwargs)

            if 'method' not in kwargs:
                kwargs['method'] = 'POST'

        super(JSONRequest, self).__init__(*args, **kwargs)
        self.headers.setdefault('Content-Type', 'application/json')
        self.headers.setdefault('Accept', 'application/json, text/javascript, */*; q=0.01')
        self._dumps_kwargs = dumps_kwargs

    def replace(self, *args, **kwargs):
        body_passed = kwargs.get('body', None) is not None
        data = kwargs.pop('data', None)
        data_passed = data is not None

        if body_passed and data_passed:
            warnings.warn('Both body and data passed. data will be ignored')

        elif not body_passed and data_passed:
            kwargs['body'] = self.dump(data, **self._dumps_kwargs)

        return super(JSONRequest, self).replace(*args, **kwargs)

    def dump(self, data, **kwargs):
        """Convert to JSON """
        return json.dumps(data, sort_keys=True, **kwargs)
