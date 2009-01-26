"""
This module implements the FormRequest class which is a more covenient class
(that Request) to generate Requests based on form data.

See documentation in docs/ref/request-response.rst
"""

import urllib

from scrapy.http.request import Request
from scrapy.utils.python import unicode_to_str

class FormRequest(Request):

    def __init__(self, *args, **kwargs):
        formdata = kwargs.pop('formdata', None)
        Request.__init__(self, *args, **kwargs)
        if formdata:
            items = formdata.iteritems() if isinstance(formdata, dict) else formdata
            query = [(unicode_to_str(k, self.encoding), unicode_to_str(v, self.encoding)) for k, v in items]
            self.body = urllib.urlencode(query)
            self.headers['Content-Type'] = 'application/x-www-form-urlencoded'
