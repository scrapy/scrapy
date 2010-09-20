"""
This module implements the FormRequest class which is a more covenient class
(than Request) to generate Requests based on form data.

See documentation in docs/topics/request-response.rst
"""

import urllib
from cStringIO import StringIO

from scrapy.xlib.ClientForm import ParseFile

from scrapy.http.request import Request
from scrapy.utils.python import unicode_to_str

def _unicode_to_str(string, encoding):
    if hasattr(string, '__iter__'):
        return [unicode_to_str(k, encoding) for k in string]
    else:
        return unicode_to_str(string, encoding)


class FormRequest(Request):

    __slots__ = ()

    def __init__(self, *args, **kwargs):
        formdata = kwargs.pop('formdata', None)
        super(FormRequest, self).__init__(*args, **kwargs)

        if formdata:
            items = formdata.iteritems() if isinstance(formdata, dict) else formdata
            query = [(unicode_to_str(k, self.encoding), _unicode_to_str(v, self.encoding))
                    for k, v in items]
            self.method = 'POST'
            self._set_body(urllib.urlencode(query, doseq=1))
            self.headers['Content-Type'] = 'application/x-www-form-urlencoded'

    @classmethod
    def from_response(cls, response, formname=None, formnumber=0, formdata=None, 
                      clickdata=None, dont_click=False, **kwargs):
        encoding = getattr(response, 'encoding', 'utf-8')
        forms = ParseFile(StringIO(response.body), response.url,
                          encoding=encoding, backwards_compat=False)
        if not forms:
            raise ValueError("No <form> element found in %s" % response)
        
        form = None

        if formname:
            for f in forms:
                if f.name == formname:
                    form = f
                    break

        if not form:
            try:
                form = forms[formnumber]
            except IndexError:
                raise IndexError("Form number %d not found in %s" % (formnumber, response))
        if formdata:
            # remove all existing fields with the same name before, so that
            # formdata fields properly can properly override existing ones,
            # which is the desired behaviour
            form.controls = [c for c in form.controls if c.name not in formdata]
            for k, v in formdata.iteritems():
                for v2 in v if hasattr(v, '__iter__') else [v]:
                    form.new_control('text', k, {'value': v2})

        if dont_click:
            url, body, headers = form._switch_click('request_data')
        else:
            url, body, headers = form.click_request_data(**(clickdata or {}))

        kwargs.setdefault('headers', {}).update(headers)

        return cls(url, method=form.method, body=body, **kwargs)
