"""
This module implements the FormRequest class which is a more covenient class
(than Request) to generate Requests based on form data.

See documentation in docs/topics/request-response.rst
"""

import urllib

from lxml import html

from scrapy.http.request import Request


class MultipleElementsFound(Exception):
    pass


class FormRequest(Request):

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
        if not hasattr(formdata, "items"):
            try:
                if formdata:
                    formdata = dict(formdata)
                else: formdata = {}
            except (ValueError, TypeError):
                raise ValueError('formdata should be a dict or iterable of tuples')

        encoding = kwargs.get('encoding', response.encoding or 'UTF-8')
        hxs = html.fromstring(response.body_as_unicode(),
                              base_url=response.url)
        form = _get_form(hxs, formname, formnumber, response)
        inputs = _get_inputs(form, formdata, dont_click, clickdata, response)
        values = [(_unicode_to_str(key, encoding), _unicode_to_str(value, encoding))
                  for key,value in inputs]
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

    inputs.extend([(key, value) for key, value in formdata.iteritems()])
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
