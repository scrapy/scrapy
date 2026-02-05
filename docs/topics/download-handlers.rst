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

.. _download-handlers-ref:

Built-in download handlers reference
====================================

DataURIDownloadHandler
----------------------

.. autoclass:: scrapy.core.downloader.handlers.datauri.DataURIDownloadHandler

| Supported scheme: ``data``.
| Lazy: no.

This handler supports RFC 2397 ``data:content/type;base64,`` data URIs.

FileDownloadHandler
-------------------

.. autoclass:: scrapy.core.downloader.handlers.file.FileDownloadHandler

| Supported scheme: ``file``.
| Lazy: no.

This handler supports ``file:///path`` local file URIs. It doesn't
support remote files.

FTPDownloadHandler
------------------

.. autoclass:: scrapy.core.downloader.handlers.ftp.FTPDownloadHandler

| Supported scheme: ``ftp``.
| Lazy: no.

This handler supports ``ftp://host/path`` FTP URIs.

It's implemented using :mod:`twisted.protocols.ftp`.

.. _twisted-http2-handler:

H2DownloadHandler
-----------------

.. autoclass:: scrapy.core.downloader.handlers.http2.H2DownloadHandler

| Supported scheme: ``https``.
| Lazy: yes.

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

.. warning::

    This handler is experimental, and not yet recommended for production
    environments. Future Scrapy versions may introduce related changes without
    a deprecation period or warning.

.. note::

    Known limitations of the HTTP/2 implementation in this handler include:

    -   No support for HTTP/2 Cleartext (h2c), since no major browser supports
        HTTP/2 unencrypted (refer `http2 faq`_).

    -   No setting to specify a maximum `frame size`_ larger than the default
        value, 16384. Connections to servers that send a larger frame will
        fail.

    -   No support for `server pushes`_, which are ignored.

    -   No support for the :signal:`bytes_received` and
        :signal:`headers_received` signals.

.. _frame size: https://datatracker.ietf.org/doc/html/rfc7540#section-4.2
.. _http2 faq: https://http2.github.io/faq/#does-http2-require-encryption
.. _server pushes: https://datatracker.ietf.org/doc/html/rfc7540#section-8.2

HTTP11DownloadHandler
---------------------

.. autoclass:: scrapy.core.downloader.handlers.http11.HTTP11DownloadHandler

| Supported schemes: ``http``, ``https``.
| Lazy: no.

This handler supports ``http://host/path`` and ``https://host/path`` URLs and
uses the HTTP/1.1 protocol for them.

It's implemented using :mod:`twisted.web.client`.

S3DownloadHandler
-----------------

.. autoclass:: scrapy.core.downloader.handlers.s3.S3DownloadHandler

| Supported scheme: ``s3``.
| Lazy: yes.

This handler supports ``s3://bucket/path`` S3 URIs.

It's implemented using the ``botocore`` library and needs it to be installed.
