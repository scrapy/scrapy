"""
This module implements the FormRequest class which is a more covenient class
(that Request) to generate Requests based on form data.

See documentation in docs/ref/request-response.rst
"""

import urllib

from scrapy.http.request import Request
from scrapy.utils.python import unicode_to_str

def _unicode_to_str(string, encoding):
    if hasattr(string, '__iter__'):
        return [unicode_to_str(k, encoding) for k in string]
    else:
        return unicode_to_str(string, encoding)


class FormRequest(Request):

    def __init__(self, *args, **kwargs):
        formdata = kwargs.pop('formdata', None)
        Request.__init__(self, *args, **kwargs)

        if formdata:
            items = formdata.iteritems() if isinstance(formdata, dict) else formdata
            query = [(unicode_to_str(k, self.encoding), _unicode_to_str(v, self.encoding))
                    for k, v in items]
            self.body = urllib.urlencode(query, doseq=1)
            self.headers['Content-Type'] = 'application/x-www-form-urlencoded'
