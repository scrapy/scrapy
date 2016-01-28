"""
This module contains general purpose URL functions not found in the standard
library.

Some of the functions that used to be imported from this module have been moved
to the w3lib.url module. Always import those from there instead.
"""
import posixpath
import re
from six.moves.urllib.parse import (ParseResult, urlunparse, urldefrag,
                                    urlparse, parse_qsl, urlencode,
                                    unquote)

# scrapy.utils.url was moved to w3lib.url and import * ensures this
# move doesn't break old code
from w3lib.url import *
from w3lib.url import _safe_chars
from scrapy.utils.python import to_native_str


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


def canonicalize_url(url, keep_blank_values=True, keep_fragments=False,
                     encoding=None):
    """Canonicalize the given url by applying the following procedures:

    - sort query arguments, first by key, then by value
    - percent encode paths and query arguments. non-ASCII characters are
      percent-encoded using UTF-8 (RFC-3986)
    - normalize all spaces (in query arguments) '+' (plus symbol)
    - normalize percent encodings case (%2f -> %2F)
    - remove query arguments with blank values (unless keep_blank_values is True)
    - remove fragments (unless keep_fragments is True)

    The url passed can be a str or unicode, while the url returned is always a
    str.

    For examples see the tests in tests/test_utils_url.py
    """

    scheme, netloc, path, params, query, fragment = parse_url(url)
    keyvals = parse_qsl(query, keep_blank_values)
    keyvals.sort()
    query = urlencode(keyvals)

    # XXX: copied from w3lib.url.safe_url_string to add encoding argument
    # path = to_native_str(path, encoding)
    # path = moves.urllib.parse.quote(path, _safe_chars, encoding='latin1') or '/'

    path = safe_url_string(_unquotepath(path)) or '/'
    fragment = '' if not keep_fragments else fragment
    return urlunparse((scheme, netloc.lower(), path, params, query, fragment))


def _unquotepath(path):
    for reserved in ('2f', '2F', '3f', '3F'):
        path = path.replace('%' + reserved, '%25' + reserved.upper())
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
