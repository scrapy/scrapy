"""
This module implements the FormRequest class which is a more convenient class
(than Request) to generate Requests based on form data.

See documentation in docs/topics/request-response.rst
"""

from urllib.parse import urljoin, urlencode

import lxml.html
from parsel.selector import create_root_node
from w3lib.html import strip_html5_whitespace

from scrapy.http.request import Request
from scrapy.utils.python import to_bytes, is_listlike
from scrapy.utils.response import get_base_url


class FormRequest(Request):
    valid_form_methods = ['GET', 'POST']

    def __init__(self, *args, **kwargs):
        formdata = kwargs.pop('formdata', None)
        if formdata and kwargs.get('method') is None:
            kwargs['method'] = 'POST'

        super().__init__(*args, **kwargs)

        if formdata:
            items = formdata.items() if isinstance(formdata, dict) else formdata
            querystr = _urlencode(items, self.encoding)
            if self.method == 'POST':
                self.headers.setdefault(b'Content-Type', b'application/x-www-form-urlencoded')
                self._set_body(querystr)
            else:
                self._set_url(self.url + ('&' if '?' in self.url else '?') + querystr)

    @classmethod
    def from_response(cls, response, formname=None, formid=None, formnumber=0, formdata=None,
                      clickdata=None, dont_click=False, formxpath=None, formcss=None, **kwargs):

        kwargs.setdefault('encoding', response.encoding)

        if formcss is not None:
            from parsel.csstranslator import HTMLTranslator
            formxpath = HTMLTranslator().css_to_xpath(formcss)

        form = _get_form(response, formname, formid, formnumber, formxpath)
        formdata = _get_inputs(form, formdata, dont_click, clickdata, response)
        url = _get_form_url(form, kwargs.pop('url', None))

        method = kwargs.pop('method', form.method)
        if method is not None:
            method = method.upper()
            if method not in cls.valid_form_methods:
                method = 'GET'

        return cls(url=url, method=method, formdata=formdata, **kwargs)


def _get_form_url(form, url):
    if url is None:
        action = form.get('action')
        if action is None:
            return form.base_url
        return urljoin(form.base_url, strip_html5_whitespace(action))
    return urljoin(form.base_url, url)


def _urlencode(seq, enc):
    values = [(to_bytes(k, enc), to_bytes(v, enc))
              for k, vs in seq
              for v in (vs if is_listlike(vs) else [vs])]
    return urlencode(values, doseq=True)


def _get_form(response, formname, formid, formnumber, formxpath):
    """Find the form element """
    root = create_root_node(response.text, lxml.html.HTMLParser,
                            base_url=get_base_url(response))
    forms = root.xpath('//form')
    if not forms:
        raise ValueError(f"No <form> element found in {response}")

    if formname is not None:
        f = root.xpath(f'//form[@name="{formname}"]')
        if f:
            return f[0]

    if formid is not None:
        f = root.xpath(f'//form[@id="{formid}"]')
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
        raise ValueError(f'No <form> element found with {formxpath}')

    # If we get here, it means that either formname was None
    # or invalid
    if formnumber is not None:
        try:
            form = forms[formnumber]
        except IndexError:
            raise IndexError(f"Form number {formnumber} not found in {response}")
        else:
            return form


def _get_inputs(form, formdata, dont_click, clickdata, response):
    try:
        formdata_keys = dict(formdata or ()).keys()
    except (ValueError, TypeError):
        raise ValueError('formdata should be a dict or iterable of tuples')

    if not formdata:
        formdata = ()
    inputs = form.xpath('descendant::textarea'
                        '|descendant::select'
                        '|descendant::input[not(@type) or @type['
                        ' not(re:test(., "^(?:submit|image|reset)$", "i"))'
                        ' and (../@checked or'
                        '  not(re:test(., "^(?:checkbox|radio)$", "i")))]]',
                        namespaces={
                            "re": "http://exslt.org/regular-expressions"})
    values = [(k, '' if v is None else v)
              for k, v in (_value(e) for e in inputs)
              if k and k not in formdata_keys]

    if not dont_click:
        clickable = _get_clickable(clickdata, form)
        if clickable and clickable[0] not in formdata and not clickable[0] is None:
            values.append(clickable)

    if isinstance(formdata, dict):
        formdata = formdata.items()

    values.extend((k, v) for k, v in formdata if v is not None)
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
        # And for select tags without options
        o = ele.value_options
        return (n, o[0]) if o else (None, None)
    elif v is not None and multiple:
        # This is a workround to bug in lxml fixed 2.3.1
        # fix https://github.com/lxml/lxml/commit/57f49eed82068a20da3db8f1b18ae00c1bab8b12#L1L1139
        selected_options = ele.xpath('.//option[@selected]')
        v = [(o.get('value') or o.text or '').strip() for o in selected_options]
    return n, v


def _get_clickable(clickdata, form):
    """
    Returns the clickable element specified in clickdata,
    if the latter is given. If not, it returns the first
    clickable element found
    """
    clickables = list(form.xpath(
        'descendant::input[re:test(@type, "^(submit|image)$", "i")]'
        '|descendant::button[not(@type) or re:test(@type, "^submit$", "i")]',
        namespaces={"re": "http://exslt.org/regular-expressions"}
    ))
    if not clickables:
        return

    # If we don't have clickdata, we just use the first clickable element
    if clickdata is None:
        el = clickables[0]
        return (el.get('name'), el.get('value') or '')

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
            return (el.get('name'), el.get('value') or '')

    # We didn't find it, so now we build an XPath expression out of the other
    # arguments, because they can be used as such
    xpath = './/*' + ''.join(f'[@{k}="{v}"]' for k, v in clickdata.items())
    el = form.xpath(xpath)
    if len(el) == 1:
        return (el[0].get('name'), el[0].get('value') or '')
    elif len(el) > 1:
        raise ValueError(f"Multiple elements found ({el!r}) matching the "
                         f"criteria in clickdata: {clickdata!r}")
    else:
        raise ValueError(f'No clickable element matching clickdata: {clickdata!r}')
