"""
Functions for handling encoding of web pages
"""
import re
import codecs
import encodings
from typing import Callable, Match, Optional, Tuple, Union, cast

from w3lib._types import AnyUnicodeError, StrOrBytes
import w3lib.util

_HEADER_ENCODING_RE = re.compile(r"charset=([\w-]+)", re.I)


def http_content_type_encoding(content_type: Optional[str]) -> Optional[str]:
    """Extract the encoding in the content-type header

    >>> import w3lib.encoding
    >>> w3lib.encoding.http_content_type_encoding("Content-Type: text/html; charset=ISO-8859-4")
    'iso8859-4'

    """

    if content_type:
        match = _HEADER_ENCODING_RE.search(content_type)
        if match:
            return resolve_encoding(match.group(1))

    return None


# regexp for parsing HTTP meta tags
_TEMPLATE = r"""%s\s*=\s*["']?\s*%s\s*["']?"""
_SKIP_ATTRS = """(?:\\s+
    [^=<>/\\s"'\x00-\x1f\x7f]+  # Attribute name
    (?:\\s*=\\s*
    (?:  # ' and " are entity encoded (&apos;, &quot;), so no need for \', \"
        '[^']*'   # attr in '
        |
        "[^"]*"   # attr in "
        |
        [^'"\\s]+  # attr having no ' nor "
    ))?
)*?"""  # must be used with re.VERBOSE flag
_HTTPEQUIV_RE = _TEMPLATE % ("http-equiv", "Content-Type")
_CONTENT_RE = _TEMPLATE % ("content", r"(?P<mime>[^;]+);\s*charset=(?P<charset>[\w-]+)")
_CONTENT2_RE = _TEMPLATE % ("charset", r"(?P<charset2>[\w-]+)")
_XML_ENCODING_RE = _TEMPLATE % ("encoding", r"(?P<xmlcharset>[\w-]+)")

# check for meta tags, or xml decl. and stop search if a body tag is encountered
# pylint: disable=consider-using-f-string
_BODY_ENCODING_PATTERN = (
    r"<\s*(?:meta%s(?:(?:\s+%s|\s+%s){2}|\s+%s)|\?xml\s[^>]+%s|body)"
    % (_SKIP_ATTRS, _HTTPEQUIV_RE, _CONTENT_RE, _CONTENT2_RE, _XML_ENCODING_RE)
)
_BODY_ENCODING_STR_RE = re.compile(_BODY_ENCODING_PATTERN, re.I | re.VERBOSE)
_BODY_ENCODING_BYTES_RE = re.compile(
    _BODY_ENCODING_PATTERN.encode("ascii"), re.I | re.VERBOSE
)


def html_body_declared_encoding(html_body_str: StrOrBytes) -> Optional[str]:
    '''Return the encoding specified in meta tags in the html body,
    or ``None`` if no suitable encoding was found

    >>> import w3lib.encoding
    >>> w3lib.encoding.html_body_declared_encoding(
    ... """<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN"
    ...      "http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd">
    ... <html xmlns="http://www.w3.org/1999/xhtml" xml:lang="en" lang="en">
    ... <head>
    ...     <title>Some title</title>
    ...     <meta http-equiv="content-type" content="text/html;charset=utf-8" />
    ... </head>
    ... <body>
    ... ...
    ... </body>
    ... </html>""")
    'utf-8'
    >>>

    '''

    # html5 suggests the first 1024 bytes are sufficient, we allow for more
    chunk = html_body_str[:4096]
    match: Union[Optional[Match[bytes]], Optional[Match[str]]]
    if isinstance(chunk, bytes):
        match = _BODY_ENCODING_BYTES_RE.search(chunk)
    else:
        match = _BODY_ENCODING_STR_RE.search(chunk)

    if match:
        encoding = (
            match.group("charset")
            or match.group("charset2")
            or match.group("xmlcharset")
        )
        if encoding:
            return resolve_encoding(w3lib.util.to_unicode(encoding))

    return None


# Default encoding translation
# this maps cannonicalized encodings to target encodings
# see http://www.whatwg.org/specs/web-apps/current-work/multipage/parsing.html#character-encodings-0
# in addition, gb18030 supercedes gb2312 & gbk
# the keys are converted using _c18n_encoding and in sorted order
DEFAULT_ENCODING_TRANSLATION = {
    "ascii": "cp1252",
    "big5": "big5hkscs",
    "euc_kr": "cp949",
    "gb2312": "gb18030",
    "gb_2312_80": "gb18030",
    "gbk": "gb18030",
    "iso8859_11": "cp874",
    "iso8859_9": "cp1254",
    "latin_1": "cp1252",
    "macintosh": "mac_roman",
    "shift_jis": "cp932",
    "tis_620": "cp874",
    "win_1251": "cp1251",
    "windows_31j": "cp932",
    "win_31j": "cp932",
    "windows_874": "cp874",
    "win_874": "cp874",
    "x_sjis": "cp932",
    "zh_cn": "gb18030",
}


def _c18n_encoding(encoding: str) -> str:
    """Canonicalize an encoding name

    This performs normalization and translates aliases using python's
    encoding aliases
    """
    normed = encodings.normalize_encoding(encoding).lower()
    return cast(str, encodings.aliases.aliases.get(normed, normed))


def resolve_encoding(encoding_alias: str) -> Optional[str]:
    """Return the encoding that `encoding_alias` maps to, or ``None``
    if the encoding cannot be interpreted

    >>> import w3lib.encoding
    >>> w3lib.encoding.resolve_encoding('latin1')
    'cp1252'
    >>> w3lib.encoding.resolve_encoding('gb_2312-80')
    'gb18030'
    >>>

    """
    c18n_encoding = _c18n_encoding(encoding_alias)
    translated = DEFAULT_ENCODING_TRANSLATION.get(c18n_encoding, c18n_encoding)
    try:
        return codecs.lookup(translated).name
    except LookupError:
        return None


_BOM_TABLE = [
    (codecs.BOM_UTF32_BE, "utf-32-be"),
    (codecs.BOM_UTF32_LE, "utf-32-le"),
    (codecs.BOM_UTF16_BE, "utf-16-be"),
    (codecs.BOM_UTF16_LE, "utf-16-le"),
    (codecs.BOM_UTF8, "utf-8"),
]
_FIRST_CHARS = {c[0] for (c, _) in _BOM_TABLE}


def read_bom(data: bytes) -> Union[Tuple[None, None], Tuple[str, bytes]]:
    r"""Read the byte order mark in the text, if present, and
    return the encoding represented by the BOM and the BOM.

    If no BOM can be detected, ``(None, None)`` is returned.

    >>> import w3lib.encoding
    >>> w3lib.encoding.read_bom(b'\xfe\xff\x6c\x34')
    ('utf-16-be', '\xfe\xff')
    >>> w3lib.encoding.read_bom(b'\xff\xfe\x34\x6c')
    ('utf-16-le', '\xff\xfe')
    >>> w3lib.encoding.read_bom(b'\x00\x00\xfe\xff\x00\x00\x6c\x34')
    ('utf-32-be', '\x00\x00\xfe\xff')
    >>> w3lib.encoding.read_bom(b'\xff\xfe\x00\x00\x34\x6c\x00\x00')
    ('utf-32-le', '\xff\xfe\x00\x00')
    >>> w3lib.encoding.read_bom(b'\x01\x02\x03\x04')
    (None, None)
    >>>

    """

    # common case is no BOM, so this is fast
    if data and data[0] in _FIRST_CHARS:
        for bom, encoding in _BOM_TABLE:
            if data.startswith(bom):
                return encoding, bom
    return None, None


# Python decoder doesn't follow unicode standard when handling
# bad utf-8 encoded strings. see http://bugs.python.org/issue8271
codecs.register_error(
    "w3lib_replace", lambda exc: ("\ufffd", cast(AnyUnicodeError, exc).end)
)


def to_unicode(data_str: bytes, encoding: str) -> str:
    """Convert a str object to unicode using the encoding given

    Characters that cannot be converted will be converted to ``\\ufffd`` (the
    unicode replacement character).
    """
    return data_str.decode(encoding, "replace")


def html_to_unicode(
    content_type_header: Optional[str],
    html_body_str: bytes,
    default_encoding: str = "utf8",
    auto_detect_fun: Optional[Callable[[bytes], Optional[str]]] = None,
) -> Tuple[str, str]:
    r'''Convert raw html bytes to unicode

    This attempts to make a reasonable guess at the content encoding of the
    html body, following a similar process to a web browser.

    It will try in order:

    * BOM (byte-order mark)
    * http content type header
    * meta or xml tag declarations
    * auto-detection, if the `auto_detect_fun` keyword argument is not ``None``
    * default encoding in keyword arg (which defaults to utf8)

    If an encoding other than the auto-detected or default encoding is used,
    overrides will be applied, converting some character encodings to more
    suitable alternatives.

    If a BOM is found matching the encoding, it will be stripped.

    The `auto_detect_fun` argument can be used to pass a function that will
    sniff the encoding of the text. This function must take the raw text as an
    argument and return the name of an encoding that python can process, or
    None.  To use chardet, for example, you can define the function as::

        auto_detect_fun=lambda x: chardet.detect(x).get('encoding')

    or to use UnicodeDammit (shipped with the BeautifulSoup library)::

        auto_detect_fun=lambda x: UnicodeDammit(x).originalEncoding

    If the locale of the website or user language preference is known, then a
    better default encoding can be supplied.

    If `content_type_header` is not present, ``None`` can be passed signifying
    that the header was not present.

    This method will not fail, if characters cannot be converted to unicode,
    ``\\ufffd`` (the unicode replacement character) will be inserted instead.

    Returns a tuple of ``(<encoding used>, <unicode_string>)``

    Examples:

    >>> import w3lib.encoding
    >>> w3lib.encoding.html_to_unicode(None,
    ... b"""<!DOCTYPE html>
    ... <head>
    ... <meta charset="UTF-8" />
    ... <meta name="viewport" content="width=device-width" />
    ... <title>Creative Commons France</title>
    ... <link rel='canonical' href='http://creativecommons.fr/' />
    ... <body>
    ... <p>Creative Commons est une organisation \xc3\xa0 but non lucratif
    ... qui a pour dessein de faciliter la diffusion et le partage des oeuvres
    ... tout en accompagnant les nouvelles pratiques de cr\xc3\xa9ation \xc3\xa0 l\xe2\x80\x99\xc3\xa8re numerique.</p>
    ... </body>
    ... </html>""")
    ('utf-8', '<!DOCTYPE html>\n<head>\n<meta charset="UTF-8" />\n<meta name="viewport" content="width=device-width" />\n<title>Creative Commons France</title>\n<link rel=\'canonical\' href=\'http://creativecommons.fr/\' />\n<body>\n<p>Creative Commons est une organisation \xe0 but non lucratif\nqui a pour dessein de faciliter la diffusion et le partage des oeuvres\ntout en accompagnant les nouvelles pratiques de cr\xe9ation \xe0 l\u2019\xe8re numerique.</p>\n</body>\n</html>')
    >>>

    '''
    bom_enc, bom = read_bom(html_body_str)
    if bom_enc is not None:
        bom = cast(bytes, bom)
        return bom_enc, to_unicode(html_body_str[len(bom) :], bom_enc)

    enc = http_content_type_encoding(content_type_header)
    if enc is not None:
        if enc == "utf-16" or enc == "utf-32":
            enc += "-be"
        return enc, to_unicode(html_body_str, enc)
    enc = html_body_declared_encoding(html_body_str)
    if enc is None and (auto_detect_fun is not None):
        enc = auto_detect_fun(html_body_str)
    if enc is None:
        enc = default_encoding
    return enc, to_unicode(html_body_str, enc)
