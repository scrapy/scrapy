"""
This module implements the FormRequest class which is a more covenient class
(than Request) to generate Requests based on form data.

See documentation in docs/topics/request-response.rst
"""

import urllib
from lxml import html

from scrapy.http.request.form import FormRequest
from scrapy.utils.python import unicode_to_str

def _unicode_to_str(string, encoding):
    if hasattr(string, '__iter__'):
        return [unicode_to_str(k, encoding) for k in string]
    else:
        return unicode_to_str(string, encoding)


class LxmlFormRequest(FormRequest):

    __slots__ = ()

    @classmethod
    def from_response(cls, response, formname=None, formnumber=0, formdata=None,
                       clickdata=None, dont_click=False, **kwargs):
        if not hasattr(formdata, "items"):
            try:
                formdata = dict(formdata)
            except (ValueError, TypeError):
                raise ValueError('formdata should be a dict or iterable of tuples')
            
        hxs = html.fromstring(response.body, base_url=response.url)
        forms = hxs.forms
        if not forms:
            raise ValueError("No <form> element found in %s" % response)
        
        form = None

        if formname:
            for f in forms:
                attrs = f.attrib
                if 'name' in attrs and formname==attrs['name']: 
                    form = f
                    break

        if not form:
            try:
                form = forms[formnumber]
            except IndexError:
                raise IndexError("Form number %d not found in %s" % (formnumber, response))
        
        if not dont_click:
            # get first button to click
            for el in form.xpath(".//input[@type='submit']"):
                key = el.xpath("@name")
                value = el.xpath("@value")
                if key and not clickdata:
                    if key[0] not in formdata:
                        formdata[key[0]] = value[0] if value else ''
                    break
        # lxml doesnt use first option  if there is no 'selected'
        for sel in form.xpath(".//select"):
            key = sel.xpath('@name')
            if not key:continue
            if key[0] in formdata:continue
            if not sel.xpath(".//option[@selected]"):
                formdata[key[0]] = sel.xpath(".//option[1]/@value") or ''
        def dummy_open_http(method, url, values):
            return method, url, values
        method, url, values = html.submit_form(form, formdata, dummy_open_http)
        
        if method == "POST":
            kwargs.setdefault('headers', {}).update(
                        {'Content-Type':'application/x-www-form-urlencoded'})
            body = urllib.urlencode(values)
        else:
            if '?' in url:
                url += '&'
            else:
                url += '?'
            url += urllib.urlencode(values)
            body=None

        return cls(url, method=form.method, body=body, **kwargs)
    
    
    
    
    
    
    
    
    
    