"""
This module implements the FormRequest class which is a more covenient class
(than Request) to generate Requests based on form data.

See documentation in docs/topics/request-response.rst
"""

import urllib
import lxml.html
from scrapy.http.request import Request
from scrapy.utils.python import unicode_to_str


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
                      clickdata=None, dont_click=False, formxpath=None, **kwargs):
        kwargs.setdefault('encoding', response.encoding)
        form = _get_form(response, formname, formnumber, formxpath)
        formdata = _get_inputs(form, formdata, dont_click, clickdata, response)
        url = form.action or form.base_url
        method = kwargs.pop('method', form.method)
        return cls(url, method=method, formdata=formdata, **kwargs)


def _urlencode(seq, enc):
    values = [(unicode_to_str(k, enc), unicode_to_str(v, enc))
              for k, vs in seq
              for v in (vs if hasattr(vs, '__iter__') else [vs])]
    return urllib.urlencode(values, doseq=1)

def _get_form(response, formname, formnumber, formxpath):
    """Find the form element """
    from scrapy.selector.lxmldocument import LxmlDocument
    root = LxmlDocument(response, lxml.html.HTMLParser)
    forms = root.xpath('//form')
    if not forms:
        raise ValueError("No <form> element found in %s" % response)

    if formname is not None:
        f = root.xpath('//form[@name="%s"]' % formname)
        if f:
            return f[0]

    # Get form element from xpath, if not found, go up
    if formxpath is not None:
        nodes = root.xpath(formxpath)
        if nodes:
            el = nodes[0]
            while True:
                if el.tag == 'form':
                    return el
                el = el.getparent()
                if el is None:
                    break
        raise ValueError('No <form> element found with %s' % formxpath)

    # If we get here, it means that either formname was None
    # or invalid
    if formnumber is not None:
        try:
            form = forms[formnumber]
        except IndexError:
            raise IndexError("Form number %d not found in %s" %
                                (formnumber, response))
        else:
            return form

def _get_inputs(form, formdata, dont_click, clickdata, response):
    try:
        formdata = dict(formdata or ())
    except (ValueError, TypeError):
        raise ValueError('formdata should be a dict or iterable of tuples')

    inputs = form.xpath('descendant::textarea'
                        '|descendant::select'
                        '|descendant::input[@type!="submit" and @type!="image" '
                        'and ((@type!="checkbox" and @type!="radio") or @checked)]')
    values = [(k, u'' if v is None else v) \
              for k, v in (_value(e) for e in inputs) \
              if k and k not in formdata]

    if not dont_click:
        clickable = _get_clickable(clickdata, form)
        if clickable and clickable[0] not in formdata and not clickable[0] is None:
            values.append(clickable)

    values.extend(formdata.iteritems())
    return values

def _value(ele):
    n = ele.name
    v = ele.value
    if ele.tag == 'select':
        return _select_value(ele, n, v)
    return n, v

def _select_value(ele, n, v):
    multiple = ele.multiple
    if v is None and not multiple:
        # Match browser behaviour on simple select tag without options selected
        # And for select tags wihout options
        o = ele.value_options
        return (n, o[0]) if o else (None, None)
    elif v is not None and multiple:
        # This is a workround to bug in lxml fixed 2.3.1
        # fix https://github.com/lxml/lxml/commit/57f49eed82068a20da3db8f1b18ae00c1bab8b12#L1L1139
        selected_options = ele.xpath('.//option[@selected]')
        v = [(o.get('value') or o.text or u'').strip() for o in selected_options]
    return n, v


def _get_clickable(clickdata, form):
    """
    Returns the clickable element specified in clickdata,
    if the latter is given. If not, it returns the first
    clickable element found
    """
    clickables = [el for el in form.xpath('.//input[@type="submit"]')]
    if not clickables:
        return

    # If we don't have clickdata, we just use the first clickable element
    if clickdata is None:
        el = clickables[0]
        return (el.name, el.value)

    # If clickdata is given, we compare it to the clickable elements to find a
    # match. We first look to see if the number is specified in clickdata,
    # because that uniquely identifies the element
    nr = clickdata.get('nr', None)
    if nr is not None:
        try:
            el = list(form.inputs)[nr]
        except IndexError:
            pass
        else:
            return (el.name, el.value)

    # We didn't find it, so now we build an XPath expression out of the other
    # arguments, because they can be used as such
    xpath = u'.//*' + \
            u''.join(u'[@%s="%s"]' % c for c in clickdata.iteritems())
    el = form.xpath(xpath)
    if len(el) == 1:
        return (el[0].name, el[0].value)
    elif len(el) > 1:
        raise ValueError("Multiple elements found (%r) matching the criteria "
                         "in clickdata: %r" % (el, clickdata))
    else:
        raise ValueError('No clickable element matching clickdata: %r' % (clickdata,))
