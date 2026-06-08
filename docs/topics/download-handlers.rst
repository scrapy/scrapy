.. _topics-download-handlers:

=================
Download handlers
=================

Download handlers are Scrapy :ref:`components <topics-components>` used to
download :ref:`requests <topics-request-response>` and produce responses from
them.

Using download handlers
=======================

The :setting:`DOWNLOAD_HANDLERS_BASE` and :setting:`DOWNLOAD_HANDLERS` settings
tell Scrapy which handler is responsible for a given URL scheme. Their values
are merged into a mapping from scheme names to handler classes. When Scrapy
initializes it creates instances of all configured download handlers (except
for :ref:`lazy ones <lazy-download-handlers>`) and stores them in a similar
mapping. When Scrapy needs to download a request it extracts the scheme from
its URL, finds the handler for this scheme, passes the request to it and gets a
response from it.  If there is no handler for the scheme, the request is not
downloaded and a :exc:`~scrapy.exceptions.NotSupported` exception is raised.

The :setting:`DOWNLOAD_HANDLERS_BASE` setting contains the default mapping of
handlers. You can use the :setting:`DOWNLOAD_HANDLERS` setting to add handlers
for additional schemes and to replace or disable default ones:

.. code-block:: python

    DOWNLOAD_HANDLERS = {
        # disable support for ftp:// requests
        "ftp": None,
        # replace the default one for http://
        "http": "my.download_handlers.HttpHandler",
        # http:// and https:// are different schemes,
        # even though they may use the same handler
        "https": "my.download_handlers.HttpHandler",
        # support for any custom scheme can be added
        "sftp": "my.download_handlers.SftpHandler",
    }

Replacing HTTP(S) download handlers
-----------------------------------

While Scrapy provides a default handler for ``http`` and ``https`` schemes,
users may want to use a different handler, provided by Scrapy or by some
3rd-party package. There are several considerations to keep in mind related to
this.

First of all, as ``http`` and ``https`` are separate schemes, they need
separate entries in the :setting:`DOWNLOAD_HANDLERS` setting, even though it's
likely that the same handler class will be used for both schemes.

Additionally, some of the Scrapy settings, like :setting:`DOWNLOAD_MAXSIZE`,
are honored by the default HTTP(S) handler but not necessarily by alternative
ones. The same may apply to other Scrapy features, e.g. the
:signal:`bytes_received` and :signal:`headers_received` signals.

.. _lazy-download-handlers:

Lazy instantiation of download handlers
---------------------------------------

A download handler can be marked as "lazy" by setting its ``lazy`` class
attribute to ``True``. Such handlers are only instantiated when they need to
download their first request. This may be useful when the instantiation is slow
or requires dependencies that are not always available, and the handler is not
needed on every spider run. For example, :class:`the built-in S3 handler
<.S3DownloadHandler>` is lazy.

Writing your own download handler
=================================

A download handler is a :ref:`component <topics-components>` that defines
the following API:

.. class:: SampleDownloadHandler

    .. attribute:: lazy
        :type: bool

        If ``False``, the handler will be instantiated when Scrapy is
        initialized.

        If ``True``, the handler will only be instantiated when the first
        request handled by it needs to be downloaded.

    .. method:: download_request(request: Request) -> Response:
        :async:

        Download the given request and return a response.

    .. method:: close() -> None
        :async:

        Clean up any resources used by the handler.

An optional base class for custom handlers is provided:

.. autoclass:: scrapy.core.downloader.handlers.base.BaseDownloadHandler
    :members:
    :undoc-members:
    :member-order: bysource

.. _download-handlers-exceptions:

Exceptions raised by download handlers
======================================

.. versionadded:: 2.15.0

The built-in download handlers raise Scrapy-specific exceptions instead of
implementation-specific ones, so that code that handles these exceptions can be
written in a generic way. We recommend custom download handlers to also use
these exceptions.

.. autoexception:: scrapy.exceptions.CannotResolveHostError

.. autoexception:: scrapy.exceptions.DownloadCancelledError

.. autoexception:: scrapy.exceptions.DownloadConnectionRefusedError

.. autoexception:: scrapy.exceptions.DownloadFailedError

.. autoexception:: scrapy.exceptions.DownloadTimeoutError

.. autoexception:: scrapy.exceptions.ResponseDataLossError

.. autoexception:: scrapy.exceptions.UnsupportedURLSchemeError

.. _download-handlers-ref:

Built-in HTTP download handlers reference
=========================================

Scrapy ships several handlers for HTTP and HTTPS requests. While all of them
support basic features, they may differ in support of specific Scrapy features
and settings and HTTP protocol features. See the documentation of specific
handlers and specific settings for more information. Additionally, as the
underlying HTTP client implementations differ between handlers, the behavior of
specific websites may be different when doing the same Scrapy requests but
using different handlers.

Here is a comparison of some features of the built-in HTTP handlers, see the
individual handler docs for more differences:

================== ================= ===================== ====================
Feature            H2DownloadHandler HTTP11DownloadHandler HttpxDownloadHandler
================== ================= ===================== ====================
Requires asyncio   No                No                    Yes
Requires a reactor Yes               Yes                   No
HTTP/1.1           No                Yes                   Yes
HTTP/2             Yes               No                    Yes
TLS implementation ``cryptography``  ``cryptography``      Stdlib ``ssl``
HTTP proxies       No                Yes                   Yes
SOCKS proxies      No                No                    Yes
================== ================= ===================== ====================

You can find additional HTTP download handlers in the
scrapy-download-handlers-incubator_ package. This package is made by the Scrapy
developers and contains experimental handlers that may be included in some
later Scrapy version but can already be used. Please refer to the documentation
of this package for more information.

.. _scrapy-download-handlers-incubator: https://github.com/scrapy-plugins/scrapy-download-handlers-incubator

.. _twisted-http2-handler:

H2DownloadHandler
-----------------

.. autoclass:: scrapy.core.downloader.handlers.http2.H2DownloadHandler

| Supported scheme: ``https``.
| :ref:`Lazy <lazy-download-handlers>`: yes.
| :ref:`Requires asyncio support <using-asyncio>`: no.
| :ref:`Requires a Twisted reactor <asyncio-without-reactor>`: yes.

This handler supports ``https://host/path`` URLs and uses the HTTP/2 protocol
for them.

It's implemented using :mod:`twisted.web.client` and the ``h2`` library.

For this handler to work you need to install the ``Twisted[http2]`` extra
dependency.

If you want to use this handler you need to replace the default one for the
``https`` scheme:

.. code-block:: python

    DOWNLOAD_HANDLERS = {
        "https": "scrapy.core.downloader.handlers.http2.H2DownloadHandler",
    }

Features and limitations
^^^^^^^^^^^^^^^^^^^^^^^^

.. warning::

    This handler is experimental, and not yet recommended for production
    environments. Future Scrapy versions may introduce related changes without
    a deprecation period or warning.

=========================== ================================================
HTTP proxies                No (not implemented)
SOCKS proxies               No (not supported by the library)
HTTP/2                      Yes
``response.certificate``    :class:`twisted.internet.ssl.Certificate` object
Per-request ``bindaddress`` Yes
TLS implementation          ``pyOpenSSL``/``cryptography``
=========================== ================================================

Other limitations:

-   No support for HTTP/1.1.

-   IPv6 support requires setting :setting:`TWISTED_DNS_RESOLVER`
    to ``scrapy.resolver.CachingHostnameResolver``.

-   No support for the :signal:`bytes_received` and :signal:`headers_received`
    signals.

Known limitations of the HTTP/2 support:

-   No support for HTTP/2 Cleartext (h2c), since no major browser supports
    HTTP/2 unencrypted (refer `http2 faq`_).

-   No setting to specify a maximum `frame size`_ larger than the default
    value, 16384. Connections to servers that send a larger frame will fail.

-   No support for `server pushes`_, which are ignored.

.. _frame size: https://datatracker.ietf.org/doc/html/rfc7540#section-4.2
.. _http2 faq: https://http2.github.io/faq/#does-http2-require-encryption
.. _server pushes: https://datatracker.ietf.org/doc/html/rfc7540#section-8.2

HTTP11DownloadHandler
---------------------

.. autoclass:: scrapy.core.downloader.handlers.http11.HTTP11DownloadHandler

| Supported schemes: ``http``, ``https``.
| :ref:`Lazy <lazy-download-handlers>`: no.
| :ref:`Requires asyncio support <using-asyncio>`: no.
| :ref:`Requires a Twisted reactor <asyncio-without-reactor>`: yes.

This handler supports ``http://host/path`` and ``https://host/path`` URLs and
uses the HTTP/1.1 protocol for them.

It's implemented using :mod:`twisted.web.client`.

Features and limitations
^^^^^^^^^^^^^^^^^^^^^^^^

=========================== ================================================
HTTP proxies                Yes
SOCKS proxies               No (not supported by the library)
HTTP/2                      No (implemented as a separate handler)
``response.certificate``    :class:`twisted.internet.ssl.Certificate` object
Per-request ``bindaddress`` Yes
TLS implementation          ``pyOpenSSL``/``cryptography``
=========================== ================================================

Other limitations:

-   IPv6 support requires setting :setting:`TWISTED_DNS_RESOLVER`
    to ``scrapy.resolver.CachingHostnameResolver``.

-   HTTPS proxies to HTTPS destinations are not supported.

HttpxDownloadHandler
--------------------

.. versionadded:: 2.15.0

.. autoclass:: scrapy.core.downloader.handlers._httpx.HttpxDownloadHandler

| Supported schemes: ``http``, ``https``.
| :ref:`Lazy <lazy-download-handlers>`: no.
| :ref:`Requires asyncio support <using-asyncio>`: yes.
| :ref:`Requires a Twisted reactor <asyncio-without-reactor>`: no.

This handler supports ``http://host/path`` and ``https://host/path`` URLs and
uses the HTTP/1.1 or HTTP/2 protocol for them.

It's implemented using the ``httpx`` library and needs it to be installed.

If you want to use this handler you need to replace the default ones for the
``http`` and ``https`` schemes:

.. code-block:: python

    DOWNLOAD_HANDLERS = {
        "http": "scrapy.core.downloader.handlers._httpx.HttpxDownloadHandler",
        "https": "scrapy.core.downloader.handlers._httpx.HttpxDownloadHandler",
    }

Features and limitations
^^^^^^^^^^^^^^^^^^^^^^^^

.. warning::

    This handler is experimental, and not yet recommended for production
    environments. Future Scrapy versions may introduce related changes without
    a deprecation period or warning or even remove it altogether.

=========================== =======================================
HTTP proxies                Yes
SOCKS proxies               Yes (SOCKS5; requires ``httpx[socks]``)
HTTP/2                      Yes (requires ``httpx[http2]``)
``response.certificate``    DER bytes
Per-request ``bindaddress`` No (not supported by the library)
TLS implementation          Standard library ``ssl``
=========================== =======================================

Other limitations:

-   The handler creates a separate connection pool for each proxy URL (due to
    limitations of ``httpx``) which may lead to higher resource usage when
    using proxy rotation.

.. setting:: HTTPX_HTTP2_ENABLED

HTTPX_HTTP2_ENABLED
^^^^^^^^^^^^^^^^^^^

Default: ``False``

Whether to enable HTTP/2 support in this handler. The ``httpx[http2]`` extra
needs to be installed if you want to enable this setting.

.. versionadded:: VERSION

Built-in non-HTTP download handlers reference
=============================================

DataURIDownloadHandler
----------------------

.. autoclass:: scrapy.core.downloader.handlers.datauri.DataURIDownloadHandler

| Supported scheme: ``data``.
| :ref:`Lazy <lazy-download-handlers>`: no.
| :ref:`Requires asyncio support <using-asyncio>`: no.
| :ref:`Requires a Twisted reactor <asyncio-without-reactor>`: no.

This handler supports RFC 2397 ``data:content/type;base64,`` data URIs.

FileDownloadHandler
-------------------

.. autoclass:: scrapy.core.downloader.handlers.file.FileDownloadHandler

| Supported scheme: ``file``.
| :ref:`Lazy <lazy-download-handlers>`: no.
| :ref:`Requires asyncio support <using-asyncio>`: no.
| :ref:`Requires a Twisted reactor <asyncio-without-reactor>`: no.

This handler supports ``file:///path`` local file URIs. It doesn't
support remote files.

FTPDownloadHandler
------------------

.. autoclass:: scrapy.core.downloader.handlers.ftp.FTPDownloadHandler

| Supported scheme: ``ftp``.
| :ref:`Lazy <lazy-download-handlers>`: no.
| :ref:`Requires asyncio support <using-asyncio>`: no.
| :ref:`Requires a Twisted reactor <asyncio-without-reactor>`: yes.

This handler supports ``ftp://host/path`` FTP URIs.

It's implemented using :mod:`twisted.protocols.ftp`.

S3DownloadHandler
-----------------

.. autoclass:: scrapy.core.downloader.handlers.s3.S3DownloadHandler

| Supported scheme: ``s3``.
| :ref:`Lazy <lazy-download-handlers>`: yes.
| :ref:`Requires asyncio support <using-asyncio>`: no.
| :ref:`Requires a Twisted reactor <asyncio-without-reactor>`: no.

This handler supports ``s3://bucket/path`` S3 URIs.

It's implemented using the ``botocore`` library and needs it to be installed.
