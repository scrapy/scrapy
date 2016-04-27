"""
This module contains general purpose URL functions not found in the standard
library.

Some of the functions that used to be imported from this module have been moved
to the w3lib.url module. Always import those from there instead.
"""
import posixpath
import re
import six
from six.moves.urllib.parse import (ParseResult, urlunparse, urldefrag,
                                    urlparse, parse_qsl, urlencode,
                                    quote, unquote)
if not six.PY2:
    from urllib.parse import unquote_to_bytes

# scrapy.utils.url was moved to w3lib.url and import * ensures this
# move doesn't break old code
from w3lib.url import *
from w3lib.url import _safe_chars
from scrapy.utils.python import to_bytes, to_native_str, to_unicode


def url_is_from_any_domain(url, domains):
    """Return True if the url belongs to any of the given domains"""
    host = parse_url(url).netloc.lower()
    if not host:
        return False
    domains = [d.lower() for d in domains]
    return any((host == d) or (host.endswith('.%s' % d)) for d in domains)


def url_is_from_spider(url, spider):
    """Return True if the url belongs to the given spider"""
    return url_is_from_any_domain(url,
        [spider.name] + list(getattr(spider, 'allowed_domains', [])))


def url_has_any_extension(url, extensions):
    return posixpath.splitext(parse_url(url).path)[1].lower() in extensions


def _safe_ParseResult(parts, encoding='utf8', path_encoding='utf8'):
    return (
        to_native_str(parts.scheme),
        to_native_str(parts.netloc.encode('idna')),

        # default encoding for path component SHOULD be UTF-8
        quote(to_bytes(parts.path, path_encoding), _safe_chars),
        quote(to_bytes(parts.params, path_encoding), _safe_chars),

        # encoding of query and fragment follows page encoding
        # or form-charset (if known and passed)
        quote(to_bytes(parts.query, encoding), _safe_chars),
        quote(to_bytes(parts.fragment, encoding), _safe_chars)
    )


def canonicalize_url(url, keep_blank_values=True, keep_fragments=False,
                     encoding=None):
    """Canonicalize the given url by applying the following procedures:

    - sort query arguments, first by key, then by value
    - percent encode paths ; non-ASCII characters are percent-encoded
      using UTF-8 (RFC-3986)
    - percent encode query arguments ; non-ASCII characters are percent-encoded
      using passed `encoding` (UTF-8 by default)
    - normalize all spaces (in query arguments) '+' (plus symbol)
    - normalize percent encodings case (%2f -> %2F)
    - remove query arguments with blank values (unless `keep_blank_values` is True)
    - remove fragments (unless `keep_fragments` is True)

    The url passed can be bytes or unicode, while the url returned is
    always a native str (bytes in Python 2, unicode in Python 3).

    For examples see the tests in tests/test_utils_url.py
    """
    # If supplied `encoding` is not compatible with all characters in `url`,
    # fallback to UTF-8 as safety net.
    # UTF-8 can handle all Unicode characters,
    # so we should be covered regarding URL normalization,
    # if not for proper URL expected by remote website.
    try:
        scheme, netloc, path, params, query, fragment = _safe_ParseResult(
            parse_url(url), encoding=encoding)
    except UnicodeEncodeError as e:
        scheme, netloc, path, params, query, fragment = _safe_ParseResult(
            parse_url(url), encoding='utf8')

    # 1. decode query-string as UTF-8 (or keep raw bytes),
    #    sort values,
    #    and percent-encode them back
    if six.PY2:
        keyvals = parse_qsl(query, keep_blank_values)
    else:
        # Python3's urllib.parse.parse_qsl does not work as wanted
        # for percent-encoded characters that do not match passed encoding,
        # they get lost.
        #
        # e.g., 'q=b%a3' becomes [('q', 'b\ufffd')]
        # (ie. with 'REPLACEMENT CHARACTER' (U+FFFD),
        #      instead of \xa3 that you get with Python2's parse_qsl)
        #
        # what we want here is to keep raw bytes, and percent encode them
        # so as to preserve whatever encoding what originally used.
        #
        # See https://tools.ietf.org/html/rfc3987#section-6.4:
        #
        # For example, it is possible to have a URI reference of
        # "http://www.example.org/r%E9sum%E9.xml#r%C3%A9sum%C3%A9", where the
        # document name is encoded in iso-8859-1 based on server settings, but
        # where the fragment identifier is encoded in UTF-8 according to
        # [XPointer]. The IRI corresponding to the above URI would be (in XML
        # notation)
        # "http://www.example.org/r%E9sum%E9.xml#r&#xE9;sum&#xE9;".
        # Similar considerations apply to query parts.  The functionality of
        # IRIs (namely, to be able to include non-ASCII characters) can only be
        # used if the query part is encoded in UTF-8.
        keyvals = parse_qsl_to_bytes(query, keep_blank_values)
    keyvals.sort()
    query = urlencode(keyvals)

    # 2. decode percent-encoded sequences in path as UTF-8 (or keep raw bytes)
    #    and percent-encode path again (this normalizes to upper-case %XX)
    uqp = _unquotepath(path)
    path = quote(uqp, _safe_chars) or '/'

    fragment = '' if not keep_fragments else fragment

    # every part should be safe already
    return urlunparse((scheme, netloc.lower(), path, params, query, fragment))


def _unquotepath(path):
    for reserved in ('2f', '2F', '3f', '3F'):
        path = path.replace('%' + reserved, '%25' + reserved.upper())

    if six.PY2:
        # in Python 2, '%a3' becomes '\xa3', which is what we want
        return unquote(path)
    else:
        # in Python 3,
        # standard lib's unquote() does not work for non-UTF-8
        # percent-escaped characters, they get lost.
        # e.g., '%a3' becomes 'REPLACEMENT CHARACTER' (U+FFFD)
        #
        # unquote_to_bytes() returns raw bytes instead
        return unquote_to_bytes(path)


def parse_url(url, encoding=None):
    """Return urlparsed url from the given argument (which could be an already
    parsed url)
    """
    if isinstance(url, ParseResult):
        return url
    return urlparse(to_unicode(url, encoding))


if not six.PY2:
    from urllib.parse import _coerce_args, unquote_to_bytes

    def parse_qsl_to_bytes(qs, keep_blank_values=False, strict_parsing=False):
        """Parse a query given as a string argument.

        Data are returned as a list of name, value pairs as bytes.

        Arguments:

        qs: percent-encoded query string to be parsed

        keep_blank_values: flag indicating whether blank values in
            percent-encoded queries should be treated as blank strings.  A
            true value indicates that blanks should be retained as blank
            strings.  The default false value indicates that blank values
            are to be ignored and treated as if they were  not included.

        strict_parsing: flag indicating what to do with parsing errors. If
            false (the default), errors are silently ignored. If true,
            errors raise a ValueError exception.

        """
        # This code is the same as Python3's parse_qsl()
        # (at https://hg.python.org/cpython/rev/c38ac7ab8d9a)
        # except for the unquote(s, encoding, errors) calls replaced
        # with unquote_to_bytes(s)
        qs, _coerce_result = _coerce_args(qs)
        pairs = [s2 for s1 in qs.split('&') for s2 in s1.split(';')]
        r = []
        for name_value in pairs:
            if not name_value and not strict_parsing:
                continue
            nv = name_value.split('=', 1)
            if len(nv) != 2:
                if strict_parsing:
                    raise ValueError("bad query field: %r" % (name_value,))
                # Handle case of a control-name with no equal sign
                if keep_blank_values:
                    nv.append('')
                else:
                    continue
            if len(nv[1]) or keep_blank_values:
                name = nv[0].replace('+', ' ')
                name = unquote_to_bytes(name)
                name = _coerce_result(name)
                value = nv[1].replace('+', ' ')
                value = unquote_to_bytes(value)
                value = _coerce_result(value)
                r.append((name, value))
        return r


def escape_ajax(url):
    """
    Return the crawleable url according to:
    http://code.google.com/web/ajaxcrawling/docs/getting-started.html

    >>> escape_ajax("www.example.com/ajax.html#!key=value")
    'www.example.com/ajax.html?_escaped_fragment_=key%3Dvalue'
    >>> escape_ajax("www.example.com/ajax.html?k1=v1&k2=v2#!key=value")
    'www.example.com/ajax.html?k1=v1&k2=v2&_escaped_fragment_=key%3Dvalue'
    >>> escape_ajax("www.example.com/ajax.html?#!key=value")
    'www.example.com/ajax.html?_escaped_fragment_=key%3Dvalue'
    >>> escape_ajax("www.example.com/ajax.html#!")
    'www.example.com/ajax.html?_escaped_fragment_='

    URLs that are not "AJAX crawlable" (according to Google) returned as-is:

    >>> escape_ajax("www.example.com/ajax.html#key=value")
    'www.example.com/ajax.html#key=value'
    >>> escape_ajax("www.example.com/ajax.html#")
    'www.example.com/ajax.html#'
    >>> escape_ajax("www.example.com/ajax.html")
    'www.example.com/ajax.html'
    """
    defrag, frag = urldefrag(url)
    if not frag.startswith('!'):
        return url
    return add_or_replace_parameter(defrag, '_escaped_fragment_', frag[1:])


def add_http_if_no_scheme(url):
    """Add http as the default scheme if it is missing from the url."""
    match = re.match(r"^\w+://", url, flags=re.I)
    if not match:
        parts = urlparse(url)
        scheme = "http:" if parts.netloc else "http://"
        url = scheme + url

    return url


def guess_scheme(url):
    """Add an URL scheme if missing: file:// for filepath-like input or http:// otherwise."""
    parts = urlparse(url)
    if parts.scheme:
        return url
    # Note: this does not match Windows filepath
    if re.match(r'''^                   # start with...
                    (
                        \.              # ...a single dot,
                        (
                            \. | [^/\.]+  # optionally followed by
                        )?                # either a second dot or some characters
                    )?      # optional match of ".", ".." or ".blabla"
                    /       # at least one "/" for a file path,
                    .       # and something after the "/"
                    ''', parts.path, flags=re.VERBOSE):
        return any_to_uri(url)
    else:
        return add_http_if_no_scheme(url)
