"""
This module implements the FormRequest class which is a more covenient class
(than Request) to generate Requests based on form data.

See documentation in docs/topics/request-response.rst
"""

import urllib
from lxml import html

from scrapy.http.request.form import FormRequest


def unicode_to_str(text, encoding='utf-8', errors='strict'):
    if isinstance(text, unicode):
        return text.encode(encoding, errors)
    elif isinstance(text, str):
        return unicode(text, 'utf-8', errors).encode(encoding, errors)
    else:
        raise TypeError('unicode_to_str must receive a unicode or str object, got %s' % type(text).__name__)

def _unicode_to_str(string, encoding):
    if hasattr(string, '__iter__'):
        return [unicode_to_str(k, encoding) for k in string]
    else:
        return unicode_to_str(string, encoding)


class LxmlFormRequest(FormRequest):

    __slots__ = ()

    @classmethod
    def from_response(cls, response, formname=None, formnumber=0, formdata=None,
                       dont_click=False, **kwargs):
        if not hasattr(formdata, "items"):
            try:
                if formdata:
                    formdata = dict(formdata)
                else: formdata = {}
            except (ValueError, TypeError):
                raise ValueError('formdata should be a dict or iterable of tuples')
        encoding = kwargs.get('encoding', response.encoding or 'UTF-8')
        hxs = html.fromstring(response.body_as_unicode(), base_url=response.url)
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

        clickable = set()
        results = []
        for el in form.inputs:
            name = el.name
            if not name or name in formdata:
                continue
            tag = html._nons(el.tag)
            if tag == 'textarea':
                results.append((name, el.value))
            elif tag == 'select':
                if u' xmlns' in response.body_as_unicode()[:200]:
                    #use builtin select parser with namespaces
                    value = el.value
                else:
                    value = el.xpath(".//option[@selected]") or None

                if el.multiple:
                    for v in value:
                        if v is not None:
                            results.append((name, v))
                elif value is not None:
                    results.append((name, value[0] if isinstance(value, list) else value))
                else:
                    option = el.xpath(".//option[1]/@value")
                    if option:
                        results.append((name, option[0]))
            else:
                assert tag == 'input', ("Unexpected tag: %r" % el)
                if el.checkable and not el.checked:
                    continue
                if el.type in ( 'image', 'reset'):
                    continue
                elif el.type=='submit':
                    clickable.add(el)
                value = el.value
                if value is not None:
                    results.append((name, el.value))
        if not dont_click and clickable:
            if not clickable.intersection(formdata):
                button = clickable.pop()
                results.append((button.name, button.value))

        results.extend([(key, value) for key, value in formdata.iteritems()])
        values = [(_unicode_to_str(key, encoding), _unicode_to_str(value, encoding))
                  for key,value in results]
        if form.action:
            url = form.action
        else:
            url = form.base_url
        if form.method == "POST":
            kwargs.setdefault('headers', {}).update(
                        {'Content-Type':'application/x-www-form-urlencoded'})
            body = urllib.urlencode(values, doseq=1)
        else:
            if '?' in url:
                url += '&'
            else:
                url += '?'
            url += urllib.urlencode(values, doseq=1)
            body=None

        return cls(url, method=form.method, body=body, encoding=encoding, **kwargs)
