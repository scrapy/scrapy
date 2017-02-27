"""
This module contains general purpose URL functions not found in the standard
library.

Some of the functions that used to be imported from this module have been moved
to the w3lib.url module. Always import those from there instead.
"""
import posixpath
import re
from six.moves.urllib.parse import (ParseResult, urldefrag, urlparse, urlunparse)

# scrapy.utils.url was moved to w3lib.url and import * ensures this
# move doesn't break old code
from w3lib.url import *
from w3lib.url import _safe_chars, _unquotepath
from scrapy.utils.python import to_unicode


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


def parse_url(url, encoding=None):
    """Return urlparsed url from the given argument (which could be an already
    parsed url)
    """
    if isinstance(url, ParseResult):
        return url
    return urlparse(to_unicode(url, encoding))


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


def strip_url(url, strip_credentials=True, strip_default_port=True, origin_only=False, strip_fragment=True):

    """Strip URL string from some of its components:

    - `strip_credentials` removes "user:password@"
    - `strip_default_port` removes ":80" (resp. ":443", ":21")
      from http:// (resp. https://, ftp://) URLs
    - `origin_only` replaces path component with "/", also dropping
      query and fragment components ; it also strips credentials
    - `strip_fragment` drops any #fragment component
    """

    parsed_url = urlparse(url)
    netloc = parsed_url.netloc
    if (strip_credentials or origin_only) and (parsed_url.username or parsed_url.password):
        netloc = netloc.split('@')[-1]
    if strip_default_port and parsed_url.port:
        if (parsed_url.scheme, parsed_url.port) in (('http', 80),
                                                    ('https', 443),
                                                    ('ftp', 21)):
            netloc = netloc.replace(':{p.port}'.format(p=parsed_url), '')
    return urlunparse((
        parsed_url.scheme,
        netloc,
        '/' if origin_only else parsed_url.path,
        '' if origin_only else parsed_url.params,
        '' if origin_only else parsed_url.query,
        '' if strip_fragment else parsed_url.fragment
    ))
