"""
Functions for dealing with markup text
"""

import re
from html.entities import name2codepoint
from typing import Iterable, Match, AnyStr, Optional, Pattern, Tuple, Union
from urllib.parse import urljoin

from w3lib.util import to_unicode
from w3lib.url import safe_url_string
from w3lib._types import StrOrBytes

_ent_re = re.compile(
    r"&((?P<named>[a-z\d]+)|#(?P<dec>\d+)|#x(?P<hex>[a-f\d]+))(?P<semicolon>;?)",
    re.IGNORECASE,
)
_tag_re = re.compile(r"<[a-zA-Z\/!].*?>", re.DOTALL)
_baseurl_re = re.compile(r"<base\s[^>]*href\s*=\s*[\"\']\s*([^\"\'\s]+)\s*[\"\']", re.I)
_meta_refresh_re = re.compile(
    r'<meta\s[^>]*http-equiv[^>]*refresh[^>]*content\s*=\s*(?P<quote>["\'])(?P<int>(\d*\.)?\d+)\s*;\s*url=\s*(?P<url>.*?)(?P=quote)',
    re.DOTALL | re.IGNORECASE,
)
_meta_refresh_re2 = re.compile(
    r'<meta\s[^>]*content\s*=\s*(?P<quote>["\'])(?P<int>(\d*\.)?\d+)\s*;\s*url=\s*(?P<url>.*?)(?P=quote)[^>]*?\shttp-equiv\s*=[^>]*refresh',
    re.DOTALL | re.IGNORECASE,
)

_cdata_re = re.compile(
    r"((?P<cdata_s><!\[CDATA\[)(?P<cdata_d>.*?)(?P<cdata_e>\]\]>))", re.DOTALL
)

HTML5_WHITESPACE = " \t\n\r\x0c"


def replace_entities(
    text: AnyStr,
    keep: Iterable[str] = (),
    remove_illegal: bool = True,
    encoding: str = "utf-8",
) -> str:
    """Remove entities from the given `text` by converting them to their
    corresponding unicode character.

    `text` can be a unicode string or a byte string encoded in the given
    `encoding` (which defaults to 'utf-8').

    If `keep` is passed (with a list of entity names) those entities will
    be kept (they won't be removed).

    It supports both numeric entities (``&#nnnn;`` and ``&#hhhh;``)
    and named entities (such as ``&nbsp;`` or ``&gt;``).

    If `remove_illegal` is ``True``, entities that can't be converted are removed.
    If `remove_illegal` is ``False``, entities that can't be converted are kept "as
    is". For more information see the tests.

    Always returns a unicode string (with the entities removed).

    >>> import w3lib.html
    >>> w3lib.html.replace_entities(b'Price: &pound;100')
    'Price: \\xa3100'
    >>> print(w3lib.html.replace_entities(b'Price: &pound;100'))
    Price: £100
    >>>

    """

    def convert_entity(m: Match[str]) -> str:
        groups = m.groupdict()
        number = None
        if groups.get("dec"):
            number = int(groups["dec"], 10)
        elif groups.get("hex"):
            number = int(groups["hex"], 16)
        elif groups.get("named"):
            entity_name = groups["named"]
            if entity_name.lower() in keep:
                return m.group(0)
            else:
                number = name2codepoint.get(entity_name) or name2codepoint.get(
                    entity_name.lower()
                )
        if number is not None:
            # Numeric character references in the 80-9F range are typically
            # interpreted by browsers as representing the characters mapped
            # to bytes 80-9F in the Windows-1252 encoding. For more info
            # see: http://en.wikipedia.org/wiki/Character_encodings_in_HTML
            try:
                if 0x80 <= number <= 0x9F:
                    return bytes((number,)).decode("cp1252")
                else:
                    return chr(number)
            except (ValueError, OverflowError):
                pass

        return "" if remove_illegal and groups.get("semicolon") else m.group(0)

    return _ent_re.sub(convert_entity, to_unicode(text, encoding))


def has_entities(text: AnyStr, encoding: Optional[str] = None) -> bool:
    return bool(_ent_re.search(to_unicode(text, encoding)))


def replace_tags(text: AnyStr, token: str = "", encoding: Optional[str] = None) -> str:
    """Replace all markup tags found in the given `text` by the given token.
    By default `token` is an empty string so it just removes all tags.

    `text` can be a unicode string or a regular string encoded as `encoding`
    (or ``'utf-8'`` if `encoding` is not given.)

    Always returns a unicode string.

    Examples:

    >>> import w3lib.html
    >>> w3lib.html.replace_tags('This text contains <a>some tag</a>')
    'This text contains some tag'
    >>> w3lib.html.replace_tags('<p>Je ne parle pas <b>fran\\xe7ais</b></p>', ' -- ', 'latin-1')
    ' -- Je ne parle pas  -- fran\\xe7ais --  -- '
    >>>

    """

    return _tag_re.sub(token, to_unicode(text, encoding))


_REMOVECOMMENTS_RE = re.compile("<!--.*?(?:-->|$)", re.DOTALL)


def remove_comments(text: AnyStr, encoding: Optional[str] = None) -> str:
    """Remove HTML Comments.

    >>> import w3lib.html
    >>> w3lib.html.remove_comments(b"test <!--textcoment--> whatever")
    'test  whatever'
    >>>

    """

    utext = to_unicode(text, encoding)
    return _REMOVECOMMENTS_RE.sub("", utext)


def remove_tags(
    text: AnyStr,
    which_ones: Iterable[str] = (),
    keep: Iterable[str] = (),
    encoding: Optional[str] = None,
) -> str:
    """Remove HTML Tags only.

    `which_ones` and `keep` are both tuples, there are four cases:

    ==============  ============= ==========================================
    ``which_ones``  ``keep``      what it does
    ==============  ============= ==========================================
    **not empty**   empty         remove all tags in ``which_ones``
    empty           **not empty** remove all tags except the ones in ``keep``
    empty           empty         remove all tags
    **not empty**   **not empty** not allowed
    ==============  ============= ==========================================


    Remove all tags:

    >>> import w3lib.html
    >>> doc = '<div><p><b>This is a link:</b> <a href="http://www.example.com">example</a></p></div>'
    >>> w3lib.html.remove_tags(doc)
    'This is a link: example'
    >>>

    Keep only some tags:

    >>> w3lib.html.remove_tags(doc, keep=('div',))
    '<div>This is a link: example</div>'
    >>>

    Remove only specific tags:

    >>> w3lib.html.remove_tags(doc, which_ones=('a','b'))
    '<div><p>This is a link: example</p></div>'
    >>>

    You can't remove some and keep some:

    >>> w3lib.html.remove_tags(doc, which_ones=('a',), keep=('p',))
    Traceback (most recent call last):
        ...
    ValueError: Cannot use both which_ones and keep
    >>>

    """
    if which_ones and keep:
        raise ValueError("Cannot use both which_ones and keep")

    which_ones = {tag.lower() for tag in which_ones}
    keep = {tag.lower() for tag in keep}

    def will_remove(tag: str) -> bool:
        tag = tag.lower()
        if which_ones:
            return tag in which_ones
        else:
            return tag not in keep

    def remove_tag(m: Match[str]) -> str:
        tag = m.group(1)
        return "" if will_remove(tag) else m.group(0)

    regex = "</?([^ >/]+).*?>"
    retags = re.compile(regex, re.DOTALL | re.IGNORECASE)

    return retags.sub(remove_tag, to_unicode(text, encoding))


def remove_tags_with_content(
    text: AnyStr, which_ones: Iterable[str] = (), encoding: Optional[str] = None
) -> str:
    """Remove tags and their content.

    `which_ones` is a tuple of which tags to remove including their content.
    If is empty, returns the string unmodified.

    >>> import w3lib.html
    >>> doc = '<div><p><b>This is a link:</b> <a href="http://www.example.com">example</a></p></div>'
    >>> w3lib.html.remove_tags_with_content(doc, which_ones=('b',))
    '<div><p> <a href="http://www.example.com">example</a></p></div>'
    >>>

    """

    utext = to_unicode(text, encoding)
    if which_ones:
        tags = "|".join([rf"<{tag}\b.*?</{tag}>|<{tag}\s*/>" for tag in which_ones])
        retags = re.compile(tags, re.DOTALL | re.IGNORECASE)
        utext = retags.sub("", utext)
    return utext


def replace_escape_chars(
    text: AnyStr,
    which_ones: Iterable[str] = ("\n", "\t", "\r"),
    replace_by: StrOrBytes = "",
    encoding: Optional[str] = None,
) -> str:
    """Remove escape characters.

    `which_ones` is a tuple of which escape characters we want to remove.
    By default removes ``\\n``, ``\\t``, ``\\r``.

    `replace_by` is the string to replace the escape characters by.
    It defaults to ``''``, meaning the escape characters are removed.

    """

    utext = to_unicode(text, encoding)
    for ec in which_ones:
        utext = utext.replace(ec, to_unicode(replace_by, encoding))
    return utext


def unquote_markup(
    text: AnyStr,
    keep: Iterable[str] = (),
    remove_illegal: bool = True,
    encoding: Optional[str] = None,
) -> str:
    """
    This function receives markup as a text (always a unicode string or
    a UTF-8 encoded string) and does the following:

    1. removes entities (except the ones in `keep`) from any part of it
        that is not inside a CDATA
    2. searches for CDATAs and extracts their text (if any) without modifying it.
    3. removes the found CDATAs

    """

    def _get_fragments(
        txt: str, pattern: Pattern[str]
    ) -> Iterable[Union[str, Match[str]]]:
        offset = 0
        for match in pattern.finditer(txt):
            match_s, match_e = match.span(1)
            yield txt[offset:match_s]
            yield match
            offset = match_e
        yield txt[offset:]

    utext = to_unicode(text, encoding)
    ret_text = ""
    for fragment in _get_fragments(utext, _cdata_re):
        if isinstance(fragment, str):
            # it's not a CDATA (so we try to remove its entities)
            ret_text += replace_entities(
                fragment, keep=keep, remove_illegal=remove_illegal
            )
        else:
            # it's a CDATA (so we just extract its content)
            ret_text += fragment.group("cdata_d")
    return ret_text


def get_base_url(
    text: AnyStr, baseurl: StrOrBytes = "", encoding: str = "utf-8"
) -> str:
    """Return the base url if declared in the given HTML `text`,
    relative to the given base url.

    If no base url is found, the given `baseurl` is returned.

    """

    utext: str = remove_comments(text, encoding=encoding)
    m = _baseurl_re.search(utext)
    if m:
        return urljoin(
            safe_url_string(baseurl), safe_url_string(m.group(1), encoding=encoding)
        )
    else:
        return safe_url_string(baseurl)


def get_meta_refresh(
    text: AnyStr,
    baseurl: str = "",
    encoding: str = "utf-8",
    ignore_tags: Iterable[str] = ("script", "noscript"),
) -> Union[Tuple[None, None], Tuple[float, str]]:
    """Return the http-equiv parameter of the HTML meta element from the given
    HTML text and return a tuple ``(interval, url)`` where interval is an integer
    containing the delay in seconds (or zero if not present) and url is a
    string with the absolute url to redirect.

    If no meta redirect is found, ``(None, None)`` is returned.

    """

    try:
        utext = to_unicode(text, encoding)
    except UnicodeDecodeError:
        print(text)
        raise
    utext = remove_tags_with_content(utext, ignore_tags)
    utext = remove_comments(replace_entities(utext))
    m = _meta_refresh_re.search(utext) or _meta_refresh_re2.search(utext)
    if m:
        interval = float(m.group("int"))
        url = safe_url_string(m.group("url").strip(" \"'"), encoding)
        url = urljoin(baseurl, url)
        return interval, url
    else:
        return None, None


def strip_html5_whitespace(text: str) -> str:
    r"""
    Strip all leading and trailing space characters (as defined in
    https://www.w3.org/TR/html5/infrastructure.html#space-character).

    Such stripping is useful e.g. for processing HTML element attributes which
    contain URLs, like ``href``, ``src`` or form ``action`` - HTML5 standard
    defines them as "valid URL potentially surrounded by spaces"
    or "valid non-empty URL potentially surrounded by spaces".

    >>> strip_html5_whitespace(' hello\n')
    'hello'
    """
    return text.strip(HTML5_WHITESPACE)
