"""
This module implements the FormRequest class which is a more convenient class
(than Request) to generate Requests based on form data.

See documentation in docs/topics/request-response.rst
"""

import six
from six.moves.urllib.parse import urljoin, urlencode

import lxml.html
from parsel.selector import create_root_node
from w3lib.html import strip_html5_whitespace

from scrapy.http.request import Request
from scrapy.utils.python import to_bytes, is_listlike
from scrapy.utils.response import get_base_url


class FormRequest(Request):
    """The :class:`FormRequest` class adds a new argument to the constructor. The
    remaining arguments are the same as for the :class:`Request` class and are
    not documented here.

    :param formdata: is a :class:`dict` (or iterable of (key, value)
        :class:`tuples <tuple>`) containing HTML Form data which will be
        url-encoded and assigned to the body of the request.

    The :class:`FormRequest` objects support the following class method in
    addition to the standard :class:`Request` methods:
    """

    def __init__(self, *args, **kwargs):
        formdata = kwargs.pop('formdata', None)
        if formdata and kwargs.get('method') is None:
            kwargs['method'] = 'POST'

        super(FormRequest, self).__init__(*args, **kwargs)

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
        """Returns a new :class:`FormRequest` object with its form field values
        pre-populated with those found in the HTML ``<form>`` element contained
        in the given response. For an example see
        :ref:`topics-request-response-ref-request-userlogin`.

        The policy is to automatically simulate a click, by default, on any form
        control that looks clickable, like a ``<input type="submit">``.  Even
        though this is quite convenient, and often the desired behaviour,
        sometimes it can cause problems which could be hard to debug. For
        example, when working with forms that are filled and/or submitted using
        javascript, the default :meth:`from_response` behaviour may not be the
        most appropriate. To disable this behaviour you can set the
        ``dont_click`` argument to ``True``. Also, if you want to change the
        control clicked (instead of disabling it) you can also use the
        ``clickdata`` argument.

        .. caution:: Using this method with select elements which have leading
            or trailing whitespace in the option values will not work due to a
            `bug in lxml`_, which should be fixed in lxml 3.8 and above.

        :param response: the response containing a HTML form which will be used
            to pre-populate the form fields
        :type response: :class:`~scrapy.http.Response` object

        :param formname: if given, the form with name attribute set to this value will be used.
        :type formname: str

        :param formid: if given, the form with id attribute set to this value will be used.
        :type formid: str

        :param formxpath: if given, the first form that matches the xpath will be used.
        :type formxpath: str

        :param formcss: if given, the first form that matches the css selector will be used.
        :type formcss: str

        :param formnumber: the number of form to use, when the response contains
            multiple forms. The first one (and also the default) is ``0``.
        :type formnumber: int

        :param formdata: fields to override in the form data. If a field was
            already present in the response ``<form>`` element, its value is
            overridden by the one passed in this parameter. If a value passed in
            this parameter is ``None``, the field will not be included in the
            request, even if it was present in the response ``<form>`` element.
        :type formdata: dict

        :param clickdata: attributes to lookup the control clicked. If it's not
            given, the form data will be submitted simulating a click on the
            first clickable element. In addition to html attributes, the control
            can be identified by its zero-based index relative to other
            submittable inputs inside the form, via the ``nr`` attribute.
        :type clickdata: dict

        :param dont_click: If True, the form data will be submitted without
            clicking in any element.
        :type dont_click: bool

        The other parameters of this class method are passed directly to the
        :class:`FormRequest` constructor.

        .. versionadded:: 0.10.3
            The ``formname`` parameter.

        .. versionadded:: 0.17
            The ``formxpath`` parameter.

        .. versionadded:: 1.1.0
            The ``formcss`` parameter.

        .. versionadded:: 1.1.0
            The ``formid`` parameter.
        """

        kwargs.setdefault('encoding', response.encoding)

        if formcss is not None:
            from parsel.csstranslator import HTMLTranslator
            formxpath = HTMLTranslator().css_to_xpath(formcss)

        form = _get_form(response, formname, formid, formnumber, formxpath)
        formdata = _get_inputs(form, formdata, dont_click, clickdata, response)
        url = _get_form_url(form, kwargs.pop('url', None))
        method = kwargs.pop('method', form.method)
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
    return urlencode(values, doseq=1)


def _get_form(response, formname, formid, formnumber, formxpath):
    """Find the form element """
    root = create_root_node(response.text, lxml.html.HTMLParser,
                            base_url=get_base_url(response))
    forms = root.xpath('//form')
    if not forms:
        raise ValueError("No <form> element found in %s" % response)

    if formname is not None:
        f = root.xpath('//form[@name="%s"]' % formname)
        if f:
            return f[0]

    if formid is not None:
        f = root.xpath('//form[@id="%s"]' % formid)
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
        encoded = formxpath if six.PY3 else formxpath.encode('unicode_escape')
        raise ValueError('No <form> element found with %s' % encoded)

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
    values = [(k, u'' if v is None else v)
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
    clickables = [
        el for el in form.xpath(
            'descendant::input[re:test(@type, "^(submit|image)$", "i")]'
            '|descendant::button[not(@type) or re:test(@type, "^submit$", "i")]',
            namespaces={"re": "http://exslt.org/regular-expressions"})
        ]
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
    xpath = u'.//*' + \
            u''.join(u'[@%s="%s"]' % c for c in six.iteritems(clickdata))
    el = form.xpath(xpath)
    if len(el) == 1:
        return (el[0].get('name'), el[0].get('value') or '')
    elif len(el) > 1:
        raise ValueError("Multiple elements found (%r) matching the criteria "
                         "in clickdata: %r" % (el, clickdata))
    else:
        raise ValueError('No clickable element matching clickdata: %r' % (clickdata,))
