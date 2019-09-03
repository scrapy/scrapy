"""
This module provides some useful functions for working with
scrapy.http.Request objects
"""

import hashlib
import json
from functools import partial
from warnings import warn

from six import string_types
from six.moves.urllib.parse import urlunparse
from w3lib.http import basic_auth_header
from w3lib.url import canonicalize_url

from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.utils.httpobj import urlparse_cached
from scrapy.utils.misc import load_object
from scrapy.utils.python import to_bytes, to_native_str


def _load_object(path_or_object):
    """"It works as scrapy.utils.misc.load_object but it returns the input as
    is if it is already an object."""
    if isinstance(path_or_object, string_types):
        return load_object(path_or_object)
    return path_or_object


def json_serializer(data):
    """Returns the input :class:`dict` as an UTF-8-encoded JSON structure with
    sorted object keys."""
    return json.dumps(data, sort_keys=True).encode('utf-8')


def sha1_hasher(data):
    """Returns the SHA1 hash of the input :class:`bytes`, also as
    :class:`bytes`."""
    return hashlib.sha1(data).digest()


def process_request_fingerprint(request, data, url_processor=canonicalize_url,
                                headers=None, meta=None):
    """Given a :class:`request <scrapy.http.Request>` and a data :class:`dict`,
    it returns a :class:`dict` containing data from the request.

    The default output data includes a canonical version
    (:func:`w3lib.url.canonicalize_url`) of :attr:`request.url
    <scrapy.http.Request.url>` and the values of
    :attr:`request.method <scrapy.http.Request.method>` and
    :attr:`request.body <scrapy.http.Request.body>` (as an hexadecimal
    representation of its binary data).

    Override *url_processor* to change how the :attr:`request.url
    <scrapy.http.Request.url>` is preprocessed.

    You may use *headers* and *meta* to pass an iterable of keys from
    :attr:`request.headers <scrapy.http.Request.headers>` and
    :attr:`request.meta <scrapy.http.Request.meta>` that should be included in
    the output data as well.

    For example, to take into account the ``splash`` meta key::

        process_request_fingerprint(request, data, meta=['splash'])

    This function can be used in combination with Python’s
    :func:`~functools.partial` to easily define a processor function for
    :setting:`REQUEST_FINGERPRINT_PROCESSORS`::

        REQUEST_FINGERPRINT_PROCESSORS = [
            partial(process_request_fingerprint, meta=['splash']),
        ]
    """
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

    Example::

        >>> from scrapy import Request
        >>> request = Request('https://example.com')
        >>> request.fingerprint is None
        True
        >>> from scrapy.settings import Settings
        >>> request_fingerprint(request, hexadecimal=False, settings=Settings())
        b'\\x87\\xd9\\xb2q\\x8a\\xf8\\xdad%\\xc2i\\x06\\xc6\\x8f\\xbd<1i{\\xf5'
        >>> request.fingerprint
        b'\\x87\\xd9\\xb2q\\x8a\\xf8\\xdad%\\xc2i\\x06\\xc6\\x8f\\xbd<1i{\\xf5'

    .. deprecated:: VERSION

        ``include_headers``, use the :setting:`REQUEST_FINGERPRINT_PROCESSORS`
        setting instead

    .. deprecated:: VERSION

        ``hexadecimal=True``, future versions will always return the
        fingerprint as :class:`bytes`; use ``hexadecimal=False``
    """
    def encode(fingerprint):
        if hexadecimal:
            return fingerprint.hex()
        return fingerprint

    if include_headers is not None:
        warn('`include_headers` is deprecated. Use the '
             'REQUEST_FINGERPRINT_PROCESSORS setting instead.',
             ScrapyDeprecationWarning)
    if hexadecimal is not False:
        warn('`hexadecimal=True` is deprecated. Future versions will always '
             'return the fingerprint as `bytes`. Use `hexadecimal=False`.',
             ScrapyDeprecationWarning)
    if settings is None:
        warn('Calls omitting the `settings` parameter are deprecated. This '
             'parameter will be required in future versions.',
             ScrapyDeprecationWarning)

    use_new_behavior = include_headers is None and settings is not None
    if request.fingerprint is not None and use_new_behavior:
        return encode(request.fingerprint)

    if use_new_behavior:
        processors = [
            _load_object(processor) for processor in
            request.meta.get('fingerprint_processors',
                             settings.getlist('REQUEST_FINGERPRINT_PROCESSORS',
                                              [process_request_fingerprint]))]
        serializer = _load_object(
            request.meta.get('fingerprint_serializer',
                             settings.get('REQUEST_FINGERPRINT_SERIALIZER',
                                          json_serializer)))
        hasher = _load_object(
            request.meta.get('fingerprint_hasher',
                             settings.get('REQUEST_FINGERPRINT_HASHER',
                                          sha1_hasher)))
    else:
        processors = [partial(process_request_fingerprint,
                              headers=include_headers)]
        serializer = json_serializer
        hasher = sha1_hasher

    data = {}
    for processor in processors:
        data = processor(request, data)
    fingerprint = hasher(serializer(data))

    if use_new_behavior:
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
