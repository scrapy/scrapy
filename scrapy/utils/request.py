"""
This module provides some useful functions for working with
scrapy.http.Request objects
"""

import hashlib
from warnings import warn

from six.moves.urllib.parse import urlunparse
from w3lib.http import basic_auth_header
from w3lib.url import canonicalize_url

from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.utils.httpobj import urlparse_cached
from scrapy.utils.python import to_bytes, to_native_str


def request_fingerprint(request, include_headers=None, hexadecimal=True,
                        settings=None):
    """Fills :attr:`request.fingerprint <scrapy.http.Request.fingerprint>` if
    needed and returns the fingerprint of *request*.

    If :attr:`request.fingerprint <scrapy.http.Request.fingerprint>` is already
    defined, its value is returned. Otherwise, the fingerprint of the request
    is calculated, assigned to
    :attr:`request.fingerprint <scrapy.http.Request.fingerprint>` and returned.

    *settings* must be an instance of :class:`scrapy.settings.Settings`. Most
    Scrapy components can get one from :attr:`crawler.settings
    <scrapy.crawler.Crawler.settings>`.

    .. deprecated:: VERSION

        ``hexadecimal=True`` is deprecated. Future versions will always return
        the fingerprint as :class:`bytes`. Use ``hexadecimal=False``.

    Example::

        >>> from scrapy import Request
        >>> request = Request('https://example.com')
        >>> request.fingerprint is None
        True
        >>> request_fingerprint(request, hexadecimal=False)
        b"mt\\x87A\\xa9'\\xb1\\x04T\\xc8:\\xc2\\x85\\xb0\\x02\\xcd#\\x99d\\xea"
        >>> request.fingerprint
        b"mt\\x87A\\xa9'\\xb1\\x04T\\xc8:\\xc2\\x85\\xb0\\x02\\xcd#\\x99d\\xea"
    """
    def encoded_fingerprint(request):
        if hexadecimal:
            return request.fingerprint.hex()
        return request.fingerprint

    if hexadecimal:
        warn('`hexadecimal=True` is deprecated. Future versions will always '
             'return the fingerprint as `bytes`. Use `hexadecimal=False`.',
             ScrapyDeprecationWarning)
    if settings is None:
        warn('Calls omitting the `settings` parameter are deprecated. This '
             'parameter will be required in future versions.',
             ScrapyDeprecationWarning)

    if request.fingerprint is not None:
        return encoded_fingerprint(request)
    fp = hashlib.sha1()
    fp.update(to_bytes(request.method))
    fp.update(to_bytes(canonicalize_url(request.url)))
    fp.update(request.body or b'')
    if include_headers:
        for header in sorted(include_headers):
            header = to_bytes(header.lower())
            if header in request.headers:
                fp.update(header)
                for v in request.headers.getlist(header):
                    fp.update(v)
    request.fingerprint = fp.digest()
    return encoded_fingerprint(request)


def request_authenticate(request, username, password):
    """Autenticate the given request (in place) using the HTTP basic access
    authentication mechanism (RFC 2617) and the given username and password
    """
    request.headers['Authorization'] = basic_auth_header(username, password)


def request_httprepr(request):
    """Return the raw HTTP representation (as bytes) of the given request.
    This is provided only for reference since it's not the actual stream of
    bytes that will be send when performing the request (that's controlled
    by Twisted).
    """
    parsed = urlparse_cached(request)
    path = urlunparse(('', '', parsed.path or '/', parsed.params, parsed.query, ''))
    s = to_bytes(request.method) + b" " + to_bytes(path) + b" HTTP/1.1\r\n"
    s += b"Host: " + to_bytes(parsed.hostname or b'') + b"\r\n"
    if request.headers:
        s += request.headers.to_string() + b"\r\n"
    s += b"\r\n"
    s += request.body
    return s


def referer_str(request):
    """ Return Referer HTTP header suitable for logging. """
    referrer = request.headers.get('Referer')
    if referrer is None:
        return referrer
    return to_native_str(referrer, errors='replace')
