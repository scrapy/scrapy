"""
This module implements the FormRequest class which is a more covenient class
(than Request) to generate Requests based on form data.

See documentation in docs/topics/request-response.rst
"""

import urllib

from lxml import html

from scrapy.http.request import Request
from scrapy.utils.python import unicode_to_str


class MultipleElementsFound(Exception):
    pass


class FormRequest(Request):

    def __init__(self, *args, **kwargs):
        formdata = kwargs.pop('formdata', None)
        if formdata and kwargs.get('method') is None:
            kwargs['method'] = 'POST'

        super(FormRequest, self).__init__(*args, **kwargs)

        if formdata:
            items = formdata.iteritems() if isinstance(formdata, dict) else formdata
            querystr = _urlencode(items, self.encoding)
            if self.method == 'POST':
                self.headers.setdefault('Content-Type', 'application/x-www-form-urlencoded')
                self._set_body(querystr)
            else:
                self._set_url(self.url + ('&' if '?' in self.url else '?') + querystr)

    @classmethod
    def from_response(cls, response, formname=None, formnumber=0, formdata=None,
                      clickdata=None, dont_click=False, **kwargs):
        if not hasattr(formdata, "items"):
            try:
                formdata = dict(formdata) if formdata else {}
            except (ValueError, TypeError):
                raise ValueError('formdata should be a dict or iterable of tuples')

        kwargs.setdefault('encoding', response.encoding)
        hxs = html.fromstring(response.body_as_unicode(), base_url=response.url)
        form = _get_form(hxs, formname, formnumber, response)
        formdata = _get_inputs(form, formdata, dont_click, clickdata, response)
        url = form.action or form.base_url
        return cls(url, method=form.method, formdata=formdata, **kwargs)

def _urlencode(seq, enc):
    values = [(unicode_to_str(k, enc), unicode_to_str(v, enc))
              for k, vs in seq
              for v in (vs if hasattr(vs, '__iter__') else [vs])]
    return urllib.urlencode(values, doseq=1)

def _get_form(hxs, formname, formnumber, response):
    """
    Uses all the passed arguments to get the required form
    element
    """
    if not hxs.forms:
        raise ValueError("No <form> element found in %s" % response)

    if formname is not None:
        f = hxs.xpath('//form[@name="%s"]' % formname)
        if f:
            return f[0]

    # If we get here, it means that either formname was None
    # or invalid
    if formnumber is not None:
        try:
            form = hxs.forms[formnumber]
        except IndexError:
            raise IndexError("Form number %d not found in %s" %
                                (formnumber, response))
        else:
            return form

def _get_inputs(form, formdata, dont_click, clickdata, response):
    """
    Returns all the inputs that will be sent with the request,
    both those already present in the form and those given by
    the user
    """
    clickables = []
    inputs = []
    for el in form.inputs:
        name = el.name
        if not name or name in formdata:
            continue
        tag = html._nons(el.tag)
        if tag == 'textarea':
            inputs.append((name, el.value))
        elif tag == 'select':
            if u' xmlns' in response.body_as_unicode()[:200]:
                #use builtin select parser with namespaces
                value = el.value
            else:
                value = el.xpath(".//option[@selected]") or None

            if el.multiple:
                for v in value:
                    if v is not None:
                        inputs.append((name, v))
            elif value is not None:
                inputs.append((name, value[0] if isinstance(value, list)
                                               else value))
            else:
                option = el.xpath(".//option[1]/@value")
                if option:
                    inputs.append((name, option[0]))
        else:
            assert tag == 'input', ("Unexpected tag: %r" % el)
            if el.checkable and not el.checked:
                continue
            if el.type in ('image', 'reset'):
                continue
            elif el.type == 'submit':
                clickables.append(el)
            else:
                value = el.value
                if value is not None:
                    inputs.append((name, el.value))

    # If we are allowed to click on buttons and we have clickable
    # elements, we move on to see if we have any clickdata
    if not dont_click and clickables:
        clickable = _get_clickable(clickdata, clickables, form)
        inputs.append(clickable)

    inputs.extend(formdata.iteritems())
    return inputs

def _get_clickable(clickdata, clickables, form):
    """
    Returns the clickable element specified in clickdata,
    if the latter is given. If not, it returns the first
    clickable element found
    """
    # If clickdata is given, we compare it to the clickable elements
    # to find a match
    if clickdata is not None:
        # We first look to see if the number is specified in
        # clickdata, because that uniquely identifies the element
        nr = clickdata.get('nr', None)
        if nr is not None:
            try:
                el = list(form.inputs)[nr]
            except IndexError:
                pass
            else:
                return (el.name, el.value)

        # We didn't find it, so now we build an XPath expression
        # out of the other arguments, because they can be used
        # as such
        else:
            xpath_pred = []
            for k, v in clickdata.items():
                if k == 'coord':
                    v = ','.join(str(c) for c in v)
                xpath_pred.append('[@%s="%s"]' % (k, v))

            xpath_expr = '//*%s' % ''.join(xpath_pred)
            el = form.xpath(xpath_expr)
            if len(el) > 1:
                raise MultipleElementsFound(
                        "Multiple elements found (%r) matching the criteria"
                        " in clickdata: %r" % (el, clickdata)
                )
            else:
                return (el[0].name, el[0].value)

    # If we don't have clickdata, we just use the first
    # clickable element
    else:
        el = clickables.pop(0)
        return (el.name, el.value)
