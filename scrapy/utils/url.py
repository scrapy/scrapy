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
                                    unquote)
from six.moves.urllib.parse import quote, urlsplit, urlunsplit
if six.PY3:
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


def safe_url_string(url, encoding='utf8', path_encoding='utf8'):
    """Convert the given url into a legal URL by escaping unsafe characters
    according to RFC-3986.

    If a unicode url is given, it is first converted to str using the given
    encoding (which defaults to 'utf-8'). When passing a encoding, you should
    use the encoding of the original page (the page from which the url was
    extracted from).

    Calling this function on an already "safe" url will return the url
    unmodified.

    Always returns a native str (bytes in Python 2, unicode in Python 3).
    """
    # Python3 chokes on bytes input with non-ASCII chars
    # This is wrong! encoding only applies to query part, not the whole URL
    #parts = urlsplit(to_unicode(url, encoding=encoding))
    # let's consider the string as "correct": if bytes, they should be safe
    parts = urlsplit(url)

    # quote() in Python2 return type follows input type
    # quote() in Python3 always returns Unicode (native str)
    return urlunsplit((
        to_native_str(parts.scheme),
        to_native_str(parts.netloc),

        # default encoding for path component SHOULD be UTF-8
        quote(to_bytes(parts.path, path_encoding), _safe_chars),

        # encoding of query and fragment follows page encoding
        # or form-charset (if known and passed)
        quote(to_bytes(parts.query, encoding), _safe_chars),
        quote(to_bytes(parts.fragment, encoding), _safe_chars),
    ))


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
    scheme, netloc, path, params, query, fragment = parse_url(url)

    # 1. decode query-string using document encoding
    ekwargs = {}
    if not six.PY2:
        # Python3's urllib.parse methods have "encoding" argument
        # Python2's methods handle non-UTF-8 encoded input just fine
        ekwargs['encoding'] = encoding
    keyvals = parse_qsl(query, keep_blank_values, **ekwargs)
    keyvals.sort()
    query = urlencode(keyvals, **ekwargs)

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

    if six.PY3:
        # regular unquote() does not work in Python 3 for non-UTF-8
        # percent-escaped characters, they get lost.
        # e.g., '%a3' becomes 'REPLACEMENT CHARACTER' (U+FFFD)
        #
        # unquote_to_bytes() returns raw bytes instead
        return unquote_to_bytes(path)
    else:
        # in Python 2, '%a3' becomes '\xa3', which is what we want
        return unquote(path)


def parse_url(url, encoding=None):
    """Return urlparsed url from the given argument (which could be an already
    parsed url)
    """
    if isinstance(url, ParseResult):
        return url
    return urlparse(to_native_str(url, encoding))


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
