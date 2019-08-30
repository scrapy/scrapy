"""
This module provides some useful functions for working with
scrapy.http.Request objects
"""

import hashlib
import json
from warnings import warn

from six.moves.urllib.parse import urlunparse
from w3lib.http import basic_auth_header
from w3lib.url import canonicalize_url

from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.utils.httpobj import urlparse_cached
from scrapy.utils.python import to_bytes, to_native_str


def process_request_fingerprint(request, data, url_processor=canonicalize_url,
                                headers=None, meta=None):
    data['method'] = request.method
    data['url'] = url_processor(request.url)
    data['body'] = request.body.hex() or ''
    if headers:
        for key in headers:
            key = key.lower()
            if key in request.headers:
                header_dict = data.setdefault('headers', {})
                header_dict[key] = [value.decode() for value in
                                    request.headers.getlist(key)]
    if meta:
        for key in meta:
            if key in request.meta:
                meta_dict = data.setdefault('meta', {})
                meta_dict[key] = request.meta[key]
    return data


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
        b'\\x87\\xd9\\xb2q\\x8a\\xf8\\xdad%\\xc2i\\x06\\xc6\\x8f\\xbd<1i{\\xf5'
        >>> request.fingerprint
        b'\\x87\\xd9\\xb2q\\x8a\\xf8\\xdad%\\xc2i\\x06\\xc6\\x8f\\xbd<1i{\\xf5'
    """
    def encode(fingerprint):
        if hexadecimal:
            return fingerprint.hex()
        return fingerprint

    if hexadecimal:
        warn('`hexadecimal=True` is deprecated. Future versions will always '
             'return the fingerprint as `bytes`. Use `hexadecimal=False`.',
             ScrapyDeprecationWarning)
    if settings is None:
        warn('Calls omitting the `settings` parameter are deprecated. This '
             'parameter will be required in future versions.',
             ScrapyDeprecationWarning)

    if request.fingerprint is not None and include_headers is None:
        return encode(request.fingerprint)
    fingerprint_data = process_request_fingerprint(
        request, {}, headers=include_headers)
    data_string = json.dumps(fingerprint_data, sort_keys=True)
    fingerprint = hashlib.sha1(data_string.encode('utf-8')).digest()
    if include_headers is None:
        request.fingerprint = fingerprint
    return encode(fingerprint)


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
