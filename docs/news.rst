.. _news:

Release notes
=============

Scrapy 2.20.0 (unreleased)
--------------------------

Highlights:

-   Web-browser-like detection of response encodings, base URLs and meta
    refresh redirects, powered by frostwork_

-   Requests can be awaited to get their response

-   Non-asyncio Twisted reactors are deprecated

Security bug fixes
~~~~~~~~~~~~~~~~~~

-   Scrapy now limits by default the memory that responses can take, fixing
    `CVE-2017-14158`_.

    In previous Scrapy versions, the only limit on the total size of responses
    in memory, ``SCRAPER_SLOT_MAX_ACTIVE_SIZE``, covered responses waiting for
    or going through spider callbacks. Responses to other requests, like those
    of :ref:`media pipelines <topics-media-pipeline>`, had no limit. For
    example, when media pipelines downloaded files faster than they could store
    them, e.g. to Amazon S3, the downloaded files piled up in memory, so a
    crawled website could make Scrapy run out of memory.

    The new :setting:`RESPONSE_MAX_ACTIVE_SIZE` setting replaces
    ``SCRAPER_SLOT_MAX_ACTIVE_SIZE`` and covers all responses in memory,
    including those to :ref:`awaited requests <inline-requests>` and to
    requests sent with :meth:`ExecutionEngine.download_async()
    <scrapy.core.engine.ExecutionEngine.download_async>`. Use it to change or
    disable the limit. The :command:`shell` disables it.

    .. _CVE-2017-14158: https://github.com/advisories/GHSA-h7wm-ph43-c39p

    (:gh:`482`, :gh:`4583`, :gh:`6430`, :gh:`8417`, :gh:`8459`, :gh:`8460`)

-   :class:`~scrapy.downloadermiddlewares.httpcompression.HttpCompressionMiddleware`
    now decodes at most 1 content coding per response by default, and drops
    responses that apply more with :exc:`~scrapy.exceptions.IgnoreRequest`.

    In previous Scrapy versions, the number of content codings was unlimited,
    so a malicious server could send a response with a ``Content-Encoding``
    header that chains thousands of codings (e.g. ``gzip, gzip, gzip, …``) to
    make Scrapy run as many decompression passes, causing high CPU and memory
    usage. See the `j72p-v7rm-cwm3`_ security advisory for details.

    To allow more content codings per response, set the new
    :setting:`COMPRESSION_MAX_ENCODINGS` setting.

    .. _j72p-v7rm-cwm3: https://github.com/scrapy/scrapy/security/advisories/GHSA-j72p-v7rm-cwm3

-   When :reqmeta:`http_auth_domain` is not set, the credentials from
    :reqmeta:`http_user` and :reqmeta:`http_pass` are now only sent to the
    origin (scheme, host and port) of the request where they were first used.

    In previous Scrapy versions, they were sent to any URL, so after a
    cross-origin redirect,
    :class:`~scrapy.downloadermiddlewares.httpauth.HttpAuthMiddleware` added
    them again to the ``Authorization`` header that
    :class:`~scrapy.downloadermiddlewares.redirect.RedirectMiddleware` had
    removed, sending them to the redirect target. A website could redirect
    Scrapy to a host under its control to steal those credentials. See the
    `466x-p45j-m4fx`_ security advisory for details.

    .. _466x-p45j-m4fx: https://github.com/scrapy/scrapy/security/advisories/GHSA-466x-p45j-m4fx

    (:gh:`8329`)

-   When using a proxy from the ``http_proxy`` or ``https_proxy`` environment
    variables, redirects now honor the ``no_proxy`` environment variable.

    In previous Scrapy versions, a redirect to a URL with the same scheme kept
    the proxy of the original request, even if the redirect host matched
    ``no_proxy``. A website could redirect Scrapy to an internal host, and that
    request would be sent through the proxy. For ``http://`` URLs, this exposed
    the request to the proxy, including any cookies or credentials for that
    host, and allowed the proxy to forge the response. See the
    `x3px-j3qh-fp5w`_ security advisory for details.

    .. _x3px-j3qh-fp5w: https://github.com/scrapy/scrapy/security/advisories/GHSA-x3px-j3qh-fp5w

-   :class:`~scrapy.pipelines.files.S3FilesStore` now uses HTTPS with the
    default Scrapy settings.

    In previous Scrapy versions, the default value of :setting:`AWS_USE_SSL`,
    ``None``, was incorrectly interpreted to mean "disable HTTPS", so
    :class:`~scrapy.pipelines.files.S3FilesStore` used plain HTTP when talking
    to S3 unless that setting was explicitly set to ``True`` or
    :setting:`AWS_ENDPOINT_URL` was set to a custom HTTPS URL.

    An attacker who could observe that traffic could read the contents, S3
    paths and metadata of the files uploaded by
    :class:`~scrapy.pipelines.files.FilesPipeline` and
    :class:`~scrapy.pipelines.images.ImagesPipeline`, the AWS access key ID
    (but not the secret access key) and, with temporary credentials, the
    session token (``X-Amz-Security-Token``). An attacker who could tamper with
    that traffic could make Scrapy falsely think that a file is up to date or
    was successfully stored. See the `fwm7-29m4-rrj9`_ security advisory for
    details.

    To restore the previous behavior, set :setting:`AWS_USE_SSL` to ``False``.

    .. _fwm7-29m4-rrj9: https://github.com/scrapy/scrapy/security/advisories/GHSA-fwm7-29m4-rrj9

-   :class:`~scrapy.linkextractors.lxmlhtml.LxmlLinkExtractor` and
    :class:`~scrapy.spiders.SitemapSpider` now only follow ``http://`` and
    ``https://`` URLs by default, plus URLs that use the scheme of the response
    they come from.

    In previous Scrapy versions, link extractors also followed ``file://`` and
    ``ftp://`` URLs, and :class:`~scrapy.spiders.SitemapSpider` followed URLs
    of any scheme. A crawled website could use that to make Scrapy read local
    files, send the :setting:`FTP_USER` and :setting:`FTP_PASSWORD` credentials
    to an FTP server of its choosing, or send requests signed with the
    :setting:`AWS_ACCESS_KEY_ID` credentials to an S3 bucket of its choosing.
    See the `q7wc-mr9r-gcjh`_ security advisory for details.

    To follow URLs with other schemes, use the new ``schemes`` parameter of
    :class:`~scrapy.linkextractors.lxmlhtml.LxmlLinkExtractor` or the new
    :attr:`~scrapy.spiders.SitemapSpider.sitemap_schemes` attribute of
    :class:`~scrapy.spiders.SitemapSpider`.

    .. _q7wc-mr9r-gcjh: https://github.com/scrapy/scrapy/security/advisories/GHSA-q7wc-mr9r-gcjh

Modified requirements
~~~~~~~~~~~~~~~~~~~~~

-   Dropped support for Python 3.10.
    (:gh:`8261`)

-   Dropped support for PyPy.
    (:gh:`7849`, :gh:`8358`, :gh:`8367`, :gh:`8393`)

-   New dependencies:

    - aiodns_ >= 3.3.0

    - aioftp_ >= 0.26.1

    - formerly_ >= 0.1.0

    - frostwork_ >= 0.2.0

    - typing-extensions_ >= 4.6.0 (on Python 3.12 and lower)

    (:gh:`7894`, :gh:`8213`, :gh:`8303`, :gh:`8376`, :gh:`8378`, :gh:`8393`)

-   charset-normalizer_ is no longer a dependency.
    (:gh:`8393`)

-   Increased the minimum versions of the following dependencies:

    - cssselect_: 0.9.1 → 1.2.0

    - itemloaders_: 1.0.1 → 1.0.5

    - lxml_: 4.6.4 → 4.9.4

    - parsel_: 1.5.0 → 1.8.1

    - Protego_: 0.1.15 → 0.2.0

    - queuelib_: 1.6.1 → 1.8.0

    - Twisted_: 21.7.0 → 23.10.0

    - w3lib_: 2.1.1 → 2.6.0

    (:gh:`6430`, :gh:`8195`, :gh:`8261`, :gh:`8303`, :gh:`8393`, :gh:`8460`)

-   Changes to :ref:`extras <extras>`:

    - New ``clipboard``, ``memusage`` and ``socks`` extras.

    - ``gcs``: google-cloud-storage_ 1.29.0 → 1.30.0

    - ``httpx``: httpx2_ 2.0.0 → 2.3.0

    - ``images``: Pillow_ 8.3.2 → 9.2.0

    - ``s3``: boto3_ 1.20.0 → 1.35.2, and aioboto3_ >= 9.0.0 is now
      included.

    - ``twisted-http2``: Twisted_ 21.7.0 → 23.10.0

    - ``uvloop``: uvloop_ 0.16.0 → 0.17.0

    (:gh:`6430`, :gh:`7826`, :gh:`7932`, :gh:`8058`, :gh:`8062`, :gh:`8162`,
    :gh:`8213`, :gh:`8261`, :gh:`8330`, :gh:`8341`, :gh:`8460`)

Backward-incompatible changes
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

-   Changes to the ``fetch()`` shortcut of the :ref:`Scrapy shell
    <topics-shell>`:

    - Requests are now downloaded with
      :meth:`ExecutionEngine.download_async()
      <scrapy.core.engine.ExecutionEngine.download_async>` instead of being
      passed to the scheduler. As a result, spider middlewares and duplicate
      filtering are no longer applied to them.

    - When a :class:`~scrapy.Request` object is passed, its ``callback`` and
      ``errback`` are no longer called, and a warning is issued if they are
      set.

    - The engine is no longer started, so the :signal:`engine_started` and
      :signal:`engine_stopped` signals are not sent, and components that start
      on them, such as the :class:`~scrapy.extensions.memusage.MemoryUsage`
      extension and the :ref:`telnet console <topics-telnetconsole>`, do not
      run in the shell.

    (:gh:`8174`, :gh:`8176`, :gh:`8179`)

-   Changes to the behavior of :class:`~scrapy.core.engine.ExecutionEngine`
    methods that change its state:

    - :meth:`~scrapy.core.engine.ExecutionEngine.close_spider_async` now also
      stops the engine. Calling it while the spider is opening now closes the
      spider as soon as it is open, calling it while the spider is closing now
      completes immediately instead of waiting for the in-flight requests, and
      calling it after the spider has been closed no longer raises
      :exc:`RuntimeError`.

    - :meth:`~scrapy.core.engine.ExecutionEngine.stop_async` now just calls
      :meth:`~scrapy.core.engine.ExecutionEngine.close_spider_async` with the
      ``shutdown`` reason. Calling it after
      :meth:`~scrapy.core.engine.ExecutionEngine.open_spider_async` and before
      :meth:`~scrapy.core.engine.ExecutionEngine.start_async` now closes the
      spider instead of raising :exc:`RuntimeError`. Calling it while the
      spider is closing or after the engine has stopped now completes
      immediately, instead of raising :exc:`RuntimeError` or waiting for the
      in-flight requests.

    - :meth:`~scrapy.core.engine.ExecutionEngine.start_async` now raises
      :exc:`RuntimeError` if called before
      :meth:`~scrapy.core.engine.ExecutionEngine.open_spider_async` has
      finished, instead of sending the :signal:`engine_started` signal
      anyway, and if called after the engine has stopped.

    - The :signal:`engine_stopped` signal is now sent only after all
      :signal:`engine_started` handlers have finished.

    - If the spider is closed before the engine is started, for example by
      calling :meth:`~scrapy.core.engine.ExecutionEngine.close_spider_async`
      from a :signal:`spider_opened` handler, the :signal:`engine_started` and
      :signal:`engine_stopped` signals are not sent.

    - :meth:`Crawler.stop_async() <scrapy.crawler.Crawler.stop_async>`, when
      called before the engine is running, e.g. while the spider is being
      opened, now closes the spider as soon as it is open, instead of being
      ignored.

    - A :exc:`~scrapy.exceptions.CloseSpider` exception raised while the spider
      is opening now closes the spider as soon as it is open, instead of being
      re-raised by
      :meth:`~scrapy.core.engine.ExecutionEngine.open_spider_async`.

    - ``crawl()`` and
      :meth:`~scrapy.core.engine.ExecutionEngine.download_async` now raise
      :exc:`RuntimeError` when called while the spider is closing, once the
      close has stopped waiting for the requests in progress.

    (:gh:`6916`, :gh:`8217`, :gh:`8272`, :gh:`8319`)

-   Setting the :attr:`ExecutionEngine.running
    <scrapy.core.engine.ExecutionEngine.running>` attribute no longer has any
    effect, and is deprecated. Its value is now ``False`` while the spider is
    closing.
    (:gh:`8181`)

-   :class:`~scrapy.core.downloader.handlers.ftp.FTPDownloadHandler` now
    enforces :setting:`DOWNLOAD_MAXSIZE` and :setting:`DOWNLOAD_WARNSIZE`, also
    when using :reqmeta:`ftp_local_filename`, so downloads bigger than 1 GiB
    now fail by default. To download bigger files, raise the limit to a size
    that fits them, with :setting:`DOWNLOAD_MAXSIZE` or with the
    :reqmeta:`download_maxsize` request meta key for specific requests. You can
    also set the limit to ``0`` to lift it altogether.
    (:gh:`8213`)

-   The built-in HTTP download handlers now limit their open connections with
    the new :setting:`CONCURRENT_CONNECTIONS_PER_HANDLER` setting, whose
    default value is derived from the limit of open files of the process, or
    is 480 on Windows.
    :class:`~scrapy.core.downloader.handlers.http11.HTTP11DownloadHandler` and
    :class:`~scrapy.core.downloader.handlers.http2.H2DownloadHandler` had no
    such limit before, and
    :class:`~scrapy.core.downloader.handlers._aiohttp.AiohttpDownloadHandler`
    and :class:`~scrapy.core.downloader.handlers._httpx.HttpxDownloadHandler`
    used :setting:`CONCURRENT_REQUESTS` as their limit. If you set
    :setting:`CONCURRENT_REQUESTS` higher than that default, a warning is
    logged, and you need to set :setting:`CONCURRENT_CONNECTIONS_PER_HANDLER`
    or, on platforms other than Windows, raise the limit of open files of the
    process (see :ref:`faq-too-many-open-files`).
    (:gh:`2653`, :gh:`5024`, :gh:`5618`, :gh:`7932`)

-   :class:`~scrapy.core.downloader.handlers._httpx.HttpxDownloadHandler` no
    longer falls back to the ``httpx`` package when httpx2_ is not installed.
    Install the ``httpx`` :ref:`extra <extras>` to use it.
    (:gh:`7932`)

-   Responses that your code keeps in memory, e.g. in the
    :attr:`.Request.meta` of scheduled requests or in component attributes,
    now count toward :setting:`RESPONSE_MAX_ACTIVE_SIZE` until they are
    released, and so do responses in a reference cycle until Python's garbage
    collector frees them. Keeping many responses can now slow down your crawl.
    To find out whether your crawl keeps responses alive, see
    :ref:`topics-leaks`.

    If requests have been held back by the limit for 5 seconds with none being
    downloaded and no response released, Scrapy runs Python's garbage collector
    and, if that releases no response, lets one request through, logging a
    warning the first time and increasing the new
    :stat:`response_max_active_size/bypass_count` stat.

    Scrapy itself no longer keeps responses alive in reference cycles after a
    request fails, e.g. with an
    :exc:`~scrapy.spidermiddlewares.httperror.HttpError` that no errback
    handles, or after a failed media pipeline download.

    (:gh:`6430`, :gh:`8417`, :gh:`8459`, :gh:`8460`)

-   Header names in ``Headers`` objects, i.e. in :attr:`Request.headers
    <scrapy.Request.headers>` and :attr:`Response.headers
    <scrapy.http.Response.headers>`, now keep the case they are first set
    with, instead of being converted to ``Title-Case``.
    Lookups are still case-insensitive, but code that iterates over header
    names and compares them to ``Title-Case`` strings must be updated.

    Over HTTP/1.1,
    :class:`~scrapy.core.downloader.handlers._aiohttp.AiohttpDownloadHandler`
    and :class:`~scrapy.core.downloader.handlers._httpx.HttpxDownloadHandler`
    now send header names in the case you write them in, and keep the case of
    response header names as received. See the :ref:`comparison of download
    handlers <download-handlers-ref>`.

    (:gh:`2711`, :gh:`7893`, :gh:`8265`)

-   :func:`~scrapy.downloadermiddlewares.retry.get_retry_request`, and hence
    :class:`~scrapy.downloadermiddlewares.retry.RetryMiddleware`, now sets the
    new :reqmeta:`skip_dupefilter_once` request meta key on retry requests
    instead of setting their :attr:`~scrapy.Request.dont_filter` attribute to
    ``True``. As a result, with schedulers that support that meta key, like
    the default one, requests derived from a retry request, e.g. redirects,
    are no longer exempt from duplicate filtering.
    (:gh:`6895`, :gh:`8224`)

-   Requests whose meta is copied from a downloaded request, e.g. redirects and
    retries, are now assigned to the download slot of their own URL domain,
    instead of keeping the slot of the original request. Requests whose meta is
    copied from a request whose :reqmeta:`download_slot` request meta key you
    set keep that slot, so set it to keep redirects and retries in the slot of
    the original request.
    (:gh:`8337`)

-   :reqmeta:`http_user` and :reqmeta:`http_pass` are now only sent to the
    origin (scheme, host and port) of the request that you set them on, so
    they are no longer sent after a cross-origin redirect. To send them to a
    different origin, set the :reqmeta:`http_auth_domain` request meta key.
    :class:`~scrapy.downloadermiddlewares.httpauth.HttpAuthMiddleware` also no
    longer sets the ``Authorization`` header of requests whose URL scheme is
    neither ``http`` nor ``https``.
    (:gh:`8329`)

-   Keys of :ref:`component priority dictionaries
    <component-priority-dictionaries>`, such as
    :setting:`DOWNLOADER_MIDDLEWARES`, that cannot be resolved into a
    component, e.g. the import path of a component that no longer exists, now
    raise :exc:`ValueError`, even if their priority is ``None``. Some of them
    used to be silently ignored, and a missing module used to raise
    :exc:`ModuleNotFoundError` instead. Fix the import path or remove the
    entry.
    (:gh:`7820`, :gh:`8159`)

-   :class:`HttpCompressionMiddleware
    <scrapy.downloadermiddlewares.httpcompression.HttpCompressionMiddleware>`
    now raises :exc:`~scrapy.exceptions.DecompressionError` for a response body
    that cannot be decompressed, instead of the exception of the underlying
    decompression library, e.g. :exc:`zlib.error`, :exc:`OSError` or
    :exc:`EOFError`. Update any code that catches those exceptions, e.g. in
    request errbacks.
    (:gh:`8177`)

-   ``str()`` of a :class:`~scrapy.Spider` object now returns its
    :attr:`~scrapy.Spider.name`. Use ``repr()`` to get the previous output,
    e.g. ``<MySpider 'my_spider' at 0x7f0e2c1a3b50>``.
    (:gh:`1576`, :gh:`8086`)

-   The ``scrapy.utils.defer.parallel()`` and
    ``scrapy.utils.defer.parallel_async()`` functions, now deprecated, return a
    :class:`~twisted.internet.defer.Deferred` that fires with ``None``, instead
    of with the result list of a :class:`~twisted.internet.defer.DeferredList`.
    (:gh:`5182`, :gh:`7959`)

-   The ``process_response()`` method of :class:`HttpCompressionMiddleware
    <scrapy.downloadermiddlewares.httpcompression.HttpCompressionMiddleware>`
    is now a coroutine function. Code that calls it must now await it, and
    subclasses that override it and call ``super().process_response()`` must
    now be ``async def``.
    (:gh:`3751`, :gh:`8153`)

-   The ``item_scraped()`` method of
    ``scrapy.extensions.feedexport.FeedExporter``, and the
    ``start_exporting()`` and ``finish_exporting()`` methods of
    ``scrapy.extensions.feedexport.FeedSlot``, are now coroutine functions.
    (:gh:`5622`, :gh:`6273`, :gh:`7800`)

-   ``parent_id`` is now part of :attr:`Request.attributes
    <scrapy.Request.attributes>`, so :meth:`Request.replace()
    <scrapy.Request.replace>` and
    :func:`~scrapy.utils.request.request_from_dict` pass a ``parent_id``
    keyword argument to the request class. :class:`~scrapy.Request` subclasses
    whose ``__init__()`` method accepts neither ``parent_id`` nor
    ``**kwargs`` must be updated.
    (:gh:`8225`)

-   :ref:`Item exporters <topics-exporters>` now turn the values of fields
    without a serializer into lists if they are list-like, e.g. tuples or sets,
    and into dictionaries if they are items, recursively. This changes the
    output of :class:`~scrapy.exporters.PickleItemExporter`,
    :class:`~scrapy.exporters.MarshalItemExporter`,
    :class:`~scrapy.exporters.PprintItemExporter` and custom
    :class:`~scrapy.exporters.BaseItemExporter` subclasses, and
    :class:`~scrapy.exporters.CsvItemExporter` now joins list-like values,
    e.g. sets, the way it joins lists.
    (:gh:`3888`, :gh:`3890`, :gh:`8057`)

-   The output of a request :ref:`errback <errbacks>` that runs because a
    download failed now goes through the
    :meth:`~scrapy.spidermiddlewares.SpiderMiddleware.process_spider_output`
    methods of :ref:`spider middlewares <topics-spider-middleware>`, with
    ``None`` as the response, and exceptions raised while iterating that output
    reach their
    :meth:`~scrapy.spidermiddlewares.SpiderMiddleware.process_spider_exception`
    methods. Spider middlewares whose methods expect a response must now also
    handle ``None``. Built-in spider middlewares now also process that output,
    e.g. :class:`~scrapy.spidermiddlewares.urllength.UrlLengthMiddleware` can
    drop requests from such errbacks, and
    :class:`~scrapy.spidermiddlewares.start.StartSpiderMiddleware` now sets
    :reqmeta:`is_start_request` in its ``process_start()`` method instead of in
    ``get_processed_request()``.
    (:gh:`4999`, :gh:`7992`)

-   Feed storages now refuse :ref:`feed modes <feed-mode>` that they do not
    support, which prevents the crawl from starting. In particular, setting
    the ``overwrite`` feed option to ``False`` for an :ref:`S3
    <topics-feed-storage-s3>` feed, which used to log a warning, now raises
    :exc:`ValueError`. For a :ref:`GCS <topics-feed-storage-gcs>` feed, which
    used to log a warning and overwrite the file, it now appends to the file.
    (:gh:`5580`, :gh:`7826`, :gh:`8173`)

-   :attr:`~scrapy.spiders.SitemapSpider.sitemap_follow` now also filters the
    sitemap URLs declared in :file:`robots.txt` files. If you set it, make sure
    it matches the URLs of the sitemaps declared in the :file:`robots.txt`
    files that you want to follow.
    (:gh:`1182`, :gh:`8175`)

-   The ``process_request()`` method of
    :class:`~scrapy.downloadermiddlewares.httpcache.HttpCacheMiddleware` is now
    a coroutine function. Code that calls it must now await it, and subclasses
    that override it and call ``super().process_request()`` must now be
    ``async def``.
    (:gh:`2744`, :gh:`7915`)

-   ``XMLFeedSpider.parse_nodes()`` and ``CSVFeedSpider.parse_rows()`` are now
    asynchronous generators. Code that calls them must now iterate over their
    output with ``async for``.
    (:gh:`8392`)

-   The settings of the built-in storages of :ref:`media pipelines
    <topics-media-pipeline>` are no longer set as class attributes of those
    storages, e.g. ``S3FilesStore.POLICY`` keeps its default value regardless
    of :setting:`FILES_STORE_S3_ACL`. Read them from the storage object of the
    pipeline instead, e.g. ``pipeline.store.POLICY``.
    (:gh:`7925`)

-   ``Scraper.slot`` and the deprecated ``scrapy.core.scraper.Slot`` class
    now take a :class:`~scrapy.crawler.Crawler` object instead of a maximum
    active size, their ``finish_response()`` method no longer takes a
    *result* parameter, their ``MIN_RESPONSE_SIZE`` attribute was removed,
    and their deprecated ``active_size`` attribute is read-only.
    (:gh:`6430`)

-   The engine status that the :ref:`telnet console <topics-telnetconsole>`
    reports now includes ``engine.response_active_size`` instead of
    ``engine.scraper.slot.active_size`` and
    ``engine.scraper.slot.needs_backout()``.
    (:gh:`6430`)

-   The deprecated ``METAREFRESH_IGNORE_TAGS`` setting and the *ignore_tags*
    parameter of the deprecated ``scrapy.utils.response.get_meta_refresh()``
    function now raise :exc:`ValueError` for tags other than ``script``,
    ``noscript`` and ``template``, and only whether ``noscript`` is listed has
    any effect. ``METAREFRESH_IGNORE_TAGS`` is ignored altogether if
    :setting:`METAREFRESH_SCRIPTING` is set with the same or a higher
    :ref:`priority <populating-settings>`.
    (:gh:`8393`)

-   Scrapy no longer calls the deprecated ``spider_opened()`` and
    ``spider_closed()`` methods of
    :class:`~scrapy.extensions.spiderstate.SpiderState`, so overriding them in
    a subclass has no effect. Handle the :signal:`spider_state_loaded` and
    :signal:`spider_state_saving` signals instead.
    (:gh:`5153`, :gh:`7650`, :gh:`7656`)

-   Due to the new minimum version of w3lib_, 2.6.0:

    - Request URLs are now normalized the way web browsers normalize them, so
      :attr:`Request.url <scrapy.Request.url>` and :attr:`Response.url
      <scrapy.http.Response.url>` can differ from the URL you pass, e.g.
      ``https://EXAMPLE.com`` becomes ``https://example.com/``,
      ``https://example.com/a/../b`` becomes ``https://example.com/b``, and
      ``https://0x7f.1/`` becomes ``https://127.0.0.1/``. Update any code that
      compares request or response URLs to literal strings.

    - :ref:`Request fingerprints <request-fingerprints>` might differ for some
      URLs, so that cached responses of
      :class:`~scrapy.downloadermiddlewares.httpcache.HttpCacheMiddleware` and
      the seen requests of a :ref:`job directory <job-dir>` from an earlier
      version might not match the same requests.

    (:gh:`8393`)

-   For encodings declared in the response, :attr:`TextResponse.encoding
    <scrapy.http.TextResponse.encoding>` now reports the Python codec names of
    the encodings that web browsers use, e.g. ``gbk`` instead of ``gb18030``
    for a ``gb2312`` label, and ``utf-16-le`` instead of ``utf-16``. It also
    reports ``utf-8`` instead of ``cp1252`` when the response declares no
    encoding and its body is ASCII-only, e.g. empty. For encoding labels that
    web browsers decode as a single U+FFFD character, like ``hz``, it reports
    ``replacement``, which raises :exc:`UnicodeDecodeError` when decoding any
    non-empty body, so use :attr:`TextResponse.text
    <scrapy.http.TextResponse.text>` instead of
    ``response.body.decode(response.encoding)``.

    :attr:`TextResponse.text <scrapy.http.TextResponse.text>` can also differ:

    - The detected encoding of responses that declare none and are not valid
      UTF-8 can change.

    - Encodings that web browsers ignore, like ``utf-32`` or ``cp437``, are now
      ignored when declared, and the encoding is detected instead. A ``<meta>``
      tag or XML declaration that declares UTF-16 now means UTF-8.

    - Encoding declarations in ``<meta>`` tags are now found past the first
      4096 bytes of the response body.

    - Response bodies are decoded the way web browsers decode them, which for
      some encodings, like ``euc-jp``, differs from Python codecs.

    (:gh:`8393`)

-   The base URL of a response, used by :meth:`TextResponse.urljoin()
    <scrapy.http.TextResponse.urljoin>`, :ref:`selectors <topics-selectors>`
    and :ref:`link extractors <topics-link-extractors>`, and the meta refresh
    that :class:`~scrapy.downloadermiddlewares.redirect.MetaRefreshMiddleware`
    follows, are now found closer to the way web browsers find them. In
    particular, they are now found anywhere in the response body, instead of
    only in its first 4096 characters, the meta refresh with the shortest
    delay, and the last one among those with that delay, now wins over the
    first one, meta refreshes within ``<script>`` or ``<template>`` elements,
    or to the response URL itself, ignoring its fragment, are no longer
    followed, and the base URL is normalized like request URLs.
    (:gh:`8393`)

-   The ``response`` attribute of :class:`~scrapy.Selector` objects is now
    read-only. For the selector of a response, i.e.
    :attr:`TextResponse.selector <scrapy.http.TextResponse.selector>`, it no
    longer keeps the response alive, and becomes ``None`` once nothing else
    refers to the response.
    (:gh:`8245`)

-   A negative value of :setting:`FILES_EXPIRES` or :setting:`IMAGES_EXPIRES`
    now disables expiration, so that files are never downloaded again once
    fetched. Previously, it made files be downloaded again every time; set
    the setting to ``0`` for that.
    (:gh:`8046`)

-   Crawls closed because :meth:`~scrapy.Spider.start` raised an exception, or
    by :setting:`CLOSESPIDER_ERRORCOUNT`, now make the :command:`crawl` and
    :command:`runspider` commands exit with code 1.
    (:gh:`8082`, :gh:`8203`)

-   A blank line between :ref:`contract <topics-contracts>` lines in a callback
    docstring now starts a new batch of contracts, which needs its own ``@url``
    line; otherwise, the contracts of that batch do not run.

    ``ContractsManager.extract_contracts()`` now returns a list of batches,
    each a list of contracts, and ``ContractsManager.from_method()`` now
    returns a list of requests instead of a request or ``None``.

    (:gh:`768`, :gh:`8043`)

Deprecations
~~~~~~~~~~~~

-   The following modules are deprecated, with no replacement:

    - ``scrapy.utils.benchserver``

    - ``scrapy.utils.console``

    - ``scrapy.utils.datatypes``

    - ``scrapy.utils.display``

    - ``scrapy.utils.ftp``

    - ``scrapy.utils.gz``

    - ``scrapy.utils.job``

    - ``scrapy.utils.ossignal``

    - ``scrapy.utils.sitemap``

    - ``scrapy.utils.ssl``

    - ``scrapy.utils.template``

    - ``scrapy.utils.versions``

    (:gh:`7766`, :gh:`8135`, :gh:`8146`, :gh:`8270`)

-   The following functions, classes and methods are deprecated, with no
    replacement:

    - ``scrapy.core.scraper.Scraper.handle_spider_error()``

    - ``scrapy.spiders.sitemap.iterloc()``

    - ``scrapy.utils.defer.aiter_errback()``

    - ``scrapy.utils.defer.iter_errback()``

    - ``scrapy.utils.defer.parallel()``

    - ``scrapy.utils.defer.parallel_async()``

    - ``scrapy.utils.python.MutableAsyncChain``

    (:gh:`8175`, :gh:`8288`, :gh:`8350`, :gh:`8363`, :gh:`8414`)

-   ``scrapy.utils.python.garbage_collect()`` is deprecated, use
    :func:`gc.collect` instead.
    (:gh:`8367`)

-   Passing a coroutine to ``scrapy.utils.spider.iterate_spider_output()``, for
    which it returns a :class:`~twisted.internet.defer.Deferred` instead of an
    iterable, is deprecated. Await the coroutine and pass its result instead.
    (:gh:`8394`)

-   Passing a synchronous iterable to
    ``scrapy.core.scraper.Scraper.handle_spider_output_async()`` is deprecated,
    pass an asynchronous iterable instead.
    (:gh:`8288`)

-   ``scrapy.utils.reactor.is_asyncio_reactor_installed()`` is deprecated. To
    check for asyncio support, use
    :func:`~scrapy.utils.asyncio.is_asyncio_available`. To check whether a
    reactor is installed, use ``scrapy.utils.reactor.is_reactor_installed()``.
    See :ref:`asyncio-old-versions` for code that must also support older
    Scrapy versions.
    (:gh:`8128`, :gh:`8454`)

-   Defining a ``parse_item()`` method in a
    :class:`~scrapy.spiders.XMLFeedSpider` subclass is deprecated. Define
    :meth:`~scrapy.spiders.XMLFeedSpider.parse_node` instead.
    (:gh:`8147`)

-   Exceptions that the ``process_response()`` method of a downloader
    middleware raises can now reach the ``process_exception()`` methods of the
    downloader middlewares that have not processed the response yet, so that
    :class:`~scrapy.downloadermiddlewares.retry.RetryMiddleware` can retry
    them. Because existing ``process_exception()`` methods may not expect those
    exceptions, e.g. the :exc:`~scrapy.exceptions.IgnoreRequest` raised to drop
    a response, this only happens when the new
    :setting:`DOWNLOADER_MIDDLEWARE_RESPONSE_EXCEPTIONS` setting is ``True``.
    Its default value, ``False``, is deprecated, and a warning is issued when
    an exception would reach the ``process_exception()`` method of a
    non-Scrapy downloader middleware if the setting were ``True``. Check that
    those methods handle such exceptions as intended, and set the setting to
    ``True``. New projects generated with :command:`startproject` already do.
    (:gh:`7790`, :gh:`8177`)

-   ``scrapy.utils.deprecate.create_deprecated_class()`` is deprecated, use
    ``formerly.deprecated_class()`` from formerly_ instead.
    ``scrapy.utils.decorators.deprecated()`` is deprecated, use
    :func:`warnings.deprecated` instead (or ``typing_extensions.deprecated()``
    on Python 3.12 and lower).
    (:gh:`7894`)

-   ``scrapy.utils.url.add_http_if_no_scheme()`` is deprecated. Use
    :func:`w3lib.url.add_http_if_no_scheme` instead.
    (:gh:`2186`, :gh:`8189`)

-   The following methods of ``Headers`` are deprecated:

    - ``fromkeys()``: pass ``(key, value)`` pairs to ``Headers`` instead.

    - ``has_key()``: use the ``in`` operator instead.

    - ``normkey()`` and ``normvalue()``.

    - ``setlist()``: assign the list instead, e.g. ``headers[key] =
      values``.

    - ``setlistdefault()``: use ``setdefault()`` instead.

    - ``to_unicode_dict()``: use ``to_tuple_list()`` instead.

    (:gh:`8259`, :gh:`8264`)

-   The ``spider_closed_callback`` parameter of
    :class:`~scrapy.core.engine.ExecutionEngine` is deprecated. Closing the
    spider now stops the engine, and :meth:`Crawler.crawl_async()
    <scrapy.crawler.Crawler.crawl_async>` completes when that happens.
    (:gh:`6916`, :gh:`8217`)

-   Setting the :attr:`ExecutionEngine.running
    <scrapy.core.engine.ExecutionEngine.running>` attribute is deprecated, and
    has no effect.
    (:gh:`8181`)

-   Custom :ref:`schedulers <topics-scheduler>` that do not set
    :attr:`~scrapy.core.scheduler.BaseScheduler.supports_skip_dupefilter_once`
    to ``True`` are deprecated, including subclasses of the default scheduler
    that override its
    :meth:`~scrapy.core.scheduler.BaseScheduler.enqueue_request` method.
    Scrapy turns :reqmeta:`skip_dupefilter_once` into ``dont_filter=True`` for
    them, with a warning. To update a scheduler,
    handle :reqmeta:`skip_dupefilter_once` in its
    :meth:`~scrapy.core.scheduler.BaseScheduler.enqueue_request` method and
    set
    :attr:`~scrapy.core.scheduler.BaseScheduler.supports_skip_dupefilter_once`
    to ``True``.
    (:gh:`6895`, :gh:`8224`)

-   The ``overwrite`` feed option is deprecated. Use the new ``mode``
    :ref:`feed option <feed-mode>` instead: ``"overwrite"`` instead of
    ``True``, ``"append"`` instead of ``False``. The ``overwrite`` attribute of
    :class:`~scrapy.extensions.feedexport.FTPFeedStorage` is deprecated as
    well.

    The default value of the new :setting:`FEED_MODE` setting, ``None``, is
    also deprecated: it will change to ``"create"`` in a future version of
    Scrapy, so that existing feed targets are not modified. Set
    :setting:`FEED_MODE`, or the ``mode`` option of every feed, to silence the
    deprecation warning. New projects set :setting:`FEED_MODE` to ``"create"``
    in their :file:`settings.py` file.
    (:gh:`5580`, :gh:`7826`)

-   The ``STORE_SCHEMES`` attribute of
    :class:`~scrapy.pipelines.files.FilesPipeline` is deprecated. Use the new
    :setting:`MEDIA_STORAGES` setting instead.
    (:gh:`5991`, :gh:`7925`)

-   The ``spider_opened()`` and ``spider_closed()`` methods of
    :class:`~scrapy.extensions.spiderstate.SpiderState` are deprecated. Use the
    new :signal:`spider_state_loaded` and :signal:`spider_state_saving`
    signals instead.
    (:gh:`5153`, :gh:`7650`, :gh:`7656`)

-   The *spider* and *to_native_str_type* parameters of
    ``scrapy.robotstxt.decode_robotstxt()`` are deprecated and have no effect.
    (:gh:`8316`)

-   Calling :meth:`AsyncCrawlerRunner.crawl()
    <scrapy.crawler.AsyncCrawlerRunner.crawl>` without a running asyncio event
    loop while :setting:`TWISTED_REACTOR_ENABLED` is ``False`` is deprecated.
    Call it from a coroutine that runs in the event loop instead, e.g. one
    passed to :func:`asyncio.run`.
    (:gh:`7201`, :gh:`7681`, :gh:`8327`)

-   ``ImagesPipeline.convert_image()`` has a new *image_format* keyword-only
    parameter with the original image format. Overriding the method without
    that parameter, and calling it without it, are deprecated.
    (:gh:`8198`, :gh:`8457`)

-   The ``SCRAPER_SLOT_MAX_ACTIVE_SIZE`` setting is deprecated. Use
    :setting:`RESPONSE_MAX_ACTIVE_SIZE` instead.

    ``scrapy.core.scraper.Slot`` is deprecated as well, and so are the
    ``active_size`` and ``max_active_size`` attributes and the
    ``needs_backout()`` method of ``Scraper.slot``. Use
    :attr:`ExecutionEngine.response_active_size
    <scrapy.core.engine.ExecutionEngine.response_active_size>`,
    :setting:`RESPONSE_MAX_ACTIVE_SIZE` and
    :meth:`ExecutionEngine.needs_backout()
    <scrapy.core.engine.ExecutionEngine.needs_backout>` instead.

    (:gh:`6430`)

-   Using a Twisted reactor other than
    :class:`~twisted.internet.asyncioreactor.AsyncioSelectorReactor` is
    deprecated, be it set through the ``TWISTED_REACTOR`` setting, installed
    by code outside Scrapy, or passed to
    :func:`~scrapy.utils.reactor.install_reactor`. Setting ``TWISTED_REACTOR``
    to ``None`` or ``""`` is deprecated as well. Remove any custom
    ``TWISTED_REACTOR`` setting from your code.

    The ``FORCE_CRAWLER_PROCESS`` setting is deprecated as well.

    (:gh:`8111`, :gh:`8454`)

-   Passing an encoding that web browsers do not support, e.g. ``cp437``, to
    the *encoding* parameter of :class:`~scrapy.http.TextResponse` is
    deprecated. To decode a response body with such an encoding, use
    ``response.body.decode(encoding)``.
    (:gh:`8393`)

-   ``scrapy.utils.response.get_base_url()`` and
    ``scrapy.utils.response.get_meta_refresh()`` are deprecated. Use the new
    :attr:`TextResponse.base_url <scrapy.http.TextResponse.base_url>` and
    :attr:`TextResponse.meta_refresh <scrapy.http.TextResponse.meta_refresh>`
    attributes instead. When there is no meta refresh, the latter is ``None``
    instead of ``(None, None)``.
    (:gh:`8393`)

-   The ``METAREFRESH_IGNORE_TAGS`` setting is deprecated. Use the new
    :setting:`METAREFRESH_SCRIPTING` setting instead.
    (:gh:`8393`)

New features
~~~~~~~~~~~~

-   :class:`~scrapy.Request` objects can now be awaited, e.g. in a spider
    callback, to send them and get their response. See :ref:`inline-requests`.
    (:gh:`1144`, :gh:`8207`)

-   Added a :setting:`DOWNLOAD_HANDLERS_BY_NAME` setting and a
    :reqmeta:`download_handler` request meta key, to :ref:`choose a download
    handler per request <download-handler-ids>`, e.g. a browser-based handler
    for only some requests. The default :ref:`request fingerprinter
    <request-fingerprints>` takes :reqmeta:`download_handler` into account
    when it does not match the URL scheme.

    :class:`~scrapy.downloadermiddlewares.robotstxt.RobotsTxtMiddleware` now
    copies :reqmeta:`download_handler` from the request that triggers a
    ``robots.txt`` request, and sets the new :reqmeta:`is_robotstxt_request`
    request meta key on the ``robots.txt`` requests that it sends.

    (:gh:`5510`, :gh:`7885`)

-   Added a :reqmeta:`body_file` request meta key, which writes the response
    body into a file as it is downloaded, so that large responses can be
    downloaded without keeping them in memory, with :ref:`download handlers
    that support it <download-handlers-ref>`. Set it to a file path, or to
    ``True`` to write into a new temporary file. Those requests get a
    :class:`~scrapy.http.BodyFileResponse`, and neither they nor their
    responses count toward :setting:`RESPONSE_MAX_ACTIVE_SIZE`.
    (:gh:`3880`, :gh:`4620`, :gh:`5044`, :gh:`7987`, :gh:`8466`)

-   Sending a shutdown signal, e.g. with Ctrl+C, a second time now triggers a
    fast stop, which drops queued and in-progress downloads instead of waiting
    for them to finish. Sending it a third time forces an unclean shutdown,
    which used to happen on the second signal. Dropped requests are counted in
    the new ``downloader/request_dropped_count`` stat.

    :meth:`Crawler.stop_async() <scrapy.crawler.Crawler.stop_async>`,
    :meth:`CrawlerRunner.stop() <scrapy.crawler.CrawlerRunner.stop>` and
    :meth:`AsyncCrawlerRunner.stop() <scrapy.crawler.AsyncCrawlerRunner.stop>`
    have a new keyword-only ``mode`` parameter that can be ``"graceful"`` (the
    default), ``"fast"`` or ``"force"``, which works as ``"fast"`` unless you
    use :class:`~scrapy.crawler.CrawlerProcess` or
    :class:`~scrapy.crawler.AsyncCrawlerProcess`.
    :meth:`~scrapy.core.engine.ExecutionEngine.stop_async` and
    :meth:`~scrapy.core.engine.ExecutionEngine.close_spider_async` accept
    ``"graceful"`` and ``"fast"``. A custom :setting:`DOWNLOADER` class needs
    a ``stop()`` coroutine method, returning the number of dropped requests,
    for fast stops to drop its downloads.
    (:gh:`4749`, :gh:`5000`, :gh:`7455`, :gh:`8296`, :gh:`8312`)

-   Added the :reqmeta:`delay` request meta key, which holds a request for at
    least the given number of seconds before sending it, and the
    :reqmeta:`delayed` request meta key, which lists the delays that a request
    has been held for.
    (:gh:`802`, :gh:`3835`, :gh:`4980`, :gh:`5015`, :gh:`7873`)

-   Added :attr:`TextResponse.base_url <scrapy.http.TextResponse.base_url>` and
    :attr:`TextResponse.meta_refresh <scrapy.http.TextResponse.meta_refresh>`,
    which return the base URL of a response and the
    :class:`~scrapy.http.response.text.MetaRefresh` that a web browser with
    JavaScript enabled would follow, and which you can set to override what the
    response body says. When :setting:`METAREFRESH_SCRIPTING` is ``False``,
    :class:`~scrapy.downloadermiddlewares.redirect.MetaRefreshMiddleware`
    ignores an overridden :attr:`~scrapy.http.TextResponse.meta_refresh`.
    (:gh:`8393`)

-   Added a :setting:`METAREFRESH_SCRIPTING` setting, which you can set to
    ``False`` to follow the meta refresh that a web browser with JavaScript
    disabled would follow.
    (:gh:`8393`)

-   Added a :setting:`FEED_MODE` setting and a ``mode`` :ref:`feed option
    <feed-options>`, which set what happens when the target of a feed already
    exists: ``"append"`` to it, ``"overwrite"`` it, or ``"create"``, which
    leaves it untouched, logs an error and increases the
    ``feedexport/conflicts/<storage class>`` stat. Custom feed storages declare
    the modes that they support with the new
    :attr:`~scrapy.extensions.feedexport.FeedStorageProtocol.supported_modes`
    attribute.

    The ``-o`` command-line option also follows :setting:`FEED_MODE`, so in a
    project with :setting:`FEED_MODE` set to ``"create"``, ``-o`` leaves an
    existing file untouched. Use ``-O`` to overwrite it.
    (:gh:`5580`, :gh:`7826`)

-   Added :class:`~scrapy.dupefilters.DiskDupeFilter`, a
    :setting:`DUPEFILTER_CLASS` that keeps request fingerprints in an SQLite
    database on disk instead of in memory, to lower memory usage on large
    crawls.
    (:gh:`5307`, :gh:`7952`)

-   Added a :setting:`JOBDIR_SYNC_EVERY` setting to write the
    :file:`active.json` file of the :ref:`job directory <job-dir>`, and the
    database of :class:`~scrapy.dupefilters.DiskDupeFilter`, while the crawl
    runs, so that a crawl killed before it can stop cleanly can resume from
    its latest state, provided that :setting:`SCHEDULER_DISK_QUEUE` and
    :setting:`SCHEDULER_START_DISK_QUEUE` use SQLite-based queues. Custom
    :setting:`SCHEDULER_PRIORITY_QUEUE` classes need the new
    :attr:`~scrapy.pqueues.PriorityQueueProtocol.changed` attribute and
    :meth:`~scrapy.pqueues.PriorityQueueProtocol.state` method to support it.

    :file:`active.json` is also now written atomically, so that it cannot be
    left half-written.

    (:gh:`7978`, :gh:`8152`, :gh:`8322`)

-   Added :attr:`Request.id <scrapy.Request.id>`, a unique identifier of each
    request, and :attr:`Request.parent_id <scrapy.Request.parent_id>`, the
    :attr:`~scrapy.Request.id` of the request it derives from, which Scrapy
    sets for requests from callbacks and errbacks, from
    :meth:`Response.follow() <scrapy.http.Response.follow>` and from
    :meth:`Request.replace() <scrapy.Request.replace>`, e.g. redirects and
    retries. Use the new *parent_id* parameter of :class:`~scrapy.Request` to
    set it on requests that your code builds on behalf of another request, e.g.
    in a downloader middleware. Both survive serialization, e.g. into the disk
    queues of a :ref:`job directory <job-dir>`.
    (:gh:`8225`)

-   Added a :command:`genrequest` command, which prints the Python code of a
    :class:`~scrapy.Request` object equivalent to a cURL command, given as an
    argument or read from the system clipboard with the new ``clipboard``
    :ref:`extra <extras>`.
    (:gh:`3990`, :gh:`3991`, :gh:`8058`)

-   Added a :command:`complete` command, which prints a :ref:`shell completion
    <completion>` script for Bash, fish or Zsh. Completion covers the spiders,
    settings and templates of the current project, and custom commands, which
    can provide their own candidates by overriding the new
    :meth:`~scrapy.commands.ScrapyCommand.complete_argument` and
    :meth:`~scrapy.commands.ScrapyCommand.complete_option` methods. It replaces
    the completion scripts that were in the :file:`extras` directory of the
    source code repository.
    (:gh:`6453`, :gh:`7899`)

-   Added a :setting:`STICKY_META_KEYS` setting to copy request metadata keys
    from a response into the follow-up requests yielded by its callback,
    handled by the new
    :class:`~scrapy.spidermiddlewares.stickymeta.StickyMetaParamsMiddleware`.

    The new middleware has priority 1000 in
    :setting:`SPIDER_MIDDLEWARES_BASE`, and
    :class:`~scrapy.spidermiddlewares.metacopy.MetaCopyDetectionMiddleware`
    moved from 1000 to 999.

    (:gh:`3645`, :gh:`3770`, :gh:`4141`, :gh:`7711`, :gh:`8166`)

-   :class:`~scrapy.spiders.Rule` has new ``name`` and ``from_rules``
    parameters, to apply a rule only to responses reached through specific
    other rules.
    (:gh:`982`, :gh:`8066`)

-   A callback docstring can now define several batches of :ref:`contracts
    <topics-contracts>`, one per paragraph, and a batch can repeat ``@url`` to
    check the callback against more than one sample request. Custom contracts
    can set the new ``generates_request`` attribute of
    :class:`~scrapy.contracts.Contract` to ``True`` to behave like ``@url``.
    (:gh:`768`, :gh:`8043`)

-   The :ref:`Google Cloud Storage feed storage <topics-feed-storage-gcs>` now
    supports the ``"append"`` :ref:`feed mode <feed-mode>`, instead of logging
    a warning and overwriting the feed.
    (:gh:`7823`, :gh:`8173`)

-   :setting:`FILES_EXPIRES` and :setting:`IMAGES_EXPIRES` now support
    fractional numbers of days, e.g. ``0.5`` for 12 hours, and negative values,
    which disable expiration, so that files are never downloaded again once
    fetched.
    (:gh:`2309`, :gh:`4731`, :gh:`8046`)

-   The *reactor_path* parameter of
    :func:`~scrapy.utils.reactor.install_reactor` is now optional, and
    defaults to the asyncio reactor.
    (:gh:`8125`)

-   Added a :setting:`DOWNLOADER_MIDDLEWARE_RESPONSE_EXCEPTIONS` setting which,
    when ``True``, passes exceptions raised by the ``process_response()``
    method of a downloader middleware to the ``process_exception()`` methods of
    the downloader middlewares that have not processed the response yet. This
    allows :class:`~scrapy.downloadermiddlewares.retry.RetryMiddleware` to
    retry responses that other middlewares reject, e.g. responses that cannot
    be decompressed, for which :exc:`~scrapy.exceptions.DecompressionError` is
    now part of :setting:`RETRY_EXCEPTIONS`.
    (:gh:`1900`, :gh:`3506`, :gh:`7790`, :gh:`8177`)

-   :exc:`~scrapy.exceptions.CloseSpider` can now be raised from
    :ref:`downloader middlewares <topics-downloader-middleware>` to close the
    spider.
    (:gh:`2578`, :gh:`8177`)

-   Added :class:`JsonValidationMiddleware
    <scrapy.downloadermiddlewares.jsonvalidation.JsonValidationMiddleware>`,
    with priority 560 in :setting:`DOWNLOADER_MIDDLEWARES_BASE` and enabled
    with the :setting:`JSONVALIDATION_ENABLED` setting, which raises
    :exc:`json.JSONDecodeError` for successful
    :class:`~scrapy.http.JsonResponse` responses with an invalid JSON body.
    :exc:`json.JSONDecodeError` is now part of :setting:`RETRY_EXCEPTIONS`, so
    those responses are retried if
    :setting:`DOWNLOADER_MIDDLEWARE_RESPONSE_EXCEPTIONS` is ``True``.
    (:gh:`8215`)

-   Added an *error* keyword-only parameter to
    :exc:`~scrapy.exceptions.CloseSpider` and
    :meth:`~scrapy.core.engine.ExecutionEngine.close_spider_async`, to mark a
    crawl as failed. Failed crawls set the new :stat:`finish_reason_error` stat
    to ``True``, get ``error=True`` in their :signal:`spider_closed` signal,
    and make the :command:`crawl` and :command:`runspider` commands exit with
    code 1. Crawls closed because :meth:`~scrapy.Spider.start` raised an
    exception (``start_error``) are now also marked as failed, and so are
    crawls closed by :setting:`CLOSESPIDER_ERRORCOUNT`.
    (:gh:`1241`, :gh:`2171`, :gh:`3653`, :gh:`3654`, :gh:`8082`, :gh:`8203`,
    :gh:`8204`, :gh:`8352`, :gh:`8357`)

-   Added an :setting:`IMAGES_PRESERVE_FORMAT` setting to :ref:`keep images in
    their original format <preserving-image-format>` instead of converting them
    to JPEG. Stored images then get no file extension.
    (:gh:`1705`, :gh:`2471`, :gh:`8198`)

-   Added an ``item_processor`` :ref:`feed option <feed-options>` to
    :ref:`replace each item with any number of items <item-processor>` in a
    given feed, and a ``feedexport/item_count/<storage class>`` stat with the
    number of exported entries per storage class.
    (:gh:`5905`, :gh:`7911`)

-   Added an :setting:`UPLOAD_TIMEOUT` setting to set how long uploads to
    remote :ref:`feed storages <topics-feed-storage-backends>` and :ref:`media
    pipeline storages <topics-media-pipeline>` (Amazon S3, Google Cloud Storage
    and FTP) wait for a response before giving up.
    (:gh:`5011`, :gh:`8162`)

-   Added a :setting:`MEDIA_CACHE_SIZE` setting to limit how many download
    outcomes :ref:`media pipelines <topics-media-pipeline>` keep in memory,
    which by default they keep for the whole crawl.
    (:gh:`939`, :gh:`8193`)

-   :setting:`LOG_FORMAT` now supports a ``%(spider)s`` placeholder with the
    name of the spider that triggered the log message, or ``-`` for messages
    not tied to a spider.
    (:gh:`1576`, :gh:`8086`)

-   :class:`~scrapy.statscollectors.StatsCollector` objects are now
    :class:`mutable mappings <collections.abc.MutableMapping>` of stats, e.g.
    ``stats["hostname"] = socket.gethostname()``.
    (:gh:`3230`, :gh:`8241`)

-   The :meth:`~scrapy.exporters.BaseItemExporter.start_exporting`,
    :meth:`~scrapy.exporters.BaseItemExporter.export_item` and
    :meth:`~scrapy.exporters.BaseItemExporter.finish_exporting` methods of
    :ref:`item exporters <topics-exporters>` used by :ref:`feed exports
    <topics-feed-exports>`, and the
    :meth:`~scrapy.extensions.feedexport.FeedStorageProtocol.open` and
    :meth:`~scrapy.extensions.feedexport.FeedStorageProtocol.store` methods of
    :ref:`feed storages <topics-feed-storage-custom>`, can now be coroutine
    functions.
    (:gh:`5622`, :gh:`6273`, :gh:`7800`)

-   Added a :setting:`LOG_LEVELS` setting, to set the minimum log level of
    specific loggers, overriding the levels that Scrapy sets by default.
    (:gh:`2231`, :gh:`7921`)

-   The :command:`settings` command now takes the settings of enabled
    :ref:`add-ons <topics-addons>` into account, and has a new ``--spider``
    option to take the settings of a spider into account as well.
    (:gh:`7010`, :gh:`7828`)

-   Added a :reqmeta:`skip_dupefilter_once` request meta key, which skips
    duplicate filtering for a request without affecting the requests derived
    from it, and a
    :attr:`~scrapy.core.scheduler.BaseScheduler.supports_skip_dupefilter_once`
    attribute for schedulers to declare that they support it.
    (:gh:`6895`, :gh:`8224`)

-   The FTP download handlers now list the contents of a directory when the
    URL path is empty or ends in ``/``, returning the output of the FTP
    ``NLST`` command, one name per line.
    (:gh:`1478`, :gh:`2505`, :gh:`8197`)

-   The :ref:`memory usage extension <topics-extensions-ref-memusage>` now
    works on Windows, with the new ``memusage`` :ref:`extra <extras>`.
    (:gh:`4070`, :gh:`8062`)

-   Added :class:`~scrapy.core.engine.EngineState` and
    :attr:`ExecutionEngine.state <scrapy.core.engine.ExecutionEngine.state>`,
    which tell the lifecycle state of the engine.
    (:gh:`6916`, :gh:`8217`)

-   The :command:`fetch`, :command:`view`, :command:`shell` and
    :command:`parse` commands now support a ``--curl`` option, to build the
    request from a cURL command instead of from a URL argument.
    (:gh:`36`, :gh:`447`, :gh:`7703`)

-   Added an experimental FTP and FTPS download handler,
    :class:`~scrapy.core.downloader.handlers._aioftp.AioftpDownloadHandler`,
    used by default when running :ref:`without a Twisted reactor
    <asyncio-without-reactor>`. The new ``socks`` :ref:`extra <extras>`
    enables its support for SOCKS proxies.
    (:gh:`7261`, :gh:`8213`, :gh:`8341`)

-   Added :setting:`MEDIA_STORAGES` and :setting:`MEDIA_STORAGES_BASE`
    settings, which map URL schemes to the storage classes of the :ref:`media
    pipelines <topics-media-pipeline>`, to support additional schemes or
    replace built-in storages. Storage classes can define a ``from_crawler()``
    class method to read settings, including settings specific to the files or
    images pipeline, or to a pipeline subclass.

    Pipelines no longer share the settings of built-in storages, so that e.g.
    the files and images pipelines of a crawl can use different values for
    :setting:`FILES_STORE_S3_ACL` and :setting:`IMAGES_STORE_S3_ACL`.
    (:gh:`5991`, :gh:`7925`)

-   Added :setting:`FILES_CHECKSUM_ALGORITHM` and
    :setting:`IMAGES_CHECKSUM_ALGORITHM` settings, to calculate the checksums
    of :ref:`media pipeline <topics-media-pipeline>` files with a
    :mod:`hashlib` algorithm other than MD5.
    (:gh:`3306`, :gh:`7951`)

-   :class:`~scrapy.linkextractors.lxmlhtml.LxmlLinkExtractor` has a new
    ``schemes`` parameter to choose the URL schemes of extracted links, and
    :data:`scrapy.linkextractors.SUPPORTED_SCHEMES` lists the URL schemes that
    Scrapy can download out of the box.
    (:gh:`4979`, :gh:`7994`)

-   Added :meth:`SitemapSpider.sitemap_request()
    <scrapy.spiders.SitemapSpider.sitemap_request>`, which you can override to
    customize the requests that :class:`~scrapy.spiders.SitemapSpider` builds
    from sitemap entries, e.g. to pass sitemap data to callbacks.
    (:gh:`2565`, :gh:`3543`, :gh:`8175`)

-   Added a :meth:`~scrapy.robotstxt.RobotParser.sitemaps` method to
    :class:`~scrapy.robotstxt.RobotParser`, implemented by the
    :ref:`Protego <protego-parser>` and :ref:`Robotexclusionrulesparser
    <rerp-parser>` parsers, which returns the sitemap URLs declared in the
    :file:`robots.txt` file, and a *response* parameter to the
    :signal:`robots_parsed` signal.
    (:gh:`3967`, :gh:`8069`, :gh:`8175`)

-   Added the :signal:`spider_state_loaded`, :signal:`spider_state_saving`
    and :signal:`feed_slots_initialized` signals.
    (:gh:`5153`, :gh:`7650`, :gh:`7656`)

-   Added an :ref:`event loop lag monitor <event-loop-lag>` extension, enabled
    by default, which logs a warning when code blocks the event loop for longer
    than the new :setting:`EVENT_LOOP_LAG_THRESHOLD` setting, 10 seconds by
    default.
    (:gh:`3197`, :gh:`8093`)

-   When :class:`~scrapy.downloadermiddlewares.robotstxt.RobotsTxtMiddleware`
    denies at least one :ref:`start request <start-requests>` and no start
    request can be crawled, the crawl now finishes with the
    ``robotstxt_denied`` :stat:`finish_reason` instead of ``finished``, and an
    error is logged.
    (:gh:`6164`)

-   :func:`~scrapy.utils.httpobj.urlparse_cached` now also accepts a URL
    string, and ``scrapy.utils.url.url_is_from_any_domain()``,
    ``url_is_from_spider()`` and ``url_has_any_extension()`` now also accept
    :class:`~scrapy.Request` and :class:`~scrapy.http.Response` objects.
    Built-in components now reuse URL parsing results more, which makes
    crawls faster.
    (:gh:`8247`)

-   Added a :reqmeta:`proxy_headers` request meta key, to send headers to the
    proxy set in :reqmeta:`proxy`, e.g. in the ``CONNECT`` request of HTTPS
    URLs.
    (:gh:`3329`, :gh:`7888`)

-   Added
    :class:`~scrapy.downloadermiddlewares.uriuserinfo.UriUserInfoMiddleware`,
    enabled by default, which removes the credentials from request URLs like
    ``https://user:pass@example.com`` and sets them as :reqmeta:`http_user`
    and :reqmeta:`http_pass`, or as :reqmeta:`ftp_user` and
    :reqmeta:`ftp_password` for FTP URLs. As a result, :attr:`Request.url
    <scrapy.Request.url>` and :attr:`Response.url <scrapy.http.Response.url>`
    no longer include those credentials after that middleware.
    (:gh:`669`, :gh:`851`, :gh:`1466`, :gh:`4474`)

-   Added an :setting:`HTTPCACHE_SCOPE` setting, which allows sharing the HTTP
    cache across spiders and, with
    :class:`~scrapy.extensions.httpcache.FilesystemCacheStorage`, splitting it
    by request host instead of by spider.
    (:gh:`5166`, :gh:`5175`, :gh:`7964`)

-   Added a :setting:`LOG_ROOT_FORMATTER` setting, which sets the formatter of
    the root log handler. Such formatters implement the new
    :class:`~scrapy.LogRootFormatterProtocol`, and the new
    :class:`~scrapy.LogRootFormatter` is the default one, which you can also
    use in your own log handlers.
    :setting:`LOG_COLOR` also works with custom formatters.
    (:gh:`8336`)

-   Added a :setting:`CONNECTION_KEEPALIVE_TIMEOUT` setting, which sets how
    long the built-in HTTP download handlers keep idle connections open for
    reuse. Its default value, 240 seconds, is the timeout that the
    Twisted-based handlers already used; the aiohttp- and httpx-based handlers
    used their library defaults, 15 and 5 seconds respectively.
    (:gh:`8342`)

-   Added :meth:`Response.follow_redirect()
    <scrapy.http.Response.follow_redirect>`, which returns a request that
    follows the ``Location`` header of the response.
    (:gh:`8331`)

-   When :setting:`DOWNLOAD_FAIL_ON_DATALOSS` or the
    :reqmeta:`download_fail_on_dataloss` request meta key is ``False``,
    hitting the download timeout while receiving the response body now
    returns the part of the response received so far, with the ``dataloss``
    flag, instead of raising :exc:`~scrapy.exceptions.DownloadTimeoutError`,
    with all built-in download handlers except
    :class:`~scrapy.core.downloader.handlers.ftp.FTPDownloadHandler`.
    (:gh:`3407`, :gh:`3492`, :gh:`8084`, :gh:`8464`)

-   :class:`~scrapy.core.downloader.handlers.http11.HTTP11DownloadHandler`
    now supports proxies with an IPv6 address, proxies whose host name only
    resolves to IPv6 addresses, given an IPv6-capable
    :setting:`TWISTED_DNS_RESOLVER`, and HTTPS requests to IPv6 addresses
    through a proxy.
    (:gh:`6674`, :gh:`7090`, :gh:`8116`, :gh:`8343`)

-   When asyncio support is available and ``aioboto3`` is installed,
    :ref:`S3 feed storage <topics-feed-storage-s3>` uploads files with it,
    instead of running ``boto3`` in a thread. Similarly, the :ref:`S3 storage
    of media pipelines <media-pipelines-s3>` uses ``aiobotocore``, when
    installed, instead of ``botocore``.
    (:gh:`3845`, :gh:`8330`, :gh:`8339`)

-   Added a :setting:`CONCURRENT_CONNECTIONS_PER_HANDLER` setting, which limits
    the number of connections, idle ones included, that each download handler
    keeps open. By default, the limit is derived from the maximum number of
    open files allowed for the process, or from the :func:`select.select`
    limit on Windows, to prevent ``Too many open files`` errors (see
    :ref:`faq-too-many-open-files`).
    (:gh:`2653`, :gh:`5024`, :gh:`5618`, :gh:`7932`)

-   Added a :setting:`REDIRECT_HTTP_CODES` setting and a
    :reqmeta:`redirect_http_codes` request meta key, which set the response
    status codes whose ``Location`` header
    :class:`~scrapy.downloadermiddlewares.redirect.RedirectMiddleware` follows,
    e.g. to follow the ``Location`` header of 201 responses. Media pipelines
    with :setting:`MEDIA_ALLOW_REDIRECTS` enabled leave responses with those
    status codes to
    :class:`~scrapy.downloadermiddlewares.redirect.RedirectMiddleware`.
    (:gh:`1615`, :gh:`7801`)

-   :class:`~scrapy.core.downloader.handlers.http11.HTTP11DownloadHandler` now
    supports ``https://`` proxy URLs for ``https://`` destination URLs.
    (:gh:`5828`, :gh:`7776`)

-   When several requests for the same resource are sent concurrently,
    :class:`~scrapy.downloadermiddlewares.httpcache.HttpCacheMiddleware` now
    downloads it only once, and, if the response is cached, serves it from the
    cache to the other requests.
    The new :stat:`httpcache/wait` stat counts the requests that waited for
    another one.
    (:gh:`2744`, :gh:`7915`)

-   ``XMLFeedSpider.parse_node()``, ``CSVFeedSpider.parse_row()`` and the
    *errback* of :class:`~scrapy.spiders.Rule` can now be defined as coroutine
    functions (``async def``) or asynchronous generator functions.
    (:gh:`8392`)

-   ``item_completed()`` in subclasses of ``MediaPipeline`` can now be defined
    as a coroutine function (``async def``), and ``stat_file()`` in
    :ref:`custom media storages <media-pipeline-custom-storage>` can now await
    :mod:`asyncio` code.
    (:gh:`8413`)

-   :meth:`BaseSettings.getlist() <scrapy.settings.BaseSettings.getlist>` now
    parses a string that is a JSON list, e.g. ``-s 'MY_LIST=["a,b", "c"]'``, so
    that items that contain commas can be set from the command line.
    (:gh:`8416`)

-   Added a :setting:`RESPONSE_ROUGH_SIZE` setting, the
    :attr:`ExecutionEngine.response_active_size
    <scrapy.core.engine.ExecutionEngine.response_active_size>` attribute, and
    the :stat:`request_backout_seconds/concurrency`,
    :stat:`request_backout_seconds/response_max_active_size` and
    :stat:`request_backout_seconds/total` stats. See
    :ref:`crawl-bottlenecks`.
    (:gh:`5302`, :gh:`6206`, :gh:`6430`)

Improvements
~~~~~~~~~~~~

-   The encoding of a response that doesn't declare one is now detected the
    way web browsers do: UTF-8 if the body is valid UTF-8, otherwise a guess
    based on the body and on the top-level domain of the response URL, as
    Firefox does. Encoding declarations in ``<meta>`` tags are also found the
    way web browsers find them, and declared encoding names are mapped to
    encodings the way web browsers map them, e.g. ``gb2312`` to GBK instead of
    GB18030.
    (:gh:`8393`)

-   With parsel_ 1.12.0+, :class:`~scrapy.Selector` objects created from a
    UTF-8 response now parse the response body as is, instead of decoding it
    first, which saves time and memory.
    (:gh:`5906`, :gh:`8195`, :gh:`8222`, :gh:`8393`)

-   Responses are now freed as soon as nothing refers to them, also after
    using their selector or after their callback raises an exception, instead
    of when the garbage collector runs, which lowers peak memory usage.
    (:gh:`2977`, :gh:`8245`)

-   The reactor settings :setting:`DNSCACHE_ENABLED`, :setting:`DNSCACHE_SIZE`,
    :setting:`DNS_TIMEOUT`, :setting:`REACTOR_THREADPOOL_MAXSIZE` and
    :setting:`TWISTED_DNS_RESOLVER` can now be :ref:`set from a spider
    <spider-settings>` when using :class:`~scrapy.crawler.CrawlerProcess` or
    :class:`~scrapy.crawler.AsyncCrawlerProcess`. When :ref:`running multiple
    spiders in the same process <run-multiple-spiders>`, the values of the
    first spider are used, and a warning is issued for any later spider that
    defines a different value. The DNS resolver now gets the
    :class:`~scrapy.crawler.Crawler` of that first spider in its
    ``from_crawler()`` method.
    (:gh:`5988`, :gh:`7923`)

-   The :command:`runspider` command now accepts file paths without an
    extension, such as the ones of Bash process substitution
    (``scrapy runspider <(…)``).
    (:gh:`4827`, :gh:`8036`)

-   Items are now processed by tasks started on demand, instead of by a fixed
    number of tasks, one per :setting:`CONCURRENT_ITEMS`, started for every
    response, so a high :setting:`CONCURRENT_ITEMS` value no longer slows down
    crawls. :setting:`CONCURRENT_ITEMS` values lower than ``1`` now work as
    ``1``.
    (:gh:`5182`, :gh:`7959`)

-   Exceptions raised while exporting an item to a :ref:`feed
    <topics-feed-exports>` now include the item in a note.
    (:gh:`2775`, :gh:`8191`)

-   When a :class:`~scrapy.http.TextResponse` is created with a :class:`str`
    body and a UTF-8 encoding, that body is now reused as
    :attr:`~scrapy.http.TextResponse.text` instead of being decoded again.
    (:gh:`8220`)

-   Improved the performance of link extraction with
    :class:`~scrapy.linkextractors.lxmlhtml.LxmlLinkExtractor`.
    (:gh:`8126`)

-   Compressed response bodies of 8 KiB or more are now decompressed in a
    thread, so that other responses can be processed meanwhile.
    (:gh:`3751`, :gh:`8153`)

-   The Scrapy version and the versions of :setting:`LOG_VERSIONS` are now
    logged when each crawler is set up, after :ref:`add-ons <topics-addons>`
    and spider settings are applied, so that they can change
    :setting:`BOT_NAME` and :setting:`LOG_VERSIONS`. They are now also logged
    when using :class:`~scrapy.crawler.CrawlerRunner` or
    :class:`~scrapy.crawler.AsyncCrawlerRunner`. Add-ons can now :ref:`log
    the versions of their dependencies <topics-addons>`.
    (:gh:`8246`)

-   ``scrapy.pipelines.files.S3FilesStore`` now supports any header that
    botocore_ supports for uploads, and :ref:`media pipelines
    <topics-media-pipeline>` now document how to set custom headers for files
    uploaded to Amazon S3.
    (:gh:`4788`, :gh:`4813`, :gh:`8171`)

-   :class:`~scrapy.core.downloader.handlers.http2.H2DownloadHandler` now
    sends the ``Content-Length`` request header that you set, instead of
    replacing it, with a warning, with one built from the request body.
    (:gh:`4919`, :gh:`7944`)

-   :class:`~scrapy.core.downloader.handlers.http2.H2DownloadHandler` now
    supports :setting:`DOWNLOAD_FAIL_ON_DATALOSS` and the
    :reqmeta:`download_fail_on_dataloss` request meta key: when the setting or
    meta key is ``False``, responses cut short by a lost connection are now
    returned with the ``dataloss`` flag; otherwise, they now fail with
    :exc:`~scrapy.exceptions.ResponseDataLossError` instead of
    :exc:`~scrapy.exceptions.DownloadFailedError`. HTTP/2 data loss is now also
    detected by
    :class:`~scrapy.core.downloader.handlers._httpx.HttpxDownloadHandler`.
    (:gh:`5048`, :gh:`7989`)

-   Spiders that request the :file:`robots.txt` file of a host, like
    :class:`~scrapy.spiders.SitemapSpider`, no longer download it twice when
    :setting:`ROBOTSTXT_OBEY` is ``True``:
    :class:`~scrapy.downloadermiddlewares.robotstxt.RobotsTxtMiddleware` now
    parses the response of a request for the :file:`robots.txt` file of a
    host, if it has not downloaded it yet, instead of downloading it again.
    (:gh:`3967`, :gh:`8069`)

-   Requests that set the :reqmeta:`download_maxsize` request meta key but not
    :reqmeta:`download_warnsize` no longer log a warning based on
    :setting:`DOWNLOAD_WARNSIZE`.
    (:gh:`8213`)

-   :class:`~scrapy.core.downloader.handlers._aiohttp.AiohttpDownloadHandler`
    is now :ref:`lazy <lazy-download-handlers>`.
    (:gh:`8346`)

-   Connecting a handler to a built-in signal, where the handler declares an
    argument which the signal never sends, e.g. because of a typo, now issues a
    warning.
    (:gh:`8345`)

-   :func:`~scrapy.utils.asyncio.call_later` and the processing of the output
    of spider callbacks now run in the :mod:`contextvars` context that was
    current when they were scheduled also when not using the asyncio reactor,
    so that context variables set by your code, e.g. for tracing or logging,
    are kept.
    (:gh:`8347`)

-   Improved the performance of ``scrapy.utils.python.binary_is_text()``,
    which is used to pick the class of responses.
    (:gh:`8362`)

-   :class:`~scrapy.downloadermiddlewares.cookies.CookiesMiddleware` now
    ignores received cookies with a ``__Secure-`` or ``__Host-`` name prefix
    that do not meet the requirements of that prefix, as web browsers do, e.g.
    such cookies received over plain HTTP.
    (:gh:`5431`, :gh:`8431`)

-   Improved the performance of :ref:`feed exports <topics-feed-exports>`,
    especially for items with scalar field values.
    (:gh:`8461`)

-   Improved the performance of :class:`~scrapy.statscollectors.StatsCollector`
    method calls.
    (:gh:`8243`)

-   Other code refactoring and improvements.
    (:gh:`8262`, :gh:`8263`, :gh:`8295`, :gh:`8313`, :gh:`8323`, :gh:`8335`,
    :gh:`8353`, :gh:`8365`, :gh:`8385`, :gh:`8391`, :gh:`8415`)

Bug fixes
~~~~~~~~~

-   :class:`~scrapy.core.downloader.handlers.ftp.FTPDownloadHandler` now raises
    :exc:`~scrapy.exceptions.DownloadFailedError` when the server drops the
    connection, so that those downloads are retried.
    (:gh:`1511`, :gh:`8206`)

-   :class:`~scrapy.pipelines.files.FilesPipeline` now treats responses with
    the 201 status code as successful downloads.
    (:gh:`8349`)

-   The ``Cookie`` header now lists cookies with the same path length from
    oldest to newest, as :rfc:`6265#section-5.4` requires.
    (:gh:`5431`, :gh:`8321`)

-   The :command:`runspider` command now runs the given file even if its name
    matches that of an already imported module, e.g. :file:`json.py`.
    (:gh:`8036`, :gh:`8463`)

-   The :command:`check` command now reports errors that prevent a spider
    from crawling, e.g. errors raised while creating the spider, instead of
    silently ignoring them.
    (:gh:`3716`, :gh:`7991`)

-   :meth:`Request.from_curl() <scrapy.Request.from_curl>` now handles
    headers without a value (``-H 'Name;'``) as curl does, ignores headers
    that curl would not send, supports ``-u`` with a user name and no
    password, and raises :exc:`ValueError` for an empty command, instead of
    failing with unexpected exceptions. It also turns ``-H 'Name:'`` into a
    header set to ``None``, i.e. not sent, instead of a header with an empty
    value, accepts Bash ``$'…'`` quoting in any argument, e.g. headers,
    although it does not decode backslash escapes, and keeps a leading ``$`` in
    request data instead of removing it.

    :meth:`Request.to_curl() <scrapy.Request.to_curl>` now includes every
    value of repeated headers, handles headers set to ``None`` and no longer
    fails on headers that are not valid UTF-8.

    (:gh:`8131`, :gh:`8138`, :gh:`8148`, :gh:`8267`, :gh:`8291`, :gh:`8292`)

-   ``Headers.to_tuple_list()`` no longer raises :exc:`UnicodeDecodeError`;
    bytes that cannot be decoded are replaced with U+FFFD.
    (:gh:`2592`, :gh:`2637`, :gh:`8192`)

-   :func:`copy.copy` on an :class:`~scrapy.Item` now returns a shallow copy,
    like :meth:`Item.copy() <scrapy.Item.copy>`. It used to return an item
    that shared its fields with the original, so that setting or deleting a
    field on one also did it on the other.
    (:gh:`8172`)

-   Calling ``exit()`` or ``quit()`` in the :ref:`telnet console
    <topics-telnetconsole>` now closes the connection, instead of logging an
    unhandled error.
    (:gh:`3853`, :gh:`8065`)

-   An exception raised while building the :setting:`SCHEDULER` is now
    reported as is, instead of being followed by a
    :exc:`RuntimeError` about an unassigned engine slot.
    (:gh:`8169`)

-   The ``lastseen`` field of the representation of a downloader slot, e.g.
    in the :ref:`telnet console <topics-telnetconsole>`, now shows the
    monotonic timestamp of the last activity instead of a meaningless date.
    (:gh:`8182`)

-   :class:`~scrapy.spiders.SitemapSpider` now resolves relative and
    protocol-relative URLs in sitemaps against the sitemap URL.
    (:gh:`965`, :gh:`8210`)

-   :class:`~scrapy.spiders.CrawlSpider` now follows the links of a response
    also when the callback of the matching rule raises an exception.
    (:gh:`4108`, :gh:`8200`)

-   A :ref:`feed <topics-feed-exports>` URI with a placeholder that is neither
    a spider attribute nor returned by the ``uri_params`` function now makes
    only that feed be skipped, with an error logged, instead of raising
    :exc:`KeyError` and leaving the remaining feeds unopened.
    (:gh:`2089`, :gh:`8205`)

-   Fixed the file modification times that
    :class:`~scrapy.pipelines.files.FilesPipeline` reads from Amazon S3, Google
    Cloud Storage and FTP storages to apply :setting:`FILES_EXPIRES`. S3 and
    Google Cloud Storage times were off by the UTC offset of the local time
    zone, and FTP times were misread.
    (:gh:`8186`, :gh:`8196`)

-   Lines of a callback docstring that start with ``@`` but do not name a
    registered :ref:`contract <topics-contracts>`, e.g. a decorator in a code
    example, are now ignored, instead of raising :exc:`KeyError` or making the
    :command:`check` command treat the callback as having contracts. As a
    result, a misspelled contract name is also ignored.
    (:gh:`8226`)

-   The :command:`bench` command now listens on a random free port, instead of
    failing when port 8998 is in use.
    (:gh:`8230`)

-   :setting:`CONCURRENT_REQUESTS_PER_DOMAIN` and the ``concurrency`` key of
    :setting:`DOWNLOAD_SLOTS` are now enforced when using asyncio with no
    download delay.
    (:gh:`8256`, :gh:`8257`)

-   :class:`~scrapy.spiders.SitemapSpider` now detects XML sitemaps also in
    responses that are not :class:`~scrapy.http.XmlResponse` objects, e.g.
    from third-party download handlers, based on their headers, URL and body.
    (:gh:`6362`, :gh:`7904`)

-   Fixed the handling of headers that are not valid UTF-8 or ASCII in some
    download handlers:

    - :class:`~scrapy.core.downloader.handlers._httpx.HttpxDownloadHandler`
      no longer fails on non-ASCII request headers.

    - :class:`~scrapy.core.downloader.handlers._aiohttp.AiohttpDownloadHandler`
      no longer fails on request or response headers that are not valid
      UTF-8. Invalid UTF-8 in request headers is sent as U+FFFD, with a
      warning.

    - :class:`~scrapy.core.downloader.handlers.http2.H2DownloadHandler` no
      longer fails, or hangs, on request or response headers that are not
      valid UTF-8.

    (:gh:`8265`)

-   ``Headers.get()`` now returns the given default value for a header set to
    ``None``.
    (:gh:`8268`)

-   Fixed the ``downloader/request_bytes`` and ``downloader/response_bytes``
    stats, which miscounted line breaks for requests with all headers set to
    ``None`` and for responses with multi-value headers, and
    ``scrapy.utils.request.request_httprepr()``, which added an extra line
    break for requests with all headers set to ``None``.
    (:gh:`8266`, :gh:`8271`)

-   Changing the header values in the output of :meth:`Request.to_dict()
    <scrapy.Request.to_dict>` or :meth:`Response.to_dict()
    <scrapy.http.Response.to_dict>` no longer changes the original request or
    response.
    (:gh:`8269`)

-   :class:`~scrapy.core.downloader.handlers.http11.HTTP11DownloadHandler` now
    closes the proxy connection of an HTTPS request that times out, or is
    otherwise cancelled, before the proxy has established the tunnel.
    (:gh:`3614`, :gh:`7810`)

-   :class:`~scrapy.downloadermiddlewares.redirect.RedirectMiddleware` no
    longer copies the fragment of the original URL into the redirect URL when
    the ``Location`` header ends with an empty fragment (``#``).
    (:gh:`8100`)

-   When using a :ref:`job directory <job-dir>`, the default scheduler now pops
    requests by :attr:`~scrapy.Request.priority` across its memory and disk
    queues, instead of popping every request from the memory queue before any
    from the disk queue.

    Custom :setting:`SCHEDULER_PRIORITY_QUEUE` classes need to implement the
    new :meth:`~scrapy.pqueues.PriorityQueueProtocol.next_priority` method to
    get this behavior. :class:`~scrapy.pqueues.PriorityQueueProtocol`
    documents the interface of priority queue classes.
    (:gh:`3666`, :gh:`8237`)

-   When resuming a crawl from a :ref:`job directory <job-dir>`, feeds whose
    URI uses ``%(batch_id)d`` now continue the batch numbering of the previous
    run, instead of starting from 1 again and overwriting the existing files.
    (:gh:`5153`, :gh:`7650`, :gh:`7656`)

-   :ref:`Item exporters <topics-exporters>` now serialize nested items, and
    lists of them, using the serializers declared in their own fields.
    (:gh:`3888`, :gh:`3890`, :gh:`8057`)

-   Fixed :class:`~scrapy.utils.asyncio.AsyncioLoopingCall` sometimes calling
    its function twice in a row when the event loop woke it up slightly early,
    which could, for example, close a spider because of
    :setting:`CLOSESPIDER_TIMEOUT_NO_ITEM` while it was still producing items.
    (:gh:`8294`)

-   The :ref:`RobotFileParser <python-robotfileparser>` parser now ignores
    the invalid bytes of a :file:`robots.txt` file that is not valid UTF-8,
    like the other built-in parsers, instead of ignoring the whole file.
    (:gh:`8316`)

-   Exceptions raised while handling the output of a spider callback, e.g.
    by a custom scheduler or log formatter, are now logged, and no longer
    interfere with the handling of the rest of that output.
    (:gh:`8318`)

-   Scrapy now uses the event loop of the installed asyncio reactor when no
    event loop is running, instead of the current event loop of the thread,
    which can be a different one or none at all, e.g. when the reactor was
    installed with a loop that is not set as the current one.
    (:gh:`7201`, :gh:`8324`, :gh:`8325`)

-   Stopping a crawl while an item yielded from :meth:`~scrapy.Spider.start` is
    going through the :ref:`item pipelines <topics-item-pipeline>` no longer
    hangs.
    (:gh:`8348`)

-   :class:`~scrapy.core.downloader.handlers.http2.H2DownloadHandler` now
    fails requests with the connection error when it cannot connect to the
    server, instead of letting them hit the download timeout, and later
    requests to the same server try to connect again.
    (:gh:`8332`)

-   Fixed :class:`~scrapy.pqueues.ScrapyPriorityQueue`, which the default
    :class:`~scrapy.pqueues.DownloaderAwarePriorityQueue` uses for each
    download slot, returning no request or a request other than the one that
    its ``peek()`` method returned, which could happen with requests of the
    same priority in its start request and regular request queues, or after a
    request failed to be serialized into a disk queue.
    (:gh:`7837`)

-   The :ref:`telnet console <topics-telnetconsole>`, and any other caller of
    ``scrapy.utils.reactor.listen_tcp()``, now tries the next port when another
    process starts listening on the same port at the same time, instead of
    failing to start.
    (:gh:`8356`)

-   Fixed :class:`~scrapy.downloadermiddlewares.robotstxt.RobotsTxtMiddleware`
    letting through requests disallowed by :file:`robots.txt` when they were
    sent while the :file:`robots.txt` file of their website was being
    downloaded for another request.
    (:gh:`8297`, :gh:`8386`)

-   :class:`~scrapy.spiders.SitemapSpider` now only treats links with
    ``rel="alternate"`` as alternate links, instead of any link, e.g.
    canonical ones, both when
    :attr:`~scrapy.spiders.SitemapSpider.sitemap_alternate_links` is enabled
    and in the entries passed to
    :meth:`~scrapy.spiders.SitemapSpider.sitemap_filter`.
    (:gh:`8390`)

-   Download handlers are now closed when the engine is closed without having
    been started, e.g. when opening the spider fails, and the downloader is now
    closed when the engine is stopped without a spider.
    (:gh:`8167`, :gh:`8377`)

-   The spider is no longer considered idle, and so no longer closed, while a
    request taken from the scheduler has not reached the downloader yet, which
    could happen with a custom :setting:`DOWNLOADER`.
    (:gh:`8315`, :gh:`8355`)

-   The reactorless :command:`shell` now waits for the engine to start before
    letting you use it.
    (:gh:`8168`)

-   On Windows,
    :class:`~scrapy.core.downloader.handlers._aiohttp.AiohttpDownloadHandler`
    no longer connects to the wrong port in rare cases.
    (:gh:`8382`)

-   The Scrapy :command:`shell` no longer uses ptpython_ on Windows when the
    standard output is not a console, which ptpython_ does not support.
    (:gh:`8367`)

Documentation
~~~~~~~~~~~~~

-   Documented :ref:`how blocking code in callbacks and other components
    slows down downloads <optimize-blocking>` and inflates their
    :reqmeta:`download_latency`.
    (:gh:`3197`, :gh:`8160`)

-   Documented :ref:`how to change concurrency and delays from the telnet
    console <telnet-concurrency>` on a running crawl.
    (:gh:`4196`, :gh:`8164`)

-   Documented that the ``open_spider()`` and ``close_spider()`` methods of
    :ref:`item pipelines <topics-item-pipeline>` run concurrently, and only
    ``process_item()`` follows the :setting:`ITEM_PIPELINES` order.
    (:gh:`2645`, :gh:`8158`)

-   Documented :ref:`how to set up a development environment <dev-setup>` to
    contribute to Scrapy.
    (:gh:`4451`, :gh:`8165`)

-   Moved the release notes of Scrapy 2.13 and older into separate pages per
    major version.
    (:gh:`8150`)

-   Documented :ref:`how to extract clean content and parse values
    <extraction>`, :ref:`how to sign requests with OAuth <mw-oauth>`, how to
    deduplicate repeated query string parameters in :ref:`request fingerprints
    <custom-request-fingerprinter>`, and that retried status codes should also
    be in :setting:`HTTPCACHE_IGNORE_HTTP_CODES`.
    (:gh:`40`, :gh:`1113`, :gh:`2297`, :gh:`8190`, :gh:`8202`, :gh:`8208`,
    :gh:`8209`)

-   Improved the API reference of :class:`~scrapy.spiders.SitemapSpider`,
    :class:`~scrapy.spiders.XMLFeedSpider` and
    :class:`~scrapy.spiders.CSVFeedSpider`.
    (:gh:`8229`, :gh:`8239`)

-   Documented the order of the :signal:`spider_opened`,
    :signal:`engine_started`, :signal:`spider_closed` and
    :signal:`engine_stopped` signals.
    (:gh:`1523`, :gh:`8101`)

-   Documented that the :setting:`JOBDIR` and :setting:`HTTPCACHE_DIR`
    directories must be protected from :ref:`write access by untrusted
    parties <security-local-data>`.
    (:gh:`8252`)

-   Documented :ref:`how to write custom feed storage backends
    <topics-feed-storage-custom>` and the :ref:`built-in feed storage backend
    classes <feed-storage-classes>`.
    (:gh:`7800`)

-   Added an introduction video to the :ref:`page about coding agents
    <agents>`.
    (:gh:`8253`)

-   :class:`~scrapy.spiders.CrawlSpider` and :class:`~scrapy.spiders.Rule` are
    now documented through their docstrings, and the documentation now
    recommends :class:`~scrapy.Spider` over
    :class:`~scrapy.spiders.CrawlSpider` for crawls that do not fit its
    declarative rules.
    (:gh:`7025`, :gh:`8240`)

-   Documented the
    :meth:`~scrapy.core.engine.ExecutionEngine.open_spider_async`,
    :meth:`~scrapy.core.engine.ExecutionEngine.start_async`,
    :meth:`~scrapy.core.engine.ExecutionEngine.close_spider_async` and
    :meth:`~scrapy.core.engine.ExecutionEngine.stop_async` methods of the
    execution engine.
    (:gh:`6164`, :gh:`8462`)

-   Documented :ref:`how to write asyncio code that also supports older Scrapy
    versions <asyncio-old-versions>`, and the documentation now recommends
    :func:`asyncio.to_thread` to call blocking code from :ref:`coroutines
    <topics-coroutines>`.
    (:gh:`7956`, :gh:`8454`)

-   Reviewed the documentation of :class:`~scrapy.Spider`, which now covers
    all its attributes, including :attr:`~scrapy.Spider.state`.
    (:gh:`7025`, :gh:`7811`)

-   Updated the :ref:`installation guide <intro-install>`, and documented
    :ref:`what to do when installing a dependency fails <install-no-wheel>`.
    (:gh:`5308`, :gh:`7878`)

-   The :ref:`tutorial <intro-tutorial>` now shows how to crawl
    ``quotes.toscrape.com`` faster with :setting:`DOWNLOAD_SLOTS`.
    (:gh:`8334`)

-   Documented :exc:`~scrapy.spidermiddlewares.httperror.HttpError`, the
    IPv6 support of the built-in :ref:`download handlers
    <topics-download-handlers>`, the ``bootstrap_failed`` attribute of crawler
    processes, and where exceptions that interrupt a crawl started from a
    :ref:`script <run-from-script>` reach your code.
    (:gh:`8338`, :gh:`8340`, :gh:`8344`)

-   Added a :ref:`page about getting help <getting-help>`.
    (:gh:`3688`)

-   Documented that high values of :setting:`CONCURRENT_REQUESTS` may exceed
    the limit of open file descriptors that the operating system sets, and how
    to raise that limit.
    (:gh:`5259`, :gh:`5272`)

-   Other documentation improvements and fixes.
    (:gh:`5859`, :gh:`7114`, :gh:`8151`, :gh:`8161`, :gh:`8314`, :gh:`8403`,
    :gh:`8404`, :gh:`8436`, :gh:`8453`)

Quality assurance
~~~~~~~~~~~~~~~~~

-   Improved and fixed type hints.
    (:gh:`7811`, :gh:`8078`, :gh:`8183`, :gh:`8311`, :gh:`8333`, :gh:`8440`)

-   Improved CodSpeed benchmarks.
    (:gh:`8227`, :gh:`8234`, :gh:`8456`)

-   Improved the documentation build and the contributor tooling, including
    an ``AGENTS.md`` file for coding agents.
    (:gh:`8011`, :gh:`8154`, :gh:`8157`, :gh:`8188`, :gh:`8212`, :gh:`8214`,
    :gh:`8216`, :gh:`8219`, :gh:`8238`, :gh:`8251`, :gh:`8364`, :gh:`8384`,
    :gh:`8409`, :gh:`8411`)

-   CI and test improvements and fixes.
    (:gh:`6141`, :gh:`7949`, :gh:`8127`, :gh:`8155`, :gh:`8156`, :gh:`8194`,
    :gh:`8223`, :gh:`8228`, :gh:`8231`, :gh:`8232`, :gh:`8233`, :gh:`8235`,
    :gh:`8236`, :gh:`8258`, :gh:`8273`, :gh:`8274`, :gh:`8275`, :gh:`8276`,
    :gh:`8277`, :gh:`8278`, :gh:`8279`, :gh:`8280`, :gh:`8281`, :gh:`8286`,
    :gh:`8300`, :gh:`8301`, :gh:`8311`, :gh:`8314`, :gh:`8317`, :gh:`8320`,
    :gh:`8351`, :gh:`8359`, :gh:`8360`, :gh:`8361`, :gh:`8372`, :gh:`8374`,
    :gh:`8375`, :gh:`8381`, :gh:`8387`, :gh:`8388`, :gh:`8389`, :gh:`8406`,
    :gh:`8412`, :gh:`8423`, :gh:`8444`)

.. _release-2.19.0:

Scrapy 2.19.0 (2026-09-10)
--------------------------

Highlights:

-   New ``RemoteControl`` extension which allows inspecting and controlling a
    running crawl over HTTP, used by the :ref:`Scrapy MCP server
    <using-mcp-server>`

-   Experimental ``aiohttp``-based download handler (now the default when
    running without a reactor)

Modified requirements
~~~~~~~~~~~~~~~~~~~~~

-   Added support for Python 3.15.
    (:gh:`7511`)

-   New dependencies:

    - aiohttp_ >= 3.13.3

    - charset-normalizer_ >= 3.4.0

    - platformdirs_ >= 2.0.0

    (:gh:`7866`, :gh:`8054`)

Backward-incompatible changes
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

-   When running :ref:`without a Twisted reactor <asyncio-without-reactor>`,
    i.e. with :setting:`TWISTED_REACTOR_ENABLED` set to ``False``, the default
    download handler for ``http`` and ``https`` is now
    :class:`~scrapy.core.downloader.handlers._aiohttp.AiohttpDownloadHandler`
    instead of
    :class:`~scrapy.core.downloader.handlers._httpx.HttpxDownloadHandler`. You
    can configure
    :class:`~scrapy.core.downloader.handlers._httpx.HttpxDownloadHandler` in
    the :setting:`DOWNLOAD_HANDLERS` setting if you want.
    (:gh:`8118`)

-   ``scrapy.http.cookies.WrappedRequest.is_unverifiable()`` now always returns
    ``False``, and the undocumented ``is_unverifiable`` request meta key that
    it used to read is ignored.
    (:gh:`7933`)

Deprecations
~~~~~~~~~~~~

-   The ``RANDOMIZE_DOWNLOAD_DELAY`` setting is deprecated. Use the new
    :setting:`DOWNLOAD_DELAY_JITTER` setting instead. Similarly, the
    ``randomize_delay`` key of the :setting:`DOWNLOAD_SLOTS` setting is
    deprecated in favor of a new ``jitter`` key, the ``randomize_delay``
    attribute of :class:`scrapy.core.downloader.Slot` is deprecated in favor of
    its new ``jitter`` attribute, and the ``randomize_delay`` attribute
    of :class:`scrapy.core.downloader.Downloader` is deprecated in favor of the
    :setting:`DOWNLOAD_DELAY_JITTER` setting.
    (:gh:`7881`)

-   The ``install_root_handler`` parameter of
    :func:`~scrapy.utils.log.configure_logging`,
    :class:`~scrapy.crawler.CrawlerProcess` and
    :class:`~scrapy.crawler.AsyncCrawlerProcess` is deprecated. Use the new
    :setting:`LOG_INSTALL_ROOT_HANDLER` setting instead.
    (:gh:`4793`, :gh:`8041`)

-   The ``scrapy.dupefilters.RFPDupeFilter.fingerprints`` attribute is
    deprecated. Overriding
    :meth:`scrapy.dupefilters.RFPDupeFilter.request_fingerprint` is deprecated
    as well; set the :setting:`REQUEST_FINGERPRINTER_CLASS` setting instead.
    (:gh:`5517`, :gh:`7943`)

-   Overriding the ``add_pre_hook()`` or ``add_post_hook()`` methods of
    :class:`~scrapy.contracts.Contract` is deprecated. Define
    ``pre_process()`` or ``post_process()`` instead.
    (:gh:`6681`, :gh:`7886`)

New features
~~~~~~~~~~~~

-   Added a :class:`~scrapy.extensions.remote_control.RemoteControl`
    extension, enabled by default, which allows connecting to crawl processes
    via HTTP and running code inside them.
    (:gh:`7866`)

-   Added an experimental HTTP download handler based on aiohttp_,
    :class:`~scrapy.core.downloader.handlers._aiohttp.AiohttpDownloadHandler`.
    (:gh:`8118`)

-   Added SQLite-backed scheduler queues:
    :class:`~scrapy.squeues.PickleFifoSQLiteQueue`,
    :class:`~scrapy.squeues.PickleLifoSQLiteQueue`,
    :class:`~scrapy.squeues.MarshalFifoSQLiteQueue` and
    :class:`~scrapy.squeues.MarshalLifoSQLiteQueue`. They write each request
    within its own transaction, so that an unclean shutdown cannot corrupt the
    on-disk queue, at the cost of slower scheduling.
    (:gh:`845`, :gh:`7877`)

-   Added a :setting:`DOWNLOAD_DELAY_JITTER` setting, and a ``jitter`` key for
    :setting:`DOWNLOAD_SLOTS`, which set the magnitude of the random variation
    applied to :setting:`DOWNLOAD_DELAY`. They replace the
    ``RANDOMIZE_DOWNLOAD_DELAY`` setting and the ``randomize_delay`` key, which
    could only toggle a fixed ±50%.
    (:gh:`7881`)

-   Added a :setting:`LOG_COLOR` setting, which colorizes log output by log
    level when logging to a terminal. It needs the new :ref:`color <extras>`
    extra.
    (:gh:`8091`)

-   The encoding of a response that doesn't declare one is now detected with
    charset-normalizer_ when the response body is neither ASCII nor UTF-8,
    instead of always falling back to ``cp1252``.
    (:gh:`3135`, :gh:`8054`)

-   Added a :setting:`LOG_INSTALL_ROOT_HANDLER` setting, which replaces the
    deprecated ``install_root_handler`` parameter and, unlike it, can also be
    set from a :file:`settings.py` module or from the command line.
    (:gh:`4793`, :gh:`8041`)

-   :ref:`Contracts <topics-contracts>` now support callbacks defined with
    ``async def``, including asynchronous generators.
    (:gh:`6681`, :gh:`7886`)

-   Added the :class:`~scrapy.contracts.default.MethodContract` (``@method``),
    :class:`~scrapy.contracts.default.BodyContract` (``@body``),
    :class:`~scrapy.contracts.default.HeaderContract` (``@header``) and
    :class:`~scrapy.contracts.default.CookieContract` (``@cookie``)
    contracts, which set the corresponding attributes of the sample request,
    and an ``-a`` option for the :command:`check` command, to set spider
    arguments as in the :command:`crawl` command.
    (:gh:`1918`, :gh:`8053`)

-   Added :meth:`Response.to_dict() <scrapy.http.Response.to_dict>`,
    :meth:`Response.from_dict() <scrapy.http.Response.from_dict>` and
    :func:`~scrapy.utils.response.response_from_dict`, and used them in the
    built-in :ref:`HTTP cache storages <httpcache-storage-fs>`, which now
    restore cached responses of any response class, including those of
    third-party plugins, with all their attributes.
    (:gh:`1450`, :gh:`7908`)

-   Cached responses now indicate when they were stored, through the new
    :reqmeta:`cache_timestamp` request meta key.
    (:gh:`2221`, :gh:`8034`)

-   The ``format`` key of :setting:`FEEDS` is now inferred from the file
    extension of the feed URI when not set, e.g. ``json`` for a URI ending in
    :file:`.json`.
    (:gh:`1158`, :gh:`8031`)

-   Added :func:`~scrapy.utils.project.find_projects`, which yields the root
    directory of every Scrapy project in a directory tree.
    (:gh:`8024`)

-   Added a public :attr:`~scrapy.core.engine.ExecutionEngine.scheduler`
    attribute to :class:`~scrapy.core.engine.ExecutionEngine`.
    (:gh:`8099`)

-   :class:`~scrapy.statscollectors.StatsCollector` objects now implement
    ``__str__()``, which returns the pretty-printed stats.
    (:gh:`2746`)

-   :func:`~scrapy.utils.response.open_in_browser` now also supports
    responses that are neither HTML nor plain text, picking a file extension
    based on the ``Content-Type`` header.
    (:gh:`3902`, :gh:`8067`)

-   The ``-t``/``--template`` option of the :command:`genspider` command now
    also takes a path to a :file:`.tmpl` file, so that a custom template can
    be used without setting :setting:`TEMPLATES_DIR`.
    (:gh:`8071`)

-   The ``--pdb`` command-line option now uses ipdb_ instead of :mod:`pdb`
    when ipdb_ is installed.
    (:gh:`4284`, :gh:`8052`)

-   Log records about item processing, i.e. about items scraped, dropped or
    raising an exception, now carry the item in their ``extra`` dict, under
    the ``item`` key, so that custom logging handlers can read it.
    (:gh:`8085`)

Improvements
~~~~~~~~~~~~

-   :class:`~scrapy.dupefilters.RFPDupeFilter` now keeps request fingerprints
    as :class:`bytes`, to reduce memory usage. The :file:`requests.seen` file
    that it writes in the :ref:`job directory <job-dir>` is now a binary file.
    (:gh:`5517`, :gh:`7943`)

-   The ``--pdb`` command-line option now starts a post-mortem debugging
    session on every logged error that comes with a traceback, instead of on
    every :class:`~twisted.python.failure.Failure` object built anywhere in
    the process.
    (:gh:`3552`, :gh:`8037`)

-   The Scrapy :command:`shell` no longer prints the ``DEBUG`` messages of
    parso_, an indirect dependency of IPython, when :setting:`LOG_LEVEL` is
    ``DEBUG``.
    (:gh:`8060`)

-   Other code refactoring and improvements.
    (:gh:`8123`)

Bug fixes
~~~~~~~~~

-   :class:`~scrapy.core.downloader.handlers.http11.HTTP11DownloadHandler`
    now sets :attr:`~scrapy.http.Response.certificate` and
    :attr:`~scrapy.http.Response.ip_address` attributes even for responses
    without a body.
    (:gh:`4466`, :gh:`8048`)

-   HTTP connection pool keys in
    :class:`~scrapy.core.downloader.handlers.http11.HTTP11DownloadHandler` and
    :class:`~scrapy.core.downloader.handlers.http2.H2DownloadHandler` now
    include the request bind address (see :setting:`DOWNLOAD_BIND_ADDRESS`), so
    that requests bound to different addresses no longer reuse each other's
    pooled connections.
    (:gh:`3565`, :gh:`8081`)

-   :class:`~scrapy.downloadermiddlewares.httpcache.HttpCacheMiddleware` now
    updates the headers of a cached response, and stores it again, when a
    revalidation request gets a 304 response.
    (:gh:`3778`, :gh:`8068`)

-   An exception raised in a spider callback that no
    :meth:`~scrapy.spidermiddlewares.SpiderMiddleware.process_spider_exception`
    method handles is now offered to each of those methods only once.
    (:gh:`4729`, :gh:`7996`)

-   Defining :attr:`~scrapy.Spider.allowed_domains` as a property no longer
    breaks the commands that match a URL to a spider, i.e. :command:`shell`,
    :command:`fetch` and :command:`parse`. A property cannot be evaluated on
    a spider class, so it is now ignored, with a warning, instead of raising
    :exc:`TypeError`.
    (:gh:`3119`, :gh:`8094`)

-   :func:`~scrapy.utils.project.get_project_settings` now adds the project
    directory to :data:`sys.path` also when the ``SCRAPY_SETTINGS_MODULE``
    environment variable is set, so that the settings module that the variable
    points to can be imported.
    (:gh:`4780`, :gh:`8042`)

-   :class:`scrapy.utils.datatypes.LocalCache` no longer evicts the oldest item
    when updating an existing one.
    (:gh:`8113`)

Documentation
~~~~~~~~~~~~~

-   Added a page :ref:`about using Scrapy with coding agents <agents>`,
    covering the official agent plugin and the Scrapy MCP server.
    (:gh:`8120`)

-   Documented the request metadata keys that were missing from the
    :ref:`list of special keys <topics-request-meta>`, and documented that keys
    whose name starts with an underscore are internal.
    (:gh:`3585`, :gh:`5564`, :gh:`7933`)

-   Documented :ref:`how to write custom Scrapy commands <custom-commands>`,
    :ref:`how to write custom spider templates <spider-templates>`, :ref:`how
    to access the response of a failed media download
    <media-pipeline-failed-downloads>` and :ref:`how to set request headers
    for media pipeline requests <media-request-headers>`.
    (:gh:`2046`,
    :gh:`2504`,
    :gh:`3056`,
    :gh:`6844`,
    :gh:`6904`,
    :gh:`8049`,
    :gh:`8056`,
    :gh:`8063`)

-   Documented how to subclass
    :class:`~scrapy.downloadermiddlewares.redirect.RedirectMiddleware` to
    allow or deny redirects based on the target URL, and how to set the
    priority of the requests that :class:`~scrapy.spiders.CrawlSpider`
    generates from its rules.
    (:gh:`3613`, :gh:`4009`, :gh:`8061`, :gh:`8070`)

-   Documented that :func:`~scrapy.utils.project.get_project_settings`
    returns project settings only, that spiders :ref:`running concurrently in
    the same process <run-multiple-spiders>` get independent crawlers,
    middlewares and settings, and that Scrapy sets the ``request`` attribute
    of the :class:`~twisted.python.failure.Failure` objects that it passes to
    errbacks.
    (:gh:`2378`,
    :gh:`4253`,
    :gh:`6408`,
    :gh:`7901`,
    :gh:`8051`,
    :gh:`8055`)

-   Documented :class:`~scrapy.commands.ScrapyCommand` and
    :class:`~scrapy.statscollectors.StatsCollector`.
    (:gh:`6844`, :gh:`6904`, :gh:`8072`)

-   Improved the contents of ``llms-full.txt`` and Markdown versions of
    documentation pages.
    (:gh:`8083`,
    :gh:`8087`,
    :gh:`8088`,
    :gh:`8089`,
    :gh:`8117`,
    :gh:`8119`)

Quality assurance
~~~~~~~~~~~~~~~~~

-   Reached 100% test coverage.
    (:gh:`8021`)

-   Improved and fixed type hints.
    (:gh:`8017`, :gh:`8077`, :gh:`8102`)

-   Improved CodSpeed benchmarks.
    (:gh:`8030`, :gh:`8080`)

-   CI and test improvements and fixes.
    (:gh:`8027`,
    :gh:`8039`,
    :gh:`8059`,
    :gh:`8064`,
    :gh:`8073`,
    :gh:`8075`,
    :gh:`8076`,
    :gh:`8079`,
    :gh:`8092`,
    :gh:`8103`,
    :gh:`8115`)

.. _release-2.18.0:

Scrapy 2.18.0 (2026-08-20)
--------------------------

Highlights:

-   ``HttpxDownloadHandler`` now uses `httpx2 <https://httpx2.pydantic.dev/>`__

-   The Twisted-based HTTP/2 download handler is no longer experimental

-   ``brotli`` and Zstandard support are now always available, and :ref:`optional
    extras <extras>` cover the rest of the optional features

-   Late :class:`~scrapy.crawler.Crawler` attributes, such as
    :attr:`~scrapy.crawler.Crawler.stats`, now raise :exc:`RuntimeError`
    instead of being ``None`` before the crawl starts

-   Item exporters now export fields in declaration order

-   New :class:`~scrapy.spidermiddlewares.metacopy.MetaCopyDetectionMiddleware`

-   New :ref:`optimization <optimize>` page and :ref:`built-in stats reference
    <topics-stats-reference>`

Modified requirements
~~~~~~~~~~~~~~~~~~~~~

-   ``brotli`` (``brotlicffi`` on PyPy) and Zstandard support (the standard
    library :mod:`compression.zstd` module on Python 3.14 and higher, the
    ``backports.zstd`` package on earlier versions) are now required, so
    ``br`` and ``zstd`` are always included in the ``Accept-Encoding`` header
    of requests, and Brotli- and Zstandard-compressed responses are always
    decoded. Websites may now serve such responses to crawls that previously
    did not advertise support for them.

    The minimum required versions are ``brotli`` 1.2.0, ``brotlicffi``
    1.2.0.0 and ``backports.zstd`` 1.3.0.

    (:gh:`4698`, :gh:`6978`, :gh:`7083`, :gh:`7929`, :gh:`8009`)

-   Increased the minimum versions of the following dependencies:

    - cryptography_: 37.0.0 → 41.0.5

    - pyOpenSSL_: 22.0.0 → 24.3.0

    - queuelib_: 1.4.2 → 1.6.1

    - service_identity_: 23.1.0 → 24.2.0

    - w3lib_: 1.17.0 → 2.1.1

    (:gh:`7841`, :gh:`7874`, :gh:`7879`, :gh:`8001`)

-   The IPython :ref:`shell <topics-shell>` requires IPython 8.15.0 or higher.
    Install the :ref:`ipython extra <extras>` to get a compatible version.
    (:gh:`5447`, :gh:`7596`, :gh:`7816`)

Backward-incompatible changes
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

-   The following runtime usage of zope.interface_ interfaces is removed:

    - :class:`~scrapy.spiderloader.SpiderLoader` and
      :class:`~scrapy.spiderloader.DummySpiderLoader` are no longer marked
      as implementing the ``ISpiderLoader`` interface.

    - :func:`~scrapy.spiderloader.get_spider_loader` no longer checks that the
      configured spider loader implements the ``ISpiderLoader`` interface.

    - :class:`~scrapy.extensions.feedexport.BlockingFeedStorage`,
      :class:`~scrapy.extensions.feedexport.FileFeedStorage` and
      :class:`~scrapy.extensions.feedexport.StdoutFeedStorage` are no longer
      marked as implementing the ``IFeedStorage`` interface.

    - :class:`~scrapy.core.downloader.handlers.http2.H2DownloadHandler` no
      longer checks that the ``DOWNLOADER_CLIENTCONTEXTFACTORY`` class
      implements the ``IPolicyForHTTPS`` interface.

    (:gh:`6585`, :gh:`7731`)

-   The :attr:`~scrapy.crawler.Crawler.engine`,
    :attr:`~scrapy.crawler.Crawler.extensions`,
    :attr:`~scrapy.crawler.Crawler.logformatter`,
    :attr:`~scrapy.crawler.Crawler.request_fingerprinter` and
    :attr:`~scrapy.crawler.Crawler.stats` attributes of
    :class:`~scrapy.crawler.Crawler` raise :exc:`RuntimeError` when read before
    the crawl starts, instead of being ``None`` until then.

    Code that reads them from the :signal:`spider_opened` signal handler
    onwards is unaffected, and no longer needs to narrow their type. Code that
    checked whether they were set, e.g. ``if crawler.stats:``, must be updated,
    since reading them now raises instead of returning ``None``.

    (:gh:`6136`, :gh:`7882`)

-   :ref:`Item exporters <topics-exporters>` now export the fields of an item
    in declaration order, i.e. the order in which they are defined in the
    :ref:`item class <item-types>`, instead of the order in which they were
    populated, as :class:`~scrapy.exporters.CsvItemExporter` already did.
    :class:`dict` items, which have no declared fields, keep using the key
    order of each item.
    (:gh:`6662`, :gh:`6854`, :gh:`7824`)

-   ``scrapy.utils.serialize.ScrapyJSONEncoder``, used by :ref:`JSON feed
    exports <topics-feed-format-json>`, the :ref:`telnet console
    <topics-telnetconsole>` and the
    :class:`~scrapy.extensions.periodic_log.PeriodicLog` extension, now
    serializes :class:`~datetime.datetime`, :class:`~datetime.date` and
    :class:`~datetime.time` objects in ISO 8601 format, e.g.
    ``2023-08-03T23:24:57.148903+00:00`` instead of ``2023-08-03 23:24:57``,
    keeping microseconds and time zone information.

    Its ``DATE_FORMAT`` and ``TIME_FORMAT`` attributes are removed.

    (:gh:`2087`, :gh:`7918`)

-   ``scrapy.utils.trackref.live_refs`` is now a
    :class:`~weakref.WeakKeyDictionary` instead of a
    :class:`collections.defaultdict`, so that classes defined at run time are
    released once they are no longer used. Reading the entry of a class with no
    tracked instances now raises :exc:`KeyError` instead of creating and
    returning an empty mapping.
    (:gh:`5995`, :gh:`7922`)

-   The ``MEMDEBUG_NOTIFY`` setting is removed. It had no effect, but code
    reading it now gets ``None`` instead of its default value, which was an
    empty list.
    (:gh:`7737`)

-   ``scrapy.utils.log.logformatter_adapter()`` no longer passes the whole
    :class:`dict` returned by a :ref:`log formatter <custom-log-formats>`
    method as logging arguments when that ``dict`` has no ``args`` key, or its
    ``args`` are empty, and its ``msg`` has no ``%(name)s`` placeholders. Such
    messages are now logged verbatim, so a literal ``%`` in them no longer
    breaks logging.

    An ``args`` :class:`tuple` is now expanded into one logging argument per
    item, so that ``%``-style placeholders work with it as they do with a
    ``dict``.

    (:gh:`5570`, :gh:`5572`, :gh:`7936`)

-   :setting:`FEEDS` keys and ``FEED_URI`` values that are
    :class:`pathlib.Path` objects are now used as paths, instead of being
    converted into ``file://`` URIs. This makes them keep working when they
    contain :ref:`URI parameters <topics-feed-uri-params>` or characters that
    URI conversion would percent-encode.
    (:gh:`5794`, :gh:`6425`, :gh:`6611`, :gh:`7674`)

-   :class:`~scrapy.Selector` and :attr:`TextResponse.selector
    <scrapy.http.TextResponse.selector>` no longer force the ``html`` selector
    type for responses that are neither :class:`~scrapy.http.HtmlResponse` nor
    :class:`~scrapy.http.XmlResponse` objects. A
    :class:`~scrapy.http.JsonResponse` gets the ``json`` type, and for any
    other response ``parsel`` determines the type from the body.

    The response class, and hence the selector type, comes from the content
    type that the website reports. When a website reports the wrong content
    type, recast the response, e.g. ``response.replace(cls=HtmlResponse)``.

    (:gh:`4627`, :gh:`5291`, :gh:`6025`, :gh:`7924`, :gh:`7972`)

-   :ref:`AutoThrottle <topics-autothrottle>` no longer sets the
    ``download_delay`` attribute of the running spider to define the starting
    delay of download slots. The starting delay is still applied, but code
    that reads that attribute at run time no longer sees it.
    (:gh:`7167`, :gh:`7175`, :gh:`7833`)

-   The :command:`check` command now ignores :setting:`ITEM_PIPELINES` and
    :setting:`FEEDS`, since contracts check the output of callbacks instead of
    sending it to item processing, so a check run no longer triggers their side
    effects, e.g. writing an empty output file. Use the ``-s`` command-line
    option to set them back for a check run.
    (:gh:`3385`, :gh:`7957`)

-   :class:`~scrapy.spiders.XMLFeedSpider` and
    :class:`~scrapy.spiders.CSVFeedSpider` no longer raise
    :exc:`~scrapy.exceptions.NotConfigured` when ``parse_node()`` or
    ``parse_row()`` is not defined; the resulting :exc:`AttributeError` is
    reported instead.
    (:gh:`7768`)

Deprecation removals
~~~~~~~~~~~~~~~~~~~~

-   ``scrapy.utils.misc.md5sum()``, deprecated since Scrapy 2.12.0, is
    removed.
    (:gh:`6264`, :gh:`8023`)

-   ``scrapy.utils.iterators.xmliter()``, deprecated since Scrapy 2.11.1
    because it is vulnerable to ReDoS attacks, is removed. Use
    :func:`~scrapy.utils.iterators.xmliter_lxml` instead.
    (:gh:`7765`)

-   ``scrapy.utils.datatypes.CaselessDict``, deprecated since Scrapy 2.10.0,
    is removed. Use
    :class:`~scrapy.utils.datatypes.CaseInsensitiveDict` instead.
    (:gh:`5146`, :gh:`8023`)

Deprecations
~~~~~~~~~~~~

-   The ``download_delay`` spider attribute is deprecated. Use the
    :setting:`DOWNLOAD_DELAY` setting, or :setting:`DOWNLOAD_SLOTS` to set a
    delay for specific domains, instead.

    The ``max_concurrent_requests`` spider attribute, deprecated since Scrapy
    2.14.0, now sets the :setting:`CONCURRENT_REQUESTS_PER_DOMAIN` setting,
    which is what it always mapped to, and warns accordingly.

    Both attributes are ignored, with a different warning, when the
    corresponding setting is already set at the ``spider`` priority or higher.

    (:gh:`7167`, :gh:`7175`, :gh:`7833`)

-   The ``Spider.log()`` method is deprecated. Use the methods of
    :attr:`Spider.logger <scrapy.Spider.logger>` instead.
    (:gh:`7739`)

-   The ``scrapy.interfaces`` module and its ``ISpiderLoader`` interface are
    deprecated. Custom spider loaders only need to follow
    :class:`~scrapy.spiderloader.SpiderLoaderProtocol`.
    (:gh:`6585`, :gh:`7731`)

-   ``scrapy.extensions.feedexport.IFeedStorage`` is deprecated. Custom feed
    storages only need to follow
    ``scrapy.extensions.feedexport.FeedStorageProtocol``.
    (:gh:`6585`, :gh:`7731`)

-   ``scrapy.utils.python.re_rsearch()`` is deprecated.
    (:gh:`7765`)

-   Importing ``FileException`` from ``scrapy.pipelines.files`` is deprecated.
    Import it from ``scrapy.pipelines.media`` instead.
    (:gh:`7544`, :gh:`7673`, :gh:`7973`)

-   Setting ``request.meta["is_secure"]`` to ``False`` to send an ``s3://``
    request over plaintext HTTP is deprecated. The flag will be ignored in a
    future Scrapy version.
    (:gh:`7738`)

-   The unused ``multiplier`` attribute of
    :class:`~scrapy.extensions.periodic_log.PeriodicLog` is deprecated.
    (:gh:`7809`, :gh:`7982`)

-   Returning, from a :ref:`log formatter <custom-log-formats>` method, a
    ``msg`` with ``%(name)s`` placeholders and no ``args`` is deprecated. Those
    placeholders are still interpolated with the returned :class:`dict`, but in
    a future Scrapy version the message will be logged verbatim. Return those
    values under ``args`` instead.
    (:gh:`5570`, :gh:`7971`)

New features
~~~~~~~~~~~~

-   Added :ref:`optional extras <extras>` for every optional dependency of
    Scrapy: ``bpython``, ``gcs``, ``httpx``, ``images``, ``ipython``,
    ``ptpython``, ``robotparser``, ``s3``, ``twisted-http2`` and ``uvloop``.
    For example, ``pip install scrapy[s3,images]``.
    (:gh:`7596`)

-   :class:`~scrapy.core.downloader.handlers._httpx.HttpxDownloadHandler` now
    uses `httpx2 <https://httpx2.pydantic.dev/>`__, the successor of ``httpx``,
    which the new :ref:`httpx extra <extras>` installs together with its HTTP/2
    and SOCKS proxy support. ``httpx`` is still used when ``httpx2`` is not
    installed, but it is no longer tested.
    (:gh:`7762`)

-   Added a :signal:`robots_parsed` signal, sent by
    :class:`~scrapy.downloadermiddlewares.robotstxt.RobotsTxtMiddleware` after
    it parses a :file:`robots.txt` file. It supports :ref:`asynchronous
    handlers <signal-deferred>`.

    Added a :meth:`~scrapy.robotstxt.RobotParser.crawl_delay` method to
    :class:`~scrapy.robotstxt.RobotParser`, implemented by all built-in
    :ref:`robots.txt parsers <topics-dlmw-robots>`.

    (:gh:`7830`)

-   Added a :meth:`Request.to_curl() <scrapy.Request.to_curl>` method, the
    inverse of :meth:`~scrapy.Request.from_curl`.
    (:gh:`7743`, :gh:`7746`, :gh:`7802`)

-   Added a :reqmeta:`depth_reset` request meta key that gives a request depth
    0 instead of the depth of its source response plus 1.
    (:gh:`891`, :gh:`7913`)

-   Added
    :class:`~scrapy.spidermiddlewares.metacopy.MetaCopyDetectionMiddleware`,
    enabled by default, which warns once per crawl when a spider yields a
    request carrying internal :attr:`~scrapy.Request.meta` keys that were
    likely copied from ``response.meta``, and a
    :setting:`META_COPY_WARN_SKIP_KEYS` setting to exclude keys from that
    check.
    (:gh:`7588`)

-   Added an :setting:`AWS_MAX_POOL_CONNECTIONS` setting, which defines the
    connection pool size of the AWS clients of the :ref:`S3 feed storage
    backend <topics-feed-storage-s3>` and the :ref:`S3 media pipeline storage
    backend <media-pipelines-s3>`, and defaults to
    :setting:`REACTOR_THREADPOOL_MAXSIZE`. It is also exposed as a
    ``max_pool_connections`` parameter of ``S3FeedStorage`` and as an
    ``AWS_MAX_POOL_CONNECTIONS`` attribute of ``S3FilesStore``.
    (:gh:`4985`, :gh:`7794`)

-   Added a :func:`scrapy.utils.asyncio.sleep` function, which works both with
    and without a Twisted reactor.
    (:gh:`7843`)

-   :setting:`CONCURRENT_REQUESTS` can now be set to ``0`` for no limit.
    (:gh:`7840`)

-   :class:`~scrapy.core.downloader.handlers.http2.H2DownloadHandler` is no
    longer experimental, and it now sends the :signal:`bytes_received` and
    :signal:`headers_received` signals and supports
    :exc:`~scrapy.exceptions.StopDownload`.
    (:gh:`5046`, :gh:`5047`, :gh:`5055`, :gh:`7896`, :gh:`7986`)

-   An exception raised by :meth:`Spider.start() <scrapy.Spider.start>` is now
    reported through the :signal:`spider_error` signal and the
    :stat:`spider_exceptions/count` and :stat:`spider_exceptions/{exception}`
    stats, and closes the spider with the new ``start_error``
    :stat:`finish_reason` instead of ``finished``. See :ref:`start-error`.

    :exc:`~scrapy.exceptions.CloseSpider` raised from :meth:`Spider.start()
    <scrapy.Spider.start>` now closes the spider with the given reason, instead
    of being reported as a start error.

    (:gh:`3463`, :gh:`4058`, :gh:`4182`, :gh:`6148`, :gh:`7884`)

-   :exc:`~scrapy.exceptions.CloseSpider` can now also be raised while the
    spider is starting, e.g. from a :signal:`spider_opened` signal handler or
    from the ``open_spider()`` method of an :ref:`item pipeline
    <topics-item-pipeline>`, to close the spider before it starts crawling.
    Every component still gets started, and stopped, before the spider is
    closed with the given reason.
    (:gh:`3435`, :gh:`7905`)

-   Added an :ref:`FTPS feed storage backend <feed-storage-ftps>`, i.e. support
    for the ``ftps`` URI scheme in :setting:`FEEDS`, which uploads the feed
    over a TLS connection, verifying the certificate of the server.
    (:gh:`4180`, :gh:`7953`)

-   Changes to :attr:`Spider.allowed_domains <scrapy.Spider.allowed_domains>`
    during a crawl are now taken into account by
    :class:`~scrapy.downloadermiddlewares.offsite.OffsiteMiddleware`, whose
    :meth:`~scrapy.downloadermiddlewares.offsite.OffsiteMiddleware.should_follow`
    method is now documented as the way to implement a different offsite
    policy.
    (:gh:`3257`, :gh:`3412`, :gh:`7903`, :gh:`7912`)

-   :class:`~scrapy.settings.BaseSettings` methods that take settings, such as
    :meth:`~scrapy.settings.BaseSettings.update` and the ``settings`` parameter
    of crawler classes, now also accept an iterable of ``(name, value)``
    tuples.
    (:gh:`7759`, :gh:`7763`)

-   The ``cookies`` parameter of :class:`~scrapy.Request` now also accepts
    :class:`bool`, :class:`float` and :class:`int` values, and the ``formdata``
    parameter of :class:`~scrapy.FormRequest` now accepts any mapping or
    iterable of key-value pairs.
    (:gh:`7858`, :gh:`7864`)

-   Added a ``scrapy.utils.reactorless.uninstall_reactor_import_hook()``
    function, which :meth:`AsyncCrawlerProcess.start()
    <scrapy.crawler.AsyncCrawlerProcess.start>` now uses to uninstall the
    :mod:`twisted.internet.reactor` import hook when it exits.
    (:gh:`7747`)

-   Added the :stat:`depth/request_ignored_count` and
    :stat:`httpcache/retrieve_error` stats.
    (:gh:`1308`, :gh:`2222`, :gh:`7805`, :gh:`7916`)

-   The :meth:`~scrapy.exporters.BaseItemExporter.get_serialized_fields` method
    of :ref:`item exporters <topics-exporters>`, previously named
    ``_get_serialized_fields()``, is now public and documented, for
    :ref:`custom item exporters <custom-exporters>` to use.
    (:gh:`5706`, :gh:`7931`)

-   Scrapy now writes the session keys of its HTTPS connections to the file
    that the ``SSLKEYLOGFILE`` environment variable points to, so that traffic
    analysis tools such as Wireshark can decrypt them. See :ref:`debug-tls`.
    (:gh:`4368`, :gh:`7948`)

-   Added an :setting:`HTTP2_MAX_FRAME_SIZE` setting, which allows raising the
    maximum HTTP/2 frame size that servers may send, previously fixed at
    16384, above which connections failed.
    (:gh:`5050`, :gh:`7988`)

-   The :command:`crawl`, :command:`parse` and :command:`runspider` commands
    now warn when :setting:`FEEDS` is set, e.g. through ``-o`` or ``-O``, but
    the :class:`~scrapy.extensions.feedexport.FeedExporter` extension is
    disabled, so that no item is exported.
    (:gh:`5970`, :gh:`6082`, :gh:`6373`, :gh:`7902`)

-   Log formatters (:setting:`LOG_FORMATTER`), item processors
    (:setting:`ITEM_PROCESSOR`) and :ref:`robots.txt parsers
    <topics-dlmw-robots>` (:setting:`ROBOTSTXT_PARSER`) are now built as
    :ref:`components <topics-components>`, so they no longer need a
    ``from_crawler()`` method.
    (:gh:`7808`)

Bug fixes
~~~~~~~~~

-   :class:`~scrapy.downloadermiddlewares.httpcache.HttpCacheMiddleware` now
    logs a warning and handles the request as a cache miss when reading a cache
    entry raises an exception, e.g. because the entry is corrupted, instead of
    letting the exception propagate. It also counts those entries in the new
    :stat:`httpcache/retrieve_error` stat.
    (:gh:`2222`, :gh:`7805`)

-   :ref:`Feed URIs <topics-feed-uri-params>` now only expand ``%(...)s``
    parameters, keeping any other percent character as is, so that
    percent-encoded URIs, e.g. one with ``%20`` in a path or with
    percent-encoded FTP credentials, are no longer misinterpreted as
    printf-style formatting directives.
    (:gh:`5794`, :gh:`6425`, :gh:`7674`)

-   :ref:`Feed exports <topics-feed-exports>` now start storing a
    :setting:`FEED_EXPORT_BATCH_ITEM_COUNT` batch as soon as it is complete,
    instead of waiting until the spider closes.
    (:gh:`7730`, :gh:`7733`)

-   :class:`~scrapy.exporters.CsvItemExporter` now warns when the fields that
    it took from the first item do not cover the fields of a later item, i.e.
    when it silently drops data.
    (:gh:`4002`, :gh:`4053`, :gh:`7613`, :gh:`7651`)

-   ``GCSFeedStorage`` no longer requires the ``storage.buckets.get``
    permission.
    (:gh:`5475`, :gh:`7945`)

-   :ref:`Media pipelines <topics-media-pipeline>` now log media requests that
    were filtered out, e.g. as offsite requests, at the ``DEBUG`` level and
    without a traceback, instead of reporting them as download errors.
    (:gh:`7544`, :gh:`7673`)

-   :class:`~scrapy.downloadermiddlewares.offsite.OffsiteMiddleware` now raises
    :exc:`~scrapy.exceptions.IgnoreRequest` with a message, e.g. ``Filtered
    offsite request to 'offsite.example'``, which errbacks and log messages
    that report that exception now include.
    (:gh:`7544`, :gh:`7673`)

-   :class:`~scrapy.core.downloader.handlers.http11.HTTP11DownloadHandler` now
    skips response header lines that have no colon, logging them at the
    ``DEBUG`` level, as web browsers do, instead of being unable to download
    such a response at all.
    (:gh:`210`, :gh:`7806`)

-   :class:`~scrapy.downloadermiddlewares.cookies.CookiesMiddleware` now sends
    domain cookies to hosts without a dot in their name and to hosts given as
    an IP address.
    (:gh:`6410`, :gh:`7900`)

-   :meth:`TextResponse.json() <scrapy.http.TextResponse.json>` now decodes
    bodies that are not valid UTF-8, UTF-16 or UTF-32 using
    :attr:`TextResponse.encoding <scrapy.http.TextResponse.encoding>`, instead
    of raising :exc:`UnicodeDecodeError`.
    (:gh:`6456`, :gh:`7897`)

-   ``scrapy.resolver.CachingHostnameResolver`` now caches addresses without a
    port, and sets the requested port on cache hits, so that a cached address
    no longer carries the port of the request that populated the cache.
    (:gh:`6442`, :gh:`7772`)

-   :class:`~scrapy.pqueues.DownloaderAwarePriorityQueue` now removes the
    directory of a download slot from the :setting:`JOBDIR` directory once that
    slot is drained.
    (:gh:`5275`, :gh:`7955`)

-   :class:`~scrapy.extensions.telnet.TelnetConsole` no longer raises an
    exception on shutdown when it could not listen on any of the
    :setting:`TELNETCONSOLE_PORT` ports.
    (:gh:`2702`, :gh:`7910`)

-   The :setting:`DOWNLOAD_WARNSIZE` warning is no longer logged twice for a
    response whose ``Content-Length`` header already exceeded the limit.
    (:gh:`2476`, :gh:`7963`)

-   :class:`HttpCompressionMiddleware
    <scrapy.downloadermiddlewares.httpcompression.HttpCompressionMiddleware>`
    now logs a warning when it drops a response for exceeding
    :setting:`DOWNLOAD_MAXSIZE` during decompression.
    (:gh:`6616`, :gh:`7742`)

-   :class:`~scrapy.spidermiddlewares.depth.DepthMiddleware` now logs only the
    first request ignored for exceeding :setting:`DEPTH_LIMIT`, and counts them
    all in the new :stat:`depth/request_ignored_count` stat.
    (:gh:`1308`, :gh:`7916`)

-   :command:`parse` now sets the callback it uses on the request of the
    response it passes to that callback.
    (:gh:`3095`, :gh:`3124`, :gh:`7803`)

-   The IPython :ref:`shell <topics-shell>` now works when an asyncio event
    loop is already running in the same thread, e.g. when calling
    ``scrapy.shell.inspect_response()`` from a callback while using the asyncio
    reactor.
    (:gh:`5447`, :gh:`7816`)

-   :meth:`Request.from_curl() <scrapy.Request.from_curl>` now merges repeated
    ``-d``, ``--data`` and ``--data-raw`` options into a single body joined
    with ``&``, as curl does, instead of keeping only the last one.
    (:gh:`7728`)

-   The ``copy()`` method and the ``|=`` operator of
    ``scrapy.utils.datatypes.CaseInsensitiveDict`` no longer leave the internal
    mapping of original key spellings shared or out of date.
    (:gh:`7783`)

-   :meth:`ExecutionEngine.download_async()
    <scrapy.core.engine.ExecutionEngine.download_async>` no longer recurses
    once per returned request, e.g. once per redirect.
    (:gh:`7544`, :gh:`7673`)

-   :class:`LinkExtractor <scrapy.linkextractors.lxmlhtml.LxmlLinkExtractor>`
    now canonicalizes each extracted URL once instead of twice when
    ``canonicalize`` is ``True``.
    (:gh:`7961`)

-   Items yielded from :meth:`Spider.start() <scrapy.Spider.start>` now keep
    the spider busy until the :ref:`item pipelines <topics-item-pipeline>` are
    done with them, so that a spider that only yields items from
    :meth:`~scrapy.Spider.start` no longer closes before processing them.
    (:gh:`7029`, :gh:`7891`)

-   :func:`~scrapy.utils.response.open_in_browser` now also adds its ``base``
    tag to HTML responses that have no ``head`` element, and it now overrides a
    ``base`` tag already present in the response, so that relative URLs resolve
    against the response URL in every case.
    (:gh:`6550`, :gh:`7879`)

-   :meth:`Spider.start() <scrapy.Spider.start>` implementations that are not
    asynchronous generators now raise :exc:`TypeError` with a message that says
    so, instead of failing in a way that does not point at the cause.
    (:gh:`5426`, :gh:`7946`)

-   The :command:`check`, :command:`fetch` and :command:`parse` commands now
    return the exit code 1 when a component fails to initialize, as
    :command:`crawl` and :command:`runspider` already did.
    (:gh:`4292`, :gh:`7920`)

-   :class:`HttpCompressionMiddleware
    <scrapy.downloadermiddlewares.httpcompression.HttpCompressionMiddleware>`
    no longer hangs on a ``deflate`` response body followed by extra bytes.
    (:gh:`7841`)

-   :func:`scrapy.utils.python.get_func_args` now reports the parameters that a
    :class:`functools.partial` object binds by position, instead of an empty
    list.
    (:gh:`7841`)

-   Fixed :exc:`NameError` exceptions on Python 3.14, where :pep:`649` made
    annotation evaluation lazy, when inspecting the signature of a callable
    with annotations imported only for type checking.
    (:gh:`7796`, :gh:`7818`)

-   ``scrapy.utils.decorators.deprecated`` can now be used both as
    ``@deprecated`` and as ``@deprecated(...)`` without confusing type
    checkers.
    (:gh:`7797`)

-   The default download handlers can now download from domains with emoji
    characters or underscores, which were previously rejected.
    (:gh:`3321`, :gh:`4330`, :gh:`7846`)

-   Callbacks and media pipeline results no longer wait 100 ms before
    proceeding.
    (:gh:`8019`)

-   Shutting down a crawl no longer risks raising an unhandled
    :exc:`RuntimeError` if the code interrupted by the shutdown signal was
    itself writing to the log.
    (:gh:`8022`)

-   Nested selectors, e.g. the result of calling
    :meth:`~scrapy.Selector.jmespath` on a selector, now let ``parsel``
    determine their type instead of forcing the ``html`` type, so that they no
    longer return the wrong type or value.
    (:gh:`8038`, :gh:`8040`)

Documentation
~~~~~~~~~~~~~

-   Added a :ref:`built-in stats reference <topics-stats-reference>`, covering
    every stat that Scrapy sets.
    (:gh:`6351`, :gh:`7814`)

-   Replaced the broad crawls page with a new :ref:`optimization <optimize>`
    page, about finding the bottleneck of a crawl before changing any setting,
    which covers :ref:`broad crawls <broad-crawls>` as one of its sections.
    (:gh:`4737`, :gh:`7938`)

-   Added a :ref:`concepts <concepts>` page, a quick map of Scrapy's main
    building blocks, what problem each one solves, and when to reach for it.
    (:gh:`1569`, :gh:`8025`)

-   Added a :ref:`cookies <cookies>` page, which gathers what used to be
    spread across the request and downloader middleware pages.
    (:gh:`7947`)

-   Added :ref:`callbacks <callbacks>` and :ref:`errbacks <errbacks>` sections
    to the request and response page, covering :ref:`callback assignment
    <callback-assignment>`, :ref:`how to write a callback <writing-callbacks>`
    and :ref:`supported callback output <callback-output>`.
    (:gh:`5054`, :gh:`6437`, :gh:`7821`, :gh:`7898`)

-   Documented the :setting:`ITEM_PROCESSOR` setting and the
    :class:`~scrapy.pipelines.ItemProcessorProtocol` protocol that its value
    must implement.
    (:gh:`7983`)

-   Documented :ref:`how to write an item exporter <custom-exporters>`,
    :ref:`how to test an item pipeline <test-item-pipeline>`, :ref:`how to
    download a request from a downloader middleware <mw-download>`, :ref:`how
    to name media files after the response <file-naming-response>`, :ref:`how
    to add objects to the shell <shell-update-vars>` and :ref:`how to run
    spiders inside an existing application <run-spiders-in-apps>` or :ref:`in a
    Jupyter notebook <run-in-notebook>`.
    (:gh:`915`,
    :gh:`1199`,
    :gh:`2594`,
    :gh:`5706`,
    :gh:`6554`,
    :gh:`6594`,
    :gh:`7751`,
    :gh:`7872`,
    :gh:`7876`,
    :gh:`7889`,
    :gh:`7909`,
    :gh:`7931`)

-   Added an :ref:`inspecting live traffic <debug-live-traffic>` section to the
    debugging page, covering Wireshark and mitmproxy.
    (:gh:`5222`, :gh:`8007`)

-   Documented how :class:`~scrapy.http.TextResponse` resolves the response
    encoding, and how to resolve it differently, e.g. to give the encoding
    declared in the response body precedence over the ``Content-Type`` header.
    (:gh:`4933`, :gh:`7977`)

-   Documented the :ref:`memory use of response parsing
    <security-response-size>` and the :ref:`parser limits
    <security-parser-limits>` that Scrapy lifts, in the security page.
    (:gh:`5700`, :gh:`7930`)

-   Documented that :ref:`signal handlers run in an undefined order
    <signal-order>`, that :signal:`scheduler_empty` must only be awaited from
    :meth:`~scrapy.Spider.start`, that concurrency and politeness settings
    apply per crawler when :ref:`running multiple spiders in the same process
    <run-multiple-spiders>`, and that a :setting:`JOBDIR` directory cannot be
    shared across Scrapy versions.
    (:gh:`3191`,
    :gh:`5330`,
    :gh:`5522`,
    :gh:`7861`,
    :gh:`7883`,
    :gh:`7907`,
    :gh:`7941`)

-   Documented that the ``html`` iterator of
    :class:`~scrapy.spiders.XMLFeedSpider` can silently mangle tags that HTML
    treats as void elements, e.g. ``<link>``, dropping their content and
    closing tag.
    (:gh:`4675`, :gh:`8045`)

-   Documented that the ``keep_fragments`` parameter of
    :func:`~scrapy.utils.request.fingerprint` is not a substitute for
    rendering JavaScript to reach content that a headless browser loads based
    on the URL fragment.
    (:gh:`4789`, :gh:`8033`)

-   Documented :ref:`how to derive the job directory from the spider name
    <job-dir-spider-name>`.
    (:gh:`4748`, :gh:`8035`)

-   Documented that the project name from :file:`scrapy.cfg` also appears
    elsewhere by default, and which of those uses actually require it to
    match.
    (:gh:`2484`, :gh:`8044`)

-   Many other corrections and improvements.
    (:gh:`4589`,
    :gh:`4796`,
    :gh:`5532`,
    :gh:`5548`,
    :gh:`6053`,
    :gh:`6184`,
    :gh:`6627`,
    :gh:`6787`,
    :gh:`6943`,
    :gh:`6989`,
    :gh:`7710`,
    :gh:`7725`,
    :gh:`7737`,
    :gh:`7767`,
    :gh:`7769`,
    :gh:`7771`,
    :gh:`7774`,
    :gh:`7775`,
    :gh:`7777`,
    :gh:`7779`,
    :gh:`7780`,
    :gh:`7817`,
    :gh:`7832`,
    :gh:`7835`,
    :gh:`7862`,
    :gh:`7871`,
    :gh:`7875`,
    :gh:`7880`,
    :gh:`7890`,
    :gh:`7903`,
    :gh:`7913`,
    :gh:`7917`,
    :gh:`7939`,
    :gh:`7940`,
    :gh:`7962`,
    :gh:`7965`)

Quality assurance
~~~~~~~~~~~~~~~~~

-   Improved and fixed type hints.
    (:gh:`7712`,
    :gh:`7785`,
    :gh:`7858`,
    :gh:`7864`,
    :gh:`7865`,
    :gh:`7867`)

-   Added CPU benchmarks, tracked on CodSpeed, so that performance regressions
    are caught before they are merged and performance work can be measured.
    (:gh:`7831`,
    :gh:`7839`,
    :gh:`7870`,
    :gh:`7887`,
    :gh:`7914`,
    :gh:`7954`)

-   Added a nightly job that runs the test suite against the development
    branches of dependencies, so that incompatibilities are found before those
    dependencies are released.
    (:gh:`5291`, :gh:`6025`, :gh:`7924`, :gh:`7960`)

-   CI and test improvements and fixes.
    (:gh:`5049`,
    :gh:`5620`,
    :gh:`5837`,
    :gh:`6478`,
    :gh:`6794`,
    :gh:`7262`,
    :gh:`7437`,
    :gh:`7702`,
    :gh:`7720`,
    :gh:`7724`,
    :gh:`7727`,
    :gh:`7736`,
    :gh:`7741`,
    :gh:`7749`,
    :gh:`7753`,
    :gh:`7755`,
    :gh:`7768`,
    :gh:`7778`,
    :gh:`7782`,
    :gh:`7792`,
    :gh:`7793`,
    :gh:`7795`,
    :gh:`7797`,
    :gh:`7798`,
    :gh:`7809`,
    :gh:`7829`,
    :gh:`7834`,
    :gh:`7836`,
    :gh:`7838`,
    :gh:`7841`,
    :gh:`7844`,
    :gh:`7848`,
    :gh:`7853`,
    :gh:`7854`,
    :gh:`7857`,
    :gh:`7859`,
    :gh:`7863`,
    :gh:`7895`,
    :gh:`7906`,
    :gh:`7928`,
    :gh:`7935`,
    :gh:`7966`,
    :gh:`7968`,
    :gh:`7974`,
    :gh:`7979`,
    :gh:`7985`,
    :gh:`7990`,
    :gh:`7993`,
    :gh:`7995`,
    :gh:`8000`,
    :gh:`8001`,
    :gh:`8002`)

.. _release-2.17.0:

Scrapy 2.17.0 (2026-07-07)
--------------------------

Highlights:

-   Security bug fixes

-   HTTP/2 and SOCKS proxy support for ``HttpxDownloadHandler``

-   Improved settings for changing allowed TLS versions

Security bug fixes
~~~~~~~~~~~~~~~~~~

-   ``s3://`` requests now use HTTPS by default, instead of plaintext HTTP.

    Previously, :class:`~scrapy.core.downloader.handlers.s3.S3DownloadHandler`
    sent signed S3 requests over plaintext HTTP unless
    ``request.meta["is_secure"]`` was set to a true value, exposing the request
    path, the AWS ``Authorization`` header, the ``X-Amz-Security-Token`` header
    (when using temporary credentials), and the response contents to network
    attackers, who could also tamper with responses. See the `76g3-c3x4-crvx`_
    security advisory for details.

    To restore the previous behavior for a given request, set
    ``request.meta["is_secure"]`` to ``False``.

    .. _76g3-c3x4-crvx: https://github.com/scrapy/scrapy/security/advisories/GHSA-76g3-c3x4-crvx

Deprecations
~~~~~~~~~~~~

-   The ``DOWNLOADER_CLIENT_TLS_METHOD`` setting is deprecated. You should use
    the :setting:`DOWNLOAD_TLS_MIN_VERSION` and/or
    :setting:`DOWNLOAD_TLS_MAX_VERSION` settings instead if you want to change
    the TLS method selection.
    (:gh:`3288`, :gh:`6546`)

-   The following spider attributes are deprecated in favor of settings:

    - ``http_user`` (use :setting:`HTTPAUTH_USER`)

    - ``http_pass`` (use :setting:`HTTPAUTH_PASS`)

    - ``http_auth_domain`` (use :setting:`HTTPAUTH_DOMAIN`)

    (:gh:`7590`)

-   The ``scrapy.commands.ScrapyCommand.help()`` method is deprecated. It was
    never called by Scrapy.
    (:gh:`7626`, :gh:`7633`)

-   The following TLS-related functions and constants, intended for internal
    use, are deprecated:

    - ``scrapy.core.downloader.tls.METHOD_TLS``

    - ``scrapy.core.downloader.tls.METHOD_TLSv10``

    - ``scrapy.core.downloader.tls.METHOD_TLSv11``

    - ``scrapy.core.downloader.tls.METHOD_TLSv12``

    - ``scrapy.core.downloader.tls.openssl_methods``

    - ``scrapy.core.downloader.tls.DEFAULT_CIPHERS``

    - ``scrapy.utils.ssl.ffi_buf_to_string()``

    - ``scrapy.utils.ssl.get_temp_key_info()``

    - ``scrapy.utils.ssl.x509name_to_string()``

    (:gh:`6546`, :gh:`7619`, :gh:`7665`)

-   The ``CRAWLSPIDER_FOLLOW_LINKS`` setting is deprecated. You can set
    ``follow=False`` in your rules to achieve the same effect.
    (:gh:`7592`)

-   Instantiating
    :class:`~scrapy.downloadermiddlewares.httpcompression.HttpCompressionMiddleware`
    without a ``crawler`` argument is deprecated.
    (:gh:`7655`)

-   Instantiating
    :class:`~scrapy.spidermiddlewares.referer.RefererMiddleware` without a
    ``settings`` argument is deprecated.
    (:gh:`7664`)

New features
~~~~~~~~~~~~

-   Added support for HTTP/2 requests to
    :class:`~scrapy.core.downloader.handlers._httpx.HttpxDownloadHandler`. It
    requires setting the new :setting:`HTTPX_HTTP2_ENABLED` setting to
    ``True``.
    (:gh:`7575`)

-   Added support for SOCKS proxies to
    :class:`~scrapy.core.downloader.handlers._httpx.HttpxDownloadHandler`.
    (:gh:`747`, :gh:`7575`)

-   Added :setting:`DOWNLOAD_TLS_MIN_VERSION` and
    :setting:`DOWNLOAD_TLS_MAX_VERSION` settings as replacements for the
    ``DOWNLOADER_CLIENT_TLS_METHOD`` setting (which is now deprecated).
    Compared to the old setting, they support specifying a range of allowed
    versions and support newer TLS versions.
    (:gh:`4821`, :gh:`6546`)

-   Added :setting:`HTTPAUTH_USER`, :setting:`HTTPAUTH_PASS` and
    :setting:`HTTPAUTH_DOMAIN` settings and :reqmeta:`http_user`,
    :reqmeta:`http_pass` and :reqmeta:`http_auth_domain` meta keys as more
    flexible ways to set HTTP authentication data.
    (:gh:`7590`)

-   Added a :reqmeta:`verbatim_url` meta key that can be set to ``True`` to
    skip request URL canonicalization.
    (:gh:`7473`)

-   Added ``deny_tags`` and ``deny_attrs`` arguments to :class:`LinkExtractor
    <scrapy.linkextractors.lxmlhtml.LxmlLinkExtractor>`.
    (:gh:`6321`, :gh:`7679`)

-   :attr:`scrapy.Item.fields` now returns the fields in the definition order
    instead of the alphabetical one.
    (:gh:`7015`, :gh:`7694`)

-   Added a :setting:`RETRY_GIVE_UP_LOG_LEVEL` setting, a
    :reqmeta:`give_up_log_level` meta key and a ``give_up_log_level`` argument
    of the
    :func:`~scrapy.downloadermiddlewares.retry.get_retry_request` function that
    allow changing the log level of the message logged when the retry limit has
    been reached.
    (:gh:`4622`, :gh:`5297`, :gh:`7567`)

-   It's now possible to set :setting:`DOWNLOADER_CLIENT_TLS_CIPHERS` to
    ``None`` to use the default ciphers of the underlying TLS implementation.
    (:gh:`7499`, :gh:`7665`)

Improvements
~~~~~~~~~~~~

-   :class:`~scrapy.FormRequest` is no longer deprecated, only its
    ``from_response()`` method is still deprecated.
    (:gh:`7561`, :gh:`7671`)

-   Switched the item definition in the default project template from a
    :class:`scrapy.item.Item` to a dataclass.
    (:gh:`7493`, :gh:`7513`)

-   Fixed deprecation warnings with pyOpenSSL 26.3.0.
    (:gh:`7619`)

-   Removed the runtime warnings for :attr:`Spider.allowed_domains
    <scrapy.Spider.allowed_domains>` containing URLs or domains with ports
    instead of just domains and for spider classes having a ``start_url``
    attribute instead of :class:`~scrapy.spiders.Spider.start_urls`. Please use
    :doc:`scrapy-lint <scrapy-lint:index>` to find mistakes in your spider code
    instead.
    (:gh:`4421`, :gh:`7627`)

-   :func:`scrapy.utils.test.get_crawler` now disables
    :setting:`TELNETCONSOLE_ENABLED` by default.
    (:gh:`7644`)

-   Other code refactoring and improvements.
    (:gh:`7409`, :gh:`7593`, :gh:`7594`, :gh:`7611`, :gh:`7649`)

Bug fixes
~~~~~~~~~

-   :class:`~scrapy.core.downloader.handlers._httpx.HttpxDownloadHandler` no
    longer ignores proxy credentials for redirected or retried requests.
    (:gh:`7601`, :gh:`7630`)

-   :class:`~scrapy.extensions.feedexport.GCSFeedStorage` now closes the
    temporary file after the upload.
    (:gh:`7546`)

-   Fixed ``scrapy shell <URL>`` running a full spider crawl when there is a
    spider for the requested URL. This bug was introduced in Scrapy 2.13.0.
    (:gh:`7552`, :gh:`7557`)

-   The :setting:`IMAGES_STORE_S3_ACL` and :setting:`IMAGES_STORE_GCS_ACL`
    settings are no longer ignored. This bug was introduced in Scrapy 2.12.0.
    (:gh:`7597`, :gh:`7614`)

-   :class:`~scrapy.core.downloader.handlers.ftp.FTPDownloadHandler` now closes
    the connection after making the request.
    (:gh:`7602`, :gh:`7667`)

-   Removed the deprecated ``spider`` argument from the pipeline defined in the
    default project template.
    (:gh:`7676`)

-   Fixed ``scrapy genspider --edit`` not working.
    (:gh:`7260`, :gh:`7683`)

-   When a :class:`~scrapy.crawler.Crawler` instance is passed to
    :meth:`AsyncCrawlerRunner.create_crawler()
    <scrapy.crawler.AsyncCrawlerRunner.create_crawler>` or
    :meth:`CrawlerRunner.create_crawler()
    <scrapy.crawler.CrawlerRunner.create_crawler>`, settings from both classes
    are now merged, previously only the settings from the
    :class:`~scrapy.crawler.Crawler` instance were used.
    (:gh:`1280`, :gh:`7647`)

-   Fixed several issues with cookie handling in
    :func:`scrapy.utils.request.request_to_curl`.
    (:gh:`7603`, :gh:`7675`, :gh:`7684`)

-   Fixed :class:`scrapy.resolver.CachingThreadedResolver` not disabling the
    cache when :setting:`DNSCACHE_ENABLED` is set to ``False``.
    (:gh:`7663`)

-   Fixed :func:`scrapy.utils.response.open_in_browser` not removing comments
    when looking for the ``<base>`` tag.
    (:gh:`7506`)

-   Fixed checking for deprecated methods in custom :setting:`ITEM_PROCESSOR`
    implementations.
    (:gh:`7589`)

-   Fixed :func:`scrapy.utils.url.strip_url` corrupting some URLs with
    credentials.
    (:gh:`7604`, :gh:`7605`)

-   :func:`scrapy.utils.misc.rel_has_nofollow` now ignores the case when
    looking for "nofollow" strings.
    (:gh:`7632`)

-   Fixed an exception in :class:`scrapy.utils.sitemap.Sitemap` when parsing
    some malformed sitemaps.
    (:gh:`7686`, :gh:`7687`)

Documentation
~~~~~~~~~~~~~

-   Mentioned :doc:`scrapy-lint <scrapy-lint:index>` in the docs.
    (:gh:`4421`, :gh:`7627`)

-   Added the docs about :ref:`security considerations <security>`.
    (:gh:`7389`, :gh:`7678`)

-   Improved the :ref:`item pipeline docs <topics-item-pipeline>`.
    (:gh:`2350`, :gh:`7676`)

-   Documented which stats are collected by
    :class:`~scrapy.extensions.corestats.CoreStats`.
    (:gh:`7421`)

-   Switched documentation examples from using :class:`scrapy.item.Item` to
    using dataclasses.
    (:gh:`7493`, :gh:`7513`)

-   Added feature comparison tables to the :ref:`download handler
    <download-handlers-ref>` docs.
    (:gh:`7575`)

-   Improved the docs for :ref:`logging settings <logging-settings>`.
    (:gh:`6909`, :gh:`7668`)

-   Documented a way to :ref:`improve startup time and memory usage
    <large-project-startup>` by using :setting:`SPIDER_MODULES`.
    (:gh:`7576`, :gh:`7600`)

-   Clarified handling of the ``type`` argument of :class:`~scrapy.Selector`.
    (:gh:`7704`)

-   Other documentation improvements and fixes.
    (:gh:`4954`,
    :gh:`6120`,
    :gh:`7286`,
    :gh:`7564`,
    :gh:`7573`,
    :gh:`7598`,
    :gh:`7599`,
    :gh:`7698`)

Quality assurance
~~~~~~~~~~~~~~~~~

-   Fixed deprecation warnings with pytest 9.1.0.
    (:gh:`7621`)

-   Type hints improvements and fixes.
    (:gh:`6958`, :gh:`7586`)

-   CI and test improvements and fixes.
    (:gh:`5954`,
    :gh:`7002`,
    :gh:`7017`,
    :gh:`7247`,
    :gh:`7508`,
    :gh:`7545`,
    :gh:`7566`,
    :gh:`7574`,
    :gh:`7585`,
    :gh:`7595`,
    :gh:`7608`,
    :gh:`7610`,
    :gh:`7612`,
    :gh:`7616`,
    :gh:`7625`,
    :gh:`7637`,
    :gh:`7639`,
    :gh:`7640`,
    :gh:`7641`,
    :gh:`7642`,
    :gh:`7643`,
    :gh:`7644`,
    :gh:`7645`,
    :gh:`7646`,
    :gh:`7654`,
    :gh:`7655`,
    :gh:`7664`,
    :gh:`7672`,
    :gh:`7677`,
    :gh:`7680`,
    :gh:`7682`,
    :gh:`7692`)

.. _release-2.16.0:

Scrapy 2.16.0 (2026-05-19)
--------------------------

Highlights:

-   Official support for Python 3.14

-   Support for Twisted 26.4.0+

Modified requirements
~~~~~~~~~~~~~~~~~~~~~

-   Increased the minimum versions of the following dependencies:

    - service_identity_: 18.1.0 → 23.1.0

    (:gh:`7347`)

-   Added support for Twisted 26.4.0+.
    (:gh:`7347`, :gh:`7505`, :gh:`7520`)

-   Added support for Python 3.14.
    (:gh:`6604`, :gh:`7460`)

Backward-incompatible changes
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

-   The following classes and functions, intended for internal use by
    :class:`~scrapy.core.downloader.handlers.http11.HTTP11DownloadHandler`
    and :class:`~scrapy.core.downloader.handlers.http2.H2DownloadHandler`, have
    been made private:

    - ``scrapy.core.downloader.handlers.http11.ScrapyAgent``

    - ``scrapy.core.downloader.handlers.http11.ScrapyProxyAgent``

    - ``scrapy.core.downloader.handlers.http11.TunnelingAgent``

    - ``scrapy.core.downloader.handlers.http11.TunnelingTCP4ClientEndpoint``

    - ``scrapy.core.downloader.handlers.http11.tunnel_request_data()``

    - ``scrapy.core.downloader.handlers.http2.ScrapyH2Agent``

    (:gh:`7496`, :gh:`7510`)

Deprecations
~~~~~~~~~~~~

-   ``scrapy.FormRequest`` is deprecated. You can use the :doc:`form2request
    <form2request:index>` library instead, see :ref:`form`.
    (:gh:`6438`)

-   ``scrapy.utils.python.MutableChain`` is deprecated.
    (:gh:`7504`)

Deprecation removals
~~~~~~~~~~~~~~~~~~~~

-   The ``start_requests()`` method of :class:`~scrapy.Spider`, deprecated in
    2.13.0, is removed and no longer called. Use :meth:`~scrapy.Spider.start`
    instead, or both to maintain support for lower Scrapy versions.
    (:gh:`7490`)

-   Support for ``process_start_requests()`` methods of :ref:`spider middlewares
    <topics-spider-middleware>`, deprecated in 2.13.0, is removed. Use
    :meth:`~scrapy.spidermiddlewares.SpiderMiddleware.process_start` instead,
    or both to maintain support for lower Scrapy versions.
    (:gh:`7490`)

-   Support for synchronous ``process_spider_output()`` methods of spider
    middlewares, deprecated in Scrapy 2.13.0, is removed. You should upgrade
    the affected middlewares to have asynchronous ``process_spider_output()``
    methods.
    (:gh:`7504`)

-   The ``spider`` arguments of the following methods of
    :class:`~scrapy.core.scraper.Scraper`, deprecated in Scrapy 2.13.0, are
    removed:

    - ``close_spider()``

    - ``enqueue_scrape()``

    - ``handle_spider_error()``

    - ``handle_spider_output()``

    (:gh:`7487`)

-   HTTP/1.0 support code, deprecated in Scrapy 2.13.0, is removed. This
    includes:

    - ``scrapy.core.downloader.handlers.http10.HTTP10DownloadHandler``

    - The ``scrapy.core.downloader.webclient`` module.

    - The ``DOWNLOADER_HTTPCLIENTFACTORY`` setting.

    (:gh:`7486`)

-   The following functions, deprecated in Scrapy 2.13.0, are removed, you
    should import them from :mod:`w3lib.url` directly instead:

    - ``scrapy.utils.url.add_or_replace_parameter()``

    - ``scrapy.utils.url.add_or_replace_parameters()``

    - ``scrapy.utils.url.any_to_uri()``

    - ``scrapy.utils.url.canonicalize_url()``

    - ``scrapy.utils.url.file_uri_to_path()``

    - ``scrapy.utils.url.is_url()``

    - ``scrapy.utils.url.parse_data_uri()``

    - ``scrapy.utils.url.parse_url()``

    - ``scrapy.utils.url.path_to_file_uri()``

    - ``scrapy.utils.url.safe_download_url()``

    - ``scrapy.utils.url.safe_url_string()``

    - ``scrapy.utils.url.url_query_cleaner()``

    - ``scrapy.utils.url.url_query_parameter()``

    (:gh:`7487`)

-   The following test-related code, deprecated in Scrapy 2.13.0, is removed:

    - the ``scrapy.utils.testproc`` module

    - the ``scrapy.utils.testsite`` module

    - ``scrapy.utils.test.assert_gcs_environ()``

    - ``scrapy.utils.test.get_ftp_content_and_delete()``

    - ``scrapy.utils.test.get_gcs_content_and_delete()``

    - ``scrapy.utils.test.mock_google_cloud_storage()``

    - ``scrapy.utils.test.skip_if_no_boto()``

    - ``scrapy.utils.test.TestSpider``

    (:gh:`7487`)

-   ``scrapy.utils.versions.scrapy_components_versions()``, deprecated in
    Scrapy 2.13.0, is removed, you can use
    ``scrapy.utils.versions.get_versions()`` instead.
    (:gh:`7487`)

-   ``scrapy.downloadermiddlewares.ajaxcrawl.AjaxCrawlMiddleware`` and
    ``scrapy.utils.url.escape_ajax()``, deprecated in Scrapy 2.13.0, are
    removed.
    (:gh:`7487`)

-   The ``__init__()`` method of priority queue classes (see
    :setting:`SCHEDULER_PRIORITY_QUEUE`) now needs to support a keyword-only
    ``start_queue_cls`` parameter, not supporting it was deprecated in Scrapy
    2.13.0.
    (:gh:`7487`)

-   ``scrapy.spiders.init.InitSpider``, deprecated in Scrapy 2.13.0, is
    removed.
    (:gh:`7487`)

New features
~~~~~~~~~~~~

-   New features and improvements for
    :class:`~scrapy.core.downloader.handlers._httpx.HttpxDownloadHandler`:

    - Support for proxies.

    - Support for the :reqmeta:`download_latency` meta key.

    - Support for :attr:`Response.certificate
      <scrapy.http.Response.certificate>`.

    - Default headers set by the ``httpx`` library are no longer added to
      requests.

    (:gh:`7441`, :gh:`7524`)

-   :class:`~scrapy.core.downloader.handlers.http11.HTTP11DownloadHandler` now
    skips HTTPS proxy certificate verification when the
    :setting:`DOWNLOAD_VERIFY_CERTIFICATES` setting is set to ``False``.
    (:gh:`7496`)

Improvements
~~~~~~~~~~~~

-   :func:`time.monotonic` is used instead of :func:`time.time` to calculate
    elapsed time in various places.
    (:gh:`7377`)

-   Improved extraction of the file extension from the URL in
    :class:`~scrapy.pipelines.files.FilesPipeline`.
    (:gh:`4225`, :gh:`7414`)

-   Other code refactoring and improvements.
    (:gh:`7401`)

Bug fixes
~~~~~~~~~

-   :class:`~scrapy.core.downloader.handlers.http11.HTTP11DownloadHandler` now
    raises an exception when a request has an ``https://`` destination and an
    ``https://`` proxy, which is not supported by this handler. Previously it
    tried to connect to the proxy via HTTP in this case.
    (:gh:`7496`)

-   :class:`~scrapy.core.downloader.handlers.http2.H2DownloadHandler` now
    raises an exception for requests with ``http://`` URLs instead of trying to
    connect, which is not supported by this handler.
    (:gh:`7496`)

-   :class:`~scrapy.core.downloader.handlers.http2.H2DownloadHandler` no longer
    adds the ``:status`` pseudo-header to :attr:`Response.headers
    <scrapy.http.Response.headers>`.
    (:gh:`7441`)

-   Fixed :func:`scrapy.utils.response.open_in_browser` removing the ``<head>``
    tag when adding the ``<base>`` tag.
    (:gh:`7459`)

Documentation
~~~~~~~~~~~~~

-   Documented that
    :class:`~scrapy.core.downloader.handlers.http11.HTTP11DownloadHandler`
    doesn't support HTTPS proxies for HTTPS destinations and that
    :class:`~scrapy.core.downloader.handlers.http2.H2DownloadHandler` doesn't
    support proxies at all.
    (:gh:`7496`)

-   Added an example of using
    :class:`logging.handlers.TimedRotatingFileHandler` to rotate Scrapy logs.
    (:gh:`3628`, :gh:`7501`)

-   Added a ``CITATION.cff`` file.
    (:gh:`7502`, :gh:`7519`)

-   Mentioned ``DOWNLOADER_CLIENT_TLS_METHOD`` in :ref:`bans`.
    (:gh:`5232`, :gh:`7518`)

-   Other documentation improvements and fixes.
    (:gh:`7417`,
    :gh:`7463`,
    :gh:`7472`,
    :gh:`7480`,
    :gh:`7489`,
    :gh:`7503`,
    :gh:`7507`)

Quality assurance
~~~~~~~~~~~~~~~~~

-   Added tests that connect to https://books.toscrape.com/ to test the
    behavior with a real website. These tests are marked with the
    ``requires_internet`` pytest mark and can be skipped with e.g.
    ``-m 'not requires_internet'`` if you cannot or don't want to run them.
    (:gh:`7520`)

-   Type hints improvements and fixes.
    (:gh:`7492`, :gh:`7532`)

-   CI and test improvements and fixes.
    (:gh:`7441`, :gh:`7466`, :gh:`7491`, :gh:`7496`)

.. _release-2.15.2:

Scrapy 2.15.2 (2026-04-28)
--------------------------

Bug fixes
~~~~~~~~~

-   Fixed links in https://docs.scrapy.org/llms.txt (:gh:`7467`)

.. _release-2.15.1:

Scrapy 2.15.1 (2026-04-23)
--------------------------

Bug fixes
~~~~~~~~~

-   Sharing of the SSL context between multiple connections, introduced in
    Scrapy 2.15.0, is reverted as it caused problems and wasn't actually
    needed.
    (:gh:`7445`, :gh:`7450`)

-   Fixed :meth:`scrapy.settings.BaseSettings.getwithbase` failing on keys with
    dots that aren't import names. It now works the way it worked before Scrapy
    2.15.0, without trying to match class objects and import path. A separate
    method,
    :func:`~scrapy.settings.BaseSettings.get_component_priority_dict_with_base`,
    was added that does that, and it is now used for :ref:`component priority
    dictionaries <component-priority-dictionaries>`.
    (:gh:`7426`, :gh:`7449`)

-   Documentation rendering improvements.
    (:gh:`7452`, :gh:`7454`)

.. _release-2.15.0:

Scrapy 2.15.0 (2026-04-09)
--------------------------

Highlights:

-   Experimental support for running without a Twisted reactor

-   Experimental ``httpx``-based download handler

Backward-incompatible changes
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

-   The built-in HTTP :ref:`download handlers <download-handlers-ref>` now
    raise Scrapy-specific exceptions instead of implementation-specific ones,
    see :ref:`download-handlers-exceptions`. This can affect user code that
    handles downloader exceptions, such as ``process_exception()`` methods of
    custom :ref:`downloader middlewares <topics-downloader-middleware-custom>`.
    (:gh:`7208`)

-   In order to fix a long-standing bug with handling of asynchronous storages,
    the following changes were made to media pipeline classes, which can impact
    some of the user code that subclasses them or calls their methods directly:

    - overrides of :meth:`scrapy.pipelines.media.MediaPipeline.media_downloaded`
      and :meth:`~scrapy.pipelines.files.FilesPipeline.file_downloaded` can now
      return coroutines

    - :meth:`~scrapy.pipelines.files.FilesPipeline.media_downloaded`,
      :meth:`~scrapy.pipelines.files.FilesPipeline.file_downloaded` and
      :meth:`~scrapy.pipelines.images.ImagesPipeline.image_downloaded` now
      return coroutines

    (:gh:`2183`, :gh:`6369`, :gh:`7182`)

-   ``Request`` and ``Response`` objects: ``__slots__`` and setter changes:

    -   :class:`scrapy.http.Request` and :class:`scrapy.http.Response` now
        define ``__slots__``. Assigning arbitrary attributes to instances (for
        example, ``response.foo = 1``) will raise ``AttributeError``. Store
        per-request/response data in the request/response ``meta`` mapping
        instead of attaching new attributes to the objects.

    -   If you maintain custom ``Request`` or ``Response`` subclasses that
        relied on dynamic instance attributes, either add ``'__dict__'`` to
        your subclass ``__slots__`` to allow dynamic attributes, or migrate
        per-instance state to ``meta`` or explicit documented attributes.

    -   The setters for ``headers``, ``flags`` and ``cookies`` no longer coerce
        falsy values into ``None``. For example, ``request.headers = {}`` now
        stores an empty :class:`scrapy.http.headers.Headers` instance (not
        ``None``), and ``request.flags = []`` remains an empty list instead of
        being set to ``None``. Update code that relied on ``is None`` checks or
        the previous coercion behaviour.

    (:gh:`7036`, :gh:`7367`, :gh:`7374`)

Deprecation removals
~~~~~~~~~~~~~~~~~~~~

-   The context factory class set as the value of the
    ``DOWNLOADER_CLIENTCONTEXTFACTORY`` setting is now required to support the
    ``method`` argument of ``__init__()``, recommended since Scrapy 1.2.0.
    (:gh:`7353`)

Deprecations
~~~~~~~~~~~~

-   ``scrapy.mail.MailSender`` is deprecated. Please use :mod:`smtplib`,
    :mod:`twisted.mail.smtp` or other 3rd party email libraries.
    (:gh:`7249`, :gh:`7263`)

-   The ``scrapy.extensions.statsmailer.StatsMailer`` extension is deprecated.
    You can instead implement your own notifications by handling the
    :signal:`spider_closed` signal.
    (:gh:`7249`, :gh:`7263`)

-   The ``MEMUSAGE_NOTIFY_MAIL`` setting is deprecated. You can instead
    implement your own notifications by handling the
    :signal:`memusage_warning_reached` and :signal:`spider_closed` signals.
    (:gh:`7249`, :gh:`7263`)

-   The ``DNS_RESOLVER`` setting was renamed to :setting:`TWISTED_DNS_RESOLVER`
    and the old name is deprecated.
    (:gh:`7350`, :gh:`7361`)

-   The ``DOWNLOADER_CLIENTCONTEXTFACTORY`` setting is deprecated. If you were
    using it to switch to
    ``scrapy.core.downloader.contextfactory.BrowserLikeContextFactory``, please
    use the new :setting:`DOWNLOAD_VERIFY_CERTIFICATES` setting instead. If you
    cannot use the default context factory for some other reason, please
    subclass the :ref:`download handler <download-handlers-ref>` instead.
    (:gh:`7352`, :gh:`7379`)

-   ``scrapy.core.downloader.contextfactory.BrowserLikeContextFactory`` is
    deprecated. You can set the new :setting:`DOWNLOAD_VERIFY_CERTIFICATES`
    setting to ``True`` instead.
    (:gh:`7379`)

-   The following implementation details of the context factory handling code
    are deprecated:

    - ``scrapy.core.downloader.contextfactory.AcceptableProtocolsContextFactory``

    - ``scrapy.core.downloader.contextfactory.load_context_factory_from_settings()``

    - ``scrapy.core.downloader.contextfactory.ScrapyClientContextFactory``

    - ``scrapy.core.downloader.tls.ScrapyClientTLSOptions``

    (:gh:`7353`, :gh:`7391`)

-   Passing :class:`str` instead of :class:`bytes` to
    :class:`scrapy.utils.sitemap.Sitemap` and
    :func:`scrapy.utils.sitemap.sitemap_urls_from_robots` is deprecated.
    (:gh:`7007`)

-   ``scrapy.utils.misc.walk_modules()`` is deprecated. You can use
    :func:`scrapy.utils.misc.walk_modules_iter` instead.
    (:gh:`7388`)

-   ``scrapy.shell.Shell.inthread`` is deprecated. You can use
    :attr:`scrapy.shell.Shell.fetch_available` instead to check if
    :func:`~scrapy.shell.Shell.fetch` can be used.
    (:gh:`7395`)

-   ``scrapy.commands.ScrapyCommand.set_crawler()`` is deprecated.
    (:gh:`7276`)

New features
~~~~~~~~~~~~

-   Added an *experimental* mode for running Scrapy without installing a
    Twisted reactor: set :setting:`TWISTED_REACTOR_ENABLED` to ``False`` to
    enable it. This mode has limitations, refer to :ref:`its documentation
    <asyncio-without-reactor>` for details. As long as it's experimental, its
    behavior and related features and APIs may change in future Scrapy releases
    in a breaking way.
    (:gh:`6219`,
    :gh:`7185`,
    :gh:`7186`,
    :gh:`7187`,
    :gh:`7188`,
    :gh:`7190`,
    :gh:`7197`,
    :gh:`7199`,
    :gh:`7209`,
    :gh:`7228`,
    :gh:`7355`,
    :gh:`7366`,
    :gh:`7385`,
    :gh:`7395`)

-   Added the :func:`scrapy.utils.reactorless.is_reactorless` function that
    checks if there is a running asyncio event loop but no Twisted reactor.
    (:gh:`7185`, :gh:`7199`)

-   Changed :func:`scrapy.utils.asyncio.is_asyncio_available` to return
    ``True`` if there is a running asyncio loop, even if no Twisted reactor is
    installed.
    (:gh:`7185`, :gh:`7199`)

-   Added an *experimental* download handler that uses the httpx_ library and
    doesn't require a Twisted reactor:
    :class:`~scrapy.core.downloader.handlers._httpx.HttpxDownloadHandler`. As
    long as it's experimental, its behavior may change in future Scrapy
    releases in a breaking way.
    (:gh:`6805`, :gh:`7239`, :gh:`7368`, :gh:`7384`)

    .. _httpx: https://www.python-httpx.org/

-   Added the :setting:`DOWNLOAD_BIND_ADDRESS` setting as a global counterpart
    to the per-request :reqmeta:`bindaddress` meta key.
    (:gh:`7266`, :gh:`7283`)

-   Added the :setting:`DOWNLOAD_VERIFY_CERTIFICATES` setting that can be set
    to ``True`` to make Scrapy abort HTTPS requests when the server certificate
    is invalid or doesn't match the domain.
    (:gh:`7379`)

-   The built-in HTTP :ref:`download handlers <download-handlers-ref>` now
    raise Scrapy-specific exceptions instead of implementation-specific ones,
    to allow unified handling of similar problems caused by different
    implementations. The default value of the :setting:`RETRY_EXCEPTIONS`
    setting was updated replacing Twisted-specific exceptions with these new
    ones. The exceptions:

    - :exc:`~scrapy.exceptions.CannotResolveHostError`

    - :exc:`~scrapy.exceptions.DownloadCancelledError`

    - :exc:`~scrapy.exceptions.DownloadConnectionRefusedError`

    - :exc:`~scrapy.exceptions.DownloadFailedError`

    - :exc:`~scrapy.exceptions.DownloadTimeoutError`

    - :exc:`~scrapy.exceptions.ResponseDataLossError`

    - :exc:`~scrapy.exceptions.UnsupportedURLSchemeError`

    (:gh:`7208`)

-   Added the :signal:`memusage_warning_reached` signal emitted by the
    :class:`~scrapy.extensions.memusage.MemoryUsage` extension when the memory
    usage reaches :setting:`MEMUSAGE_WARNING_MB`.
    (:gh:`7249`, :gh:`7263`)

-   Added
    :meth:`Headers.to_tuple_list() <scrapy.http.headers.Headers.to_tuple_list>`
    that returns headers as a list of ``(key, value)`` tuples.
    (:gh:`7239`)

-   :class:`~scrapy.core.downloader.handlers.s3.S3DownloadHandler` now uses the
    download handler configured for the ``"https"`` scheme to make requests
    instead of always using
    :class:`~scrapy.core.downloader.handlers.http11.HTTP11DownloadHandler`.
    (:gh:`7369`, :gh:`7370`)

-   Added :func:`scrapy.utils.misc.walk_modules_iter` as a replacement for
    ``scrapy.utils.misc.walk_modules()`` that returns an iterable instead of a
    list.
    (:gh:`7388`)

Improvements
~~~~~~~~~~~~

-   :func:`asyncio.to_thread` is now used instead of
    :func:`twisted.internet.threads.deferToThread` in the built-in feed
    storages, media pipeline storages and the
    :func:`scrapy.utils.decorators.inthread` decorator when available.
    (:gh:`7183`, :gh:`7184`, :gh:`7349`)

-   Improved memory footprint of :class:`~scrapy.Request` and
    :class:`~scrapy.http.Response` objects by adding ``__slots__`` and omitting
    empty lists and dicts in some internal attributes.
    (:gh:`7036`, :gh:`7367`, :gh:`7374`)

-   :class:`~scrapy.core.downloader.contextfactory._ScrapyClientContextFactory`
    no longer mutates the SSL context, to avoid the behavior that was
    deprecated in pyOpenSSL 25.1.0.
    (:gh:`6859`, :gh:`7353`)

-   Improved memory usage of :class:`~scrapy.spiders.sitemap.SitemapSpider` and
    :class:`scrapy.utils.sitemap.Sitemap`.
    (:gh:`3529`, :gh:`7007`)

-   Improved the scheduling behavior of
    :class:`~scrapy.pqueues.DownloaderAwarePriorityQueue` when crawling
    multiple domains.
    (:gh:`7293`, :gh:`7351`)

-   :class:`~scrapy.core.downloader.handlers.http11.HTTP11DownloadHandler` and
    :class:`~scrapy.core.downloader.handlers.http2.H2DownloadHandler` now handle
    TLS verbose logging (see :setting:`DOWNLOADER_CLIENT_TLS_VERBOSE_LOGGING`)
    directly instead of relying on
    :class:`~scrapy.core.downloader.contextfactory._ScrapyClientContextFactory`.
    (:gh:`7387`)

-   The server certificate verification code now correctly handles certificates
    with IP addresses in ``subjectAltName``.
    (:gh:`7353`)

-   Improved reliability of :func:`scrapy.utils.trackref.get_oldest`.
    (:gh:`1758`, :gh:`7375`)

-   Other code refactoring and improvements.
    (:gh:`7210`, :gh:`7238`, :gh:`7376`, :gh:`7386`, :gh:`7395`,
    :gh:`7405`, :gh:`7410`)

Bug fixes
~~~~~~~~~

-   :ref:`Media pipelines <topics-media-pipeline>` should now wait for uploads
    to asynchronous storages (e.g.
    :class:`~scrapy.pipelines.files.S3FilesStore`) to complete.
    (:gh:`2183`, :gh:`6369`, :gh:`7182`)

-   Fixed merging ``*_BASE`` settings (e.g. merging
    :setting:`DOWNLOADER_MIDDLEWARES` with
    :setting:`DOWNLOADER_MIDDLEWARES_BASE`) when a component is referred to by
    a class object in one setting and by a string import path in the other one.
    (:gh:`6912`, :gh:`6993`)

-   ``scrapy runspider`` and ``scrapy crawl`` now set the exit code to 1 if an
    exception happened early (this was broken since Scrapy 2.13.0).
    (:gh:`6820`, :gh:`7255`)

-   Fixed repeated warnings about data loss (see
    :setting:`DOWNLOAD_FAIL_ON_DATALOSS`) not being suppressed in
    :class:`~scrapy.core.downloader.handlers.http11.HTTP11DownloadHandler`.
    (:gh:`7222`)

-   Improved FTP connection management in
    :class:`scrapy.pipelines.files.FTPFilesStore`.
    (:gh:`7256`)

-   Fixed the ``spider`` variable in the :ref:`shell <topics-shell>`, which
    wasn't available since Scrapy 2.13.0.
    (:gh:`7395`)

Documentation
~~~~~~~~~~~~~

-   The ``llms.txt`` and ``llms-full.txt`` files and Markdown versions of pages
    are now generated when the HTML documentation is built.
    (:gh:`7380`)

-   Added a "Copy as Markdown" button to the HTML documentation.
    (:gh:`7380`)

-   Added :ref:`docs for using Pydantic models as items <pydantic-items>`.
    (:gh:`6955`, :gh:`6966`)

-   Documented :ref:`job directory contents <job-dir-contents>`.
    (:gh:`4842`, :gh:`5260`)

-   Improved docs for :attr:`~scrapy.Request.dont_filter`.
    (:gh:`6398`, :gh:`7245`)

-   Clarified that settings related to :setting:`TWISTED_DNS_RESOLVER` are only
    taken into account if the selected resolver supports them.
    (:gh:`7385`)

-   Other documentation improvements and fixes.
    (:gh:`7248`, :gh:`7274`, :gh:`7406`, :gh:`7408`)

Quality assurance
~~~~~~~~~~~~~~~~~

-   Added the ``no-reactor`` test environment that doesn't install a Twisted
    reactor and uses ``pytest-asyncio`` instead of ``pytest-twisted`` to run
    asynchronous test functions.
    (:gh:`6952`, :gh:`7189`, :gh:`7233`, :gh:`7234`, :gh:`7254`,
    :gh:`7259`)

-   Fixed running tests with ``pytest-xdist``.
    (:gh:`7216`, :gh:`7257`)

-   Type hints improvements and fixes.
    (:gh:`7300`, :gh:`7331`)

-   CI and test improvements and fixes.
    (:gh:`7060`,
    :gh:`7223`,
    :gh:`7232`,
    :gh:`7241`,
    :gh:`7250`,
    :gh:`7256`,
    :gh:`7276`,
    :gh:`7277`,
    :gh:`7279`,
    :gh:`7329`,
    :gh:`7363`,
    :gh:`7381`,
    :gh:`7402`)

.. _release-2.14.2:

Scrapy 2.14.2 (2026-03-12)
--------------------------

Security bug fixes
~~~~~~~~~~~~~~~~~~

-   Values from the ``Referrer-Policy`` header of HTTP responses are no longer
    executed as Python callables. See the `cwxj-rr6w-m6w7`_ security advisory
    for details.

    .. _cwxj-rr6w-m6w7: https://github.com/scrapy/scrapy/security/advisories/GHSA-cwxj-rr6w-m6w7

-   In line with the `standard
    <https://fetch.spec.whatwg.org/#http-redirect-fetch>`__, 301 redirects of
    ``POST`` requests are converted into ``GET`` requests.

    Converting to a ``GET`` request implies not only a method change, but also
    omitting the body and ``Content-*`` headers in the redirect request. On
    cross-origin redirects (for example, cross-domain redirects), this is
    effectively a security bug fix for scenarios where the body contains
    secrets.

Deprecations
~~~~~~~~~~~~

-   Passing a response URL string as the first positional argument to
    :meth:`scrapy.spidermiddlewares.referer.RefererMiddleware.policy` is
    deprecated. Pass a :class:`~scrapy.http.Response` instead.

    The parameter has also been renamed to ``response`` to reflect this change.
    The old parameter name (``resp_or_url``) is deprecated.

New features
~~~~~~~~~~~~

-   Added a new setting, :setting:`REFERRER_POLICIES`, to allow customizing
    supported referrer policies.

Bug fixes
~~~~~~~~~

-   Made additional redirect scenarios convert to ``GET`` in line with the
    `standard <https://fetch.spec.whatwg.org/#http-redirect-fetch>`__:

    -   Only ``POST`` 302 redirects are converted into ``GET`` requests; other
        methods are preserved.

    -   ``HEAD`` 303 redirects are not converted into ``GET`` requests.

    -   ``GET`` 303 redirects do not have their body or standard ``Content-*``
        headers removed.

-   Redirects where the original request body is dropped now also have their
    ``Content-Encoding``, ``Content-Language`` and ``Content-Location`` headers
    removed, in addition to the ``Content-Type`` and ``Content-Length`` headers
    that were already being removed.

-   Redirects now preserve the source URL fragment if the redirect URL does not
    include one. This is useful when using browser-based download handlers,
    such as `scrapy-playwright`_ or `scrapy-zyte-api`_, while letting Scrapy
    handle redirects.

    .. _scrapy-playwright: https://github.com/scrapy-plugins/scrapy-playwright
    .. _scrapy-zyte-api: https://scrapy-zyte-api.readthedocs.io/en/latest/

-   The ``Referer`` header is now removed on redirect if
    :class:`~scrapy.spidermiddlewares.referer.RefererMiddleware` is disabled.

-   The handling of the ``Referer`` header on redirects now takes into account
    the ``Referer-Policy`` header of the response that triggers the redirect.

.. _release-2.14.1:

Scrapy 2.14.1 (2026-01-12)
--------------------------

Deprecations
~~~~~~~~~~~~

-   ``scrapy.utils.defer.maybeDeferred_coro()`` is deprecated. (:gh:`7212`)

Bug fixes
~~~~~~~~~

-   Fixed custom stats collectors that require a ``spider`` argument in their
    ``open_spider()`` and ``close_spider()`` methods not receiving the
    argument when called by the engine.

    Note, however, that the ``spider`` argument is now deprecated and will stop
    being passed in a future version of Scrapy.

    (:gh:`7213`)

Quality assurance
~~~~~~~~~~~~~~~~~

-   Replaced deprecated ``codecov/test-results-action@v1`` GitHub Action with
    ``codecov/codecov-action@v5``.
    (:gh:`7180`, :gh:`7215`)

.. _release-2.14.0:

Scrapy 2.14.0 (2026-01-05)
--------------------------

Highlights:

-   More coroutine-based replacements for Deferred-based APIs

-   The default priority queue is now ``DownloaderAwarePriorityQueue``

-   Dropped support for Python 3.9 and PyPy 3.10

-   Improved and documented the API for custom download handlers

Modified requirements
~~~~~~~~~~~~~~~~~~~~~

-   Dropped support for Python 3.9.
    (:gh:`7121`)

-   Dropped support for PyPy 3.10.
    (:gh:`7050`)

-   Increased the minimum versions of the following dependencies:

    - lxml_: 4.6.0 → 4.6.4

    - Pillow_ (optional dependency): 8.0.0 → 8.3.2

    - botocore_ (optional dependency): 1.4.87 → 1.13.45

-   Restored support for ``brotlicffi`` dropped in Scrapy 2.13.4. Its minimum
    supported version is now ``1.2.0.0``.
    (:gh:`7160`)

Backward-incompatible changes
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

-   If you set the ``TWISTED_REACTOR`` setting to a non-asyncio
    value at the :ref:`spider level <spider-settings>`, you
    may now need to set the ``FORCE_CRAWLER_PROCESS`` setting to
    ``True`` when running Scrapy via :ref:`its command-line tool
    <topics-commands-crawlerprocess>` to avoid a reactor mismatch exception.
    (:gh:`6845`)

-   The ``log_count/*`` stats no longer count some of the early messages that
    they counted before. While the earliest log messages, emitted before the
    counter is initialized, were never counted, the counter initialization now
    happens later than in previous Scrapy versions. You may need to adjust
    expected values if you retrieve and compare values of these stats in your
    code.
    (:gh:`7046`)

-   The classes listed below are now :term:`abstract base classes <abstract
    base class>`. They cannot be instantiated directly and their subclasses
    need to override the abstract methods listed below to be able to be
    instantiated. If you previously instantiated these classes directly, you
    will now need to subclass them and provide trivial (e.g. empty)
    implementations for the abstract methods.

    - :class:`scrapy.commands.ScrapyCommand`

        - :meth:`~scrapy.commands.ScrapyCommand.run`

        - :meth:`~scrapy.commands.ScrapyCommand.short_desc`

    - :class:`scrapy.exporters.BaseItemExporter`

        - :meth:`~scrapy.exporters.BaseItemExporter.export_item`

    - :class:`scrapy.extensions.feedexport.BlockingFeedStorage`

        - :meth:`~scrapy.extensions.feedexport.BlockingFeedStorage._store_in_thread`

    - :class:`scrapy.middleware.MiddlewareManager`

        - :meth:`~scrapy.middleware.MiddlewareManager._get_mwlist_from_settings`

    - :class:`scrapy.spidermiddlewares.referer.ReferrerPolicy`

        - :meth:`~scrapy.spidermiddlewares.referer.ReferrerPolicy.referrer`

    (:gh:`6930`)

-   Scrapy no longer passes a ``spider`` argument to any methods of the
    :setting:`stats collector <STATS_CLASS>`. It wasn't passed in many of the
    calls even in older Scrapy versions, so we don't expect existing custom
    stats collector implementations to require a ``spider`` argument. If your
    implementation needs a :class:`~scrapy.Spider` instance, you can get it
    from the :class:`~scrapy.crawler.Crawler` instance passed to the
    constructor.
    (:gh:`7011`)

-   :class:`scrapy.middleware.MiddlewareManager` no longer includes code for
    handling ``open_spider()`` and ``close_spider()`` component methods. As
    this code was only used for pipelines it was moved into
    :class:`scrapy.pipelines.ItemPipelineManager`. This change should only
    affect custom subclasses of :class:`~scrapy.middleware.MiddlewareManager`.
    The following code was moved:

    - ``scrapy.middleware.MiddlewareManager.open_spider()``

    - ``scrapy.middleware.MiddlewareManager.close_spider()``

    - Code in ``scrapy.middleware.MiddlewareManager._add_middleware()`` that
      processes ``open_spider()`` and ``close_spider()`` component methods.

    (:gh:`7006`)

-   :meth:`scrapy.downloadermiddlewares.robotstxt.RobotsTxtMiddleware.process_request`
    now returns a coroutine, previously it returned a
    :class:`~twisted.internet.defer.Deferred` object or ``None``. The
    ``robot_parser()`` method was also changed to return a coroutine. This
    change only impacts code that subclasses
    :class:`~scrapy.downloadermiddlewares.robotstxt.RobotsTxtMiddleware` or
    calls its methods directly.
    (:gh:`6802`)

-   The built-in :ref:`download handlers <download-handlers-ref>` have been
    refactored, changing the signatures of their methods. This change should
    only affect user code that subclasses any of these handlers or calls their
    methods directly.
    (:gh:`6778`, :gh:`7164`)

-   :meth:`scrapy.pipelines.media.MediaPipeline.process_item` now returns a
    coroutine, previously it returned a
    :class:`~twisted.internet.defer.Deferred` object. This
    change only impacts code that calls this method directly.
    (:gh:`7177`)

Deprecation removals
~~~~~~~~~~~~~~~~~~~~

-   The ``from_settings()`` method of the following components, deprecated in
    Scrapy 2.12.0, is removed. You should use ``from_crawler()`` instead.

    - :class:`scrapy.dupefilters.RFPDupeFilter`
    - :class:`scrapy.mail.MailSender`
    - :class:`scrapy.middleware.MiddlewareManager`
    - :class:`scrapy.core.downloader.contextfactory.ScrapyClientContextFactory`
    - :class:`scrapy.pipelines.files.FilesPipeline`
    - :class:`scrapy.pipelines.images.ImagesPipeline`

    (:gh:`7126`)

-   Scrapy no longer calls ``from_settings()`` methods of 3rd-party
    :ref:`components <topics-components>`, deprecated in Scrapy 2.12.0. You
    should define a ``from_crawler()`` method instead.
    (:gh:`7126`)

-   The initialization flow of :class:`scrapy.pipelines.media.MediaPipeline`
    and its subclasses was simplified, it now mandates ``from_crawler()``
    methods and ``crawler`` arguments of ``__init__()`` methods. Not using
    these was deprecated in Scrapy 2.12.0.
    (:gh:`7126`)

-   The ``REQUEST_FINGERPRINTER_IMPLEMENTATION`` setting, deprecated in Scrapy
    2.12.0, is removed.
    (:gh:`7126`)

-   The ``scrapy.utils.misc.create_instance()`` function, deprecated in Scrapy
    2.12.0, is removed. Use :func:`scrapy.utils.misc.build_from_crawler`
    instead.
    (:gh:`7126`)

-   The ``scrapy.core.downloader.Downloader._get_slot_key()`` function,
    deprecated in Scrapy 2.12.0, is removed. Use
    :meth:`scrapy.core.downloader.Downloader.get_slot_key` instead.
    (:gh:`7126`)

-   The ``scrapy.twisted_version`` attribute, deprecated in Scrapy 2.12.0, is
    removed. You should instead use the :attr:`twisted.version` attribute
    directly.
    (:gh:`7126`)

-   The following utility functions, deprecated in Scrapy 2.12.0, are removed:

    - ``scrapy.utils.defer.process_chain_both()``
    - ``scrapy.utils.python.equal_attributes()``
    - ``scrapy.utils.python.flatten()``
    - ``scrapy.utils.python.iflatten()``
    - ``scrapy.utils.request.request_authenticate()``
    - ``scrapy.utils.test.assert_samelines()``

    (:gh:`7126`)

-   ``scrapy.utils.serialize.ScrapyJSONDecoder``, deprecated in Scrapy 2.12.0,
    is removed.
    (:gh:`7126`)

-   The ``scrapy.extensions.feedexport.build_storage()`` function, deprecated
    in Scrapy 2.12.0, is removed, you can instead call the builder callable
    directly.
    (:gh:`7126`)

-   ``scrapy.spidermiddlewares.offsite.OffsiteMiddleware``, deprecated in
    Scrapy 2.11.2, is removed.
    :class:`scrapy.downloadermiddlewares.offsite.OffsiteMiddleware` should be
    used instead.
    (:gh:`6926`)

Deprecations
~~~~~~~~~~~~

-   The following methods that return a
    :class:`~twisted.internet.defer.Deferred` are deprecated in favor of their
    coroutine-based replacements:

    - :class:`scrapy.core.downloader.handlers.DownloadHandlers`

        - ``download_request()`` (use
          :meth:`~scrapy.core.downloader.handlers.DownloadHandlers.download_request_async`)

    - :class:`scrapy.core.downloader.middleware.DownloaderMiddlewareManager`

        - ``download()`` (use
          :meth:`~scrapy.core.downloader.middleware.DownloaderMiddlewareManager.download_async`)

    - :class:`scrapy.core.engine.ExecutionEngine`

        - ``start()`` (use
          :meth:`~scrapy.core.engine.ExecutionEngine.start_async`)

        - ``stop()`` (use
          :meth:`~scrapy.core.engine.ExecutionEngine.stop_async`)

        - ``close()`` (use
          :meth:`~scrapy.core.engine.ExecutionEngine.close_async`)

        - ``open_spider()`` (use
          :meth:`~scrapy.core.engine.ExecutionEngine.open_spider_async`)

        - ``close_spider()`` (use
          :meth:`~scrapy.core.engine.ExecutionEngine.close_spider_async`)

        - ``download()`` (use
          :meth:`~scrapy.core.engine.ExecutionEngine.download_async`)

    - :class:`scrapy.core.scraper.Scraper`

        - ``open_spider()`` (use
          :meth:`~scrapy.core.scraper.Scraper.open_spider_async`)

        - ``call_spider()`` (use
          :meth:`~scrapy.core.scraper.Scraper.call_spider_async`)

        - ``close_spider()`` (use
          :meth:`~scrapy.core.scraper.Scraper.close_spider_async`)

        - ``handle_spider_output()`` (use
          :meth:`~scrapy.core.scraper.Scraper.handle_spider_output_async`)

        - ``start_itemproc()`` (use
          :meth:`~scrapy.core.scraper.Scraper.start_itemproc_async`)

    - :class:`scrapy.core.spidermw.SpiderMiddlewareManager`

        - ``scrape_response()`` (use
          :meth:`~scrapy.core.spidermw.SpiderMiddlewareManager.scrape_response_async`)

    - :class:`scrapy.crawler.Crawler`

        - ``stop()`` (use :meth:`~scrapy.crawler.Crawler.stop_async`)

    - :class:`scrapy.pipelines.ItemPipelineManager`

        - ``process_item()`` (use
          :meth:`~scrapy.pipelines.ItemPipelineManager.process_item_async`)

        - ``open_spider()`` (use
          :meth:`~scrapy.pipelines.ItemPipelineManager.open_spider_async`)

        - ``close_spider()`` (use
          :meth:`~scrapy.pipelines.ItemPipelineManager.close_spider_async`)

    - :class:`scrapy.signalmanager.SignalManager`

        - ``send_catch_log_deferred()`` (use
          :meth:`~scrapy.signalmanager.SignalManager.send_catch_log_async`)

    - ``scrapy.utils.signal.send_catch_log_deferred()`` (use
      :func:`scrapy.utils.signal.send_catch_log_async`)

    (:gh:`6791`, :gh:`6842`, :gh:`6979`, :gh:`6997`, :gh:`6999`,
    :gh:`7005`, :gh:`7043`, :gh:`7069`, :gh:`7161`, :gh:`7164`)

-   The following spider attributes are deprecated in favor of settings:

    - ``download_maxsize`` (use :setting:`DOWNLOAD_MAXSIZE`)

    - ``download_timeout`` (use :setting:`DOWNLOAD_TIMEOUT`)

    - ``download_warnsize`` (use :setting:`DOWNLOAD_WARNSIZE`)

    - ``max_concurrent_requests`` (use
      :setting:`CONCURRENT_REQUESTS_PER_DOMAIN`)

    - ``user_agent`` (use :setting:`USER_AGENT`)

    (:gh:`6988`, :gh:`6994`, :gh:`7038`, :gh:`7039`, :gh:`7117`,
    :gh:`7176`)

-   Returning a :class:`~twisted.internet.defer.Deferred` from the following
    user-defined functions is deprecated in favor of defining them as coroutine
    functions:

    - spider callbacks and errbacks (which was never officially supported and
      may work incorrectly)

    - the ``process_request()``, ``process_response()`` and
      ``process_exception()`` methods of custom downloader middlewares

    - the ``process_item()``, ``open_spider()`` and ``close_spider()`` methods
      of custom pipelines

    - signal handlers

    - the ``download_request()`` and ``close()`` methods of custom download
      handlers

    (:gh:`6718`, :gh:`6778`, :gh:`7069`, :gh:`7147`, :gh:`7148`,
    :gh:`7149`, :gh:`7150`, :gh:`7151`, :gh:`7161`, :gh:`7164`,
    :gh:`7179`)

-   Passing a ``spider`` argument to the following methods is deprecated:

    - :meth:`scrapy.core.spidermw.SpiderMiddlewareManager.process_start`

    - :meth:`scrapy.core.downloader.Downloader.fetch`

    - :meth:`scrapy.core.downloader.Downloader._get_slot`

    - :meth:`scrapy.core.downloader.handlers.DownloadHandlers.download_request`

    - all public methods of :class:`scrapy.statscollectors.StatsCollector`

    - :meth:`scrapy.spidermiddlewares.base.BaseSpiderMiddleware.process_spider_output`

    - :meth:`scrapy.spidermiddlewares.base.BaseSpiderMiddleware.process_spider_output_async`

    - all ``process_*()`` methods of built-in downloader middlewares

    - all ``process_*()`` methods of built-in spider middlewares

    - :meth:`scrapy.pipelines.media.MediaPipeline.open_spider`

    - :meth:`scrapy.pipelines.media.MediaPipeline.process_item`

    (:gh:`6750`, :gh:`6927`, :gh:`6984`, :gh:`7006`, :gh:`7011`,
    :gh:`7033`, :gh:`7037`, :gh:`7045`, :gh:`7178`)

-   Instantiating subclasses of :class:`scrapy.middleware.MiddlewareManager`
    without a :class:`~scrapy.crawler.Crawler` instance is deprecated.
    (:gh:`6984`)

-   For the following user-defined functions and methods requiring a ``spider``
    argument is deprecated, if you need a :class:`~scrapy.Spider` instance
    inside them you should get it from the :class:`~scrapy.crawler.Crawler`
    instance (you may need to refactor your code to save that instance in e.g.
    the ``from_crawler()`` method):

    - the ``process_request()``, ``process_response()`` and
      ``process_exception()`` methods of custom downloader middlewares

    - the ``process_spider_input()``, ``process_spider_output()``,
      ``process_spider_output_async()`` and ``process_spider_exception()``
      methods of custom spider middlewares

    - the ``process_item()`` method of custom pipelines

    - the ``fetch()`` method of a custom :setting:`DOWNLOADER`

    (:gh:`6927`, :gh:`6984`, :gh:`7006`, :gh:`7037`)

-   The following things in custom download handlers are deprecated:

    - not having a ``lazy`` attribute (you should define it as ``True`` if you
      want to keep the current behavior)

    - returning a :class:`~twisted.internet.defer.Deferred` from the
      ``download_request()`` method (you should refactor it to return a
      coroutine; you also need to remove the ``spider`` argument when doing
      this)

    - not having a ``close()`` method, having a synchronous one or one that
      returns a :class:`~twisted.internet.defer.Deferred` (you should refactor
      it to return a coroutine or add an empty one if you don't have it)

    (:gh:`6778`, :gh:`7164`)

-   Custom implementations of :setting:`ITEM_PROCESSOR` should now define
    ``process_item_async()``, ``open_spider_async()`` and
    ``close_spider_async()`` methods instead of, or in addition to,
    ``process_item()``, ``open_spider()`` and ``close_spider()``.
    (:gh:`7005`, :gh:`7043`)

-   The ``CONCURRENT_REQUESTS_PER_IP`` setting is deprecated, use
    :setting:`CONCURRENT_REQUESTS_PER_DOMAIN` instead.
    (:gh:`6917`, :gh:`6921`)

-   The ``scrapy.core.downloader.handlers.http`` module is deprecated. You
    should import
    :class:`scrapy.core.downloader.handlers.http11.HTTP11DownloadHandler`
    directly instead of importing the
    ``scrapy.core.downloader.handlers.http.HTTPDownloadHandler`` alias.
    (:gh:`7079`)

-   The ``scrapy.utils.decorators.defers()`` decorator is deprecated, you can
    use :func:`twisted.internet.defer.maybeDeferred` directly or reimplement
    this decorator in your code.
    (:gh:`7164`)

-   ``scrapy.spiders.CrawlSpider._parse_response()`` is deprecated, use
    :meth:`scrapy.spiders.CrawlSpider.parse_with_rules` instead.
    (:gh:`4463`, :gh:`6804`)

-   The functions that add a delay to a Deferred are deprecated, their
    underlying Twisted functions can be used instead, either directly if a
    delay isn't needed, or with some explicit way to add a delay if it's
    needed:

    - ``scrapy.utils.defer.mustbe_deferred()`` (you can use
      :func:`twisted.internet.defer.maybeDeferred`)

    - ``scrapy.utils.defer.defer_succeed()`` (you can use
      :func:`twisted.internet.defer.succeed`)

    - ``scrapy.utils.defer.defer_fail()`` (you can use
      :func:`twisted.internet.defer.fail`)

    - ``scrapy.utils.defer.defer_result()`` (you can use
      :func:`twisted.internet.defer.succeed` and
      :func:`twisted.internet.defer.fail`)

    (:gh:`6937`)

New features
~~~~~~~~~~~~

-   Added :class:`scrapy.crawler.AsyncCrawlerProcess` and
    :class:`scrapy.crawler.AsyncCrawlerRunner` as counterparts to
    :class:`~scrapy.crawler.CrawlerProcess` and
    :class:`~scrapy.crawler.CrawlerRunner` that offer coroutine-based APIs.
    (:gh:`6789`, :gh:`6790`, :gh:`6796`, :gh:`6817`, :gh:`6845`,
    :gh:`7034`)

-   Added coroutine counterparts to some of the Deferred-based APIs:

    - :class:`scrapy.core.downloader.handlers.DownloadHandlers`

        - :meth:`~scrapy.core.downloader.handlers.DownloadHandlers.download_request_async`
          (to ``download_request()``)

    - :class:`scrapy.core.downloader.middleware.DownloaderMiddlewareManager`

        - :meth:`~scrapy.core.downloader.middleware.DownloaderMiddlewareManager.download_async`
          (to ``download()``)

    - :class:`scrapy.core.engine.ExecutionEngine`

        - :meth:`~scrapy.core.engine.ExecutionEngine.start_async` (to
          ``start()``)

        - :meth:`~scrapy.core.engine.ExecutionEngine.stop_async` (to
          ``stop()``)

        - :meth:`~scrapy.core.engine.ExecutionEngine.close_async` (to
          ``close()``)

        - :meth:`~scrapy.core.engine.ExecutionEngine.open_spider_async` (to
          ``open_spider()``)

        - :meth:`~scrapy.core.engine.ExecutionEngine.close_spider_async` (to
          ``close_spider()``)

        - :meth:`~scrapy.core.engine.ExecutionEngine.download_async` (to
          ``download()``)

    - :class:`scrapy.core.scraper.Scraper`

        - :meth:`~scrapy.core.scraper.Scraper.open_spider_async` (to
          ``open_spider()``)

        - :meth:`~scrapy.core.scraper.Scraper.close_spider_async` (to
          ``close_spider()``)

        - :meth:`~scrapy.core.scraper.Scraper.start_itemproc_async` (to
          ``start_itemproc()``)

    - :class:`scrapy.crawler.Crawler`

        - :meth:`~scrapy.crawler.Crawler.crawl_async` (to ``crawl()``)

        - :meth:`~scrapy.crawler.Crawler.stop_async` (to ``stop()``)

    - :class:`scrapy.pipelines.ItemPipelineManager`

        - :meth:`~scrapy.pipelines.ItemPipelineManager.process_item_async` (to
          ``process_item()``)

        - :meth:`~scrapy.pipelines.ItemPipelineManager.open_spider_async` (to
          ``open_spider()``)

        - :meth:`~scrapy.pipelines.ItemPipelineManager.close_spider_async` (to
          ``close_spider()``)

    - :class:`scrapy.signalmanager.SignalManager`

        - :meth:`~scrapy.signalmanager.SignalManager.send_catch_log_async` (to
          ``send_catch_log_deferred()``)

    (:gh:`6781`, :gh:`6791`, :gh:`6792`, :gh:`6795`, :gh:`6801`,
    :gh:`6817`, :gh:`6842`, :gh:`6997`, :gh:`7005`, :gh:`7043`,
    :gh:`7069`,:gh:`7164`, :gh:`7202`)

-   The default value of the :setting:`SCHEDULER_PRIORITY_QUEUE` setting is now
    ``'scrapy.pqueues.DownloaderAwarePriorityQueue'``.
    (:gh:`6924`, :gh:`6940`)

-   Added :class:`scrapy.extensions.logcount.LogCount`, an enabled-by-default
    extension that is responsible for the ``log_count/*`` stats. Previously,
    this code was in :class:`scrapy.crawler.Crawler` and couldn't be disabled.
    (:gh:`7046`)

-   Added :meth:`scrapy.spiders.CrawlSpider.parse_with_rules` as a public
    replacement for ``_parse_response()``.
    (:gh:`4463`, :gh:`6804`)

-   Added :func:`scrapy.utils.asyncio.is_asyncio_available` as an alternative
    to ``scrapy.utils.reactor.is_asyncio_reactor_installed`` with a
    future-proof name and semantics.
    (:gh:`6827`)

-   The API for :ref:`download handlers <topics-download-handlers>`, previously
    undocumented, has been modernized and documented. An optional base class,
    :class:`scrapy.core.downloader.handlers.base.BaseDownloadHandler`, has been
    added to simplify writing custom download handlers that conform to the
    current API.
    (:gh:`4944`, :gh:`6778`, :gh:`7164`)

-   Added :func:`scrapy.utils.defer.ensure_awaitable`, which can be helpful to
    call user-defined functions that can return coroutines, Deferreds or
    values directly.
    (:gh:`7005`)

-   The ``requests.seen`` file, written by
    :class:`~scrapy.dupefilters.RFPDupeFilter` when :ref:`job persistence
    <topics-jobs>` is enabled, now uses line buffering to reduce data loss in
    spider crashes.
    (:gh:`6019`, :gh:`7094`)

-   Images downloaded by :class:`~scrapy.pipelines.images.ImagesPipeline` are
    now automatically transposed based on EXIF data.
    (:gh:`6525`, :gh:`6975`)

Improvements
~~~~~~~~~~~~

-   Refactored internal functions to use coroutines instead of Deferreds.
    (:gh:`6795`, :gh:`6852`, :gh:`6855`, :gh:`6858`, :gh:`7159`)

-   Commands that don't need a :class:`~scrapy.crawler.CrawlerProcess` instance
    no longer create it.
    (:gh:`6824`)

-   Improved :command:`shell` help formatting when using IPython 9+.
    (:gh:`6915`, :gh:`6980`)

Bug fixes
~~~~~~~~~

-   Setting :setting:`FILES_STORE` or :setting:`IMAGES_STORE` to ``None`` now
    correctly disables the respective pipeline.
    (:gh:`6964`, :gh:`6969`)

-   :class:`~scrapy.downloadermiddlewares.redirect.MetaRefreshMiddleware` now
    uses the URL set in the ``<base>`` tag as the base URL when redirecting to
    a relative URL.
    (:gh:`7042`, :gh:`7047`)

-   Passing ``None`` as a value of the :reqmeta:`download_slot` request meta
    key is now handled in the same way as not setting this meta key at all.
    (:gh:`7172`)

-   Fixed parsing of the first line of ``robots.txt`` files that have a BOM.
    (:gh:`6195`, :gh:`7095`)

Documentation
~~~~~~~~~~~~~

-   Added :ref:`documentation <topics-download-handlers>` about download
    handlers, their API and built-in handlers.
    (:gh:`4944`, :gh:`7164`)

-   Added a section about the `scrapy-spider-metadata`_ library to the
    :ref:`spider argument docs <spiderargs-scrapy-spider-metadata>`.
    (:gh:`6676`, :gh:`6957`, :gh:`7116`)

    .. _scrapy-spider-metadata: https://scrapy-spider-metadata.readthedocs.io/en/latest/

-   Improved :ref:`the docs <coroutine-deferred-apis>` about coroutine-based
    and Deferred-based APIs.
    (:gh:`6800`, :gh:`7146`)

-   Other documentation improvements and fixes.
    (:gh:`7058`, :gh:`7076`, :gh:`7109`, :gh:`7195`, :gh:`7198`)

Quality assurance
~~~~~~~~~~~~~~~~~

-   Switched from ``twisted.trial`` to ``pytest-twisted`` and replaced
    remaining ``unittest`` and ``twisted.trial`` features with ``pytest`` ones.
    (:gh:`6658`, :gh:`6873`, :gh:`6884`, :gh:`6938`)

-   Enabled fancy ``pytest`` asserts.
    (:gh:`6888`)

-   Added `Sphinx Lint`_ to the ``pre-commit`` configuration.
    (:gh:`6920`)

    .. _Sphinx Lint: https://github.com/sphinx-contrib/sphinx-lint

-   CI and test improvements and fixes.
    (:gh:`6649`,
    :gh:`6769`,
    :gh:`6821`,
    :gh:`6835`,
    :gh:`6836`,
    :gh:`6846`,
    :gh:`6883`,
    :gh:`6885`,
    :gh:`6889`,
    :gh:`6905`,
    :gh:`6928`,
    :gh:`6933`,
    :gh:`6941`,
    :gh:`6942`,
    :gh:`6945`,
    :gh:`6947`,
    :gh:`6960`,
    :gh:`6968`,
    :gh:`6972`,
    :gh:`6974`,
    :gh:`6996`,
    :gh:`7003`,
    :gh:`7012`,
    :gh:`7013`,
    :gh:`7050`,
    :gh:`7059`,
    :gh:`7070`,
    :gh:`7073`,
    :gh:`7118`,
    :gh:`7127`,
    :gh:`7141`,
    :gh:`7143`,
    :gh:`7145`,
    :gh:`7173`)

-   Code cleanups.
    (:gh:`6803`,
    :gh:`6838`,
    :gh:`6849`,
    :gh:`6875`,
    :gh:`6876`,
    :gh:`6892`,
    :gh:`6930`,
    :gh:`6949`,
    :gh:`6970`,
    :gh:`6977`,
    :gh:`6986`,
    :gh:`7008`,
    :gh:`7177`)

Older releases
--------------

.. Once the first release of a minor version series is over a year old,
   move the whole series to news/2.x.rst.

.. toctree::
   :maxdepth: 1

   news/2.x
   news/1.x
   news/0.x


.. _aioboto3: https://github.com/terricain/aioboto3
.. _aiodns: https://github.com/aio-libs/aiodns
.. _aioftp: https://github.com/aio-libs/aioftp
.. _aiohttp: https://docs.aiohttp.org/en/stable/
.. _boto3: https://github.com/boto/boto3
.. _botocore: https://github.com/boto/botocore
.. _charset-normalizer: https://charset-normalizer.readthedocs.io/en/latest/
.. _cryptography: https://cryptography.io/en/latest/
.. _cssselect: https://github.com/scrapy/cssselect
.. _formerly: https://github.com/scrapy/formerly
.. _frostwork: https://github.com/scrapy/frostwork
.. _google-cloud-storage: https://github.com/googleapis/python-storage
.. _httpx2: https://github.com/pydantic/httpx2
.. _ipdb: https://github.com/gotcha/ipdb
.. _itemloaders: https://github.com/scrapy/itemloaders
.. _lxml: https://lxml.de/
.. _parsel: https://github.com/scrapy/parsel
.. _parso: https://github.com/davidhalter/parso
.. _platformdirs: https://platformdirs.readthedocs.io/en/latest/
.. _Pillow: https://github.com/python-pillow/Pillow
.. _Protego: https://github.com/scrapy/protego
.. _ptpython: https://github.com/prompt-toolkit/ptpython
.. _pyOpenSSL: https://www.pyopenssl.org/en/stable/
.. _queuelib: https://github.com/scrapy/queuelib
.. _service_identity: https://service-identity.readthedocs.io/en/stable/
.. _Twisted: https://twisted.org/
.. _typing-extensions: https://github.com/python/typing_extensions
.. _uvloop: https://github.com/MagicStack/uvloop
.. _w3lib: https://github.com/scrapy/w3lib
.. _zope.interface: https://zopeinterface.readthedocs.io/en/latest/
