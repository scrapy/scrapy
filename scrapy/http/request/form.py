"""
This module implements the FormRequest class which is a more convenient class
(than Request) to generate Requests based on form data.

See documentation in docs/topics/request-response.rst
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING, Any, Optional, Union, cast
from urllib.parse import urlencode, urljoin, urlsplit, urlunsplit

from lxml.html import FormElement  # nosec
from lxml.html import InputElement  # nosec
from lxml.html import MultipleSelectOptions  # nosec
from lxml.html import SelectElement  # nosec
from lxml.html import TextareaElement  # nosec
from w3lib.html import strip_html5_whitespace

from scrapy.http.request import Request
from scrapy.utils.python import is_listlike, to_bytes

if TYPE_CHECKING:

    # typing.Self requires Python 3.11
    from typing_extensions import Self

    from scrapy.http.response.text import TextResponse


FormdataVType = Union[str, Iterable[str]]
FormdataKVType = tuple[str, FormdataVType]
FormdataType = Optional[Union[dict[str, FormdataVType], list[FormdataKVType]]]


class FormRequest(Request):
    valid_form_methods = ["GET", "POST"]

    def __init__(
        self, *args: Any, formdata: FormdataType = None, **kwargs: Any
    ) -> None:
        if formdata and kwargs.get("method") is None:
            kwargs["method"] = "POST"

        super().__init__(*args, **kwargs)

        if formdata:
            items = formdata.items() if isinstance(formdata, dict) else formdata
            form_query_str = _urlencode(items, self.encoding)
            if self.method == "POST":
                self.headers.setdefault(
                    b"Content-Type", b"application/x-www-form-urlencoded"
                )
                self._set_body(form_query_str)
            else:
                self._set_url(
                    urlunsplit(urlsplit(self.url)._replace(query=form_query_str))
                )

    @classmethod
    def from_response(
        cls,
        response: TextResponse,
        formname: str | None = None,
        formid: str | None = None,
        formnumber: int = 0,
        formdata: FormdataType = None,
        clickdata: dict[str, str | int] | None = None,
        dont_click: bool = False,
        formxpath: str | None = None,
        formcss: str | None = None,
        **kwargs: Any,
    ) -> Self:
        kwargs.setdefault("encoding", response.encoding)

        if formcss is not None:
            from parsel.csstranslator import HTMLTranslator

            formxpath = HTMLTranslator().css_to_xpath(formcss)

        form = _get_form(response, formname, formid, formnumber, formxpath)
        formdata = _get_inputs(form, formdata, dont_click, clickdata)
        url = _get_form_url(form, kwargs.pop("url", None))

        method = kwargs.pop("method", form.method)
        if method is not None:
            method = method.upper()
            if method not in cls.valid_form_methods:
                method = "GET"

        return cls(url=url, method=method, formdata=formdata, **kwargs)


def _get_form_url(form: FormElement, url: str | None) -> str:
    assert form.base_url is not None  # typing
    if url is None:
        action = form.get("action")
        if action is None:
            return form.base_url
        return urljoin(form.base_url, strip_html5_whitespace(action))
    return urljoin(form.base_url, url)


def _urlencode(seq: Iterable[FormdataKVType], enc: str) -> str:
    values = [
        (to_bytes(k, enc), to_bytes(v, enc))
        for k, vs in seq
        for v in (cast(Iterable[str], vs) if is_listlike(vs) else [cast(str, vs)])
    ]
    return urlencode(values, doseq=True)


def _get_form(
    response: TextResponse,
    formname: str | None,
    formid: str | None,
    formnumber: int,
    formxpath: str | None,
) -> FormElement:
    """Find the wanted form element within the given response."""
    root = response.selector.root
    forms = root.xpath("//form")
    if not forms:
        raise ValueError(f"No <form> element found in {response}")

    if formname is not None:
        f = root.xpath(f'//form[@name="{formname}"]')
        if f:
            return cast(FormElement, f[0])

    if formid is not None:
        f = root.xpath(f'//form[@id="{formid}"]')
        if f:
            return cast(FormElement, f[0])

    # Get form element from xpath, if not found, go up
    if formxpath is not None:
        nodes = root.xpath(formxpath)
        if nodes:
            el = nodes[0]
            while True:
                if el.tag == "form":
                    return cast(FormElement, el)
                el = el.getparent()
                if el is None:
                    break
        raise ValueError(f"No <form> element found with {formxpath}")

    # If we get here, it means that either formname was None or invalid
    try:
        form = forms[formnumber]
    except IndexError:
        raise IndexError(f"Form number {formnumber} not found in {response}")
    return cast(FormElement, form)


def _get_inputs(
    form: FormElement,
    formdata: FormdataType,
    dont_click: bool,
    clickdata: dict[str, str | int] | None,
) -> list[FormdataKVType]:
    """Return a list of key-value pairs for the inputs found in the given form."""
    try:
        formdata_keys = dict(formdata or ()).keys()
    except (ValueError, TypeError):
        raise ValueError("formdata should be a dict or iterable of tuples")

    if not formdata:
        formdata = []
    inputs = form.xpath(
        "descendant::textarea"
        "|descendant::select"
        "|descendant::input[not(@type) or @type["
        ' not(re:test(., "^(?:submit|image|reset)$", "i"))'
        " and (../@checked or"
        '  not(re:test(., "^(?:checkbox|radio)$", "i")))]]',
        namespaces={"re": "http://exslt.org/regular-expressions"},
    )
    values: list[FormdataKVType] = [
        (k, "" if v is None else v)
        for k, v in (_value(e) for e in inputs)
        if k and k not in formdata_keys
    ]

    if not dont_click:
        clickable = _get_clickable(clickdata, form)
        if clickable and clickable[0] not in formdata and not clickable[0] is None:
            values.append(clickable)

    formdata_items = formdata.items() if isinstance(formdata, dict) else formdata
    values.extend((k, v) for k, v in formdata_items if v is not None)
    return values


def _value(
    ele: InputElement | SelectElement | TextareaElement,
) -> tuple[str | None, str | MultipleSelectOptions | None]:
    n = ele.name
    v = ele.value
    if ele.tag == "select":
        return _select_value(cast(SelectElement, ele), n, v)
    return n, v


def _select_value(
    ele: SelectElement, n: str | None, v: str | MultipleSelectOptions | None
) -> tuple[str | None, str | MultipleSelectOptions | None]:
    multiple = ele.multiple
    if v is None and not multiple:
        # Match browser behaviour on simple select tag without options selected
        # And for select tags without options
        o = ele.value_options
        return (n, o[0]) if o else (None, None)
    return n, v


def _get_clickable(
    clickdata: dict[str, str | int] | None, form: FormElement
) -> tuple[str, str] | None:
    """
    Returns the clickable element specified in clickdata,
    if the latter is given. If not, it returns the first
    clickable element found
    """
    clickables = list(
        form.xpath(
            'descendant::input[re:test(@type, "^(submit|image)$", "i")]'
            '|descendant::button[not(@type) or re:test(@type, "^submit$", "i")]',
            namespaces={"re": "http://exslt.org/regular-expressions"},
        )
    )
    if not clickables:
        return None

    # If we don't have clickdata, we just use the first clickable element
    if clickdata is None:
        el = clickables[0]
        return (el.get("name"), el.get("value") or "")

    # If clickdata is given, we compare it to the clickable elements to find a
    # match. We first look to see if the number is specified in clickdata,
    # because that uniquely identifies the element
    nr = clickdata.get("nr", None)
    if nr is not None:
        assert isinstance(nr, int)
        try:
            el = list(form.inputs)[nr]
        except IndexError:
            pass
        else:
            return (el.get("name"), el.get("value") or "")

    # We didn't find it, so now we build an XPath expression out of the other
    # arguments, because they can be used as such
    xpath = ".//*" + "".join(f'[@{k}="{v}"]' for k, v in clickdata.items())
    el = form.xpath(xpath)
    if len(el) == 1:
        return (el[0].get("name"), el[0].get("value") or "")
    if len(el) > 1:
        raise ValueError(
            f"Multiple elements found ({el!r}) matching the "
            f"criteria in clickdata: {clickdata!r}"
        )
    raise ValueError(f"No clickable element matching clickdata: {clickdata!r}")
