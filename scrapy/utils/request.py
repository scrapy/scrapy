"""
This module provides some useful functions for working with
scrapy.http.Request objects
"""

import pickle  # nosec
from hashlib import sha1
from urllib.parse import urlunparse
from weakref import WeakKeyDictionary

from w3lib.http import basic_auth_header
from w3lib.url import canonicalize_url

from scrapy.utils.httpobj import urlparse_cached
from scrapy.utils.python import to_bytes, to_unicode


def _noop_processor(*args):
    return args[0]


def default_request_key_hasher(data, request):
    """Given a request key object (`data`) and a `request`, it
    returns a :mod:`pickle`-serialized `SHA1
    <https://en.wikipedia.org/wiki/SHA-1>`_ hash of `data` as
    :class:`bytes`."""
    return sha1(pickle.dumps(data, protocol=2)).digest()


class RequestKeyBuilder:
    """Callable that, given a :class:`request <scrapy.http.Request>`, returns
    :class:`bytes` that uniquely identify *request*.

    *url_processor* (default: :func:`w3lib.url.canonicalize_url`) processes the
    *request* URL, and allows things like sorting URL query string parameters,
    so that two requests with the same URL query string parameters in different
    order still share the same request key.

    Some use cases of the `url_processor` parameter include:

    -   Comparing URLs case-insensitively::

            from w3lib.url import canonicalize_url

            def url_processor(url):
                return canonicalize_url(url).lower()

            request_key_buider = RequestKeyBuilder(url_processor=url_processor)

    -   Ignoring some URL query string parameters::

            from w3lib.url import canonicalize_url, url_query_cleaner

            def url_processor(url):
                url = canonicalize_url(url)
                parameters = ['parameters', 'to', 'ignore']
                return url_query_cleaner(url, parameterlist=parameters,
                                         remove=True)

            request_key_buider = RequestKeyBuilder(url_processor=url_processor)

    *headers* allows taking into account all or some headers. Use a list of
    strings to indicate which headers to include (header names are case
    insensitive), or use ``True`` to include all headers.

    *cb_kwargs* allows taking into account all or some :attr:`Request.cb_kwargs
    <scrapy.http.Request.cb_kwargs>` keys. Use a list of strings to indicate
    which callback keyword parameter keys to include, or use ``True`` for all
    callback keyword parameter keys.

    *meta* allows taking into account all or some :attr:`Request.meta
    <scrapy.http.Request.meta>` keys. Use a list of strings to indicate which
    meta keys to include, or use ``True`` for all meta keys.

    *post_processor* is a function that receives a list of key-value tuples
    containing key request data (based in the ``__init__`` parameters) and the
    source request object, and returns a request key as :class:`bytes`. It uses
    :func:`~scrapy.utils.request.default_request_key_hasher` by default.
    """

    def __init__(self, url_processor=canonicalize_url, headers=None,
                 meta=None, cb_kwargs=None,
                 post_processor=default_request_key_hasher):
        self._cache = WeakKeyDictionary()
        self._headers = headers
        if self._headers and self._headers is not True:
            self._headers = sorted(self._headers)
        self._cb_kwargs = cb_kwargs
        if self._cb_kwargs and self._cb_kwargs is not True:
            self._cb_kwargs = sorted(self._cb_kwargs)
        self._meta = meta
        if self._meta and self._meta is not True:
            self._meta = sorted(self._meta)
        self._post_processor = post_processor or _noop_processor
        self._url_processor = url_processor or _noop_processor

    def __call__(self, request):
        """Given a :class:`request <scrapy.http.Request>` it returns an
        immutable object that uniquely identifies `request`."""
        if request in self._cache:
            return self._cache[request]

        data = [
            ('method', request.method),
            ('url', self._url_processor(request.url)),
            ('body', request.body or b''),
        ]

        if self._headers:
            header_keys = self._headers
            if header_keys is True:
                header_keys = sorted(header.lower()
                                     for header in request.headers)
            headers = []
            for header_key in header_keys:
                if header_key in request.headers:
                    headers.append(
                        (
                            header_key,
                            tuple(value for value in
                                  request.headers.getlist(header_key))
                        )
                    )
            if headers:
                data.append(headers)

        if self._cb_kwargs:
            cb_kwargs_keys = self._cb_kwargs
            if cb_kwargs_keys is True:
                cb_kwargs_keys = sorted(request.cb_kwargs)
            cb_kwargs = []
            for cb_kwargs_key in cb_kwargs_keys:
                if cb_kwargs_key in request.cb_kwargs:
                    cb_kwargs.append((cb_kwargs_key,
                                      request.cb_kwargs[cb_kwargs_key]))
            if cb_kwargs:
                data.append(cb_kwargs)

        if self._meta:
            meta_keys = self._meta
            if meta_keys is True:
                meta_keys = sorted(request.meta)
            meta = []
            for meta_key in meta_keys:
                if meta_key in request.meta:
                    meta.append((meta_key, request.meta[meta_key]))
            if meta:
                data.append(meta)

        self._cache[request] = self._post_processor(data, request)
        return self._cache[request]


default_request_key_builder = RequestKeyBuilder()


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
    return to_unicode(referrer, errors='replace')
