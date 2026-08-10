.. _news:

Release notes
=============

Scrapy VERSION (unreleased)
---------------------------

Highlights:

-   ``HttpxDownloadHandler`` now uses `httpx2 <https://httpx2.pydantic.dev/>`__

-   ``brotli`` is now a required dependency, and :ref:`optional extras
    <extras>` cover the rest of the optional features

-   Late :class:`~scrapy.crawler.Crawler` attributes, such as
    :attr:`~scrapy.crawler.Crawler.stats`, now raise :exc:`RuntimeError`
    instead of being ``None`` before the crawl starts

-   Item exporters now export fields in declaration order

-   New :class:`~scrapy.spidermiddlewares.metacopy.MetaCopyDetectionMiddleware`

-   New :ref:`optimization <optimize>` page and :ref:`built-in stats reference
    <topics-stats-reference>`

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

-   ``brotli`` (``brotlicffi`` on PyPy) is now a required dependency, so ``br``
    is always included in the ``Accept-Encoding`` header of requests, and
    Brotli-compressed responses are always decoded. Websites may now serve
    Brotli-compressed responses to crawls that previously did not advertise
    support for them.

    The minimum required versions are ``brotli`` 1.2.0 and ``brotlicffi``
    1.2.0.0.

    (:gh:`4698`, :gh:`7929`)

-   The minimum required ``queuelib`` version is now 1.6.1.
    (:gh:`7874`)

-   :ref:`Item exporters <topics-exporters>` other than
    :class:`~scrapy.exporters.CsvItemExporter` now export the fields of an item
    in declaration order, i.e. the order in which they are defined in the
    :ref:`item class <item-types>`, instead of the order in which they were
    populated. :class:`dict` items, which have no declared fields, keep using
    the key order of each item.
    (:gh:`6662`, :gh:`7824`)

-   The ``_get_serialized_fields()`` method of :ref:`item exporters
    <topics-exporters>` is renamed to
    :meth:`~scrapy.exporters.BaseItemExporter.get_serialized_fields`, and the
    old name is gone, so :ref:`custom item exporters <custom-exporters>` that
    call or override it must be updated.
    (:gh:`5706`, :gh:`7931`)

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
    reading it now gets ``None`` instead of its default value, an empty list.
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

    (:gh:`5570`, :gh:`7936`)

-   :setting:`FEEDS` keys and ``FEED_URI`` values that are
    :class:`pathlib.Path` objects are now used as paths, instead of being
    converted into ``file://`` URIs. This makes them keep working when they
    contain :ref:`URI parameters <topics-feed-uri-params>` or characters that
    URI conversion would percent-encode.
    (:gh:`5794`, :gh:`6425`, :gh:`6611`, :gh:`7674`)

-   :class:`~scrapy.Selector` and :attr:`TextResponse.selector
    <scrapy.http.TextResponse.selector>` no longer force the ``html`` selector
    type for responses that are neither :class:`~scrapy.http.HtmlResponse` nor
    :class:`~scrapy.http.XmlResponse` objects, e.g. for a JSON response.
    ``parsel`` determines the type from the body in those cases instead.
    (:gh:`5291`, :gh:`6025`, :gh:`7924`)

-   :ref:`AutoThrottle <topics-autothrottle>` no longer sets the
    ``download_delay`` attribute of the running spider to define the starting
    delay of download slots. The starting delay is still applied, but code
    that reads that attribute at run time no longer sees it.
    (:gh:`7167`, :gh:`7175`, :gh:`7833`)

-   :class:`~scrapy.spiders.XMLFeedSpider` and
    :class:`~scrapy.spiders.CSVFeedSpider` no longer raise
    :exc:`~scrapy.exceptions.NotConfigured` when ``parse_node()`` or
    ``parse_row()`` is not defined; the resulting :exc:`AttributeError` is
    reported instead.
    (:gh:`7768`)

-   ``scrapy.pipelines.files.FileException`` moved to
    ``scrapy.pipelines.media``. It is still importable from its old location.
    (:gh:`7544`, :gh:`7673`)

-   ``H2ConnectionPool``, ``H2ClientFactory`` and ``H2ClientProtocol``, from
    ``scrapy.core.http2``, now take a :class:`~scrapy.crawler.Crawler` object
    where they used to take a :class:`~scrapy.settings.Settings` object, and
    ``scrapy.core.http2.stream.Stream`` takes an additional ``crawler``
    parameter, after ``protocol``.
    (:gh:`7896`)

-   :class:`~scrapy.downloadermiddlewares.offsite.OffsiteMiddleware` now raises
    :exc:`~scrapy.exceptions.IgnoreRequest` with a message, e.g. ``Filtered
    offsite request to 'offsite.example'``, which errbacks and log messages that
    report that exception now include.
    (:gh:`7544`, :gh:`7673`)

-   The unused ``multiplier`` attribute of
    :class:`~scrapy.extensions.periodic_log.PeriodicLog` is removed.
    (:gh:`7809`)

-   The IPython :ref:`shell <topics-shell>` requires IPython 8.15.0 or higher.
    Install the :ref:`ipython extra <extras>` to get a compatible version.
    (:gh:`5447`, :gh:`7596`, :gh:`7816`)

Deprecation removals
~~~~~~~~~~~~~~~~~~~~

-   ``scrapy.utils.iterators.xmliter()``, deprecated since Scrapy 2.11.1
    because it is vulnerable to ReDoS attacks, is removed. Use
    :func:`~scrapy.utils.iterators.xmliter_lxml` instead.
    (:gh:`7765`)

Deprecations
~~~~~~~~~~~~

-   The ``download_delay`` spider attribute is deprecated. Use the
    :setting:`DOWNLOAD_DELAY` setting, or :setting:`DOWNLOAD_SLOTS` to set a
    delay for specific domains, instead.

    The ``max_concurrent_requests`` spider attribute, deprecated since Scrapy
    2.13.0, now sets the :setting:`CONCURRENT_REQUESTS_PER_DOMAIN` setting,
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

-   Setting ``request.meta["is_secure"]`` to ``False`` to send an ``s3://``
    request over plaintext HTTP is deprecated. The flag will be ignored in a
    future Scrapy version.
    (:gh:`7738`)

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
    ``ptpython``, ``robotparser``, ``s3``, ``twisted-http2``, ``uvloop`` and
    ``zstd``. For example, ``pip install scrapy[s3,images]``.
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

-   :class:`~scrapy.core.downloader.handlers.http2.H2DownloadHandler` now sends
    the :signal:`bytes_received` and :signal:`headers_received` signals, and
    supports :exc:`~scrapy.exceptions.StopDownload`.
    (:gh:`5046`, :gh:`5055`, :gh:`7896`)

-   An exception raised by :meth:`Spider.start() <scrapy.Spider.start>` is now
    reported through the :signal:`spider_error` signal and the
    :stat:`spider_exceptions/count` and :stat:`spider_exceptions/{exception}`
    stats, and closes the spider with the new ``start_error``
    :stat:`finish_reason` instead of ``finished``. See :ref:`start-error`.

    :exc:`~scrapy.exceptions.CloseSpider` raised from :meth:`Spider.start()
    <scrapy.Spider.start>` now closes the spider with the given reason, instead
    of being reported as a start error.

    (:gh:`3463`, :gh:`4182`, :gh:`7884`)

-   :exc:`~scrapy.exceptions.CloseSpider` can now also be raised while the
    spider is starting, e.g. from a :signal:`spider_opened` signal handler or
    from the ``open_spider()`` method of an :ref:`item pipeline
    <topics-item-pipeline>`, to close the spider before it starts crawling.
    Every component still gets started, and stopped, before the spider is
    closed with the given reason.
    (:gh:`3435`, :gh:`7905`)

-   Added an :ref:`FTPS feed storage backend <feed-storage-ftps>`, i.e. support
    for the ``ftps`` URI scheme in :setting:`FEEDS`, which uploads the feed over
    a TLS connection, verifying the certificate of the server.
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

-   Log formatters (:setting:`LOG_FORMATTER`), item processors
    (``ITEM_PROCESSOR``) and :ref:`robots.txt parsers <topics-dlmw-robots>`
    (:setting:`ROBOTSTXT_PARSER`) are now built as :ref:`components
    <topics-components>`, so they no longer need a ``from_crawler()`` method.
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
    (:gh:`3095`, :gh:`7803`)

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

-   Fixed :exc:`NameError` exceptions on Python 3.14, where :pep:`649` made
    annotation evaluation lazy, when inspecting the signature of a callable
    with annotations imported only for type checking.
    (:gh:`7796`, :gh:`7818`)

-   ``scrapy.utils.decorators.deprecated`` can now be used both as
    ``@deprecated`` and as ``@deprecated(...)`` without confusing type
    checkers.
    (:gh:`7797`)

Documentation
~~~~~~~~~~~~~

-   Added a :ref:`built-in stats reference <topics-stats-reference>`, covering
    every stat that Scrapy sets.
    (:gh:`6351`, :gh:`7814`)

-   Replaced the broad crawls page with a new :ref:`optimization <optimize>`
    page, about finding the bottleneck of a crawl before changing any setting,
    which covers :ref:`broad crawls <broad-crawls>` as one of its sections.
    (:gh:`4737`, :gh:`7938`)

-   Added a :ref:`cookies <cookies>` page, which gathers what used to be
    spread across the request and downloader middleware pages.
    (:gh:`7947`)

-   Added :ref:`callbacks <callbacks>` and :ref:`errbacks <errbacks>` sections
    to the request and response page, covering :ref:`callback assignment
    <callback-assignment>`, :ref:`how to write a callback <writing-callbacks>`
    and :ref:`supported callback output <callback-output>`.
    (:gh:`5054`, :gh:`6437`, :gh:`7821`, :gh:`7898`)

-   Documented the :ref:`optional extras <extras>` of Scrapy, and which feature
    each of them enables.
    (:gh:`7596`)

-   Documented :ref:`how to write an item exporter <custom-exporters>`,
    :ref:`how to test an item pipeline <test-item-pipeline>`, :ref:`how to
    download a request from a downloader middleware <mw-download>`, :ref:`how
    to name media files after the response <file-naming-response>`, :ref:`how
    to add objects to the shell <shell-update-vars>` and :ref:`how to run
    spiders inside an existing application <run-spiders-in-apps>` or :ref:`in a
    Jupyter notebook <run-in-notebook>`.
    (:gh:`1199`,
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

-   Switched several API references to autodoc, so that they are generated from
    the docstrings: contracts, download handlers, exceptions, spider loaders,
    stats collectors, ``trackref``, and the depth and offsite middlewares.
    (:gh:`7767`,
    :gh:`7769`,
    :gh:`7771`,
    :gh:`7775`,
    :gh:`7871`,
    :gh:`7903`,
    :gh:`7913`)

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
    :gh:`7774`,
    :gh:`7777`,
    :gh:`7779`,
    :gh:`7780`,
    :gh:`7817`,
    :gh:`7832`,
    :gh:`7835`,
    :gh:`7862`,
    :gh:`7875`,
    :gh:`7880`,
    :gh:`7890`,
    :gh:`7917`,
    :gh:`7939`,
    :gh:`7940`,
    :gh:`7962`,
    :gh:`7965`)

Quality assurance
~~~~~~~~~~~~~~~~~

-   Added CPU benchmarks, tracked on CodSpeed, and a ``benchmark`` tox
    environment to run them.
    (:gh:`7831`,
    :gh:`7839`,
    :gh:`7870`,
    :gh:`7887`,
    :gh:`7914`,
    :gh:`7954`)

-   Added a nightly job that runs the test suite against the development
    branches of dependencies, and a ``vcs-deps`` tox environment for it.
    (:gh:`5291`, :gh:`6025`, :gh:`7924`, :gh:`7960`)

-   Tests that need a proxy server now look for a ``mitmdump`` executable, from
    the ``PATH``, from `uv <https://docs.astral.sh/uv/>`__ or from the
    ``MITMDUMP`` environment variable, instead of requiring mitmproxy to be
    installed in the test environment. The ``mitmproxy`` tox environment is
    gone as a result.
    (:gh:`7437`, :gh:`7720`)

-   Dropped the ``testfixtures`` test dependency.
    (:gh:`6478`, :gh:`7793`)

-   Type hints improvements and fixes.
    (:gh:`7712`,
    :gh:`7785`,
    :gh:`7858`,
    :gh:`7864`,
    :gh:`7865`,
    :gh:`7867`)

-   CI and test improvements and fixes.
    (:gh:`5620`,
    :gh:`5837`,
    :gh:`6478`,
    :gh:`6794`,
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
    :gh:`7795`,
    :gh:`7797`,
    :gh:`7798`,
    :gh:`7809`,
    :gh:`7829`,
    :gh:`7834`,
    :gh:`7836`,
    :gh:`7838`,
    :gh:`7844`,
    :gh:`7848`,
    :gh:`7853`,
    :gh:`7857`,
    :gh:`7863`,
    :gh:`7895`,
    :gh:`7906`,
    :gh:`7928`,
    :gh:`7935`,
    :gh:`7966`)

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
    :func:`scrapy.utils.versions.get_versions` instead.
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

-   If you set the :setting:`TWISTED_REACTOR` setting to a :ref:`non-asyncio
    value <disable-asyncio>` at the :ref:`spider level <spider-settings>`, you
    may now need to set the :setting:`FORCE_CRAWLER_PROCESS` setting to
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
    to :func:`scrapy.utils.reactor.is_asyncio_reactor_installed` with a
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

.. _release-2.13.4:

Scrapy 2.13.4 (2025-11-17)
--------------------------

Security bug fixes
~~~~~~~~~~~~~~~~~~

-   Improved protection against decompression bombs in
    :class:`~scrapy.downloadermiddlewares.httpcompression.HttpCompressionMiddleware`
    for responses compressed using the ``br`` and ``deflate`` methods: if a
    single compressed chunk would be larger than the response size limit (see
    :setting:`DOWNLOAD_MAXSIZE`) when decompressed, decompression is no longer
    carried out. This is especially important for the ``br`` (Brotli) method
    that can provide a very high compression ratio. Please, see the
    `CVE-2025-6176`_ and `GHSA-2qfp-q593-8484`_ security advisories for more
    information.
    (:gh:`7134`)

    .. _CVE-2025-6176: https://nvd.nist.gov/vuln/detail/CVE-2025-6176
    .. _GHSA-2qfp-q593-8484: https://github.com/advisories/GHSA-2qfp-q593-8484

Modified requirements
~~~~~~~~~~~~~~~~~~~~~

-   The minimum supported version of the optional ``brotli`` package is now
    ``1.2.0``.
    (:gh:`7134`)

-   The ``brotlicffi`` and ``brotlipy`` packages can no longer be used to
    decompress Brotli-compressed responses. Please install the ``brotli``
    package instead.
    (:gh:`7134`)

Other changes
~~~~~~~~~~~~~

-   Restricted the maximum supported Twisted version to ``25.5.0``, as Scrapy
    currently uses some private APIs changed in later Twisted versions.
    (:gh:`7142`)

-   Stopped setting the ``COVERAGE_CORE`` environment variable in tests, it
    didn't have an effect but caused the ``coverage`` module to produce a
    warning or an error.
    (:gh:`7137`)

-   Removed the documentation build dependency on the deprecated
    ``sphinx-hoverxref`` module.
    (:gh:`6786`, :gh:`6922`)

.. _release-2.13.3:

Scrapy 2.13.3 (2025-07-02)
--------------------------

-   Changed the values for :setting:`DOWNLOAD_DELAY` (from ``0`` to ``1``) and
    :setting:`CONCURRENT_REQUESTS_PER_DOMAIN` (from ``8`` to ``1``) in the
    default project template.
    (:gh:`6597`, :gh:`6918`, :gh:`6923`)

-   Improved :class:`scrapy.core.engine.ExecutionEngine` logic related to
    initialization and exception handling, fixing several cases where the
    spider would crash, hang or log an unhandled exception.
    (:gh:`6783`, :gh:`6784`, :gh:`6900`, :gh:`6908`, :gh:`6910`,
    :gh:`6911`)

-   Fixed a Windows issue with :ref:`feed exports <topics-feed-exports>` using
    :class:`scrapy.extensions.feedexport.FileFeedStorage` that caused the file
    to be created on the wrong drive.
    (:gh:`6894`, :gh:`6897`)

-   Allowed running tests with Twisted 25.5.0+ again. Pytest 8.4.1+ is now
    required for running tests in non-pinned envs as support for the new
    Twisted version was added in that version.
    (:gh:`6893`)

-   Fixed running tests with lxml 6.0.0+.
    (:gh:`6919`)

-   Added a deprecation notice for
    ``scrapy.spidermiddlewares.offsite.OffsiteMiddleware`` to :ref:`the Scrapy
    2.11.2 release notes <release-2.11.2>`.
    (:gh:`6926`)

-   Updated :ref:`contribution docs <topics-contributing>` to refer to ruff_
    instead of black_.
    (:gh:`6903`)

-   Added ``.venv/`` and ``.vscode/`` to ``.gitignore``.
    (:gh:`6901`, :gh:`6907`)


.. _release-2.13.2:

Scrapy 2.13.2 (2025-06-09)
--------------------------

-   Fixed a bug introduced in Scrapy 2.13.0 that caused results of request
    errbacks to be ignored when the errback was called because of a downloader
    error.
    (:gh:`6861`, :gh:`6863`)

-   Added a note about the behavior change of
    :func:`scrapy.utils.reactor.is_asyncio_reactor_installed` to its docs and
    to the "Backward-incompatible changes" section of :ref:`the Scrapy 2.13.0
    release notes <release-2.13.0>`.
    (:gh:`6866`)

-   Improved the message in the exception raised by
    :func:`scrapy.utils.test.get_reactor_settings` when there is no reactor
    installed.
    (:gh:`6866`)

-   Updated the :class:`scrapy.crawler.CrawlerRunner` examples in
    :ref:`topics-practices` to install the reactor explicitly, to fix
    reactor-related errors with Scrapy 2.13.0 and later.
    (:gh:`6865`)

-   Fixed ``scrapy fetch`` not working with scrapy-poet_.
    (:gh:`6872`)

-   Fixed an exception produced by :class:`scrapy.core.engine.ExecutionEngine`
    when it's closed before being fully initialized.
    (:gh:`6857`, :gh:`6867`)

-   Improved the README, updated the Scrapy logo in it.
    (:gh:`6831`, :gh:`6833`, :gh:`6839`)

-   Restricted the Twisted version used in tests to below 25.5.0, as some tests
    fail with 25.5.0.
    (:gh:`6878`, :gh:`6882`)

-   Updated type hints for Twisted 25.5.0 changes.
    (:gh:`6882`)

-   Removed the old artwork.
    (:gh:`6874`)


.. _release-2.13.1:

Scrapy 2.13.1 (2025-05-28)
--------------------------

-   Give callback requests precedence over start requests when priority values
    are the same.

    This makes changes from 2.13.0 to start request handling more intuitive and
    backward compatible. For scenarios where all requests have the same
    priorities, in 2.13.0 all start requests were sent before the first
    callback request. In 2.13.1, same as in 2.12 and lower, start requests are
    only sent when there are not enough pending callback requests to reach
    concurrency limits.

    (:gh:`6828`)

-   Added a deepwiki_ badge to the README. (:gh:`6793`)

    .. _deepwiki: https://deepwiki.com/scrapy/scrapy

-   Fixed a typo in the code example of :ref:`start-requests-lazy`.
    (:gh:`6812`, :gh:`6815`)

-   Fixed a typo in the :ref:`coroutine-support` section of the documentation.
    (:gh:`6822`)

-   Made this page more prominently listed in PyPI project links.
    (:gh:`6826`)


.. _release-2.13.0:

Scrapy 2.13.0 (2025-05-08)
--------------------------

Highlights:

-   The asyncio reactor is now enabled by default

-   Replaced ``start_requests()`` (sync) with :meth:`~scrapy.Spider.start`
    (async) and changed how it is iterated

-   Added the :reqmeta:`allow_offsite` request meta key

-   Spider middlewares that don't support asynchronous spider output are
    deprecated

-   Added a base class for :ref:`universal spider middlewares
    <universal-spider-middleware>`

Modified requirements
~~~~~~~~~~~~~~~~~~~~~

-   Dropped support for PyPy 3.9.
    (:gh:`6613`)

-   Added support for PyPy 3.11.
    (:gh:`6697`)

Backward-incompatible changes
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

-   The default value of the :setting:`TWISTED_REACTOR` setting was changed
    from ``None`` to
    ``"twisted.internet.asyncioreactor.AsyncioSelectorReactor"``. This value
    was used in newly generated projects since Scrapy 2.7.0 but now existing
    projects that don't explicitly set this setting will also use the asyncio
    reactor. You can :ref:`change this setting in your project
    <disable-asyncio>` to use a different reactor.
    (:gh:`6659`, :gh:`6713`)

-   The iteration of start requests and items no longer stops once there are
    requests in the scheduler, and instead runs continuously until all start
    requests have been scheduled.

    To reproduce the previous behavior, see :ref:`start-requests-lazy`.
    (:gh:`6729`)

-   An unhandled exception from the
    :meth:`~scrapy.spidermiddlewares.SpiderMiddleware.open_spider` method of a
    :ref:`spider middleware <topics-spider-middleware>` no longer stops the
    crawl.
    (:gh:`6729`)

-   In ``scrapy.core.engine.ExecutionEngine``:

    -   The second parameter of ``open_spider()``, ``start_requests``, has been
        removed. The start requests are determined by the ``spider`` parameter
        instead (see :meth:`~scrapy.Spider.start`).

    -   The ``slot`` attribute has been renamed to ``_slot`` and should not be
        used.

    (:gh:`6729`)

-   In ``scrapy.core.engine``, the ``Slot`` class has been renamed to ``_Slot``
    and should not be used.
    (:gh:`6729`)

-   The ``slot`` :ref:`telnet variable <telnet-vars>` has been removed.
    (:gh:`6729`)

-   In ``scrapy.core.spidermw.SpiderMiddlewareManager``,
    ``process_start_requests()`` has been replaced by ``process_start()``.
    (:gh:`6729`)

-   The ``scrape_func`` callable passed to
    ``scrapy.core.spidermw.SpiderMiddlewareManager.scrape_response()`` is now
    called with 2 parameters, ``response`` and ``request``, instead of 3, and
    must return a :class:`~twisted.internet.defer.Deferred` instead of an
    iterable.
    (:gh:`6787`)

-   The now-deprecated ``start_requests()`` method, when it returns an iterable
    instead of being defined as a generator, is now executed *after* the
    :ref:`scheduler <topics-scheduler>` instance has been created.
    (:gh:`6729`)

-   When using :setting:`JOBDIR`, :ref:`start requests <start-requests>` are
    now serialized into their own, ``s``-suffixed priority folders. You can set
    :setting:`SCHEDULER_START_DISK_QUEUE` to ``None`` or ``""`` to change that,
    but the side effects may be undesirable. See
    :setting:`SCHEDULER_START_DISK_QUEUE` for details.
    (:gh:`6729`)

-   The URL length limit, set by the :setting:`URLLENGTH_LIMIT` setting, is now
    also enforced for start requests.
    (:gh:`6777`)

-   Calling :func:`scrapy.utils.reactor.is_asyncio_reactor_installed` without
    an installed reactor now raises an exception instead of installing a
    reactor. This shouldn't affect normal Scrapy use cases, but it may affect
    3rd-party test suites that use Scrapy internals such as
    :class:`~scrapy.crawler.Crawler` and don't install a reactor explicitly. If
    you are affected by this change, you most likely need to install the
    reactor before running Scrapy code that expects it to be installed.
    (:gh:`6732`, :gh:`6735`)

-   The ``from_settings()`` method of
    :class:`~scrapy.spidermiddlewares.urllength.UrlLengthMiddleware`,
    deprecated in Scrapy 2.12.0, is removed earlier than the usual deprecation
    period (this was needed because after the introduction of the
    :class:`~scrapy.spidermiddlewares.base.BaseSpiderMiddleware` base class and
    switching built-in spider middlewares to it those middlewares need the
    :class:`~scrapy.crawler.Crawler` instance at run time). Please use
    ``from_crawler()`` instead.
    (:gh:`6693`)

-   ``scrapy.utils.url.escape_ajax()`` is no longer called when a
    :class:`~scrapy.Request` instance is created. It was only useful for
    websites supporting the ``_escaped_fragment_`` feature which most modern
    websites don't support. If you still need this you can modify the URLs
    before passing them to :class:`~scrapy.Request`.
    (:gh:`6523`, :gh:`6651`)

Deprecation removals
~~~~~~~~~~~~~~~~~~~~

-   Removed old deprecated name aliases for some signals:

    - ``stats_spider_opened`` (use ``spider_opened`` instead)

    - ``stats_spider_closing`` and ``stats_spider_closed`` (use
      ``spider_closed`` instead)

    - ``item_passed`` (use ``item_scraped`` instead)

    - ``request_received`` (use ``request_scheduled`` instead)

    (:gh:`6654`, :gh:`6655`)

Deprecations
~~~~~~~~~~~~

-   The ``start_requests()`` method of :class:`~scrapy.Spider` is deprecated,
    use :meth:`~scrapy.Spider.start` instead, or both to maintain support for
    lower Scrapy versions.
    (:gh:`456`, :gh:`3477`, :gh:`4467`, :gh:`5627`, :gh:`6729`)

-   The ``process_start_requests()`` method of :ref:`spider middlewares
    <topics-spider-middleware>` is deprecated, use
    :meth:`~scrapy.spidermiddlewares.SpiderMiddleware.process_start` instead,
    or both to maintain support for lower Scrapy versions.
    (:gh:`456`, :gh:`3477`, :gh:`4467`, :gh:`5627`, :gh:`6729`)

-   The ``__init__`` method of priority queue classes (see
    :setting:`SCHEDULER_PRIORITY_QUEUE`) should now support a keyword-only
    ``start_queue_cls`` parameter.
    (:gh:`6752`)

-   Spider middlewares that don't support asynchronous spider output are
    deprecated. The async iterable downgrading feature, needed for using such
    middlewares with asynchronous callbacks and with other spider middlewares
    that produce asynchronous iterables, is also deprecated. Please update all
    such middlewares to support asynchronous spider output. (:gh:`6664`)

-   Functions that were imported from :mod:`w3lib.url` and re-exported in
    :mod:`scrapy.utils.url` are now deprecated, you should import them from
    :mod:`w3lib.url` directly. They are:

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

    (:gh:`4577`, :gh:`6583`, :gh:`6586`)

-   HTTP/1.0 support code is deprecated. It was disabled by default and
    couldn't be used together with HTTP/1.1. If you still need it, you should
    write your own download handler or copy the code from Scrapy. The
    deprecations include:

    - ``scrapy.core.downloader.handlers.http10.HTTP10DownloadHandler``

    - ``scrapy.core.downloader.webclient.ScrapyHTTPClientFactory``

    - ``scrapy.core.downloader.webclient.ScrapyHTTPPageGetter``

    - Overriding
      ``scrapy.core.downloader.contextfactory.ScrapyClientContextFactory.getContext()``

    (:gh:`6634`)

-   The following modules and functions used only in tests are deprecated:

    - the ``scrapy.utils.testproc`` module

    - the ``scrapy.utils.testsite`` module

    - ``scrapy.utils.test.assert_gcs_environ()``

    - ``scrapy.utils.test.get_ftp_content_and_delete()``

    - ``scrapy.utils.test.get_gcs_content_and_delete()``

    - ``scrapy.utils.test.mock_google_cloud_storage()``

    - ``scrapy.utils.test.skip_if_no_boto()``

    If you need to use them in your tests or code, you can copy the code from Scrapy.
    (:gh:`6696`)

-   ``scrapy.utils.test.TestSpider`` is deprecated. If you need an empty spider
    class you can use :class:`scrapy.utils.spider.DefaultSpider` or create your
    own subclass of :class:`scrapy.Spider`.
    (:gh:`6678`)

-   ``scrapy.downloadermiddlewares.ajaxcrawl.AjaxCrawlMiddleware`` is
    deprecated. It was disabled by default and isn't useful for most of the
    existing websites.
    (:gh:`6523`, :gh:`6651`, :gh:`6656`)

-   ``scrapy.utils.url.escape_ajax()`` is deprecated.
    (:gh:`6523`, :gh:`6651`)

-   ``scrapy.spiders.init.InitSpider`` is deprecated. If you find it useful,
    you can copy its code from Scrapy.
    (:gh:`6708`, :gh:`6714`)

-   ``scrapy.utils.versions.scrapy_components_versions()`` is deprecated, use
    :func:`scrapy.utils.versions.get_versions` instead.
    (:gh:`6582`)

-   ``BaseDupeFilter.log()`` is deprecated. It does nothing and shouldn't be
    called.
    (:gh:`4151`)

-   Passing the ``spider`` argument to the following methods of
    :class:`~scrapy.core.scraper.Scraper` is deprecated:

    - ``close_spider()``

    - ``enqueue_scrape()``

    - ``handle_spider_error()``

    - ``handle_spider_output()``

    (:gh:`6764`)

New features
~~~~~~~~~~~~

-   You can now yield the start requests and items of a spider from the
    :meth:`~scrapy.Spider.start` spider method and from the
    :meth:`~scrapy.spidermiddlewares.SpiderMiddleware.process_start` spider
    middleware method, both :term:`asynchronous generators <python:asynchronous
    generator>`.

    This makes it possible to use asynchronous code to generate those start
    requests and items, e.g. reading them from a queue service or database
    using an asynchronous client, without workarounds.
    (:gh:`456`, :gh:`3477`, :gh:`4467`, :gh:`5627`, :gh:`6729`)

-   Start requests are now :ref:`scheduled <topics-scheduler>` as soon as
    possible.

    As a result, their :attr:`~scrapy.Request.priority` is now taken into
    account as soon as :setting:`CONCURRENT_REQUESTS` is reached.
    (:gh:`456`, :gh:`3477`, :gh:`4467`, :gh:`5627`, :gh:`6729`)

-   :class:`Crawler.signals <scrapy.signalmanager.SignalManager>` has a new
    :meth:`~scrapy.signalmanager.SignalManager.wait_for` method.
    (:gh:`6729`)

-   Added a new :signal:`scheduler_empty` signal.
    (:gh:`6729`)

-   Added new settings: :setting:`SCHEDULER_START_DISK_QUEUE` and
    :setting:`SCHEDULER_START_MEMORY_QUEUE`.
    (:gh:`6729`)

-   Added :class:`~scrapy.spidermiddlewares.start.StartSpiderMiddleware`, which
    sets :reqmeta:`is_start_request` to ``True`` on :ref:`start requests
    <start-requests>`.
    (:gh:`6729`)

-   Exposed a new method of :class:`Crawler.engine
    <scrapy.core.engine.ExecutionEngine>`:
    :meth:`~scrapy.core.engine.ExecutionEngine.needs_backout`.
    (:gh:`6729`)

-   Added the :reqmeta:`allow_offsite` request meta key that can be used
    instead of the more general :attr:`~scrapy.Request.dont_filter` request
    attribute to skip processing of the request by
    :class:`~scrapy.downloadermiddlewares.offsite.OffsiteMiddleware` (but not
    by other code that checks :attr:`~scrapy.Request.dont_filter`).
    (:gh:`3690`, :gh:`6151`, :gh:`6366`)

-   Added an optional base class for spider middlewares,
    :class:`~scrapy.spidermiddlewares.base.BaseSpiderMiddleware`, which can be
    helpful for writing :ref:`universal spider middlewares
    <universal-spider-middleware>` without boilerplate and code duplication.
    The built-in spider middlewares now inherit from this class.
    (:gh:`6693`, :gh:`6777`)

-   :ref:`Scrapy add-ons <topics-addons>` can now define a class method called
    ``update_pre_crawler_settings()`` to update :ref:`pre-crawler settings
    <pre-crawler-settings>`.
    (:gh:`6544`, :gh:`6568`)

-   Added :ref:`helpers <priority-dict-helpers>` for modifying :ref:`component
    priority dictionary <component-priority-dictionaries>` settings.
    (:gh:`6614`)

-   Responses that use an unknown/unsupported encoding now produce a warning.
    If Scrapy knows that installing an additional package (such as brotli_)
    will allow decoding the response, that will be mentioned in the warning.
    (:gh:`4697`, :gh:`6618`)

-   Added the ``spider_exceptions/count`` stat which tracks the total count of
    exceptions (tracked also by per-type ``spider_exceptions/*`` stats).
    (:gh:`6739`, :gh:`6740`)

-   Added the :setting:`DEFAULT_DROPITEM_LOG_LEVEL` setting and the
    :attr:`scrapy.exceptions.DropItem.log_level` attribute that allow
    customizing the log level of the message that is logged when an item is
    dropped.
    (:gh:`6603`, :gh:`6608`)

-   Added support for the ``-b, --cookie`` curl argument to
    :meth:`scrapy.Request.from_curl`.
    (:gh:`6684`)

-   Added the :setting:`LOG_VERSIONS` setting that allows customizing the
    list of software whose versions are logged when the spider starts.
    (:gh:`6582`)

-   Added the :setting:`WARN_ON_GENERATOR_RETURN_VALUE` setting that allows
    disabling run time analysis of callback code used to warn about incorrect
    ``return`` statements in generator-based callbacks. You may need to disable
    this setting if this analysis breaks on your callback code.
    (:gh:`6731`, :gh:`6738`)

Improvements
~~~~~~~~~~~~

-   Removed or postponed some calls of :func:`itemadapter.is_item` to increase
    performance.
    (:gh:`6719`)

-   Improved the error message when running a ``scrapy`` command that requires
    a project (such as ``scrapy crawl``) outside of a project directory.
    (:gh:`2349`, :gh:`3426`)

-   Added an empty :setting:`ADDONS` setting to the ``settings.py`` template
    for new projects.
    (:gh:`6587`)

Bug fixes
~~~~~~~~~

-   Yielding an item from :meth:`Spider.start <scrapy.Spider.start>` or from
    :meth:`SpiderMiddleware.process_start
    <scrapy.spidermiddlewares.SpiderMiddleware.process_start>` no longer delays
    the next iteration of starting requests and items by up to 5 seconds.
    (:gh:`6729`)

-   Fixed calculation of ``items_per_minute`` and ``responses_per_minute``
    stats.
    (:gh:`6599`)

-   Fixed an error initializing
    :class:`scrapy.extensions.feedexport.GCSFeedStorage`.
    (:gh:`6617`, :gh:`6628`)

-   Fixed an error running ``scrapy bench``.
    (:gh:`6632`, :gh:`6633`)

-   Fixed duplicated log messages about the reactor and the event loop.
    (:gh:`6636`, :gh:`6657`)

-   Fixed resolving type annotations of ``SitemapSpider._parse_sitemap()`` at
    run time, required by tools such as scrapy-poet_.
    (:gh:`6665`, :gh:`6671`)

    .. _scrapy-poet: https://github.com/scrapinghub/scrapy-poet

-   Calling :func:`scrapy.utils.reactor.is_asyncio_reactor_installed` without
    an installed reactor now raises an exception instead of installing a
    reactor.
    (:gh:`6732`, :gh:`6735`)

-   Restored support for the ``x-gzip`` content encoding.
    (:gh:`6618`)

Documentation
~~~~~~~~~~~~~

-   Documented the setting values set in the default project template.
    (:gh:`6762`, :gh:`6775`)

-   Improved the docs about asynchronous iterable support in spider
    middlewares. (:gh:`6688`)

-   Improved the :ref:`docs <coroutine-deferred-apis>` about using
    :class:`~twisted.internet.defer.Deferred`-based APIs in coroutine-based
    code and included a list of such APIs.
    (:gh:`6677`, :gh:`6734`, :gh:`6776`)

-   Improved the :ref:`contribution docs <topics-contributing>`.
    (:gh:`6561`, :gh:`6575`)

-   Removed the ``Splash`` recommendation from the :ref:`headless browser
    <topics-headless-browsing>` suggestion. We no longer recommend using
    ``Splash`` and recommend using other headless browser solutions instead.
    (:gh:`6642`, :gh:`6701`)

-   Added the dark mode to the HTML documentation.
    (:gh:`6653`)

-   Other documentation improvements and fixes.
    (:gh:`4151`,
    :gh:`6526`,
    :gh:`6620`,
    :gh:`6621`,
    :gh:`6622`,
    :gh:`6623`,
    :gh:`6624`,
    :gh:`6721`,
    :gh:`6723`,
    :gh:`6780`)

Packaging
~~~~~~~~~

-   Switched from ``setup.py`` to ``pyproject.toml``.
    (:gh:`6514`, :gh:`6547`)

-   Switched the build backend from setuptools_ to hatchling_.
    (:gh:`6771`)

    .. _hatchling: https://pypi.org/project/hatchling/

Quality assurance
~~~~~~~~~~~~~~~~~

-   Replaced most linters with ruff_.
    (:gh:`6565`,
    :gh:`6576`,
    :gh:`6577`,
    :gh:`6581`,
    :gh:`6584`,
    :gh:`6595`,
    :gh:`6601`,
    :gh:`6631`)

    .. _ruff: https://docs.astral.sh/ruff/

-   Improved accuracy and performance of collecting test coverage.
    (:gh:`6255`, :gh:`6610`)

-   Fixed an error that prevented running tests from directories other than the
    top level source directory.
    (:gh:`6567`)

-   Reduced the amount of ``mockserver`` calls in tests to improve the overall
    test run time.
    (:gh:`6637`, :gh:`6648`)

-   Fixed tests that were running the same test code more than once.
    (:gh:`6646`, :gh:`6647`, :gh:`6650`)

-   Refactored tests to use more ``pytest`` features instead of ``unittest``
    ones where possible.
    (:gh:`6678`,
    :gh:`6680`,
    :gh:`6695`,
    :gh:`6699`,
    :gh:`6700`,
    :gh:`6702`,
    :gh:`6709`,
    :gh:`6710`,
    :gh:`6711`,
    :gh:`6712`,
    :gh:`6725`)

-   Type hints improvements and fixes.
    (:gh:`6578`,
    :gh:`6579`,
    :gh:`6593`,
    :gh:`6605`,
    :gh:`6694`)

-   CI and test improvements and fixes.
    (:gh:`5360`,
    :gh:`6271`,
    :gh:`6547`,
    :gh:`6560`,
    :gh:`6602`,
    :gh:`6607`,
    :gh:`6609`,
    :gh:`6613`,
    :gh:`6619`,
    :gh:`6626`,
    :gh:`6679`,
    :gh:`6703`,
    :gh:`6704`,
    :gh:`6716`,
    :gh:`6720`,
    :gh:`6722`,
    :gh:`6724`,
    :gh:`6741`,
    :gh:`6743`,
    :gh:`6766`,
    :gh:`6770`,
    :gh:`6772`,
    :gh:`6773`)

-   Code cleanups.
    (:gh:`6600`,
    :gh:`6606`,
    :gh:`6635`,
    :gh:`6764`)


.. _release-2.12.0:

Scrapy 2.12.0 (2024-11-18)
--------------------------

Highlights:

-   Dropped support for Python 3.8, added support for Python 3.13

-   ``scrapy.Spider.start_requests()`` can now yield items

-   Added :class:`~scrapy.http.JsonResponse`

-   Added :setting:`CLOSESPIDER_PAGECOUNT_NO_ITEM`

Modified requirements
~~~~~~~~~~~~~~~~~~~~~

-   Dropped support for Python 3.8.
    (:gh:`6466`, :gh:`6472`)

-   Added support for Python 3.13.
    (:gh:`6166`)

-   Minimum versions increased for these dependencies:

    -   Twisted_: 18.9.0 → 21.7.0

    -   cryptography_: 36.0.0 → 37.0.0

    -   pyOpenSSL_: 21.0.0 → 22.0.0

    -   lxml_: 4.4.1 → 4.6.0

-   Removed ``setuptools`` from the dependency list.
    (:gh:`6487`)

Backward-incompatible changes
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

-   User-defined cookies for HTTPS requests will have the ``secure`` flag set
    to ``True`` unless it's set to ``False`` explicitly. This is important when
    these cookies are reused in HTTP requests, e.g. after a redirect to an HTTP
    URL.
    (:gh:`6357`)

-   The Reppy-based ``robots.txt`` parser,
    ``scrapy.robotstxt.ReppyRobotParser``, was removed, as it doesn't support
    Python 3.9+.
    (:gh:`5230`, :gh:`6099`, :gh:`6499`)

-   The initialization API of :class:`scrapy.pipelines.media.MediaPipeline` and
    its subclasses was improved and it's possible that some previously working
    usage scenarios will no longer work. It can only affect you if you define
    custom subclasses of ``MediaPipeline`` or create instances of these
    pipelines via ``from_settings()`` or ``__init__()`` calls instead of
    ``from_crawler()`` calls.

    Previously, ``MediaPipeline.from_crawler()`` called the ``from_settings()``
    method if it existed or the ``__init__()`` method otherwise, and then did
    some additional initialization using the ``crawler`` instance. If the
    ``from_settings()`` method existed (like in ``FilesPipeline``) it called
    ``__init__()`` to create the instance. It wasn't possible to override
    ``from_crawler()`` without calling ``MediaPipeline.from_crawler()`` from it
    which, in turn, couldn't be called in some cases (including subclasses of
    ``FilesPipeline``).

    Now, in line with the general usage of ``from_crawler()`` and
    ``from_settings()`` and the deprecation of the latter the recommended
    initialization order is the following one:

    - All ``__init__()`` methods should take a ``crawler`` argument. If they
      also take a ``settings`` argument they should ignore it, using
      ``crawler.settings`` instead. When they call ``__init__()`` of the base
      class they should pass the ``crawler`` argument to it too.
    - A ``from_settings()`` method shouldn't be defined. Class-specific
      initialization code should go into either an overridden ``from_crawler()``
      method or into ``__init__()``.
    - It's now possible to override ``from_crawler()`` and it's not necessary
      to call ``MediaPipeline.from_crawler()`` in it if other recommendations
      were followed.
    - If pipeline instances were created with ``from_settings()`` or
      ``__init__()`` calls (which wasn't supported even before, as it missed
      important initialization code), they should now be created with
      ``from_crawler()`` calls.

    (:gh:`6540`)

-   The ``response_body`` argument of :meth:`ImagesPipeline.convert_image
    <scrapy.pipelines.images.ImagesPipeline.convert_image>` is now
    positional-only, as it was changed from optional to required.
    (:gh:`6500`)

-   The ``convert`` argument of :func:`scrapy.utils.conf.build_component_list`
    is now positional-only, as the preceding argument (``custom``) was removed.
    (:gh:`6500`)

-   The ``overwrite_output`` argument of
    :func:`scrapy.utils.conf.feed_process_params_from_cli` is now
    positional-only, as the preceding argument (``output_format``) was removed.
    (:gh:`6500`)

Deprecation removals
~~~~~~~~~~~~~~~~~~~~

-   Removed the ``scrapy.utils.request.request_fingerprint()`` function,
    deprecated in Scrapy 2.7.0.
    (:gh:`6212`, :gh:`6213`)

-   Removed support for value ``"2.6"`` of setting
    ``REQUEST_FINGERPRINTER_IMPLEMENTATION``, deprecated in Scrapy 2.7.0.
    (:gh:`6212`, :gh:`6213`)

-   :class:`~scrapy.dupefilters.RFPDupeFilter` subclasses now require
    supporting the ``fingerprinter`` parameter in their ``__init__`` method,
    introduced in Scrapy 2.7.0.
    (:gh:`6102`, :gh:`6113`)

-   Removed the ``scrapy.downloadermiddlewares.decompression`` module,
    deprecated in Scrapy 2.7.0.
    (:gh:`6100`, :gh:`6113`)

-   Removed the ``scrapy.utils.response.response_httprepr()`` function,
    deprecated in Scrapy 2.6.0.
    (:gh:`6111`, :gh:`6116`)

-   Spiders with spider-level HTTP authentication, i.e. with the ``http_user``
    or ``http_pass`` attributes, must now define ``http_auth_domain`` as well,
    which was introduced in Scrapy 2.5.1.
    (:gh:`6103`, :gh:`6113`)

-   :ref:`Media pipelines <topics-media-pipeline>` methods ``file_path()``,
    ``file_downloaded()``, ``get_images()``, ``image_downloaded()``,
    ``media_downloaded()``, ``media_to_download()``, and ``thumb_path()`` must
    now support an ``item`` parameter, added in Scrapy 2.4.0.
    (:gh:`6107`, :gh:`6113`)

-   The ``__init__()`` and ``from_crawler()`` methods of :ref:`feed storage
    backend classes <topics-feed-storage>` must now support the keyword-only
    ``feed_options`` parameter, introduced in Scrapy 2.4.0.
    (:gh:`6105`, :gh:`6113`)

-   Removed the ``scrapy.loader.common`` and ``scrapy.loader.processors``
    modules, deprecated in Scrapy 2.3.0.
    (:gh:`6106`, :gh:`6113`)

-   Removed the ``scrapy.utils.misc.extract_regex()`` function, deprecated in
    Scrapy 2.3.0.
    (:gh:`6106`, :gh:`6113`)

-   Removed the ``scrapy.http.JSONRequest`` class, replaced with
    ``JsonRequest`` in Scrapy 1.8.0.
    (:gh:`6110`, :gh:`6113`)

-   ``scrapy.utils.log.logformatter_adapter`` no longer supports missing
    ``args``, ``level``, or ``msg`` parameters, and no longer supports a
    ``format`` parameter, all scenarios that were deprecated in Scrapy 1.0.0.
    (:gh:`6109`, :gh:`6116`)

-   A custom class assigned to the :setting:`SPIDER_LOADER_CLASS` setting that
    does not implement the ``ISpiderLoader`` interface
    will now raise a :exc:`zope.interface.verify.DoesNotImplement` exception at
    run time. Non-compliant classes have been triggering a deprecation warning
    since Scrapy 1.0.0.
    (:gh:`6101`, :gh:`6113`)

-   Removed the ``--output-format``/``-t`` command line option, deprecated in
    Scrapy 2.1.0. ``-O <URI>:<FORMAT>`` should be used instead.
    (:gh:`6500`)

-   Running :meth:`~scrapy.crawler.Crawler.crawl` more than once on the same
    :class:`~scrapy.crawler.Crawler` instance, deprecated in Scrapy 2.11.0, now
    raises an exception.
    (:gh:`6500`)

-   Subclassing
    :class:`~scrapy.downloadermiddlewares.httpcompression.HttpCompressionMiddleware`
    without support for the ``crawler`` argument in ``__init__()`` and without
    a custom ``from_crawler()`` method, deprecated in Scrapy 2.5.0, is no
    longer allowed.
    (:gh:`6500`)

-   Removed the ``EXCEPTIONS_TO_RETRY`` attribute of
    :class:`~scrapy.downloadermiddlewares.retry.RetryMiddleware`, deprecated in
    Scrapy 2.10.0.
    (:gh:`6500`)

-   Removed support for :ref:`S3 feed exports <topics-feed-storage-s3>` without
    the boto3_ package installed, deprecated in Scrapy 2.10.0.
    (:gh:`6500`)

-   Removed the ``scrapy.extensions.feedexport._FeedSlot`` class, deprecated in
    Scrapy 2.10.0.
    (:gh:`6500`)

-   Removed the ``scrapy.pipelines.images.NoimagesDrop`` exception, deprecated
    in Scrapy 2.8.0.
    (:gh:`6500`)

-   The ``response_body`` argument of :meth:`ImagesPipeline.convert_image
    <scrapy.pipelines.images.ImagesPipeline.convert_image>` is now required,
    not passing it was deprecated in Scrapy 2.8.0.
    (:gh:`6500`)

-   Removed the ``custom`` argument of
    :func:`scrapy.utils.conf.build_component_list`, deprecated in Scrapy
    2.10.0.
    (:gh:`6500`)

-   Removed the ``scrapy.utils.reactor.get_asyncio_event_loop_policy()``
    function, deprecated in Scrapy 2.9.0. Use :func:`asyncio.get_event_loop`
    and related standard library functions instead.
    (:gh:`6500`)

Deprecations
~~~~~~~~~~~~

-   The ``from_settings()`` methods of the :ref:`Scrapy components
    <topics-components>` that have them are now deprecated. ``from_crawler()``
    should now be used instead. Affected components:

    - :class:`scrapy.dupefilters.RFPDupeFilter`
    - :class:`scrapy.mail.MailSender`
    - :class:`scrapy.middleware.MiddlewareManager`
    - :class:`scrapy.core.downloader.contextfactory.ScrapyClientContextFactory`
    - :class:`scrapy.pipelines.files.FilesPipeline`
    - :class:`scrapy.pipelines.images.ImagesPipeline`
    - :class:`scrapy.spidermiddlewares.urllength.UrlLengthMiddleware`

    (:gh:`6540`)

-   It's now deprecated to have a ``from_settings()`` method but no
    ``from_crawler()`` method in 3rd-party :ref:`Scrapy components
    <topics-components>`. You can define a simple ``from_crawler()`` method
    that calls ``cls.from_settings(crawler.settings)`` to fix this if you don't
    want to refactor the code. Note that if you have a ``from_crawler()``
    method Scrapy will not call the ``from_settings()`` method so the latter
    can be removed.
    (:gh:`6540`)

-   The initialization API of :class:`scrapy.pipelines.media.MediaPipeline` and
    its subclasses was improved and some old usage scenarios are now deprecated
    (see also the "Backward-incompatible changes" section). Specifically:

    - It's deprecated to define an ``__init__()`` method that doesn't take a
      ``crawler`` argument.
    - It's deprecated to call an ``__init__()`` method without passing a
      ``crawler`` argument. If it's passed, it's also deprecated to pass a
      ``settings`` argument, which will be ignored anyway.
    - Calling ``from_settings()`` is deprecated, use ``from_crawler()``
      instead.
    - Overriding ``from_settings()`` is deprecated, override ``from_crawler()``
      instead.

    (:gh:`6540`)

-   The ``REQUEST_FINGERPRINTER_IMPLEMENTATION`` setting is now deprecated.
    (:gh:`6212`, :gh:`6213`)

-   The ``scrapy.utils.misc.create_instance()`` function is now deprecated, use
    :func:`scrapy.utils.misc.build_from_crawler` instead.
    (:gh:`5523`, :gh:`5884`, :gh:`6162`, :gh:`6169`, :gh:`6540`)

-   ``scrapy.core.downloader.Downloader._get_slot_key()`` is deprecated, use
    :meth:`scrapy.core.downloader.Downloader.get_slot_key` instead.
    (:gh:`6340`, :gh:`6352`)

-   ``scrapy.utils.defer.process_chain_both()`` is now deprecated.
    (:gh:`6397`)

-   ``scrapy.twisted_version`` is now deprecated, you should instead use
    :attr:`twisted.version` directly (but note that it's an
    ``incremental.Version`` object, not a tuple).
    (:gh:`6509`, :gh:`6512`)

-   ``scrapy.utils.python.flatten()`` and ``scrapy.utils.python.iflatten()``
    are now deprecated.
    (:gh:`6517`, :gh:`6519`)

-   ``scrapy.utils.python.equal_attributes()`` is now deprecated.
    (:gh:`6517`, :gh:`6519`)

-   ``scrapy.utils.request.request_authenticate()`` is now deprecated, you
    should instead just set the ``Authorization`` header directly.
    (:gh:`6517`, :gh:`6519`)

-   ``scrapy.utils.serialize.ScrapyJSONDecoder`` is now deprecated, it didn't
    contain any code since Scrapy 1.0.0.
    (:gh:`6517`, :gh:`6519`)

-   ``scrapy.utils.test.assert_samelines()`` is now deprecated.
    (:gh:`6517`, :gh:`6519`)

-   ``scrapy.extensions.feedexport.build_storage()`` is now deprecated. You can
    instead call the builder callable directly.
    (:gh:`6540`)

New features
~~~~~~~~~~~~

-   ``scrapy.Spider.start_requests()`` can now yield items.
    (:gh:`5289`, :gh:`6417`)

    .. note:: Some spider middlewares may need to be updated for Scrapy 2.12
        support before you can use them in combination with the ability to
        yield items from ``start_requests()``.

-   Added a new :class:`~scrapy.http.Response` subclass,
    :class:`~scrapy.http.JsonResponse`, for responses with a `JSON MIME type
    <https://mimesniff.spec.whatwg.org/#json-mime-type>`_.
    (:gh:`6069`, :gh:`6171`, :gh:`6174`)

-   The :class:`~scrapy.extensions.logstats.LogStats` extension now adds
    ``items_per_minute`` and ``responses_per_minute`` to the :ref:`stats
    <topics-stats>` when the spider closes.
    (:gh:`4110`, :gh:`4111`)

-   Added :setting:`CLOSESPIDER_PAGECOUNT_NO_ITEM` which allows closing the
    spider if no items were scraped in a set amount of time.
    (:gh:`6434`)

-   User-defined cookies can now include the ``secure`` field.
    (:gh:`6357`)

-   Added component getters to :class:`~scrapy.crawler.Crawler`:
    :meth:`~scrapy.crawler.Crawler.get_addon`,
    :meth:`~scrapy.crawler.Crawler.get_downloader_middleware`,
    :meth:`~scrapy.crawler.Crawler.get_extension`,
    :meth:`~scrapy.crawler.Crawler.get_item_pipeline`,
    :meth:`~scrapy.crawler.Crawler.get_spider_middleware`.
    (:gh:`6181`)

-   Slot delay updates by the :ref:`AutoThrottle extension
    <topics-autothrottle>` based on response latencies can now be disabled for
    specific requests via the :reqmeta:`autothrottle_dont_adjust_delay` meta
    key.
    (:gh:`6246`, :gh:`6527`)

-   If :setting:`SPIDER_LOADER_WARN_ONLY` is set to ``True``,
    :class:`~scrapy.spiderloader.SpiderLoader` does not raise
    :exc:`SyntaxError` but emits a warning instead.
    (:gh:`6483`, :gh:`6484`)

-   Added support for multiple-compressed responses (ones with several
    encodings in the ``Content-Encoding`` header).
    (:gh:`5143`, :gh:`5964`, :gh:`6063`)

-   Added support for multiple standard values in :setting:`REFERRER_POLICY`.
    (:gh:`6381`)

-   Added support for brotlicffi_ (previously named brotlipy_). brotli_ is
    still recommended but only brotlicffi_ works on PyPy.
    (:gh:`6263`, :gh:`6269`)

    .. _brotlicffi: https://github.com/python-hyper/brotlicffi

-   Added :class:`~scrapy.contracts.default.MetadataContract` that sets the
    request meta.
    (:gh:`6468`, :gh:`6469`)

Improvements
~~~~~~~~~~~~

-   Extended the list of file extensions that
    :class:`LinkExtractor <scrapy.linkextractors.lxmlhtml.LxmlLinkExtractor>`
    ignores by default.
    (:gh:`6074`, :gh:`6125`)

-   :func:`scrapy.utils.httpobj.urlparse_cached` is now used in more places
    instead of :func:`urllib.parse.urlparse`.
    (:gh:`6228`, :gh:`6229`)

Bug fixes
~~~~~~~~~

-   :class:`~scrapy.pipelines.media.MediaPipeline` is now an abstract class and
    its methods that were expected to be overridden in subclasses are now
    abstract methods.
    (:gh:`6365`, :gh:`6368`)

-   Fixed handling of invalid ``@``-prefixed lines in contract extraction.
    (:gh:`6383`, :gh:`6388`)

-   Importing ``scrapy.extensions.telnet`` no longer installs the default
    reactor.
    (:gh:`6432`)

-   Reduced log verbosity for dropped requests that was increased in 2.11.2.
    (:gh:`6433`, :gh:`6475`)

Documentation
~~~~~~~~~~~~~

-   Added ``SECURITY.md`` that documents the security policy.
    (:gh:`5364`, :gh:`6051`)

-   Example code for :ref:`running Scrapy from a script <run-from-script>` no
    longer imports ``twisted.internet.reactor`` at the top level, which caused
    problems with non-default reactors when this code was used unmodified.
    (:gh:`6361`, :gh:`6374`)

-   Documented the :class:`~scrapy.extensions.spiderstate.SpiderState`
    extension.
    (:gh:`6278`, :gh:`6522`)

-   Other documentation improvements and fixes.
    (:gh:`5920`,
    :gh:`6094`,
    :gh:`6177`,
    :gh:`6200`,
    :gh:`6207`,
    :gh:`6216`,
    :gh:`6223`,
    :gh:`6317`,
    :gh:`6328`,
    :gh:`6389`,
    :gh:`6394`,
    :gh:`6402`,
    :gh:`6411`,
    :gh:`6427`,
    :gh:`6429`,
    :gh:`6440`,
    :gh:`6448`,
    :gh:`6449`,
    :gh:`6462`,
    :gh:`6497`,
    :gh:`6506`,
    :gh:`6507`,
    :gh:`6524`)

Quality assurance
~~~~~~~~~~~~~~~~~

-   Added ``py.typed``, in line with `PEP 561
    <https://peps.python.org/pep-0561/>`_.
    (:gh:`6058`, :gh:`6059`)

-   Fully covered the code with type hints (except for the most complicated
    parts, mostly related to ``twisted.web.http`` and other Twisted parts
    without type hints).
    (:gh:`5989`,
    :gh:`6097`,
    :gh:`6127`,
    :gh:`6129`,
    :gh:`6130`,
    :gh:`6133`,
    :gh:`6143`,
    :gh:`6191`,
    :gh:`6268`,
    :gh:`6274`,
    :gh:`6275`,
    :gh:`6276`,
    :gh:`6279`,
    :gh:`6325`,
    :gh:`6326`,
    :gh:`6333`,
    :gh:`6335`,
    :gh:`6336`,
    :gh:`6337`,
    :gh:`6341`,
    :gh:`6353`,
    :gh:`6356`,
    :gh:`6370`,
    :gh:`6371`,
    :gh:`6384`,
    :gh:`6385`,
    :gh:`6387`,
    :gh:`6391`,
    :gh:`6395`,
    :gh:`6414`,
    :gh:`6422`,
    :gh:`6460`,
    :gh:`6466`,
    :gh:`6472`,
    :gh:`6494`,
    :gh:`6498`,
    :gh:`6516`)

-   Improved Bandit_ checks.
    (:gh:`6260`, :gh:`6264`, :gh:`6265`)

-   Added pyupgrade_ to the ``pre-commit`` configuration.
    (:gh:`6392`)

    .. _pyupgrade: https://github.com/asottile/pyupgrade

-   Added ``flake8-bugbear``, ``flake8-comprehensions``, ``flake8-debugger``,
    ``flake8-docstrings``, ``flake8-string-format`` and
    ``flake8-type-checking`` to the ``pre-commit`` configuration.
    (:gh:`6406`, :gh:`6413`)

-   CI and test improvements and fixes.
    (:gh:`5285`,
    :gh:`5454`,
    :gh:`5997`,
    :gh:`6078`,
    :gh:`6084`,
    :gh:`6087`,
    :gh:`6132`,
    :gh:`6153`,
    :gh:`6154`,
    :gh:`6201`,
    :gh:`6231`,
    :gh:`6232`,
    :gh:`6235`,
    :gh:`6236`,
    :gh:`6242`,
    :gh:`6245`,
    :gh:`6253`,
    :gh:`6258`,
    :gh:`6259`,
    :gh:`6270`,
    :gh:`6272`,
    :gh:`6286`,
    :gh:`6290`,
    :gh:`6296`
    :gh:`6367`,
    :gh:`6372`,
    :gh:`6403`,
    :gh:`6416`,
    :gh:`6435`,
    :gh:`6489`,
    :gh:`6501`,
    :gh:`6504`,
    :gh:`6511`,
    :gh:`6543`,
    :gh:`6545`)

-   Code cleanups.
    (:gh:`6196`,
    :gh:`6197`,
    :gh:`6198`,
    :gh:`6199`,
    :gh:`6254`,
    :gh:`6257`,
    :gh:`6285`,
    :gh:`6305`,
    :gh:`6343`,
    :gh:`6349`,
    :gh:`6386`,
    :gh:`6415`,
    :gh:`6463`,
    :gh:`6470`,
    :gh:`6499`,
    :gh:`6505`,
    :gh:`6510`,
    :gh:`6531`,
    :gh:`6542`)

Other
~~~~~

-   Issue tracker improvements. (:gh:`6066`)


.. _release-2.11.2:

Scrapy 2.11.2 (2024-05-14)
--------------------------

Security bug fixes
~~~~~~~~~~~~~~~~~~

-   Redirects to non-HTTP protocols are no longer followed. Please, see the
    `23j4-mw76-5v7h security advisory`_ for more information. (:gh:`457`)

    .. _23j4-mw76-5v7h security advisory: https://github.com/scrapy/scrapy/security/advisories/GHSA-23j4-mw76-5v7h

-   The ``Authorization`` header is now dropped on redirects to a different
    scheme (``http://`` or ``https://``) or port, even if the domain is the
    same. Please, see the `4qqq-9vqf-3h3f security advisory`_ for more
    information.

    .. _4qqq-9vqf-3h3f security advisory: https://github.com/scrapy/scrapy/security/advisories/GHSA-4qqq-9vqf-3h3f

-   When using system proxy settings that are different for ``http://`` and
    ``https://``, redirects to a different URL scheme will now also trigger the
    corresponding change in proxy settings for the redirected request. Please,
    see the `jm3v-qxmh-hxwv security advisory`_ for more information.
    (:gh:`767`)

    .. _jm3v-qxmh-hxwv security advisory: https://github.com/scrapy/scrapy/security/advisories/GHSA-jm3v-qxmh-hxwv

-   :attr:`Spider.allowed_domains <scrapy.Spider.allowed_domains>` is now
    enforced for all requests, and not only requests from spider callbacks.
    (:gh:`1042`, :gh:`2241`, :gh:`6358`)

-   :func:`~scrapy.utils.iterators.xmliter_lxml` no longer resolves XML
    entities. (:gh:`6265`)

-   defusedxml_ is now used to make
    :class:`scrapy.http.request.rpc.XmlRpcRequest` more secure.
    (:gh:`6250`, :gh:`6251`)

    .. _defusedxml: https://github.com/tiran/defusedxml

Deprecations
~~~~~~~~~~~~

-   ``scrapy.spidermiddlewares.offsite.OffsiteMiddleware`` (a spider
    middleware) is now deprecated and not enabled by default. The new
    downloader middleware with the same functionality,
    :class:`scrapy.downloadermiddlewares.offsite.OffsiteMiddleware`, is enabled
    instead.
    (:gh:`2241`, :gh:`6358`)


Bug fixes
~~~~~~~~~

-   Restored support for brotlipy_, which had been dropped in Scrapy 2.11.1 in
    favor of brotli_. (:gh:`6261`)

    .. note:: brotlipy is deprecated, both in Scrapy and upstream. Use brotli
        instead if you can.

-   Make :setting:`METAREFRESH_IGNORE_TAGS` ``["noscript"]`` by default. This
    prevents
    :class:`~scrapy.downloadermiddlewares.redirect.MetaRefreshMiddleware` from
    following redirects that would not be followed by web browsers with
    JavaScript enabled. (:gh:`6342`, :gh:`6347`)

-   During :ref:`feed export <topics-feed-exports>`, do not close the
    underlying file from :ref:`built-in post-processing plugins
    <builtin-plugins>`.
    (:gh:`5932`, :gh:`6178`, :gh:`6239`)

-   :class:`LinkExtractor <scrapy.linkextractors.lxmlhtml.LxmlLinkExtractor>`
    now properly applies the ``unique`` and ``canonicalize`` parameters.
    (:gh:`3273`, :gh:`6221`)

-   Do not initialize the scheduler disk queue if :setting:`JOBDIR` is an empty
    string. (:gh:`6121`, :gh:`6124`)

-   Fix :attr:`Spider.logger <scrapy.Spider.logger>` not logging custom extra
    information. (:gh:`6323`, :gh:`6324`)

-   ``robots.txt`` files with a non-UTF-8 encoding no longer prevent parsing
    the UTF-8-compatible (e.g. ASCII) parts of the document.
    (:gh:`6292`, :gh:`6298`)

-   :meth:`scrapy.http.cookies.WrappedRequest.get_header` no longer raises an
    exception if ``default`` is ``None``.
    (:gh:`6308`, :gh:`6310`)

-   :class:`~scrapy.Selector` now uses
    :func:`scrapy.utils.response.get_base_url` to determine the base URL of a
    given :class:`~scrapy.http.Response`. (:gh:`6265`)

-   The :meth:`media_to_download` method of :ref:`media pipelines
    <topics-media-pipeline>` now logs exceptions before stripping them.
    (:gh:`5067`, :gh:`5068`)

-   When passing a callback to the :command:`parse` command, build the callback
    callable with the right signature.
    (:gh:`6182`)

Documentation
~~~~~~~~~~~~~

-   Add a FAQ entry about :ref:`creating blank requests <faq-blank-request>`.
    (:gh:`6203`, :gh:`6208`)

-   Document that :attr:`scrapy.Selector.type` can be ``"json"``.
    (:gh:`6328`, :gh:`6334`)

Quality assurance
~~~~~~~~~~~~~~~~~

-   Make builds reproducible. (:gh:`5019`, :gh:`6322`)

-   Packaging and test fixes.
    (:gh:`6286`, :gh:`6290`, :gh:`6312`, :gh:`6316`, :gh:`6344`)


.. _release-2.11.1:

Scrapy 2.11.1 (2024-02-14)
--------------------------

Highlights:

-   Security bug fixes.

-   Support for Twisted >= 23.8.0.

-   Documentation improvements.

Security bug fixes
~~~~~~~~~~~~~~~~~~

-   Addressed `ReDoS vulnerabilities`_:

    -   ``scrapy.utils.iterators.xmliter`` is now deprecated in favor of
        :func:`~scrapy.utils.iterators.xmliter_lxml`, which
        :class:`~scrapy.spiders.XMLFeedSpider` now uses.

        To minimize the impact of this change on existing code,
        :func:`~scrapy.utils.iterators.xmliter_lxml` now supports indicating
        the node namespace with a prefix in the node name, and big files with
        highly nested trees when using libxml2 2.7+.

    -   Fixed regular expressions in the implementation of the
        :func:`~scrapy.utils.response.open_in_browser` function.

    Please, see the `cc65-xxvf-f7r9 security advisory`_ for more information.

    .. _ReDoS vulnerabilities: https://owasp.org/www-community/attacks/Regular_expression_Denial_of_Service_-_ReDoS
    .. _cc65-xxvf-f7r9 security advisory: https://github.com/scrapy/scrapy/security/advisories/GHSA-cc65-xxvf-f7r9

-   :setting:`DOWNLOAD_MAXSIZE` and :setting:`DOWNLOAD_WARNSIZE` now also apply
    to the decompressed response body. Please, see the `7j7m-v7m3-jqm7 security
    advisory`_ for more information.

    .. _7j7m-v7m3-jqm7 security advisory: https://github.com/scrapy/scrapy/security/advisories/GHSA-7j7m-v7m3-jqm7

-   Also in relation with the `7j7m-v7m3-jqm7 security advisory`_, the
    deprecated ``scrapy.downloadermiddlewares.decompression`` module has been
    removed.

-   The ``Authorization`` header is now dropped on redirects to a different
    domain. Please, see the `cw9j-q3vf-hrrv security advisory`_ for more
    information.

    .. _cw9j-q3vf-hrrv security advisory: https://github.com/scrapy/scrapy/security/advisories/GHSA-cw9j-q3vf-hrrv

Modified requirements
~~~~~~~~~~~~~~~~~~~~~

-   The Twisted dependency is no longer restricted to < 23.8.0. (:gh:`6024`,
    :gh:`6064`, :gh:`6142`)

Bug fixes
~~~~~~~~~

-   The OS signal handling code was refactored to no longer use private Twisted
    functions. (:gh:`6024`, :gh:`6064`, :gh:`6112`)

Documentation
~~~~~~~~~~~~~

-   Improved documentation for :class:`~scrapy.crawler.Crawler` initialization
    changes made in the 2.11.0 release. (:gh:`6057`, :gh:`6147`)

-   Extended documentation for :attr:`.Request.meta`.
    (:gh:`5565`)

-   Fixed the :reqmeta:`dont_merge_cookies` documentation. (:gh:`5936`,
    :gh:`6077`)

-   Added a link to Zyte's export guides to the :ref:`feed exports
    <topics-feed-exports>` documentation. (:gh:`6183`)

-   Added a missing note about backward-incompatible changes in
    :class:`~scrapy.exporters.PythonItemExporter` to the 2.11.0 release notes.
    (:gh:`6060`, :gh:`6081`)

-   Added a missing note about removing the deprecated
    ``scrapy.utils.boto.is_botocore()`` function to the 2.8.0 release notes.
    (:gh:`6056`, :gh:`6061`)

-   Other documentation improvements. (:gh:`6128`, :gh:`6144`,
    :gh:`6163`, :gh:`6190`, :gh:`6192`)

Quality assurance
~~~~~~~~~~~~~~~~~

-   Added Python 3.12 to the CI configuration, re-enabled tests that were
    disabled when the pre-release support was added. (:gh:`5985`,
    :gh:`6083`, :gh:`6098`)

-   Fixed a test issue on PyPy 7.3.14. (:gh:`6204`, :gh:`6205`)


.. _release-2.11.0:

Scrapy 2.11.0 (2023-09-18)
--------------------------

Highlights:

-   Spiders can now modify :ref:`settings <topics-settings>` in their
    :meth:`~scrapy.Spider.from_crawler` methods, e.g. based on :ref:`spider
    arguments <spiderargs>`.

-   Periodic logging of stats.


Backward-incompatible changes
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

-   Most of the initialization of :class:`scrapy.crawler.Crawler` instances is
    now done in :meth:`~scrapy.crawler.Crawler.crawl`, so the state of
    instances before that method is called is now different compared to older
    Scrapy versions. We do not recommend using the
    :class:`~scrapy.crawler.Crawler` instances before
    :meth:`~scrapy.crawler.Crawler.crawl` is called. (:gh:`6038`)

-   :meth:`scrapy.Spider.from_crawler` is now called before the initialization
    of various components previously initialized in
    :meth:`scrapy.crawler.Crawler.__init__` and before the settings are
    finalized and frozen. This change was needed to allow changing the settings
    in :meth:`scrapy.Spider.from_crawler`. If you want to access the final
    setting values and the initialized :class:`~scrapy.crawler.Crawler`
    attributes in the spider code as early as possible you can do this in
    ``scrapy.Spider.start_requests()`` or in a handler of the
    :signal:`engine_started` signal. (:gh:`6038`)

-   The :meth:`TextResponse.json <scrapy.http.TextResponse.json>` method now
    requires the response to be in a valid JSON encoding (UTF-8, UTF-16, or
    UTF-32). If you need to deal with JSON documents in an invalid encoding,
    use ``json.loads(response.text)`` instead. (:gh:`6016`)

-   :class:`~scrapy.exporters.PythonItemExporter` used the binary output by
    default but it no longer does. (:gh:`6006`, :gh:`6007`)

Deprecation removals
~~~~~~~~~~~~~~~~~~~~

-   Removed the binary export mode of
    :class:`~scrapy.exporters.PythonItemExporter`, deprecated in Scrapy 1.1.0.
    (:gh:`6006`, :gh:`6007`)

    .. note:: If you are using this Scrapy version on Scrapy Cloud with a stack
              that includes an older Scrapy version and get a "TypeError:
              Unexpected options: binary" error, you may need to add
              ``scrapinghub-entrypoint-scrapy >= 0.14.1`` to your project
              requirements or switch to a stack that includes Scrapy 2.11.

-   Removed the ``CrawlerRunner.spiders`` attribute, deprecated in Scrapy
    1.0.0, use :attr:`CrawlerRunner.spider_loader
    <scrapy.crawler.CrawlerRunner.spider_loader>` instead. (:gh:`6010`)

-   The :func:`scrapy.utils.response.response_httprepr` function, deprecated in
    Scrapy 2.6.0, has now been removed. (:gh:`6111`)

Deprecations
~~~~~~~~~~~~

-   Running :meth:`~scrapy.crawler.Crawler.crawl` more than once on the same
    :class:`scrapy.crawler.Crawler` instance is now deprecated. (:gh:`1587`,
    :gh:`6040`)

New features
~~~~~~~~~~~~

-   Spiders can now modify settings in their
    :meth:`~scrapy.Spider.from_crawler` method, e.g. based on :ref:`spider
    arguments <spiderargs>`. (:gh:`1305`, :gh:`1580`, :gh:`2392`,
    :gh:`3663`, :gh:`6038`)

-   Added the :class:`~scrapy.extensions.periodic_log.PeriodicLog` extension
    which can be enabled to log stats and/or their differences periodically.
    (:gh:`5926`)

-   Optimized the memory usage in :meth:`TextResponse.json
    <scrapy.http.TextResponse.json>` by removing unnecessary body decoding.
    (:gh:`5968`, :gh:`6016`)

-   Links to ``.webp`` files are now ignored by :ref:`link extractors
    <topics-link-extractors>`. (:gh:`6021`)

Bug fixes
~~~~~~~~~

-   Fixed logging enabled add-ons. (:gh:`6036`)

-   Fixed :class:`~scrapy.mail.MailSender` producing invalid message bodies
    when the ``charset`` argument is passed to
    :meth:`~scrapy.mail.MailSender.send`. (:gh:`5096`, :gh:`5118`)

-   Fixed an exception when accessing ``self.EXCEPTIONS_TO_RETRY`` from a
    subclass of :class:`~scrapy.downloadermiddlewares.retry.RetryMiddleware`.
    (:gh:`6049`, :gh:`6050`)

-   :meth:`scrapy.settings.BaseSettings.getdictorlist`, used to parse
    :setting:`FEED_EXPORT_FIELDS`, now handles tuple values. (:gh:`6011`,
    :gh:`6013`)

-   Calls to ``datetime.utcnow()``, no longer recommended to be used, have been
    replaced with calls to ``datetime.now()`` with a timezone. (:gh:`6014`)

Documentation
~~~~~~~~~~~~~

-   Updated a deprecated function call in a pipeline example. (:gh:`6008`,
    :gh:`6009`)

Quality assurance
~~~~~~~~~~~~~~~~~

-   Extended typing hints. (:gh:`6003`, :gh:`6005`, :gh:`6031`,
    :gh:`6034`)

-   Pinned brotli_ to 1.0.9 for the PyPy tests as 1.1.0 breaks them.
    (:gh:`6044`, :gh:`6045`)

-   Other CI and pre-commit improvements. (:gh:`6002`, :gh:`6013`,
    :gh:`6046`)

.. _release-2.10.1:

Scrapy 2.10.1 (2023-08-30)
--------------------------

Marked ``Twisted >= 23.8.0`` as unsupported. (:gh:`6024`, :gh:`6026`)

.. _release-2.10.0:

Scrapy 2.10.0 (2023-08-04)
--------------------------

Highlights:

-   Added Python 3.12 support, dropped Python 3.7 support.

-   The new add-ons framework simplifies configuring 3rd-party components that
    support it.

-   Exceptions to retry can now be configured.

-   Many fixes and improvements for feed exports.

Modified requirements
~~~~~~~~~~~~~~~~~~~~~

-   Dropped support for Python 3.7. (:gh:`5953`)

-   Added support for the upcoming Python 3.12. (:gh:`5984`)

-   Minimum versions increased for these dependencies:

    -   lxml_: 4.3.0 → 4.4.1

    -   cryptography_: 3.4.6 → 36.0.0

-   ``pkg_resources`` is no longer used. (:gh:`5956`, :gh:`5958`)

-   boto3_ is now recommended instead of botocore_ for exporting to S3.
    (:gh:`5833`).

Backward-incompatible changes
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

-   The value of the :setting:`FEED_STORE_EMPTY` setting is now ``True``
    instead of ``False``. In earlier Scrapy versions empty files were created
    even when this setting was ``False`` (which was a bug that is now fixed),
    so the new default should keep the old behavior. (:gh:`872`,
    :gh:`5847`)

Deprecation removals
~~~~~~~~~~~~~~~~~~~~

-   When a function is assigned to the :setting:`FEED_URI_PARAMS` setting,
    returning ``None`` or modifying the ``params`` input parameter, deprecated
    in Scrapy 2.6, is no longer supported. (:gh:`5994`, :gh:`5996`)

-   The ``scrapy.utils.reqser`` module, deprecated in Scrapy 2.6, is removed.
    (:gh:`5994`, :gh:`5996`)

-   The ``scrapy.squeues`` classes ``PickleFifoDiskQueueNonRequest``,
    ``PickleLifoDiskQueueNonRequest``, ``MarshalFifoDiskQueueNonRequest``,
    and ``MarshalLifoDiskQueueNonRequest``, deprecated in
    Scrapy 2.6, are removed. (:gh:`5994`, :gh:`5996`)

-   The property ``open_spiders`` and the methods ``has_capacity`` and
    ``schedule`` of :class:`scrapy.core.engine.ExecutionEngine`,
    deprecated in Scrapy 2.6, are removed. (:gh:`5994`, :gh:`5998`)

-   Passing a ``spider`` argument to the
    :meth:`~scrapy.core.engine.ExecutionEngine.spider_is_idle`,
    :meth:`~scrapy.core.engine.ExecutionEngine.crawl` and
    :meth:`~scrapy.core.engine.ExecutionEngine.download` methods of
    :class:`scrapy.core.engine.ExecutionEngine`, deprecated in Scrapy 2.6, is
    no longer supported. (:gh:`5994`, :gh:`5998`)

Deprecations
~~~~~~~~~~~~

-   :class:`scrapy.utils.datatypes.CaselessDict` is deprecated, use
    :class:`scrapy.utils.datatypes.CaseInsensitiveDict` instead.
    (:gh:`5146`)

-   Passing the ``custom`` argument to
    :func:`scrapy.utils.conf.build_component_list` is deprecated, it was used
    in the past to merge ``FOO`` and ``FOO_BASE`` setting values but now Scrapy
    uses :func:`scrapy.settings.BaseSettings.getwithbase` to do the same.
    Code that uses this argument and cannot be switched to ``getwithbase()``
    can be switched to merging the values explicitly. (:gh:`5726`,
    :gh:`5923`)

New features
~~~~~~~~~~~~

-   Added support for :ref:`Scrapy add-ons <topics-addons>`. (:gh:`5950`)

-   Added the :setting:`RETRY_EXCEPTIONS` setting that configures which
    exceptions will be retried by
    :class:`~scrapy.downloadermiddlewares.retry.RetryMiddleware`.
    (:gh:`2701`, :gh:`5929`)

-   Added the possiiblity to close the spider if no items were produced in the
    specified time, configured by :setting:`CLOSESPIDER_TIMEOUT_NO_ITEM`.
    (:gh:`5979`)

-   Added support for the :setting:`AWS_REGION_NAME` setting to feed exports.
    (:gh:`5980`)

-   Added support for using :class:`pathlib.Path` objects that refer to
    absolute Windows paths in the :setting:`FEEDS` setting. (:gh:`5939`)

Bug fixes
~~~~~~~~~

-   Fixed creating empty feeds even with ``FEED_STORE_EMPTY=False``.
    (:gh:`872`, :gh:`5847`)

-   Fixed using absolute Windows paths when specifying output files.
    (:gh:`5969`, :gh:`5971`)

-   Fixed problems with uploading large files to S3 by switching to multipart
    uploads (requires boto3_). (:gh:`960`, :gh:`5735`, :gh:`5833`)

-   Fixed the JSON exporter writing extra commas when some exceptions occur.
    (:gh:`3090`, :gh:`5952`)

-   Fixed the "read of closed file" error in the CSV exporter. (:gh:`5043`,
    :gh:`5705`)

-   Fixed an error when a component added by the class object throws
    :exc:`~scrapy.exceptions.NotConfigured` with a message. (:gh:`5950`,
    :gh:`5992`)

-   Added the missing :meth:`scrapy.settings.BaseSettings.pop` method.
    (:gh:`5959`, :gh:`5960`, :gh:`5963`)

-   Added :class:`~scrapy.utils.datatypes.CaseInsensitiveDict` as a replacement
    for :class:`~scrapy.utils.datatypes.CaselessDict` that fixes some API
    inconsistencies. (:gh:`5146`)

Documentation
~~~~~~~~~~~~~

-   Documented :meth:`scrapy.Spider.update_settings`. (:gh:`5745`,
    :gh:`5846`)

-   Documented possible problems with early Twisted reactor installation and
    their solutions. (:gh:`5981`, :gh:`6000`)

-   Added examples of making additional requests in callbacks. (:gh:`5927`)

-   Improved the feed export docs. (:gh:`5579`, :gh:`5931`)

-   Clarified the docs about request objects on redirection. (:gh:`5707`,
    :gh:`5937`)

Quality assurance
~~~~~~~~~~~~~~~~~

-   Added support for running tests against the installed Scrapy version.
    (:gh:`4914`, :gh:`5949`)

-   Extended typing hints. (:gh:`5925`, :gh:`5977`)

-   Fixed the ``test_utils_asyncio.AsyncioTest.test_set_asyncio_event_loop``
    test. (:gh:`5951`)

-   Fixed the ``test_feedexport.BatchDeliveriesTest.test_batch_path_differ``
    test on Windows. (:gh:`5847`)

-   Enabled CI runs for Python 3.11 on Windows. (:gh:`5999`)

-   Simplified skipping tests that depend on ``uvloop``. (:gh:`5984`)

-   Fixed the ``extra-deps-pinned`` tox env. (:gh:`5948`)

-   Implemented cleanups. (:gh:`5965`, :gh:`5986`)

.. _release-2.9.0:

Scrapy 2.9.0 (2023-05-08)
-------------------------

Highlights:

-   Per-domain download settings.
-   Compatibility with new cryptography_ and new parsel_.
-   JMESPath selectors from the new parsel_.
-   Bug fixes.

Deprecations
~~~~~~~~~~~~

-   :class:`scrapy.extensions.feedexport._FeedSlot` is renamed to
    :class:`scrapy.extensions.feedexport.FeedSlot` and the old name is
    deprecated. (:gh:`5876`)

New features
~~~~~~~~~~~~

-   Settings corresponding to :setting:`DOWNLOAD_DELAY`,
    :setting:`CONCURRENT_REQUESTS_PER_DOMAIN` and
    :setting:`RANDOMIZE_DOWNLOAD_DELAY` can now be set on a per-domain basis
    via the new :setting:`DOWNLOAD_SLOTS` setting. (:gh:`5328`)

-   Added :meth:`.TextResponse.jmespath`, a shortcut for JMESPath selectors
    available since parsel_ 1.8.1. (:gh:`5894`, :gh:`5915`)

-   Added :signal:`feed_slot_closed` and :signal:`feed_exporter_closed`
    signals. (:gh:`5876`)

-   Added :func:`scrapy.utils.request.request_to_curl`, a function to produce a
    curl command from a :class:`~scrapy.Request` object. (:gh:`5892`)

-   Values of :setting:`FILES_STORE` and :setting:`IMAGES_STORE` can now be
    :class:`pathlib.Path` instances. (:gh:`5801`)

Bug fixes
~~~~~~~~~

-   Fixed a warning with Parsel 1.8.1+. (:gh:`5903`, :gh:`5918`)

-   Fixed an error when using feed postprocessing with S3 storage.
    (:gh:`5500`, :gh:`5581`)

-   Added the missing :meth:`scrapy.settings.BaseSettings.setdefault` method.
    (:gh:`5811`, :gh:`5821`)

-   Fixed an error when using cryptography_ 40.0.0+ and
    :setting:`DOWNLOADER_CLIENT_TLS_VERBOSE_LOGGING` is enabled.
    (:gh:`5857`, :gh:`5858`)

-   The checksums returned by :class:`~scrapy.pipelines.files.FilesPipeline`
    for files on Google Cloud Storage are no longer Base64-encoded.
    (:gh:`5874`, :gh:`5891`)

-   :func:`scrapy.utils.request.request_from_curl` now supports $-prefixed
    string values for the curl ``--data-raw`` argument, which are produced by
    browsers for data that includes certain symbols. (:gh:`5899`,
    :gh:`5901`)

-   The :command:`parse` command now also works with async generator callbacks.
    (:gh:`5819`, :gh:`5824`)

-   The :command:`genspider` command now properly works with HTTPS URLs.
    (:gh:`3553`, :gh:`5808`)

-   Improved handling of asyncio loops. (:gh:`5831`, :gh:`5832`)

-   :class:`LinkExtractor <scrapy.linkextractors.lxmlhtml.LxmlLinkExtractor>`
    now skips certain malformed URLs instead of raising an exception.
    (:gh:`5881`)

-   :func:`scrapy.utils.python.get_func_args` now supports more types of
    callables. (:gh:`5872`, :gh:`5885`)

-   Fixed an error when processing non-UTF8 values of ``Content-Type`` headers.
    (:gh:`5914`, :gh:`5917`)

-   Fixed an error breaking user handling of send failures in
    :meth:`scrapy.mail.MailSender.send`. (:gh:`1611`, :gh:`5880`)

Documentation
~~~~~~~~~~~~~

-   Expanded contributing docs. (:gh:`5109`, :gh:`5851`)

-   Added blacken-docs_ to pre-commit and reformatted the docs with it.
    (:gh:`5813`, :gh:`5816`)

-   Fixed a JS issue. (:gh:`5875`, :gh:`5877`)

-   Fixed ``make htmlview``. (:gh:`5878`, :gh:`5879`)

-   Fixed typos and other small errors. (:gh:`5827`, :gh:`5839`,
    :gh:`5883`, :gh:`5890`, :gh:`5895`, :gh:`5904`)

Quality assurance
~~~~~~~~~~~~~~~~~

-   Extended typing hints. (:gh:`5805`, :gh:`5889`, :gh:`5896`)

-   Tests for most of the examples in the docs are now run as a part of CI,
    found problems were fixed. (:gh:`5816`, :gh:`5826`, :gh:`5919`)

-   Removed usage of deprecated Python classes. (:gh:`5849`)

-   Silenced ``include-ignored`` warnings from coverage. (:gh:`5820`)

-   Fixed a random failure of the ``test_feedexport.test_batch_path_differ``
    test. (:gh:`5855`, :gh:`5898`)

-   Updated docstrings to match output produced by parsel_ 1.8.1 so that they
    don't cause test failures. (:gh:`5902`, :gh:`5919`)

-   Other CI and pre-commit improvements. (:gh:`5802`, :gh:`5823`,
    :gh:`5908`)

.. _blacken-docs: https://github.com/adamchainz/blacken-docs

.. _release-2.8.0:

Scrapy 2.8.0 (2023-02-02)
-------------------------

This is a maintenance release, with minor features, bug fixes, and cleanups.

Deprecation removals
~~~~~~~~~~~~~~~~~~~~

-   The ``scrapy.utils.gz.read1`` function, deprecated in Scrapy 2.0, has now
    been removed. Use the :meth:`~io.BufferedIOBase.read1` method of
    :class:`~gzip.GzipFile` instead.
    (:gh:`5719`)

-   The ``scrapy.utils.python.to_native_str`` function, deprecated in Scrapy
    2.0, has now been removed. Use :func:`scrapy.utils.python.to_unicode`
    instead.
    (:gh:`5719`)

-   The ``scrapy.utils.python.MutableChain.next`` method, deprecated in Scrapy
    2.0, has now been removed. Use
    :meth:`~scrapy.utils.python.MutableChain.__next__` instead.
    (:gh:`5719`)

-   The ``scrapy.linkextractors.FilteringLinkExtractor`` class, deprecated
    in Scrapy 2.0, has now been removed. Use
    :class:`LinkExtractor <scrapy.linkextractors.lxmlhtml.LxmlLinkExtractor>`
    instead.
    (:gh:`5720`)

-   Support for using environment variables prefixed with ``SCRAPY_`` to
    override settings, deprecated in Scrapy 2.0, has now been removed.
    (:gh:`5724`)

-   Support for the ``noconnect`` query string argument in proxy URLs,
    deprecated in Scrapy 2.0, has now been removed. We expect proxies that used
    to need it to work fine without it.
    (:gh:`5731`)

-   The ``scrapy.utils.python.retry_on_eintr`` function, deprecated in Scrapy
    2.3, has now been removed.
    (:gh:`5719`)

-   The ``scrapy.utils.python.WeakKeyCache`` class, deprecated in Scrapy 2.4,
    has now been removed.
    (:gh:`5719`)

-   The ``scrapy.utils.boto.is_botocore()`` function, deprecated in Scrapy 2.4,
    has now been removed.
    (:gh:`5719`)


Deprecations
~~~~~~~~~~~~

-   :exc:`scrapy.pipelines.images.NoimagesDrop` is now deprecated.
    (:gh:`5368`, :gh:`5489`)

-   :meth:`ImagesPipeline.convert_image
    <scrapy.pipelines.images.ImagesPipeline.convert_image>` must now accept a
    ``response_body`` parameter.
    (:gh:`3055`, :gh:`3689`, :gh:`4753`)


New features
~~~~~~~~~~~~

-   Applied black_ coding style to files generated with the
    :command:`genspider` and :command:`startproject` commands.
    (:gh:`5809`, :gh:`5814`)

    .. _black: https://black.readthedocs.io/en/stable/

-   :setting:`FEED_EXPORT_ENCODING` is now set to ``"utf-8"`` in the
    ``settings.py`` file that the :command:`startproject` command generates.
    With this value, JSON exports won’t force the use of escape sequences for
    non-ASCII characters.
    (:gh:`5797`, :gh:`5800`)

-   The :class:`~scrapy.extensions.memusage.MemoryUsage` extension now logs the
    peak memory usage during checks, and the binary unit MiB is now used to
    avoid confusion.
    (:gh:`5717`, :gh:`5722`, :gh:`5727`)

-   The ``callback`` parameter of :class:`~scrapy.Request` can now be set
    to :func:`scrapy.http.request.NO_CALLBACK`, to distinguish it from
    ``None``, as the latter indicates that the default spider callback
    (:meth:`~scrapy.Spider.parse`) is to be used.
    (:gh:`5798`)


Bug fixes
~~~~~~~~~

-   Enabled unsafe legacy SSL renegotiation to fix access to some outdated
    websites.
    (:gh:`5491`, :gh:`5790`)

-   Fixed STARTTLS-based email delivery not working with Twisted 21.2.0 and
    better.
    (:gh:`5386`, :gh:`5406`)

-   Fixed the :meth:`finish_exporting` method of :ref:`item exporters
    <topics-exporters>` not being called for empty files.
    (:gh:`5537`, :gh:`5758`)

-   Fixed HTTP/2 responses getting only the last value for a header when
    multiple headers with the same name are received.
    (:gh:`5777`)

-   Fixed an exception raised by the :command:`shell` command on some cases
    when :ref:`using asyncio <using-asyncio>`.
    (:gh:`5740`, :gh:`5742`, :gh:`5748`, :gh:`5759`, :gh:`5760`,
    :gh:`5771`)

-   When using :class:`~scrapy.spiders.CrawlSpider`, callback keyword arguments
    (``cb_kwargs``) added to a request in the ``process_request`` callback of a
    :class:`~scrapy.spiders.Rule` will no longer be ignored.
    (:gh:`5699`)

-   The :ref:`images pipeline <images-pipeline>` no longer re-encodes JPEG
    files.
    (:gh:`3055`, :gh:`3689`, :gh:`4753`)

-   Fixed the handling of transparent WebP images by the :ref:`images pipeline
    <images-pipeline>`.
    (:gh:`3072`, :gh:`5766`, :gh:`5767`)

-   :func:`scrapy.shell.inspect_response` no longer inhibits ``SIGINT``
    (Ctrl+C).
    (:gh:`2918`)

-   :class:`LinkExtractor <scrapy.linkextractors.lxmlhtml.LxmlLinkExtractor>`
    with ``unique=False`` no longer filters out links that have identical URL
    *and* text.
    (:gh:`3798`, :gh:`3799`, :gh:`4695`, :gh:`5458`)

-   :class:`~scrapy.downloadermiddlewares.robotstxt.RobotsTxtMiddleware` now
    ignores URL protocols that do not support ``robots.txt`` (``data://``,
    ``file://``).
    (:gh:`5807`)

-   Silenced the ``filelock`` debug log messages introduced in Scrapy 2.6.
    (:gh:`5753`, :gh:`5754`)

-   Fixed the output of ``scrapy -h`` showing an unintended ``**commands**``
    line.
    (:gh:`5709`, :gh:`5711`, :gh:`5712`)

-   Made the active project indication in the output of :ref:`commands
    <topics-commands>` more clear.
    (:gh:`5715`)


Documentation
~~~~~~~~~~~~~

-   Documented how to :ref:`debug spiders from Visual Studio Code
    <debug-vscode>`.
    (:gh:`5721`)

-   Documented how :setting:`DOWNLOAD_DELAY` affects per-domain concurrency.
    (:gh:`5083`, :gh:`5540`)

-   Improved consistency.
    (:gh:`5761`)

-   Fixed typos.
    (:gh:`5714`, :gh:`5744`, :gh:`5764`)


Quality assurance
~~~~~~~~~~~~~~~~~

-   Applied :ref:`black coding style <coding-style>`, sorted import statements,
    and introduced :ref:`pre-commit <scrapy-pre-commit>`.
    (:gh:`4654`, :gh:`4658`, :gh:`5734`, :gh:`5737`, :gh:`5806`,
    :gh:`5810`)

-   Switched from :mod:`os.path` to :mod:`pathlib`.
    (:gh:`4916`, :gh:`4497`, :gh:`5682`)

-   Addressed many issues reported by Pylint.
    (:gh:`5677`)

-   Improved code readability.
    (:gh:`5736`)

-   Improved package metadata.
    (:gh:`5768`)

-   Removed direct invocations of ``setup.py``.
    (:gh:`5774`, :gh:`5776`)

-   Removed unnecessary :class:`~collections.OrderedDict` usages.
    (:gh:`5795`)

-   Removed unnecessary ``__str__`` definitions.
    (:gh:`5150`)

-   Removed obsolete code and comments.
    (:gh:`5725`, :gh:`5729`, :gh:`5730`, :gh:`5732`)

-   Fixed test and CI issues.
    (:gh:`5749`, :gh:`5750`, :gh:`5756`, :gh:`5762`, :gh:`5765`,
    :gh:`5780`, :gh:`5781`, :gh:`5782`, :gh:`5783`, :gh:`5785`,
    :gh:`5786`)


.. _release-2.7.1:

Scrapy 2.7.1 (2022-11-02)
-------------------------

New features
~~~~~~~~~~~~

-   Relaxed the restriction introduced in 2.6.2 so that the
    ``Proxy-Authorization`` header can again be set explicitly, as long as the
    proxy URL in the :reqmeta:`proxy` metadata has no other credentials, and
    for as long as that proxy URL remains the same; this restores compatibility
    with scrapy-zyte-smartproxy 2.1.0 and older (:gh:`5626`).

Bug fixes
~~~~~~~~~

-   Using ``-O``/``--overwrite-output`` and ``-t``/``--output-format`` options
    together now produces an error instead of ignoring the former option
    (:gh:`5516`, :gh:`5605`).

-   Replaced deprecated :mod:`asyncio` APIs that implicitly use the current
    event loop with code that explicitly requests a loop from the event loop
    policy (:gh:`5685`, :gh:`5689`).

-   Fixed uses of deprecated Scrapy APIs in Scrapy itself (:gh:`5588`,
    :gh:`5589`).

-   Fixed uses of a deprecated Pillow API (:gh:`5684`, :gh:`5692`).

-   Improved code that checks if generators return values, so that it no longer
    fails on decorated methods and partial methods (:gh:`5323`,
    :gh:`5592`, :gh:`5599`, :gh:`5691`).

Documentation
~~~~~~~~~~~~~

-   Upgraded the Code of Conduct to Contributor Covenant v2.1 (:gh:`5698`).

-   Fixed typos (:gh:`5681`, :gh:`5694`).

Quality assurance
~~~~~~~~~~~~~~~~~

-   Re-enabled some erroneously disabled flake8 checks (:gh:`5688`).

-   Ignored harmless deprecation warnings from :mod:`typing` in tests
    (:gh:`5686`, :gh:`5697`).

-   Modernized our CI configuration (:gh:`5695`, :gh:`5696`).


.. _release-2.7.0:

Scrapy 2.7.0 (2022-10-17)
-----------------------------

Highlights:

-   Added Python 3.11 support, dropped Python 3.6 support
-   Improved support for :ref:`asynchronous callbacks <topics-coroutines>`
-   :ref:`Asyncio support <using-asyncio>` is enabled by default on new
    projects
-   Output names of item fields can now be arbitrary strings
-   Centralized :ref:`request fingerprinting <request-fingerprints>`
    configuration is now possible

Modified requirements
~~~~~~~~~~~~~~~~~~~~~

Python 3.7 or greater is now required; support for Python 3.6 has been dropped.
Support for the upcoming Python 3.11 has been added.

The minimum required version of some dependencies has changed as well:

-   lxml_: 3.5.0 → 4.3.0

-   Pillow_ (:ref:`images pipeline <images-pipeline>`): 4.0.0 → 7.1.0

-   zope.interface_: 5.0.0 → 5.1.0

(:gh:`5512`, :gh:`5514`, :gh:`5524`, :gh:`5563`, :gh:`5664`,
:gh:`5670`, :gh:`5678`)


Deprecations
~~~~~~~~~~~~

-   :meth:`ImagesPipeline.thumb_path
    <scrapy.pipelines.images.ImagesPipeline.thumb_path>` must now accept an
    ``item`` parameter (:gh:`5504`, :gh:`5508`).

-   The ``scrapy.downloadermiddlewares.decompression`` module is now
    deprecated (:gh:`5546`, :gh:`5547`).


New features
~~~~~~~~~~~~

-   The
    :meth:`~scrapy.spidermiddlewares.SpiderMiddleware.process_spider_output`
    method of :ref:`spider middlewares <topics-spider-middleware>` can now be
    defined as an :term:`asynchronous generator` (:gh:`4978`).

-   The output of :class:`~scrapy.Request` callbacks defined as
    :ref:`coroutines <topics-coroutines>` is now processed asynchronously
    (:gh:`4978`).

-   :class:`~scrapy.spiders.crawl.CrawlSpider` now supports :ref:`asynchronous
    callbacks <topics-coroutines>` (:gh:`5657`).

-   New projects created with the :command:`startproject` command have
    :ref:`asyncio support <using-asyncio>` enabled by default (:gh:`5590`,
    :gh:`5679`).

-   The :setting:`FEED_EXPORT_FIELDS` setting can now be defined as a
    dictionary to customize the output name of item fields, lifting the
    restriction that required output names to be valid Python identifiers, e.g.
    preventing them to have whitespace (:gh:`1008`, :gh:`3266`,
    :gh:`3696`).

-   You can now customize :ref:`request fingerprinting <request-fingerprints>`
    through the new :setting:`REQUEST_FINGERPRINTER_CLASS` setting, instead of
    having to change it on every Scrapy component that relies on request
    fingerprinting (:gh:`900`, :gh:`3420`, :gh:`4113`, :gh:`4762`,
    :gh:`4524`).

-   ``jsonl`` is now supported and encouraged as a file extension for `JSON
    Lines`_ files (:gh:`4848`).

    .. _JSON Lines: https://jsonlines.org/

-   :meth:`ImagesPipeline.thumb_path
    <scrapy.pipelines.images.ImagesPipeline.thumb_path>` now receives the
    source :ref:`item <topics-items>` (:gh:`5504`, :gh:`5508`).


Bug fixes
~~~~~~~~~

-   When using Google Cloud Storage with a :ref:`media pipeline
    <topics-media-pipeline>`, :setting:`FILES_EXPIRES` now also works when
    :setting:`FILES_STORE` does not point at the root of your Google Cloud
    Storage bucket (:gh:`5317`, :gh:`5318`).

-   The :command:`parse` command now supports :ref:`asynchronous callbacks
    <topics-coroutines>` (:gh:`5424`, :gh:`5577`).

-   When using the :command:`parse` command with a URL for which there is no
    available spider, an exception is no longer raised (:gh:`3264`,
    :gh:`3265`, :gh:`5375`, :gh:`5376`, :gh:`5497`).

-   :class:`~scrapy.http.TextResponse` now gives higher priority to the `byte
    order mark`_ when determining the text encoding of the response body,
    following the `HTML living standard`_ (:gh:`5601`, :gh:`5611`).

    .. _byte order mark: https://en.wikipedia.org/wiki/Byte_order_mark
    .. _HTML living standard: https://html.spec.whatwg.org/multipage/parsing.html#determining-the-character-encoding

-   MIME sniffing takes the response body into account in FTP and HTTP/1.0
    requests, as well as in cached requests (:gh:`4873`).

-   MIME sniffing now detects valid HTML 5 documents even if the ``html`` tag
    is missing (:gh:`4873`).

-   An exception is now raised if :setting:`ASYNCIO_EVENT_LOOP` has a value
    that does not match the asyncio event loop actually installed
    (:gh:`5529`).

-   Fixed :meth:`Headers.getlist() <scrapy.http.headers.Headers.getlist>`
    returning only the last header (:gh:`5515`, :gh:`5526`).

-   Fixed :class:`LinkExtractor
    <scrapy.linkextractors.lxmlhtml.LxmlLinkExtractor>` not ignoring the
    ``tar.gz`` file extension by default (:gh:`1837`, :gh:`2067`,
    :gh:`4066`)


Documentation
~~~~~~~~~~~~~

-   Clarified the return type of :meth:`Spider.parse <scrapy.Spider.parse>`
    (:gh:`5602`, :gh:`5608`).

-   To enable
    :class:`~scrapy.downloadermiddlewares.httpcompression.HttpCompressionMiddleware`
    to do `brotli compression`_, installing brotli_ is now recommended instead
    of installing brotlipy_, as the former provides a more recent version of
    brotli.

    .. _brotli: https://github.com/google/brotli
    .. _brotli compression: https://www.ietf.org/rfc/rfc7932.txt

-   :ref:`Signal documentation <topics-signals>` now mentions :ref:`coroutine
    support <topics-coroutines>` and uses it in code examples (:gh:`4852`,
    :gh:`5358`).

-   :ref:`bans` now recommends `Common Crawl`_ instead of `Google cache`_
    (:gh:`3582`, :gh:`5432`).

    .. _Common Crawl: https://commoncrawl.org/
    .. _Google cache: https://www.googleguide.com/cached_pages.html

-   The new :ref:`topics-components` topic covers enforcing requirements on
    Scrapy components, like :ref:`downloader middlewares
    <topics-downloader-middleware>`, :ref:`extensions <topics-extensions>`,
    :ref:`item pipelines <topics-item-pipeline>`, :ref:`spider middlewares
    <topics-spider-middleware>`, and more; :ref:`enforce-asyncio-requirement`
    has also been added (:gh:`4978`).

-   :ref:`topics-settings` now indicates that setting values must be
    :ref:`picklable <pickle-picklable>` (:gh:`5607`, :gh:`5629`).

-   Removed outdated documentation (:gh:`5446`, :gh:`5373`,
    :gh:`5369`, :gh:`5370`, :gh:`5554`).

-   Fixed typos (:gh:`5442`, :gh:`5455`, :gh:`5457`, :gh:`5461`,
    :gh:`5538`, :gh:`5553`, :gh:`5558`, :gh:`5624`, :gh:`5631`).

-   Fixed other issues (:gh:`5283`, :gh:`5284`, :gh:`5559`,
    :gh:`5567`, :gh:`5648`, :gh:`5659`, :gh:`5665`).


Quality assurance
~~~~~~~~~~~~~~~~~

-   Added a continuous integration job to run `twine check`_ (:gh:`5655`,
    :gh:`5656`).

    .. _twine check: https://twine.readthedocs.io/en/stable/#twine-check

-   Addressed test issues and warnings (:gh:`5560`, :gh:`5561`,
    :gh:`5612`, :gh:`5617`, :gh:`5639`, :gh:`5645`, :gh:`5662`,
    :gh:`5671`, :gh:`5675`).

-   Cleaned up code (:gh:`4991`, :gh:`4995`, :gh:`5451`,
    :gh:`5487`, :gh:`5542`, :gh:`5667`, :gh:`5668`, :gh:`5672`).

-   Applied minor code improvements (:gh:`5661`).


.. _release-2.6.3:

Scrapy 2.6.3 (2022-09-27)
-------------------------

-   Added support for pyOpenSSL_ 22.1.0, removing support for SSLv3
    (:gh:`5634`, :gh:`5635`, :gh:`5636`).

-   Upgraded the minimum versions of the following dependencies:

    -   cryptography_: 2.0 → 3.3

    -   pyOpenSSL_: 16.2.0 → 21.0.0

    -   service_identity_: 16.0.0 → 18.1.0

    -   Twisted_: 17.9.0 → 18.9.0

    -   zope.interface_: 4.1.3 → 5.0.0

    (:gh:`5621`, :gh:`5632`)

-   Fixes test and documentation issues (:gh:`5612`, :gh:`5617`,
    :gh:`5631`).


.. _release-2.6.2:

Scrapy 2.6.2 (2022-07-25)
-------------------------

**Security bug fix:**

-   When :class:`~scrapy.downloadermiddlewares.httpproxy.HttpProxyMiddleware`
    processes a request with :reqmeta:`proxy` metadata, and that
    :reqmeta:`proxy` metadata includes proxy credentials,
    :class:`~scrapy.downloadermiddlewares.httpproxy.HttpProxyMiddleware` sets
    the ``Proxy-Authorization`` header, but only if that header is not already
    set.

    There are third-party proxy-rotation downloader middlewares that set
    different :reqmeta:`proxy` metadata every time they process a request.

    Because of request retries and redirects, the same request can be processed
    by downloader middlewares more than once, including both
    :class:`~scrapy.downloadermiddlewares.httpproxy.HttpProxyMiddleware` and
    any third-party proxy-rotation downloader middleware.

    These third-party proxy-rotation downloader middlewares could change the
    :reqmeta:`proxy` metadata of a request to a new value, but fail to remove
    the ``Proxy-Authorization`` header from the previous value of the
    :reqmeta:`proxy` metadata, causing the credentials of one proxy to be sent
    to a different proxy.

    To prevent the unintended leaking of proxy credentials, the behavior of
    :class:`~scrapy.downloadermiddlewares.httpproxy.HttpProxyMiddleware` is now
    as follows when processing a request:

    -   If the request being processed defines :reqmeta:`proxy` metadata that
        includes credentials, the ``Proxy-Authorization`` header is always
        updated to feature those credentials.

    -   If the request being processed defines :reqmeta:`proxy` metadata
        without credentials, the ``Proxy-Authorization`` header is removed
        *unless* it was originally defined for the same proxy URL.

        To remove proxy credentials while keeping the same proxy URL, remove
        the ``Proxy-Authorization`` header.

    -   If the request has no :reqmeta:`proxy` metadata, or that metadata is a
        falsy value (e.g. ``None``), the ``Proxy-Authorization`` header is
        removed.

        It is no longer possible to set a proxy URL through the
        :reqmeta:`proxy` metadata but set the credentials through the
        ``Proxy-Authorization`` header. Set proxy credentials through the
        :reqmeta:`proxy` metadata instead.

Also fixes the following regressions introduced in 2.6.0:

-   :class:`~scrapy.crawler.CrawlerProcess` supports again crawling multiple
    spiders (:gh:`5435`, :gh:`5436`)

-   Installing a Twisted reactor before Scrapy does (e.g. importing
    :mod:`twisted.internet.reactor` somewhere at the module level) no longer
    prevents Scrapy from starting, as long as a different reactor is not
    specified in :setting:`TWISTED_REACTOR` (:gh:`5525`, :gh:`5528`)

-   Fixed an exception that was being logged after the spider finished under
    certain conditions (:gh:`5437`, :gh:`5440`)

-   The ``--output``/``-o`` command-line parameter supports again a value
    starting with a hyphen (:gh:`5444`, :gh:`5445`)

-   The ``scrapy parse -h`` command no longer throws an error (:gh:`5481`,
    :gh:`5482`)


.. _release-2.6.1:

Scrapy 2.6.1 (2022-03-01)
-------------------------

Fixes a regression introduced in 2.6.0 that would unset the request method when
following redirects.


.. _release-2.6.0:

Scrapy 2.6.0 (2022-03-01)
-------------------------

Highlights:

*   :ref:`Security fixes for cookie handling <2.6-security-fixes>`

*   Python 3.10 support

*   :ref:`asyncio support <using-asyncio>` is no longer considered
    experimental, and works out-of-the-box on Windows regardless of your Python
    version

*   Feed exports now support :class:`pathlib.Path` output paths and per-feed
    :ref:`item filtering <item-filter>` and
    :ref:`post-processing <post-processing>`

.. _2.6-security-fixes:

Security bug fixes
~~~~~~~~~~~~~~~~~~

-   When a :class:`~scrapy.Request` object with cookies defined gets a
    redirect response causing a new :class:`~scrapy.Request` object to be
    scheduled, the cookies defined in the original
    :class:`~scrapy.Request` object are no longer copied into the new
    :class:`~scrapy.Request` object.

    If you manually set the ``Cookie`` header on a
    :class:`~scrapy.Request` object and the domain name of the redirect
    URL is not an exact match for the domain of the URL of the original
    :class:`~scrapy.Request` object, your ``Cookie`` header is now dropped
    from the new :class:`~scrapy.Request` object.

    The old behavior could be exploited by an attacker to gain access to your
    cookies. Please, see the `cjvr-mfj7-j4j8 security advisory`_ for more
    information.

    .. _cjvr-mfj7-j4j8 security advisory: https://github.com/scrapy/scrapy/security/advisories/GHSA-cjvr-mfj7-j4j8

    .. note:: It is still possible to enable the sharing of cookies between
              different domains with a shared domain suffix (e.g.
              ``example.com`` and any subdomain) by defining the shared domain
              suffix (e.g. ``example.com``) as the cookie domain when defining
              your cookies. See the documentation of the
              :class:`~scrapy.Request` class for more information.

-   When the domain of a cookie, either received in the ``Set-Cookie`` header
    of a response or defined in a :class:`~scrapy.Request` object, is set
    to a `public suffix <https://publicsuffix.org/>`_, the cookie is now
    ignored unless the cookie domain is the same as the request domain.

    The old behavior could be exploited by an attacker to inject cookies from a
    controlled domain into your cookiejar that could be sent to other domains
    not controlled by the attacker. Please, see the `mfjm-vh54-3f96 security
    advisory`_ for more information.

    .. _mfjm-vh54-3f96 security advisory: https://github.com/scrapy/scrapy/security/advisories/GHSA-mfjm-vh54-3f96


Modified requirements
~~~~~~~~~~~~~~~~~~~~~

-   The h2_ dependency is now optional, only needed to
    :ref:`enable HTTP/2 support <twisted-http2-handler>`. (:gh:`5113`)

    .. _h2: https://pypi.org/project/h2/


Backward-incompatible changes
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

-   The ``formdata`` parameter of :class:`~scrapy.FormRequest`, if specified
    for a non-POST request, now overrides the URL query string, instead of
    being appended to it. (:gh:`2919`, :gh:`3579`)

-   When a function is assigned to the :setting:`FEED_URI_PARAMS` setting, now
    the return value of that function, and not the ``params`` input parameter,
    will determine the feed URI parameters, unless that return value is
    ``None``. (:gh:`4962`, :gh:`4966`)

-   In :class:`scrapy.core.engine.ExecutionEngine`, methods
    :meth:`~scrapy.core.engine.ExecutionEngine.crawl`,
    :meth:`~scrapy.core.engine.ExecutionEngine.download`,
    :meth:`~scrapy.core.engine.ExecutionEngine.schedule`,
    and :meth:`~scrapy.core.engine.ExecutionEngine.spider_is_idle`
    now raise :exc:`RuntimeError` if called before
    :meth:`~scrapy.core.engine.ExecutionEngine.open_spider`. (:gh:`5090`)

    These methods used to assume that
    :attr:`ExecutionEngine.slot <scrapy.core.engine.ExecutionEngine.slot>` had
    been defined by a prior call to
    :meth:`~scrapy.core.engine.ExecutionEngine.open_spider`, so they were
    raising :exc:`AttributeError` instead.

-   If the API of the configured :ref:`scheduler <topics-scheduler>` does not
    meet expectations, :exc:`TypeError` is now raised at startup time. Before,
    other exceptions would be raised at run time. (:gh:`3559`)

-   The ``_encoding`` field of serialized :class:`~scrapy.Request` objects
    is now named ``encoding``, in line with all other fields (:gh:`5130`)


Deprecation removals
~~~~~~~~~~~~~~~~~~~~

-   ``scrapy.http.TextResponse.body_as_unicode``, deprecated in Scrapy 2.2, has
    now been removed. (:gh:`5393`)

-   ``scrapy.item.BaseItem``, deprecated in Scrapy 2.2, has now been removed.
    (:gh:`5398`)

-   ``scrapy.item.DictItem``, deprecated in Scrapy 1.8, has now been removed.
    (:gh:`5398`)

-   ``scrapy.Spider.make_requests_from_url``, deprecated in Scrapy 1.4, has now
    been removed. (:gh:`4178`, :gh:`4356`)


Deprecations
~~~~~~~~~~~~

-   When a function is assigned to the :setting:`FEED_URI_PARAMS` setting,
    returning ``None`` or modifying the ``params`` input parameter is now
    deprecated. Return a new dictionary instead. (:gh:`4962`, :gh:`4966`)

-   :mod:`scrapy.utils.reqser` is deprecated. (:gh:`5130`)

    -   Instead of :func:`~scrapy.utils.reqser.request_to_dict`, use the new
        :meth:`.Request.to_dict` method.

    -   Instead of :func:`~scrapy.utils.reqser.request_from_dict`, use the new
        :func:`scrapy.utils.request.request_from_dict` function.

-   In :mod:`scrapy.squeues`, the following queue classes are deprecated:
    :class:`~scrapy.squeues.PickleFifoDiskQueueNonRequest`,
    :class:`~scrapy.squeues.PickleLifoDiskQueueNonRequest`,
    :class:`~scrapy.squeues.MarshalFifoDiskQueueNonRequest`,
    and :class:`~scrapy.squeues.MarshalLifoDiskQueueNonRequest`. You should
    instead use:
    :class:`~scrapy.squeues.PickleFifoDiskQueue`,
    :class:`~scrapy.squeues.PickleLifoDiskQueue`,
    :class:`~scrapy.squeues.MarshalFifoDiskQueue`,
    and :class:`~scrapy.squeues.MarshalLifoDiskQueue`. (:gh:`5117`)

-   Many aspects of :class:`scrapy.core.engine.ExecutionEngine` that come from
    a time when this class could handle multiple :class:`~scrapy.Spider`
    objects at a time have been deprecated. (:gh:`5090`)

    -   The :meth:`~scrapy.core.engine.ExecutionEngine.has_capacity` method
        is deprecated.

    -   The :meth:`~scrapy.core.engine.ExecutionEngine.schedule` method is
        deprecated, use :meth:`~scrapy.core.engine.ExecutionEngine.crawl` or
        :meth:`~scrapy.core.engine.ExecutionEngine.download` instead.

    -   The :attr:`~scrapy.core.engine.ExecutionEngine.open_spiders` attribute
        is deprecated, use :attr:`~scrapy.core.engine.ExecutionEngine.spider`
        instead.

    -   The ``spider`` parameter is deprecated for the following methods:

        -   :meth:`~scrapy.core.engine.ExecutionEngine.spider_is_idle`

        -   :meth:`~scrapy.core.engine.ExecutionEngine.crawl`

        -   :meth:`~scrapy.core.engine.ExecutionEngine.download`

        Instead, call :meth:`~scrapy.core.engine.ExecutionEngine.open_spider`
        first to set the :class:`~scrapy.Spider` object.

-   :func:`scrapy.utils.response.response_httprepr` is now deprecated.
    (:gh:`4972`)


New features
~~~~~~~~~~~~

-   You can now use :ref:`item filtering <item-filter>` to control which items
    are exported to each output feed. (:gh:`4575`, :gh:`5178`,
    :gh:`5161`, :gh:`5203`)

-   You can now apply :ref:`post-processing <post-processing>` to feeds, and
    :ref:`built-in post-processing plugins <builtin-plugins>` are provided for
    output file compression. (:gh:`2174`, :gh:`5168`, :gh:`5190`)

-   The :setting:`FEEDS` setting now supports :class:`pathlib.Path` objects as
    keys. (:gh:`5383`, :gh:`5384`)

-   Enabling :ref:`asyncio <using-asyncio>` while using Windows and Python 3.8
    or later will automatically switch the asyncio event loop to one that
    allows Scrapy to work. See :ref:`asyncio-windows`. (:gh:`4976`,
    :gh:`5315`)

-   The :command:`genspider` command now supports a start URL instead of a
    domain name. (:gh:`4439`)

-   :mod:`scrapy.utils.defer` gained 2 new functions,
    :func:`~scrapy.utils.defer.deferred_to_future` and
    :func:`~scrapy.utils.defer.maybe_deferred_to_future`, to help :ref:`await
    on Deferreds when using the asyncio reactor <asyncio-await-dfd>`.
    (:gh:`5288`)

-   :ref:`Amazon S3 feed export storage <topics-feed-storage-s3>` gained
    support for `temporary security credentials`_
    (:setting:`AWS_SESSION_TOKEN`) and endpoint customization
    (:setting:`AWS_ENDPOINT_URL`). (:gh:`4998`, :gh:`5210`)

    .. _temporary security credentials: https://docs.aws.amazon.com/IAM/latest/UserGuide/security-creds.html

-   New :setting:`LOG_FILE_APPEND` setting to allow truncating the log file.
    (:gh:`5279`)

-   :attr:`Request.cookies <scrapy.Request.cookies>` values that are
    :class:`bool`, :class:`float` or :class:`int` are cast to :class:`str`.
    (:gh:`5252`, :gh:`5253`)

-   You may now raise :exc:`~scrapy.exceptions.CloseSpider` from a handler of
    the :signal:`spider_idle` signal to customize the reason why the spider is
    stopping. (:gh:`5191`)

-   When using
    :class:`~scrapy.downloadermiddlewares.httpproxy.HttpProxyMiddleware`, the
    proxy URL for non-HTTPS HTTP/1.1 requests no longer needs to include a URL
    scheme. (:gh:`4505`, :gh:`4649`)

-   All built-in queues now expose a ``peek`` method that returns the next
    queue object (like ``pop``) but does not remove the returned object from
    the queue. (:gh:`5112`)

    If the underlying queue does not support peeking (e.g. because you are not
    using ``queuelib`` 1.6.1 or later), the ``peek`` method raises
    :exc:`NotImplementedError`.

-   :class:`~scrapy.Request` and :class:`~scrapy.http.Response` now have
    an ``attributes`` attribute that makes subclassing easier. For
    :class:`~scrapy.Request`, it also allows subclasses to work with
    :func:`scrapy.utils.request.request_from_dict`. (:gh:`1877`,
    :gh:`5130`, :gh:`5218`)

-   The :meth:`~scrapy.core.scheduler.BaseScheduler.open` and
    :meth:`~scrapy.core.scheduler.BaseScheduler.close` methods of the
    :ref:`scheduler <topics-scheduler>` are now optional. (:gh:`3559`)

-   HTTP/1.1 :exc:`~scrapy.core.downloader.handlers.http11.TunnelError`
    exceptions now only truncate response bodies longer than 1000 characters,
    instead of those longer than 32 characters, making it easier to debug such
    errors. (:gh:`4881`, :gh:`5007`)

-   :class:`~scrapy.loader.ItemLoader` now supports non-text responses.
    (:gh:`5145`, :gh:`5269`)


Bug fixes
~~~~~~~~~

-   The :setting:`TWISTED_REACTOR` and :setting:`ASYNCIO_EVENT_LOOP` settings
    are no longer ignored if defined in :attr:`~scrapy.Spider.custom_settings`.
    (:gh:`4485`, :gh:`5352`)

-   Removed a module-level Twisted reactor import that could prevent
    :ref:`using the asyncio reactor <using-asyncio>`. (:gh:`5357`)

-   The :command:`startproject` command works with existing folders again.
    (:gh:`4665`, :gh:`4676`)

-   The :setting:`FEED_URI_PARAMS` setting now behaves as documented.
    (:gh:`4962`, :gh:`4966`)

-   :attr:`Request.cb_kwargs <scrapy.Request.cb_kwargs>` once again allows the
    ``callback`` keyword. (:gh:`5237`, :gh:`5251`, :gh:`5264`)

-   Made :func:`scrapy.utils.response.open_in_browser` support more complex
    HTML. (:gh:`5319`, :gh:`5320`)

-   Fixed :attr:`CSVFeedSpider.quotechar
    <scrapy.spiders.CSVFeedSpider.quotechar>` being interpreted as the CSV file
    encoding. (:gh:`5391`, :gh:`5394`)

-   Added missing setuptools_ to the list of dependencies. (:gh:`5122`)

    .. _setuptools: https://pypi.org/project/setuptools/

-   :class:`LinkExtractor <scrapy.linkextractors.lxmlhtml.LxmlLinkExtractor>`
    now also works as expected with links that have comma-separated ``rel``
    attribute values including ``nofollow``. (:gh:`5225`)

-   Fixed a :exc:`TypeError` that could be raised during :ref:`feed export
    <topics-feed-exports>` parameter parsing. (:gh:`5359`)


Documentation
~~~~~~~~~~~~~

-   :ref:`asyncio support <using-asyncio>` is no longer considered
    experimental. (:gh:`5332`)

-   Included :ref:`Windows-specific help for asyncio usage <asyncio-windows>`.
    (:gh:`4976`, :gh:`5315`)

-   Rewrote :ref:`topics-headless-browsing` with up-to-date best practices.
    (:gh:`4484`, :gh:`4613`)

-   Documented :ref:`local file naming in media pipelines
    <topics-file-naming>`. (:gh:`5069`, :gh:`5152`)

-   :ref:`faq` now covers spider file name collision issues. (:gh:`2680`,
    :gh:`3669`)

-   Provided better context and instructions to disable the
    :setting:`URLLENGTH_LIMIT` setting. (:gh:`5135`, :gh:`5250`)

-   Documented that Reppy parser does not support Python 3.9+.
    (:gh:`5226`, :gh:`5231`)

-   Documented :ref:`the scheduler component <topics-scheduler>`.
    (:gh:`3537`, :gh:`3559`)

-   Documented the method used by :ref:`media pipelines
    <topics-media-pipeline>` to :ref:`determine if a file has expired
    <file-expiration>`. (:gh:`5120`, :gh:`5254`)

-   :ref:`run-multiple-spiders` now features
    :func:`scrapy.utils.project.get_project_settings` usage. (:gh:`5070`)

-   :ref:`run-multiple-spiders` now covers what happens when you define
    different per-spider values for some settings that cannot differ at run
    time. (:gh:`4485`, :gh:`5352`)

-   Extended the documentation of the
    :class:`~scrapy.extensions.statsmailer.StatsMailer` extension.
    (:gh:`5199`, :gh:`5217`)

-   Added :setting:`JOBDIR` to :ref:`topics-settings`. (:gh:`5173`,
    :gh:`5224`)

-   Documented :attr:`Spider.attribute <scrapy.Spider.attribute>`.
    (:gh:`5174`, :gh:`5244`)

-   Documented :attr:`TextResponse.urljoin <scrapy.http.TextResponse.urljoin>`.
    (:gh:`1582`)

-   Added the ``body_length`` parameter to the documented signature of the
    :signal:`headers_received` signal. (:gh:`5270`)

-   Clarified :meth:`SelectorList.get <scrapy.selector.SelectorList.get>` usage
    in the :ref:`tutorial <intro-tutorial>`. (:gh:`5256`)

-   The documentation now features the shortest import path of classes with
    multiple import paths. (:gh:`2733`, :gh:`5099`)

-   ``quotes.toscrape.com`` references now use HTTPS instead of HTTP.
    (:gh:`5395`, :gh:`5396`)

-   Added a link to `our Discord server <https://discord.com/invite/mv3yErfpvq>`_
    to :ref:`getting-help`. (:gh:`5421`, :gh:`5422`)

-   The pronunciation of the project name is now :ref:`officially
    <intro-overview>` /ˈskreɪpaɪ/. (:gh:`5280`, :gh:`5281`)

-   Added the Scrapy logo to the README. (:gh:`5255`, :gh:`5258`)

-   Fixed issues and implemented minor improvements. (:gh:`3155`,
    :gh:`4335`, :gh:`5074`, :gh:`5098`, :gh:`5134`, :gh:`5180`,
    :gh:`5194`, :gh:`5239`, :gh:`5266`, :gh:`5271`, :gh:`5273`,
    :gh:`5274`, :gh:`5276`, :gh:`5347`, :gh:`5356`, :gh:`5414`,
    :gh:`5415`, :gh:`5416`, :gh:`5419`, :gh:`5420`)


Quality Assurance
~~~~~~~~~~~~~~~~~

-   Added support for Python 3.10. (:gh:`5212`, :gh:`5221`,
    :gh:`5265`)

-   Significantly reduced memory usage by
    :func:`scrapy.utils.response.response_httprepr`, used by the
    :class:`~scrapy.downloadermiddlewares.stats.DownloaderStats` downloader
    middleware, which is enabled by default. (:gh:`4964`, :gh:`4972`)

-   Removed uses of the deprecated :mod:`optparse` module. (:gh:`5366`,
    :gh:`5374`)

-   Extended typing hints. (:gh:`5077`, :gh:`5090`, :gh:`5100`,
    :gh:`5108`, :gh:`5171`, :gh:`5215`, :gh:`5334`)

-   Improved tests, fixed CI issues, removed unused code. (:gh:`5094`,
    :gh:`5157`, :gh:`5162`, :gh:`5198`, :gh:`5207`, :gh:`5208`,
    :gh:`5229`, :gh:`5298`, :gh:`5299`, :gh:`5310`, :gh:`5316`,
    :gh:`5333`, :gh:`5388`, :gh:`5389`, :gh:`5400`, :gh:`5401`,
    :gh:`5404`, :gh:`5405`, :gh:`5407`, :gh:`5410`, :gh:`5412`,
    :gh:`5425`, :gh:`5427`)

-   Implemented improvements for contributors. (:gh:`5080`, :gh:`5082`,
    :gh:`5177`, :gh:`5200`)

-   Implemented cleanups. (:gh:`5095`, :gh:`5106`, :gh:`5209`,
    :gh:`5228`, :gh:`5235`, :gh:`5245`, :gh:`5246`, :gh:`5292`,
    :gh:`5314`, :gh:`5322`)


.. _release-2.5.1:

Scrapy 2.5.1 (2021-10-05)
-------------------------

*   **Security bug fix:**

    If you use
    :class:`~scrapy.downloadermiddlewares.httpauth.HttpAuthMiddleware`
    (i.e. the ``http_user`` and ``http_pass`` spider attributes) for HTTP
    authentication, any request exposes your credentials to the request target.

    To prevent unintended exposure of authentication credentials to unintended
    domains, you must now additionally set a new, additional spider attribute,
    ``http_auth_domain``, and point it to the specific domain to which the
    authentication credentials must be sent.

    If the ``http_auth_domain`` spider attribute is not set, the domain of the
    first request will be considered the HTTP authentication target, and
    authentication credentials will only be sent in requests targeting that
    domain.

    If you need to send the same HTTP authentication credentials to multiple
    domains, you can use :func:`w3lib.http.basic_auth_header` instead to
    set the value of the ``Authorization`` header of your requests.

    If you *really* want your spider to send the same HTTP authentication
    credentials to any domain, set the ``http_auth_domain`` spider attribute
    to ``None``.

    Finally, if you are a user of `scrapy-splash`_, know that this version of
    Scrapy breaks compatibility with scrapy-splash 0.7.2 and earlier. You will
    need to upgrade scrapy-splash to a greater version for it to continue to
    work.


.. _release-2.5.0:

Scrapy 2.5.0 (2021-04-06)
-------------------------

Highlights:

-   Official Python 3.9 support

-   Experimental :ref:`HTTP/2 support <twisted-http2-handler>`

-   New :func:`~scrapy.downloadermiddlewares.retry.get_retry_request` function
    to retry requests from spider callbacks

-   New :class:`~scrapy.signals.headers_received` signal that allows stopping
    downloads early

-   New :class:`Response.protocol <scrapy.http.Response.protocol>` attribute

Deprecation removals
~~~~~~~~~~~~~~~~~~~~

-   Removed all code that :ref:`was deprecated in 1.7.0 <1.7-deprecations>` and
    had not :ref:`already been removed in 2.4.0 <2.4-deprecation-removals>`.
    (:gh:`4901`)

-   Removed support for the ``SCRAPY_PICKLED_SETTINGS_TO_OVERRIDE`` environment
    variable, :ref:`deprecated in 1.8.0 <1.8-deprecations>`. (:gh:`4912`)


Deprecations
~~~~~~~~~~~~

-   The :mod:`scrapy.utils.py36` module is now deprecated in favor of
    :mod:`scrapy.utils.asyncgen`. (:gh:`4900`)


New features
~~~~~~~~~~~~

-   Experimental :ref:`HTTP/2 support <twisted-http2-handler>` through a new download handler
    that can be assigned to the ``https`` protocol in the
    :setting:`DOWNLOAD_HANDLERS` setting.
    (:gh:`1854`, :gh:`4769`, :gh:`5058`, :gh:`5059`, :gh:`5066`)

-   The new :func:`scrapy.downloadermiddlewares.retry.get_retry_request`
    function may be used from spider callbacks or middlewares to handle the
    retrying of a request beyond the scenarios that
    :class:`~scrapy.downloadermiddlewares.retry.RetryMiddleware` supports.
    (:gh:`3590`, :gh:`3685`, :gh:`4902`)

-   The new :class:`~scrapy.signals.headers_received` signal gives early access
    to response headers and allows :ref:`stopping downloads
    <topics-stop-response-download>`.
    (:gh:`1772`, :gh:`4897`)

-   The new :attr:`Response.protocol <scrapy.http.Response.protocol>`
    attribute gives access to the string that identifies the protocol used to
    download a response. (:gh:`4878`)

-   :ref:`Stats <topics-stats>` now include the following entries that indicate
    the number of successes and failures in storing
    :ref:`feeds <topics-feed-exports>`::

        feedexport/success_count/<storage type>
        feedexport/failed_count/<storage type>

    Where ``<storage type>`` is the feed storage backend class name, such as
    :class:`~scrapy.extensions.feedexport.FileFeedStorage` or
    :class:`~scrapy.extensions.feedexport.FTPFeedStorage`.

    (:gh:`3947`, :gh:`4850`)

-   The :class:`~scrapy.spidermiddlewares.urllength.UrlLengthMiddleware` spider
    middleware now logs ignored URLs with ``INFO`` :ref:`logging level
    <levels>` instead of ``DEBUG``, and it now includes the following entry
    into :ref:`stats <topics-stats>` to keep track of the number of ignored
    URLs::

        urllength/request_ignored_count

    (:gh:`5036`)

-   The
    :class:`~scrapy.downloadermiddlewares.httpcompression.HttpCompressionMiddleware`
    downloader middleware now logs the number of decompressed responses and the
    total count of resulting bytes::

        httpcompression/response_bytes
        httpcompression/response_count

    (:gh:`4797`, :gh:`4799`)


Bug fixes
~~~~~~~~~

-   Fixed installation on PyPy installing PyDispatcher in addition to
    PyPyDispatcher, which could prevent Scrapy from working depending on which
    package got imported. (:gh:`4710`, :gh:`4814`)

-   When inspecting a callback to check if it is a generator that also returns
    a value, an exception is no longer raised if the callback has a docstring
    with lower indentation than the following code.
    (:gh:`4477`, :gh:`4935`)

-   The `Content-Length <https://datatracker.ietf.org/doc/html/rfc2616#section-14.13>`_
    header is no longer omitted from responses when using the default, HTTP/1.1
    download handler (see :setting:`DOWNLOAD_HANDLERS`).
    (:gh:`5009`, :gh:`5034`, :gh:`5045`, :gh:`5057`, :gh:`5062`)

-   Setting the :reqmeta:`handle_httpstatus_all` request meta key to ``False``
    now has the same effect as not setting it at all, instead of having the
    same effect as setting it to ``True``.
    (:gh:`3851`, :gh:`4694`)


Documentation
~~~~~~~~~~~~~

-   Added instructions to :ref:`install Scrapy in Windows using pip
    <intro-install-windows>`.
    (:gh:`4715`, :gh:`4736`)

-   Logging documentation now includes :ref:`additional ways to filter logs
    <topics-logging-advanced-customization>`.
    (:gh:`4216`, :gh:`4257`, :gh:`4965`)

-   Covered how to deal with long lists of allowed domains in the :ref:`FAQ
    <faq>`. (:gh:`2263`, :gh:`3667`)

-   Covered scrapy-bench_ in :ref:`benchmarking`.
    (:gh:`4996`, :gh:`5016`)

-   Clarified that one :ref:`extension <topics-extensions>` instance is created
    per crawler.
    (:gh:`5014`)

-   Fixed some errors in examples.
    (:gh:`4829`, :gh:`4830`, :gh:`4907`, :gh:`4909`,
    :gh:`5008`)

-   Fixed some external links, typos, and so on.
    (:gh:`4892`, :gh:`4899`, :gh:`4936`, :gh:`4942`, :gh:`5005`,
    :gh:`5063`)

-   The :ref:`list of Request.meta keys <topics-request-meta>` is now sorted
    alphabetically.
    (:gh:`5061`, :gh:`5065`)

-   Updated references to Scrapinghub, which is now called Zyte.
    (:gh:`4973`, :gh:`5072`)

-   Added a mention to contributors in the README. (:gh:`4956`)

-   Reduced the top margin of lists. (:gh:`4974`)


Quality Assurance
~~~~~~~~~~~~~~~~~

-   Made Python 3.9 support official (:gh:`4757`, :gh:`4759`)

-   Extended typing hints (:gh:`4895`)

-   Fixed deprecated uses of the Twisted API.
    (:gh:`4940`, :gh:`4950`, :gh:`5073`)

-   Made our tests run with the new pip resolver.
    (:gh:`4710`, :gh:`4814`)

-   Added tests to ensure that :ref:`coroutine support <coroutine-support>`
    is tested. (:gh:`4987`)

-   Migrated from Travis CI to GitHub Actions. (:gh:`4924`)

-   Fixed CI issues.
    (:gh:`4986`, :gh:`5020`, :gh:`5022`, :gh:`5027`, :gh:`5052`,
    :gh:`5053`)

-   Implemented code refactorings, style fixes and cleanups.
    (:gh:`4911`, :gh:`4982`, :gh:`5001`, :gh:`5002`, :gh:`5076`)


.. _release-2.4.1:

Scrapy 2.4.1 (2020-11-17)
-------------------------

-   Fixed :ref:`feed exports <topics-feed-exports>` overwrite support (:gh:`4845`, :gh:`4857`, :gh:`4859`)

-   Fixed the AsyncIO event loop handling, which could make code hang
    (:gh:`4855`, :gh:`4872`)

-   Fixed the IPv6-capable DNS resolver
    :class:`~scrapy.resolver.CachingHostnameResolver` for download handlers
    that call
    :meth:`reactor.resolve <twisted.internet.interfaces.IReactorCore.resolve>`
    (:gh:`4802`, :gh:`4803`)

-   Fixed the output of the :command:`genspider` command showing placeholders
    instead of the import path of the generated spider module (:gh:`4874`)

-   Migrated Windows CI from Azure Pipelines to GitHub Actions (:gh:`4869`,
    :gh:`4876`)


.. _release-2.4.0:

Scrapy 2.4.0 (2020-10-11)
-------------------------

Highlights:

*   Python 3.5 support has been dropped.

*   The ``file_path`` method of :ref:`media pipelines <topics-media-pipeline>`
    can now access the source :ref:`item <topics-items>`.

    This allows you to set a download file path based on item data.

*   The new ``item_export_kwargs`` key of the :setting:`FEEDS` setting allows
    to define keyword parameters to pass to :ref:`item exporter classes
    <topics-exporters>`

*   You can now choose whether :ref:`feed exports <topics-feed-exports>`
    overwrite or append to the output file.

    For example, when using the :command:`crawl` or :command:`runspider`
    commands, you can use the ``-O`` option instead of ``-o`` to overwrite the
    output file.

*   Zstd-compressed responses are now supported if zstandard_ is installed.

*   In settings, where the import path of a class is required, it is now
    possible to pass a class object instead.

Modified requirements
~~~~~~~~~~~~~~~~~~~~~

*   Python 3.6 or greater is now required; support for Python 3.5 has been
    dropped

    As a result:

    -   When using PyPy, PyPy 7.2.0 or greater :ref:`is now required
        <faq-python-versions>`

    -   For Amazon S3 storage support in :ref:`feed exports
        <topics-feed-storage-s3>` or :ref:`media pipelines
        <media-pipelines-s3>`, botocore_ 1.4.87 or greater is now required

    -   To use the :ref:`images pipeline <images-pipeline>`, Pillow_ 4.0.0 or
        greater is now required

    (:gh:`4718`, :gh:`4732`, :gh:`4733`, :gh:`4742`, :gh:`4743`,
    :gh:`4764`)


Backward-incompatible changes
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

*   :class:`~scrapy.downloadermiddlewares.cookies.CookiesMiddleware` once again
    discards cookies defined in :attr:`.Request.headers`.

    We decided to revert this bug fix, introduced in Scrapy 2.2.0, because it
    was reported that the current implementation could break existing code.

    If you need to set cookies for a request, use the :class:`Request.cookies
    <scrapy.Request>` parameter.

    A future version of Scrapy will include a new, better implementation of the
    reverted bug fix.

    (:gh:`4717`, :gh:`4823`)


.. _2.4-deprecation-removals:

Deprecation removals
~~~~~~~~~~~~~~~~~~~~

*   :class:`scrapy.extensions.feedexport.S3FeedStorage` no longer reads the
    values of ``access_key`` and ``secret_key`` from the running project
    settings when they are not passed to its ``__init__`` method; you must
    either pass those parameters to its ``__init__`` method or use
    :class:`S3FeedStorage.from_crawler
    <scrapy.extensions.feedexport.S3FeedStorage.from_crawler>`
    (:gh:`4356`, :gh:`4411`, :gh:`4688`)

*   :attr:`Rule.process_request <scrapy.spiders.crawl.Rule.process_request>`
    no longer admits callables which expect a single ``request`` parameter,
    rather than both ``request`` and ``response`` (:gh:`4818`)


Deprecations
~~~~~~~~~~~~

*   In custom :ref:`media pipelines <topics-media-pipeline>`, signatures that
    do not accept a keyword-only ``item`` parameter in any of the  methods that
    :ref:`now support this parameter <media-pipeline-item-parameter>` are now
    deprecated (:gh:`4628`, :gh:`4686`)

*   In custom :ref:`feed storage backend classes <topics-feed-storage>`,
    ``__init__`` method signatures that do not accept a keyword-only
    ``feed_options`` parameter are now deprecated (:gh:`547`, :gh:`716`,
    :gh:`4512`)

*   The :class:`scrapy.utils.python.WeakKeyCache` class is now deprecated
    (:gh:`4684`, :gh:`4701`)

*   The :func:`scrapy.utils.boto.is_botocore` function is now deprecated, use
    :func:`scrapy.utils.boto.is_botocore_available` instead (:gh:`4734`,
    :gh:`4776`)


New features
~~~~~~~~~~~~

.. _media-pipeline-item-parameter:

*   The following methods of :ref:`media pipelines <topics-media-pipeline>` now
    accept an ``item`` keyword-only parameter containing the source
    :ref:`item <topics-items>`:

    -   In :class:`scrapy.pipelines.files.FilesPipeline`:

        -   :meth:`~scrapy.pipelines.files.FilesPipeline.file_downloaded`

        -   :meth:`~scrapy.pipelines.files.FilesPipeline.file_path`

        -   :meth:`~scrapy.pipelines.files.FilesPipeline.media_downloaded`

        -   :meth:`~scrapy.pipelines.files.FilesPipeline.media_to_download`

    -   In :class:`scrapy.pipelines.images.ImagesPipeline`:

        -   :meth:`~scrapy.pipelines.images.ImagesPipeline.file_downloaded`

        -   :meth:`~scrapy.pipelines.images.ImagesPipeline.file_path`

        -   :meth:`~scrapy.pipelines.images.ImagesPipeline.get_images`

        -   :meth:`~scrapy.pipelines.images.ImagesPipeline.image_downloaded`

        -   :meth:`~scrapy.pipelines.images.ImagesPipeline.media_downloaded`

        -   :meth:`~scrapy.pipelines.images.ImagesPipeline.media_to_download`

    (:gh:`4628`, :gh:`4686`)

*   The new ``item_export_kwargs`` key of the :setting:`FEEDS` setting allows
    to define keyword parameters to pass to :ref:`item exporter classes
    <topics-exporters>` (:gh:`4606`, :gh:`4768`)

*   :ref:`Feed exports <topics-feed-exports>` gained overwrite support:

    *   When using the :command:`crawl` or :command:`runspider` commands, you
        can use the ``-O`` option instead of ``-o`` to overwrite the output
        file

    *   You can use the ``overwrite`` key in the :setting:`FEEDS` setting to
        configure whether to overwrite the output file (``True``) or append to
        its content (``False``)

    *   The ``__init__`` and ``from_crawler`` methods of :ref:`feed storage
        backend classes <topics-feed-storage>` now receive a new keyword-only
        parameter, ``feed_options``, which is a dictionary of :ref:`feed
        options <feed-options>`

    (:gh:`547`, :gh:`716`, :gh:`4512`)

*   Zstd-compressed responses are now supported if zstandard_ is installed
    (:gh:`4831`)

*   In settings, where the import path of a class is required, it is now
    possible to pass a class object instead (:gh:`3870`, :gh:`3873`).

    This includes also settings where only part of its value is made of an
    import path, such as :setting:`DOWNLOADER_MIDDLEWARES` or
    :setting:`DOWNLOAD_HANDLERS`.

*   :ref:`Downloader middlewares <topics-downloader-middleware>` can now
    override :class:`response.request <scrapy.http.Response.request>`.

    If a :ref:`downloader middleware <topics-downloader-middleware>` returns
    a :class:`~scrapy.http.Response` object from
    :meth:`~scrapy.downloadermiddlewares.DownloaderMiddleware.process_response`
    or
    :meth:`~scrapy.downloadermiddlewares.DownloaderMiddleware.process_exception`
    with a custom :class:`~scrapy.Request` object assigned to
    :class:`response.request <scrapy.http.Response.request>`:

    -   The response is handled by the callback of that custom
        :class:`~scrapy.Request` object, instead of being handled by the
        callback of the original :class:`~scrapy.Request` object

    -   That custom :class:`~scrapy.Request` object is now sent as the
        ``request`` argument to the :signal:`response_received` signal, instead
        of the original :class:`~scrapy.Request` object

    (:gh:`4529`, :gh:`4632`)

*   When using the :ref:`FTP feed storage backend <topics-feed-storage-ftp>`:

    -   It is now possible to set the new ``overwrite`` :ref:`feed option
        <feed-options>` to ``False`` to append to an existing file instead of
        overwriting it

    -   The FTP password can now be omitted if it is not necessary

    (:gh:`547`, :gh:`716`, :gh:`4512`)

*   The ``__init__`` method of :class:`~scrapy.exporters.CsvItemExporter` now
    supports an ``errors`` parameter to indicate how to handle encoding errors
    (:gh:`4755`)

*   When :ref:`using asyncio <using-asyncio>`, it is now possible to
    :ref:`set a custom asyncio loop <using-custom-loops>` (:gh:`4306`,
    :gh:`4414`)

*   Serialized requests (see :ref:`topics-jobs`) now support callbacks that are
    spider methods that delegate on other callable (:gh:`4756`)

*   When a response is larger than :setting:`DOWNLOAD_MAXSIZE`, the logged
    message is now a warning, instead of an error (:gh:`3874`,
    :gh:`3886`, :gh:`4752`)


Bug fixes
~~~~~~~~~

*   The :command:`genspider` command no longer overwrites existing files
    unless the ``--force`` option is used (:gh:`4561`, :gh:`4616`,
    :gh:`4623`)

*   Cookies with an empty value are no longer considered invalid cookies
    (:gh:`4772`)

*   The :command:`runspider` command now supports files with the ``.pyw`` file
    extension (:gh:`4643`, :gh:`4646`)

*   The :class:`~scrapy.downloadermiddlewares.httpproxy.HttpProxyMiddleware`
    middleware now simply ignores unsupported proxy values (:gh:`3331`,
    :gh:`4778`)

*   Checks for generator callbacks with a ``return`` statement no longer warn
    about ``return`` statements in nested functions (:gh:`4720`,
    :gh:`4721`)

*   The system file mode creation mask no longer affects the permissions of
    files generated using the :command:`startproject` command (:gh:`4722`)

*   ``scrapy.utils.iterators.xmliter`` now supports namespaced node names
    (:gh:`861`, :gh:`4746`)

*   :class:`~scrapy.Request` objects can now have ``about:`` URLs, which can
    work when using a headless browser (:gh:`4835`)


Documentation
~~~~~~~~~~~~~

*   The :setting:`FEED_URI_PARAMS` setting is now documented (:gh:`4671`,
    :gh:`4724`)

*   Improved the documentation of
    :ref:`link extractors <topics-link-extractors>` with an usage example from
    a spider callback and reference documentation for the
    :class:`~scrapy.link.Link` class (:gh:`4751`, :gh:`4775`)

*   Clarified the impact of :setting:`CONCURRENT_REQUESTS` when using the
    :class:`~scrapy.extensions.closespider.CloseSpider` extension
    (:gh:`4836`)

*   Removed references to Python 2’s ``unicode`` type (:gh:`4547`,
    :gh:`4703`)

*   We now have an :ref:`official deprecation policy <deprecation-policy>`
    (:gh:`4705`)

*   Our :ref:`documentation policies <documentation-policies>` now cover usage
    of Sphinx’s :rst:dir:`versionadded` and :rst:dir:`versionchanged`
    directives, and we have removed usages referencing Scrapy 1.4.0 and earlier
    versions (:gh:`3971`, :gh:`4310`)

*   Other documentation cleanups (:gh:`4090`, :gh:`4782`, :gh:`4800`,
    :gh:`4801`, :gh:`4809`, :gh:`4816`, :gh:`4825`)


Quality assurance
~~~~~~~~~~~~~~~~~

*   Extended typing hints (:gh:`4243`, :gh:`4691`)

*   Added tests for the :command:`check` command (:gh:`4663`)

*   Fixed test failures on Debian (:gh:`4726`, :gh:`4727`, :gh:`4735`)

*   Improved Windows test coverage (:gh:`4723`)

*   Switched to :ref:`formatted string literals <f-strings>` where possible
    (:gh:`4307`, :gh:`4324`, :gh:`4672`)

*   Modernized :func:`super` usage (:gh:`4707`)

*   Other code and test cleanups (:gh:`1790`, :gh:`3288`, :gh:`4165`,
    :gh:`4564`, :gh:`4651`, :gh:`4714`, :gh:`4738`, :gh:`4745`,
    :gh:`4747`, :gh:`4761`, :gh:`4765`, :gh:`4804`, :gh:`4817`,
    :gh:`4820`, :gh:`4822`, :gh:`4839`)


.. _release-2.3.0:

Scrapy 2.3.0 (2020-08-04)
-------------------------

Highlights:

*   :ref:`Feed exports <topics-feed-exports>` now support :ref:`Google Cloud
    Storage <topics-feed-storage-gcs>` as a storage backend

*   The new :setting:`FEED_EXPORT_BATCH_ITEM_COUNT` setting allows to deliver
    output items in batches of up to the specified number of items.

    It also serves as a workaround for :ref:`delayed file delivery
    <delayed-file-delivery>`, which causes Scrapy to only start item delivery
    after the crawl has finished when using certain storage backends
    (:ref:`S3 <topics-feed-storage-s3>`, :ref:`FTP <topics-feed-storage-ftp>`,
    and now :ref:`GCS <topics-feed-storage-gcs>`).

*   The base implementation of :ref:`item loaders <topics-loaders>` has been
    moved into a separate library, :doc:`itemloaders <itemloaders:index>`,
    allowing usage from outside Scrapy and a separate release schedule

Deprecation removals
~~~~~~~~~~~~~~~~~~~~

*   Removed the following classes and their parent modules from
    ``scrapy.linkextractors``:

    *   ``htmlparser.HtmlParserLinkExtractor``
    *   ``regex.RegexLinkExtractor``
    *   ``sgml.BaseSgmlLinkExtractor``
    *   ``sgml.SgmlLinkExtractor``

    Use
    :class:`LinkExtractor <scrapy.linkextractors.lxmlhtml.LxmlLinkExtractor>`
    instead (:gh:`4356`, :gh:`4679`)


Deprecations
~~~~~~~~~~~~

*   The ``scrapy.utils.python.retry_on_eintr`` function is now deprecated
    (:gh:`4683`)


New features
~~~~~~~~~~~~

*   :ref:`Feed exports <topics-feed-exports>` support :ref:`Google Cloud
    Storage <topics-feed-storage-gcs>` (:gh:`685`, :gh:`3608`)

*   New :setting:`FEED_EXPORT_BATCH_ITEM_COUNT` setting for batch deliveries
    (:gh:`4250`, :gh:`4434`)

*   The :command:`parse` command now allows specifying an output file
    (:gh:`4317`, :gh:`4377`)

*   :meth:`.Request.from_curl` and
    :func:`~scrapy.utils.curl.curl_to_request_kwargs` now also support
    ``--data-raw`` (:gh:`4612`)

*   A ``parse`` callback may now be used in built-in spider subclasses, such
    as :class:`~scrapy.spiders.CrawlSpider` (:gh:`712`, :gh:`732`,
    :gh:`781`, :gh:`4254` )


Bug fixes
~~~~~~~~~

*   Fixed the :ref:`CSV exporting <topics-feed-format-csv>` of
    :ref:`dataclass items <dataclass-items>` and :ref:`attr.s items
    <attrs-items>` (:gh:`4667`, :gh:`4668`)

*   :meth:`.Request.from_curl` and
    :func:`~scrapy.utils.curl.curl_to_request_kwargs` now set the request
    method to ``POST`` when a request body is specified and no request method
    is specified (:gh:`4612`)

*   The processing of ANSI escape sequences in enabled in Windows 10.0.14393
    and later, where it is required for colored output (:gh:`4393`,
    :gh:`4403`)


Documentation
~~~~~~~~~~~~~

*   Updated the `OpenSSL cipher list format`_ link in the documentation about
    the :setting:`DOWNLOADER_CLIENT_TLS_CIPHERS` setting (:gh:`4653`)

*   Simplified the code example in :ref:`topics-loaders-dataclass`
    (:gh:`4652`)

.. _OpenSSL cipher list format: https://docs.openssl.org/master/man1/openssl-ciphers/#cipher-list-format


Quality assurance
~~~~~~~~~~~~~~~~~

*   The base implementation of :ref:`item loaders <topics-loaders>` has been
    moved into :doc:`itemloaders <itemloaders:index>` (:gh:`4005`,
    :gh:`4516`)

*   Fixed a silenced error in some scheduler tests (:gh:`4644`,
    :gh:`4645`)

*   Renewed the localhost certificate used for SSL tests (:gh:`4650`)

*   Removed cookie-handling code specific to Python 2 (:gh:`4682`)

*   Stopped using Python 2 unicode literal syntax (:gh:`4704`)

*   Stopped using a backlash for line continuation (:gh:`4673`)

*   Removed unneeded entries from the MyPy exception list (:gh:`4690`)

*   Automated tests now pass on Windows as part of our continuous integration
    system (:gh:`4458`)

*   Automated tests now pass on the latest PyPy version for supported Python
    versions in our continuous integration system (:gh:`4504`)


.. _release-2.2.1:

Scrapy 2.2.1 (2020-07-17)
-------------------------

*   The :command:`startproject` command no longer makes unintended changes to
    the permissions of files in the destination folder, such as removing
    execution permissions (:gh:`4662`, :gh:`4666`)


.. _release-2.2.0:

Scrapy 2.2.0 (2020-06-24)
-------------------------

Highlights:

* Python 3.5.2+ is required now
* :ref:`dataclass objects <dataclass-items>` and
  :ref:`attrs objects <attrs-items>` are now valid :ref:`item types
  <item-types>`
* New :meth:`TextResponse.json <scrapy.http.TextResponse.json>` method
* New :signal:`bytes_received` signal that allows canceling response download
* :class:`~scrapy.downloadermiddlewares.cookies.CookiesMiddleware` fixes

Backward-incompatible changes
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

*   Support for Python 3.5.0 and 3.5.1 has been dropped; Scrapy now refuses to
    run with a Python version lower than 3.5.2, which introduced
    :class:`typing.Type` (:gh:`4615`)


Deprecations
~~~~~~~~~~~~

*   ``TextResponse.body_as_unicode()`` is now deprecated, use
    :attr:`TextResponse.text <scrapy.http.TextResponse.text>` instead
    (:gh:`4546`, :gh:`4555`, :gh:`4579`)

*   :class:`scrapy.item.BaseItem` is now deprecated, use
    :class:`scrapy.item.Item` instead (:gh:`4534`)


New features
~~~~~~~~~~~~

*   :ref:`dataclass objects <dataclass-items>` and
    :ref:`attrs objects <attrs-items>` are now valid :ref:`item types
    <item-types>`, and a new itemadapter_ library makes it easy to
    write code that :ref:`supports any item type <supporting-item-types>`
    (:gh:`2749`, :gh:`2807`, :gh:`3761`, :gh:`3881`, :gh:`4642`)

*   A new :meth:`TextResponse.json <scrapy.http.TextResponse.json>` method
    allows to deserialize JSON responses (:gh:`2444`, :gh:`4460`,
    :gh:`4574`)

*   A new :signal:`bytes_received` signal allows monitoring response download
    progress and :ref:`stopping downloads <topics-stop-response-download>`
    (:gh:`4205`, :gh:`4559`)

*   The dictionaries in the result list of a :ref:`media pipeline
    <topics-media-pipeline>` now include a new key, ``status``, which indicates
    if the file was downloaded or, if the file was not downloaded, why it was
    not downloaded; see :meth:`FilesPipeline.get_media_requests
    <scrapy.pipelines.files.FilesPipeline.get_media_requests>` for more
    information (:gh:`2893`, :gh:`4486`)

*   When using :ref:`Google Cloud Storage <media-pipeline-gcs>` for
    a :ref:`media pipeline <topics-media-pipeline>`, a warning is now logged if
    the configured credentials do not grant the required permissions
    (:gh:`4346`, :gh:`4508`)

*   :ref:`Link extractors <topics-link-extractors>` are now serializable,
    as long as you do not use :ref:`lambdas <lambda>` for parameters; for
    example, you can now pass link extractors in :attr:`.Request.cb_kwargs`
    or :attr:`.Request.meta` when :ref:`persisting
    scheduled requests <topics-jobs>` (:gh:`4554`)

*   Upgraded the :ref:`pickle protocol <pickle-protocols>` that Scrapy uses
    from protocol 2 to protocol 4, improving serialization capabilities and
    performance (:gh:`4135`, :gh:`4541`)

*   :func:`scrapy.utils.misc.create_instance` now raises a :exc:`TypeError`
    exception if the resulting instance is ``None`` (:gh:`4528`,
    :gh:`4532`)

.. _itemadapter: https://github.com/scrapy/itemadapter


Bug fixes
~~~~~~~~~

*   :class:`~scrapy.downloadermiddlewares.cookies.CookiesMiddleware` no longer
    discards cookies defined in :attr:`Request.headers
    <scrapy.Request.headers>` (:gh:`1992`, :gh:`2400`)

*   :class:`~scrapy.downloadermiddlewares.cookies.CookiesMiddleware` no longer
    re-encodes cookies defined as :class:`bytes` in the ``cookies`` parameter
    of the ``__init__`` method of :class:`~scrapy.Request`
    (:gh:`2400`, :gh:`3575`)

*   When :setting:`FEEDS` defines multiple URIs, :setting:`FEED_STORE_EMPTY` is
    ``False`` and the crawl yields no items, Scrapy no longer stops feed
    exports after the first URI (:gh:`4621`, :gh:`4626`)

*   :class:`~scrapy.spiders.Spider` callbacks defined using :doc:`coroutine
    syntax <topics/coroutines>` no longer need to return an iterable, and may
    instead return a :class:`~scrapy.Request` object, an
    :ref:`item <topics-items>`, or ``None`` (:gh:`4609`)

*   The :command:`startproject` command now ensures that the generated project
    folders and files have the right permissions (:gh:`4604`)

*   Fix a :exc:`KeyError` exception being sometimes raised from
    :class:`scrapy.utils.datatypes.LocalWeakReferencedCache` (:gh:`4597`,
    :gh:`4599`)

*   When :setting:`FEEDS` defines multiple URIs, log messages about items being
    stored now contain information from the corresponding feed, instead of
    always containing information about only one of the feeds (:gh:`4619`,
    :gh:`4629`)


Documentation
~~~~~~~~~~~~~

*   Added a new section about :ref:`accessing cb_kwargs from errbacks
    <errback-cb_kwargs>` (:gh:`4598`, :gh:`4634`)

*   Covered chompjs_ in :ref:`topics-parsing-javascript` (:gh:`4556`,
    :gh:`4562`)

*   Removed from :doc:`topics/coroutines` the warning about the API being
    experimental (:gh:`4511`, :gh:`4513`)

*   Removed references to unsupported versions of :doc:`Twisted
    <twisted:index>` (:gh:`4533`)

*   Updated the description of the :ref:`screenshot pipeline example
    <ScreenshotPipeline>`, which now uses :doc:`coroutine syntax
    <topics/coroutines>` instead of returning a
    :class:`~twisted.internet.defer.Deferred` (:gh:`4514`, :gh:`4593`)

*   Removed a misleading import line from the
    :func:`scrapy.utils.log.configure_logging` code example (:gh:`4510`,
    :gh:`4587`)

*   The display-on-hover behavior of internal documentation references now also
    covers links to :ref:`commands <topics-commands>`, :attr:`.Request.meta`
    keys, :ref:`settings <topics-settings>` and
    :ref:`signals <topics-signals>` (:gh:`4495`, :gh:`4563`)

*   It is again possible to download the documentation for offline reading
    (:gh:`4578`, :gh:`4585`)

*   Removed backslashes preceding ``*args`` and ``**kwargs`` in some function
    and method signatures (:gh:`4592`, :gh:`4596`)

.. _chompjs: https://github.com/Nykakin/chompjs


Quality assurance
~~~~~~~~~~~~~~~~~

*   Adjusted the code base further to our :ref:`style guidelines
    <coding-style>` (:gh:`4237`, :gh:`4525`, :gh:`4538`,
    :gh:`4539`, :gh:`4540`, :gh:`4542`, :gh:`4543`, :gh:`4544`,
    :gh:`4545`, :gh:`4557`, :gh:`4558`, :gh:`4566`, :gh:`4568`,
    :gh:`4572`)

*   Removed remnants of Python 2 support (:gh:`4550`, :gh:`4553`,
    :gh:`4568`)

*   Improved code sharing between the :command:`crawl` and :command:`runspider`
    commands (:gh:`4548`, :gh:`4552`)

*   Replaced ``chain(*iterable)`` with ``chain.from_iterable(iterable)``
    (:gh:`4635`)

*   You may now run the :mod:`asyncio` tests with Tox on any Python version
    (:gh:`4521`)

*   Updated test requirements to reflect an incompatibility with pytest 5.4 and
    5.4.1 (:gh:`4588`)

*   Improved :class:`~scrapy.spiderloader.SpiderLoader` test coverage for
    scenarios involving duplicate spider names (:gh:`4549`, :gh:`4560`)

*   Configured Travis CI to also run the tests with Python 3.5.2
    (:gh:`4518`, :gh:`4615`)

*   Added a `Pylint <https://www.pylint.org/>`_ job to Travis CI
    (:gh:`3727`)

*   Added a `Mypy <https://mypy-lang.org/>`_ job to Travis CI (:gh:`4637`)

*   Made use of set literals in tests (:gh:`4573`)

*   Cleaned up the Travis CI configuration (:gh:`4517`, :gh:`4519`,
    :gh:`4522`, :gh:`4537`)


.. _release-2.1.0:

Scrapy 2.1.0 (2020-04-24)
-------------------------

Highlights:

* New :setting:`FEEDS` setting to export to multiple feeds
* New :attr:`Response.ip_address <scrapy.http.Response.ip_address>` attribute

Backward-incompatible changes
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

*   :exc:`AssertionError` exceptions triggered by :ref:`assert <assert>`
    statements have been replaced by new exception types, to support running
    Python in optimized mode (see :option:`-O`) without changing Scrapy’s
    behavior in any unexpected ways.

    If you catch an :exc:`AssertionError` exception from Scrapy, update your
    code to catch the corresponding new exception.

    (:gh:`4440`)


Deprecation removals
~~~~~~~~~~~~~~~~~~~~

*   The ``LOG_UNSERIALIZABLE_REQUESTS`` setting is no longer supported, use
    :setting:`SCHEDULER_DEBUG` instead (:gh:`4385`)

*   The ``REDIRECT_MAX_METAREFRESH_DELAY`` setting is no longer supported, use
    :setting:`METAREFRESH_MAXDELAY` instead (:gh:`4385`)

*   The :class:`~scrapy.downloadermiddlewares.chunked.ChunkedTransferMiddleware`
    middleware has been removed, including the entire
    :class:`scrapy.downloadermiddlewares.chunked` module; chunked transfers
    work out of the box (:gh:`4431`)

*   The ``spiders`` property has been removed from
    :class:`~scrapy.crawler.Crawler`, use :class:`CrawlerRunner.spider_loader
    <scrapy.crawler.CrawlerRunner.spider_loader>` or instantiate
    :setting:`SPIDER_LOADER_CLASS` with your settings instead (:gh:`4398`)

*   The ``MultiValueDict``, ``MultiValueDictKeyError``, and ``SiteNode``
    classes have been removed from :mod:`scrapy.utils.datatypes`
    (:gh:`4400`)


Deprecations
~~~~~~~~~~~~

*   The ``FEED_FORMAT`` and ``FEED_URI`` settings have been deprecated in
    favor of the new :setting:`FEEDS` setting (:gh:`1336`, :gh:`3858`,
    :gh:`4507`)


New features
~~~~~~~~~~~~

*   A new setting, :setting:`FEEDS`, allows configuring multiple output feeds
    with different settings each (:gh:`1336`, :gh:`3858`, :gh:`4507`)

*   The :command:`crawl` and :command:`runspider` commands now support multiple
    ``-o`` parameters (:gh:`1336`, :gh:`3858`, :gh:`4507`)

*   The :command:`crawl` and :command:`runspider` commands now support
    specifying an output format by appending ``:<format>`` to the output file
    (:gh:`1336`, :gh:`3858`, :gh:`4507`)

*   The new :attr:`Response.ip_address <scrapy.http.Response.ip_address>`
    attribute gives access to the IP address that originated a response
    (:gh:`3903`, :gh:`3940`)

*   A warning is now issued when a value in
    :attr:`~scrapy.spiders.Spider.allowed_domains` includes a port
    (:gh:`50`, :gh:`3198`, :gh:`4413`)

*   Zsh completion now excludes used option aliases from the completion list
    (:gh:`4438`)


Bug fixes
~~~~~~~~~

*   :ref:`Request serialization <request-serialization>` no longer breaks for
    callbacks that are spider attributes which are assigned a function with a
    different name (:gh:`4500`)

*   ``None`` values in :attr:`~scrapy.spiders.Spider.allowed_domains` no longer
    cause a :exc:`TypeError` exception (:gh:`4410`)

*   Zsh completion no longer allows options after arguments (:gh:`4438`)

*   zope.interface 5.0.0 and later versions are now supported
    (:gh:`4447`, :gh:`4448`)

*   ``Spider.make_requests_from_url``, deprecated in Scrapy 1.4.0, now issues a
    warning when used (:gh:`4412`)


Documentation
~~~~~~~~~~~~~

*   Improved the documentation about signals that allow their handlers to
    return a :class:`~twisted.internet.defer.Deferred` (:gh:`4295`,
    :gh:`4390`)

*   Our PyPI entry now includes links for our documentation, our source code
    repository and our issue tracker (:gh:`4456`)

*   Covered the `curl2scrapy <https://michael-shub.github.io/curl2scrapy/>`_
    service in the documentation (:gh:`4206`, :gh:`4455`)

*   Removed references to the Guppy library, which only works in Python 2
    (:gh:`4285`, :gh:`4343`)

*   Extended use of InterSphinx to link to Python 3 documentation
    (:gh:`4444`, :gh:`4445`)

*   Added support for Sphinx 3.0 and later (:gh:`4475`, :gh:`4480`,
    :gh:`4496`, :gh:`4503`)


Quality assurance
~~~~~~~~~~~~~~~~~

*   Removed warnings about using old, removed settings (:gh:`4404`)

*   Removed a warning about importing
    :class:`~twisted.internet.testing.StringTransport` from
    ``twisted.test.proto_helpers`` in Twisted 19.7.0 or newer (:gh:`4409`)

*   Removed outdated Debian package build files (:gh:`4384`)

*   Removed :class:`object` usage as a base class (:gh:`4430`)

*   Removed code that added support for old versions of Twisted that we no
    longer support (:gh:`4472`)

*   Fixed code style issues (:gh:`4468`, :gh:`4469`, :gh:`4471`,
    :gh:`4481`)

*   Removed :func:`twisted.internet.defer.returnValue` calls (:gh:`4443`,
    :gh:`4446`, :gh:`4489`)


.. _release-2.0.1:

Scrapy 2.0.1 (2020-03-18)
-------------------------

*   :meth:`Response.follow_all <scrapy.http.Response.follow_all>` now supports
    an empty URL iterable as input (:gh:`4408`, :gh:`4420`)

*   Removed top-level :mod:`~twisted.internet.reactor` imports to prevent
    errors about the wrong Twisted reactor being installed when setting a
    different Twisted reactor using :setting:`TWISTED_REACTOR` (:gh:`4401`,
    :gh:`4406`)

*   Fixed tests (:gh:`4422`)


.. _release-2.0.0:

Scrapy 2.0.0 (2020-03-03)
-------------------------

Highlights:

* Python 2 support has been removed
* :doc:`Partial <topics/coroutines>` :ref:`coroutine syntax <async>` support
  and :doc:`experimental <topics/asyncio>` :mod:`asyncio` support
* New :meth:`Response.follow_all <scrapy.http.Response.follow_all>` method
* :ref:`FTP support <media-pipeline-ftp>` for media pipelines
* New :attr:`Response.certificate <scrapy.http.Response.certificate>`
  attribute
* IPv6 support through ``DNS_RESOLVER``

Backward-incompatible changes
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

*   Python 2 support has been removed, following `Python 2 end-of-life on
    January 1, 2020`_ (:gh:`4091`, :gh:`4114`, :gh:`4115`,
    :gh:`4121`, :gh:`4138`, :gh:`4231`, :gh:`4242`, :gh:`4304`,
    :gh:`4309`, :gh:`4373`)

*   Retry gaveups (see :setting:`RETRY_TIMES`) are now logged as errors instead
    of as debug information (:gh:`3171`, :gh:`3566`)

*   File extensions that
    :class:`LinkExtractor <scrapy.linkextractors.lxmlhtml.LxmlLinkExtractor>`
    ignores by default now also include ``7z``, ``7zip``, ``apk``, ``bz2``,
    ``cdr``, ``dmg``, ``ico``, ``iso``, ``tar``, ``tar.gz``, ``webm``, and
    ``xz`` (:gh:`1837`, :gh:`2067`, :gh:`4066`)

*   The :setting:`METAREFRESH_IGNORE_TAGS` setting is now an empty list by
    default, following web browser behavior (:gh:`3844`, :gh:`4311`)

*   The
    :class:`~scrapy.downloadermiddlewares.httpcompression.HttpCompressionMiddleware`
    now includes spaces after commas in the value of the ``Accept-Encoding``
    header that it sets, following web browser behavior (:gh:`4293`)

*   The ``__init__`` method of custom download handlers (see
    :setting:`DOWNLOAD_HANDLERS`) or subclasses of the following downloader
    handlers  no longer receives a ``settings`` parameter:

    *   :class:`scrapy.core.downloader.handlers.datauri.DataURIDownloadHandler`

    *   :class:`scrapy.core.downloader.handlers.file.FileDownloadHandler`

    Use the ``from_settings`` or ``from_crawler`` class methods to expose such
    a parameter to your custom download handlers.

    (:gh:`4126`)

*   We have refactored the :class:`scrapy.core.scheduler.Scheduler` class and
    related queue classes (see :setting:`SCHEDULER_PRIORITY_QUEUE`,
    :setting:`SCHEDULER_DISK_QUEUE` and :setting:`SCHEDULER_MEMORY_QUEUE`) to
    make it easier to implement custom scheduler queue classes. See
    :ref:`2-0-0-scheduler-queue-changes` below for details.

*   Overridden settings are now logged in a different format. This is more in
    line with similar information logged at startup (:gh:`4199`)

.. _Python 2 end-of-life on January 1, 2020: https://www.python.org/doc/sunset-python-2/


Deprecation removals
~~~~~~~~~~~~~~~~~~~~

*   The :ref:`Scrapy shell <topics-shell>` no longer provides a `sel` proxy
    object, use :meth:`response.selector <scrapy.http.TextResponse.selector>`
    instead (:gh:`4347`)

*   LevelDB support has been removed (:gh:`4112`)

*   The following functions have been removed from :mod:`scrapy.utils.python`:
    ``isbinarytext``, ``is_writable``, ``setattr_default``, ``stringify_dict``
    (:gh:`4362`)


Deprecations
~~~~~~~~~~~~

*   Using environment variables prefixed with ``SCRAPY_`` to override settings
    is deprecated (:gh:`4300`, :gh:`4374`, :gh:`4375`)

*   :class:`scrapy.linkextractors.FilteringLinkExtractor` is deprecated, use
    :class:`scrapy.linkextractors.LinkExtractor
    <scrapy.linkextractors.lxmlhtml.LxmlLinkExtractor>` instead (:gh:`4045`)

*   The ``noconnect`` query string argument of proxy URLs is deprecated and
    should be removed from proxy URLs (:gh:`4198`)

*   The :meth:`next <scrapy.utils.python.MutableChain.next>` method of
    :class:`scrapy.utils.python.MutableChain` is deprecated, use the global
    :func:`next` function or :meth:`MutableChain.__next__
    <scrapy.utils.python.MutableChain.__next__>` instead (:gh:`4153`)


New features
~~~~~~~~~~~~

*   Added :doc:`partial support <topics/coroutines>` for Python’s
    :ref:`coroutine syntax <async>` and :doc:`experimental support
    <topics/asyncio>` for :mod:`asyncio` and :mod:`asyncio`-powered libraries
    (:gh:`4010`, :gh:`4259`, :gh:`4269`, :gh:`4270`, :gh:`4271`,
    :gh:`4316`, :gh:`4318`)

*   The new :meth:`Response.follow_all <scrapy.http.Response.follow_all>`
    method offers the same functionality as
    :meth:`Response.follow <scrapy.http.Response.follow>` but supports an
    iterable of URLs as input and returns an iterable of requests
    (:gh:`2582`, :gh:`4057`, :gh:`4286`)

*   :ref:`Media pipelines <topics-media-pipeline>` now support :ref:`FTP
    storage <media-pipeline-ftp>` (:gh:`3928`, :gh:`3961`)

*   The new :attr:`Response.certificate <scrapy.http.Response.certificate>`
    attribute exposes the SSL certificate of the server as a
    :class:`twisted.internet.ssl.Certificate` object for HTTPS responses
    (:gh:`2726`, :gh:`4054`)

*   A new ``DNS_RESOLVER`` setting allows enabling IPv6 support
    (:gh:`1031`, :gh:`4227`)

*   A new :setting:`SCRAPER_SLOT_MAX_ACTIVE_SIZE` setting allows configuring
    the existing soft limit that pauses request downloads when the total
    response data being processed is too high (:gh:`1410`, :gh:`3551`)

*   A new :setting:`TWISTED_REACTOR` setting allows customizing the
    :mod:`~twisted.internet.reactor` that Scrapy uses, allowing to
    :doc:`enable asyncio support <topics/asyncio>` or deal with a
    :ref:`common macOS issue <faq-specific-reactor>` (:gh:`2905`,
    :gh:`4294`)

*   Scheduler disk and memory queues may now use the class methods
    ``from_crawler`` or ``from_settings`` (:gh:`3884`)

*   The new :attr:`Response.cb_kwargs <scrapy.http.Response.cb_kwargs>`
    attribute serves as a shortcut for :attr:`Response.request.cb_kwargs
    <scrapy.Request.cb_kwargs>` (:gh:`4331`)

*   :meth:`Response.follow <scrapy.http.Response.follow>` now supports a
    ``flags`` parameter, for consistency with :class:`~scrapy.Request`
    (:gh:`4277`, :gh:`4279`)

*   :ref:`Item loader processors <topics-loaders-processors>` can now be
    regular functions, they no longer need to be methods (:gh:`3899`)

*   :class:`~scrapy.spiders.Rule` now accepts an ``errback`` parameter
    (:gh:`4000`)

*   :class:`~scrapy.Request` no longer requires a ``callback`` parameter
    when an ``errback`` parameter is specified (:gh:`3586`, :gh:`4008`)

*   :class:`~scrapy.logformatter.LogFormatter` now supports some additional
    methods:

    *   :class:`~scrapy.logformatter.LogFormatter.download_error` for
        download errors

    *   :class:`~scrapy.logformatter.LogFormatter.item_error` for exceptions
        raised during item processing by :ref:`item pipelines
        <topics-item-pipeline>`

    *   :class:`~scrapy.logformatter.LogFormatter.spider_error` for exceptions
        raised from :ref:`spider callbacks <topics-spiders>`

    (:gh:`374`, :gh:`3986`, :gh:`3989`, :gh:`4176`, :gh:`4188`)

*   The :setting:`FEED_URI` setting now supports :class:`pathlib.Path` values
    (:gh:`3731`, :gh:`4074`)

*   A new :signal:`request_left_downloader` signal is sent when a request
    leaves the downloader (:gh:`4303`)

*   Scrapy logs a warning when it detects a request callback or errback that
    uses ``yield`` but also returns a value, since the returned value would be
    lost (:gh:`3484`, :gh:`3869`)

*   :class:`~scrapy.spiders.Spider` objects now raise an :exc:`AttributeError`
    exception if they do not have a :class:`~scrapy.spiders.Spider.start_urls`
    attribute nor reimplement ``scrapy.spiders.Spider.start_requests()``,
    but have a ``start_url`` attribute (:gh:`4133`, :gh:`4170`)

*   :class:`~scrapy.exporters.BaseItemExporter` subclasses may now use
    ``super().__init__(**kwargs)`` instead of ``self._configure(kwargs)`` in
    their ``__init__`` method, passing ``dont_fail=True`` to the parent
    ``__init__`` method if needed, and accessing ``kwargs`` at ``self._kwargs``
    after calling their parent ``__init__`` method (:gh:`4193`,
    :gh:`4370`)

*   A new ``keep_fragments`` parameter of
    ``scrapy.utils.request.request_fingerprint`` allows to generate
    different fingerprints for requests with different fragments in their URL
    (:gh:`4104`)

*   Download handlers (see :setting:`DOWNLOAD_HANDLERS`) may now use the
    ``from_settings`` and ``from_crawler`` class methods that other Scrapy
    components already supported (:gh:`4126`)

*   :class:`scrapy.utils.python.MutableChain.__iter__` now returns ``self``,
    allowing it to be used as a sequence.
    (:gh:`4153`)


Bug fixes
~~~~~~~~~

*   The :command:`crawl` command now also exits with exit code 1 when an
    exception happens before the crawling starts (:gh:`4175`, :gh:`4207`)

*   :class:`LinkExtractor.extract_links
    <scrapy.linkextractors.lxmlhtml.LxmlLinkExtractor.extract_links>` no longer
    re-encodes the query string or URLs from non-UTF-8 responses in UTF-8
    (:gh:`998`, :gh:`1403`, :gh:`1949`, :gh:`4321`)

*   The first spider middleware (see :setting:`SPIDER_MIDDLEWARES`) now also
    processes exceptions raised from callbacks that are generators
    (:gh:`4260`, :gh:`4272`)

*   Redirects to URLs starting with 3 slashes (``///``) are now supported
    (:gh:`4032`, :gh:`4042`)

*   :class:`~scrapy.Request` no longer accepts strings as ``url`` simply
    because they have a colon (:gh:`2552`, :gh:`4094`)

*   The correct encoding is now used for attach names in
    :class:`~scrapy.mail.MailSender` (:gh:`4229`, :gh:`4239`)

*   :class:`~scrapy.dupefilters.RFPDupeFilter`, the default
    :setting:`DUPEFILTER_CLASS`, no longer writes an extra ``\r`` character on
    each line in Windows, which made the size of the ``requests.seen`` file
    unnecessarily large on that platform (:gh:`4283`)

*   Z shell auto-completion now looks for ``.html`` files, not ``.http`` files,
    and covers the ``-h`` command-line switch (:gh:`4122`, :gh:`4291`)

*   Adding items to a :class:`scrapy.utils.datatypes.LocalCache` object
    without a ``limit`` defined no longer raises a :exc:`TypeError` exception
    (:gh:`4123`)

*   Fixed a typo in the message of the :exc:`ValueError` exception raised when
    :func:`scrapy.utils.misc.create_instance` gets both ``settings`` and
    ``crawler`` set to ``None`` (:gh:`4128`)


Documentation
~~~~~~~~~~~~~

*   API documentation now links to an online, syntax-highlighted view of the
    corresponding source code (:gh:`4148`)

*   Links to unexisting documentation pages now allow access to the sidebar
    (:gh:`4152`, :gh:`4169`)

*   Cross-references within our documentation now display a tooltip when
    hovered (:gh:`4173`, :gh:`4183`)

*   Improved the documentation about :meth:`LinkExtractor.extract_links
    <scrapy.linkextractors.lxmlhtml.LxmlLinkExtractor.extract_links>` and
    simplified :ref:`topics-link-extractors` (:gh:`4045`)

*   Clarified how :class:`ItemLoader.item <scrapy.loader.ItemLoader.item>`
    works (:gh:`3574`, :gh:`4099`)

*   Clarified that :func:`logging.basicConfig` should not be used when also
    using :class:`~scrapy.crawler.CrawlerProcess` (:gh:`2149`,
    :gh:`2352`, :gh:`3146`, :gh:`3960`)

*   Clarified the requirements for :class:`~scrapy.Request` objects
    :ref:`when using persistence <request-serialization>` (:gh:`4124`,
    :gh:`4139`)

*   Clarified how to install a :ref:`custom image pipeline
    <media-pipeline-example>` (:gh:`4034`, :gh:`4252`)

*   Fixed the signatures of the ``file_path`` method in :ref:`media pipeline
    <topics-media-pipeline>` examples (:gh:`4290`)

*   Covered a backward-incompatible change in Scrapy 1.7.0 affecting custom
    :class:`scrapy.core.scheduler.Scheduler` subclasses (:gh:`4274`)

*   Improved the ``README.rst`` and ``CODE_OF_CONDUCT.md`` files
    (:gh:`4059`)

*   Documentation examples are now checked as part of our test suite and we
    have fixed some of the issues detected (:gh:`4142`, :gh:`4146`,
    :gh:`4171`, :gh:`4184`, :gh:`4190`)

*   Fixed logic issues, broken links and typos (:gh:`4247`, :gh:`4258`,
    :gh:`4282`, :gh:`4288`, :gh:`4305`, :gh:`4308`, :gh:`4323`,
    :gh:`4338`, :gh:`4359`, :gh:`4361`)

*   Improved consistency when referring to the ``__init__`` method of an object
    (:gh:`4086`, :gh:`4088`)

*   Fixed an inconsistency between code and output in :ref:`intro-overview`
    (:gh:`4213`)

*   Extended :mod:`~sphinx.ext.intersphinx` usage (:gh:`4147`,
    :gh:`4172`, :gh:`4185`, :gh:`4194`, :gh:`4197`)

*   We now use a recent version of Python to build the documentation
    (:gh:`4140`, :gh:`4249`)

*   Cleaned up documentation (:gh:`4143`, :gh:`4275`)


Quality assurance
~~~~~~~~~~~~~~~~~

*   Re-enabled proxy ``CONNECT`` tests (:gh:`2545`, :gh:`4114`)

*   Added Bandit_ security checks to our test suite (:gh:`4162`,
    :gh:`4181`)

*   Added Flake8_ style checks to our test suite and applied many of the
    corresponding changes (:gh:`3944`, :gh:`3945`, :gh:`4137`,
    :gh:`4157`, :gh:`4167`, :gh:`4174`, :gh:`4186`, :gh:`4195`,
    :gh:`4238`, :gh:`4246`, :gh:`4355`, :gh:`4360`, :gh:`4365`)

*   Improved test coverage (:gh:`4097`, :gh:`4218`, :gh:`4236`)

*   Started reporting slowest tests, and improved the performance of some of
    them (:gh:`4163`, :gh:`4164`)

*   Fixed broken tests and refactored some tests (:gh:`4014`, :gh:`4095`,
    :gh:`4244`, :gh:`4268`, :gh:`4372`)

*   Modified the :doc:`tox <tox:index>` configuration to allow running tests
    with any Python version, run Bandit_ and Flake8_ tests by default, and
    enforce a minimum tox version programmatically (:gh:`4179`)

*   Cleaned up code (:gh:`3937`, :gh:`4208`, :gh:`4209`,
    :gh:`4210`, :gh:`4212`, :gh:`4369`, :gh:`4376`, :gh:`4378`)

.. _Bandit: https://bandit.readthedocs.io/en/latest/
.. _Flake8: https://flake8.pycqa.org/en/latest/


.. _2-0-0-scheduler-queue-changes:

Changes to scheduler queue classes
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The following changes may impact any custom queue classes of all types:

*   The ``push`` method no longer receives a second positional parameter
    containing ``request.priority * -1``. If you need that value, get it
    from the first positional parameter, ``request``, instead, or use
    the new :meth:`~scrapy.core.scheduler.ScrapyPriorityQueue.priority`
    method in :class:`scrapy.core.scheduler.ScrapyPriorityQueue`
    subclasses.

The following changes may impact custom priority queue classes:

*   In the ``__init__`` method or the ``from_crawler`` or ``from_settings``
    class methods:

    *   The parameter that used to contain a factory function,
        ``qfactory``, is now passed as a keyword parameter named
        ``downstream_queue_cls``.

    *   A new keyword parameter has been added: ``key``. It is a string
        that is always an empty string for memory queues and indicates the
        :setting:`JOBDIR` value for disk queues.

    *   The parameter for disk queues that contains data from the previous
        crawl, ``startprios`` or ``slot_startprios``, is now passed as a
        keyword parameter named ``startprios``.

    *   The ``serialize`` parameter is no longer passed. The disk queue
        class must take care of request serialization on its own before
        writing to disk, using the
        :func:`~scrapy.utils.reqser.request_to_dict` and
        :func:`~scrapy.utils.reqser.request_from_dict` functions from the
        :mod:`scrapy.utils.reqser` module.

The following changes may impact custom disk and memory queue classes:

*   The signature of the ``__init__`` method is now
    ``__init__(self, crawler, key)``.

The following changes affect specifically the
:class:`~scrapy.core.scheduler.ScrapyPriorityQueue` and
:class:`~scrapy.core.scheduler.DownloaderAwarePriorityQueue` classes from
:mod:`scrapy.core.scheduler` and may affect subclasses:

*   In the ``__init__`` method, most of the changes described above apply.

    ``__init__`` may still receive all parameters as positional parameters,
    however:

    *   ``downstream_queue_cls``, which replaced ``qfactory``, must be
        instantiated differently.

        ``qfactory`` was instantiated with a priority value (integer).

        Instances of ``downstream_queue_cls`` should be created using
        the new
        :meth:`ScrapyPriorityQueue.qfactory <scrapy.core.scheduler.ScrapyPriorityQueue.qfactory>`
        or
        :meth:`DownloaderAwarePriorityQueue.pqfactory <scrapy.core.scheduler.DownloaderAwarePriorityQueue.pqfactory>`
        methods.

    *   The new ``key`` parameter displaced the ``startprios``
        parameter 1 position to the right.

*   The following class attributes have been added:

    *   :attr:`~scrapy.core.scheduler.ScrapyPriorityQueue.crawler`

    *   :attr:`~scrapy.core.scheduler.ScrapyPriorityQueue.downstream_queue_cls`
        (details above)

    *   :attr:`~scrapy.core.scheduler.ScrapyPriorityQueue.key` (details above)

*   The ``serialize`` attribute has been removed (details above)

The following changes affect specifically the
:class:`~scrapy.core.scheduler.ScrapyPriorityQueue` class and may affect
subclasses:

*   A new :meth:`~scrapy.core.scheduler.ScrapyPriorityQueue.priority`
    method has been added which, given a request, returns
    ``request.priority * -1``.

    It is used in :meth:`~scrapy.core.scheduler.ScrapyPriorityQueue.push`
    to make up for the removal of its ``priority`` parameter.

*   The ``spider`` attribute has been removed. Use
    :attr:`crawler.spider <scrapy.core.scheduler.ScrapyPriorityQueue.crawler>`
    instead.

The following changes affect specifically the
:class:`~scrapy.core.scheduler.DownloaderAwarePriorityQueue` class and may
affect subclasses:

*   A new :attr:`~scrapy.core.scheduler.DownloaderAwarePriorityQueue.pqueues`
    attribute offers a mapping of downloader slot names to the
    corresponding instances of
    :attr:`~scrapy.core.scheduler.DownloaderAwarePriorityQueue.downstream_queue_cls`.

(:gh:`3884`)

.. _release-1.8.4:

Scrapy 1.8.4 (2024-02-14)
-------------------------

**Security bug fixes:**

-   Due to its `ReDoS vulnerabilities`_, ``scrapy.utils.iterators.xmliter`` is
    now deprecated in favor of :func:`~scrapy.utils.iterators.xmliter_lxml`,
    which :class:`~scrapy.spiders.XMLFeedSpider` now uses.

    To minimize the impact of this change on existing code,
    :func:`~scrapy.utils.iterators.xmliter_lxml` now supports indicating
    the node namespace as a prefix in the node name, and big files with highly
    nested trees when using libxml2 2.7+.

    Please, see the `cc65-xxvf-f7r9 security advisory`_ for more information.

-   :setting:`DOWNLOAD_MAXSIZE` and :setting:`DOWNLOAD_WARNSIZE` now also apply
    to the decompressed response body. Please, see the `7j7m-v7m3-jqm7 security
    advisory`_ for more information.

-   Also in relation with the `7j7m-v7m3-jqm7 security advisory`_, use of the
    ``scrapy.downloadermiddlewares.decompression`` module is discouraged and
    will trigger a warning.

-   The ``Authorization`` header is now dropped on redirects to a different
    domain. Please, see the `cw9j-q3vf-hrrv security advisory`_ for more
    information.

    .. _cw9j-q3vf-hrrv security advisory: https://github.com/scrapy/scrapy/security/advisories/GHSA-cw9j-q3vf-hrrv


.. _release-1.8.3:

Scrapy 1.8.3 (2022-07-25)
-------------------------

**Security bug fix:**

-   When :class:`~scrapy.downloadermiddlewares.httpproxy.HttpProxyMiddleware`
    processes a request with :reqmeta:`proxy` metadata, and that
    :reqmeta:`proxy` metadata includes proxy credentials,
    :class:`~scrapy.downloadermiddlewares.httpproxy.HttpProxyMiddleware` sets
    the ``Proxy-Authorization`` header, but only if that header is not already
    set.

    There are third-party proxy-rotation downloader middlewares that set
    different :reqmeta:`proxy` metadata every time they process a request.

    Because of request retries and redirects, the same request can be processed
    by downloader middlewares more than once, including both
    :class:`~scrapy.downloadermiddlewares.httpproxy.HttpProxyMiddleware` and
    any third-party proxy-rotation downloader middleware.

    These third-party proxy-rotation downloader middlewares could change the
    :reqmeta:`proxy` metadata of a request to a new value, but fail to remove
    the ``Proxy-Authorization`` header from the previous value of the
    :reqmeta:`proxy` metadata, causing the credentials of one proxy to be sent
    to a different proxy.

    To prevent the unintended leaking of proxy credentials, the behavior of
    :class:`~scrapy.downloadermiddlewares.httpproxy.HttpProxyMiddleware` is now
    as follows when processing a request:

    -   If the request being processed defines :reqmeta:`proxy` metadata that
        includes credentials, the ``Proxy-Authorization`` header is always
        updated to feature those credentials.

    -   If the request being processed defines :reqmeta:`proxy` metadata
        without credentials, the ``Proxy-Authorization`` header is removed
        *unless* it was originally defined for the same proxy URL.

        To remove proxy credentials while keeping the same proxy URL, remove
        the ``Proxy-Authorization`` header.

    -   If the request has no :reqmeta:`proxy` metadata, or that metadata is a
        falsy value (e.g. ``None``), the ``Proxy-Authorization`` header is
        removed.

        It is no longer possible to set a proxy URL through the
        :reqmeta:`proxy` metadata but set the credentials through the
        ``Proxy-Authorization`` header. Set proxy credentials through the
        :reqmeta:`proxy` metadata instead.


.. _release-1.8.2:

Scrapy 1.8.2 (2022-03-01)
-------------------------

**Security bug fixes:**

-   When a :class:`~scrapy.Request` object with cookies defined gets a
    redirect response causing a new :class:`~scrapy.Request` object to be
    scheduled, the cookies defined in the original
    :class:`~scrapy.Request` object are no longer copied into the new
    :class:`~scrapy.Request` object.

    If you manually set the ``Cookie`` header on a
    :class:`~scrapy.Request` object and the domain name of the redirect
    URL is not an exact match for the domain of the URL of the original
    :class:`~scrapy.Request` object, your ``Cookie`` header is now dropped
    from the new :class:`~scrapy.Request` object.

    The old behavior could be exploited by an attacker to gain access to your
    cookies. Please, see the `cjvr-mfj7-j4j8 security advisory`_ for more
    information.

    .. _cjvr-mfj7-j4j8 security advisory: https://github.com/scrapy/scrapy/security/advisories/GHSA-cjvr-mfj7-j4j8

    .. note:: It is still possible to enable the sharing of cookies between
              different domains with a shared domain suffix (e.g.
              ``example.com`` and any subdomain) by defining the shared domain
              suffix (e.g. ``example.com``) as the cookie domain when defining
              your cookies. See the documentation of the
              :class:`~scrapy.Request` class for more information.

-   When the domain of a cookie, either received in the ``Set-Cookie`` header
    of a response or defined in a :class:`~scrapy.Request` object, is set
    to a `public suffix <https://publicsuffix.org/>`_, the cookie is now
    ignored unless the cookie domain is the same as the request domain.

    The old behavior could be exploited by an attacker to inject cookies into
    your requests to some other domains. Please, see the `mfjm-vh54-3f96
    security advisory`_ for more information.

    .. _mfjm-vh54-3f96 security advisory: https://github.com/scrapy/scrapy/security/advisories/GHSA-mfjm-vh54-3f96


.. _release-1.8.1:

Scrapy 1.8.1 (2021-10-05)
-------------------------

*   **Security bug fix:**

    If you use
    :class:`~scrapy.downloadermiddlewares.httpauth.HttpAuthMiddleware`
    (i.e. the ``http_user`` and ``http_pass`` spider attributes) for HTTP
    authentication, any request exposes your credentials to the request target.

    To prevent unintended exposure of authentication credentials to unintended
    domains, you must now additionally set a new, additional spider attribute,
    ``http_auth_domain``, and point it to the specific domain to which the
    authentication credentials must be sent.

    If the ``http_auth_domain`` spider attribute is not set, the domain of the
    first request will be considered the HTTP authentication target, and
    authentication credentials will only be sent in requests targeting that
    domain.

    If you need to send the same HTTP authentication credentials to multiple
    domains, you can use :func:`w3lib.http.basic_auth_header` instead to
    set the value of the ``Authorization`` header of your requests.

    If you *really* want your spider to send the same HTTP authentication
    credentials to any domain, set the ``http_auth_domain`` spider attribute
    to ``None``.

    Finally, if you are a user of `scrapy-splash`_, know that this version of
    Scrapy breaks compatibility with scrapy-splash 0.7.2 and earlier. You will
    need to upgrade scrapy-splash to a greater version for it to continue to
    work.

.. _scrapy-splash: https://github.com/scrapy-plugins/scrapy-splash


.. _release-1.8.0:

Scrapy 1.8.0 (2019-10-28)
-------------------------

Highlights:

* Dropped Python 3.4 support and updated minimum requirements; made Python 3.8
  support official
* New :meth:`.Request.from_curl` class method
* New :setting:`ROBOTSTXT_PARSER` and :setting:`ROBOTSTXT_USER_AGENT` settings
* New :setting:`DOWNLOADER_CLIENT_TLS_CIPHERS` and
  :setting:`DOWNLOADER_CLIENT_TLS_VERBOSE_LOGGING` settings

Backward-incompatible changes
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. skip: start

*   Python 3.4 is no longer supported, and some of the minimum requirements of
    Scrapy have also changed:

    *   :doc:`cssselect <cssselect:index>` 0.9.1
    *   cryptography_ 2.0
    *   lxml_ 3.5.0
    *   pyOpenSSL_ 16.2.0
    *   queuelib_ 1.4.2
    *   service_identity_ 16.0.0
    *   six_ 1.10.0
    *   Twisted_ 17.9.0 (16.0.0 with Python 2)
    *   zope.interface_ 4.1.3

    (:gh:`3892`)

*   ``JSONRequest`` is now called :class:`~scrapy.http.JsonRequest` for
    consistency with similar classes (:gh:`3929`, :gh:`3982`)

*   If you are using a custom context factory
    (``DOWNLOADER_CLIENTCONTEXTFACTORY``), its ``__init__`` method must
    accept two new parameters: ``tls_verbose_logging`` and ``tls_ciphers``
    (:gh:`2111`, :gh:`3392`, :gh:`3442`, :gh:`3450`)

*   :class:`~scrapy.loader.ItemLoader` now turns the values of its input item
    into lists:

    .. code-block:: pycon

        >>> item = MyItem()
        >>> item["field"] = "value1"
        >>> loader = ItemLoader(item=item)
        >>> item["field"]
        ['value1']

    This is needed to allow adding values to existing fields
    (``loader.add_value('field', 'value2')``).

    (:gh:`3804`, :gh:`3819`, :gh:`3897`, :gh:`3976`, :gh:`3998`,
    :gh:`4036`)

.. skip: end

See also :ref:`1.8-deprecation-removals` below.


New features
~~~~~~~~~~~~

*   A new :meth:`Request.from_curl <scrapy.Request.from_curl>` class
    method allows :ref:`creating a request from a cURL command
    <requests-from-curl>` (:gh:`2985`, :gh:`3862`)

*   A new :setting:`ROBOTSTXT_PARSER` setting allows choosing which robots.txt_
    parser to use. It includes built-in support for
    :ref:`RobotFileParser <python-robotfileparser>`,
    :ref:`Protego <protego-parser>` (default), Reppy, and
    :ref:`Robotexclusionrulesparser <rerp-parser>`, and allows you to
    :ref:`implement support for additional parsers
    <support-for-new-robots-parser>` (:gh:`754`, :gh:`2669`,
    :gh:`3796`, :gh:`3935`, :gh:`3969`, :gh:`4006`)

*   A new :setting:`ROBOTSTXT_USER_AGENT` setting allows defining a separate
    user agent string to use for robots.txt_ parsing (:gh:`3931`,
    :gh:`3966`)

*   :class:`~scrapy.spiders.Rule` no longer requires a :class:`LinkExtractor
    <scrapy.linkextractors.lxmlhtml.LxmlLinkExtractor>` parameter
    (:gh:`781`, :gh:`4016`)

*   Use the new :setting:`DOWNLOADER_CLIENT_TLS_CIPHERS` setting to customize
    the TLS/SSL ciphers used by the default HTTP/1.1 downloader (:gh:`3392`,
    :gh:`3442`)

*   Set the new :setting:`DOWNLOADER_CLIENT_TLS_VERBOSE_LOGGING` setting to
    ``True`` to enable debug-level messages about TLS connection parameters
    after establishing HTTPS connections (:gh:`2111`, :gh:`3450`)

*   Callbacks that receive keyword arguments (see :attr:`.Request.cb_kwargs`)
    can now be tested using the new :class:`@cb_kwargs
    <scrapy.contracts.default.CallbackKeywordArgumentsContract>`
    :ref:`spider contract <topics-contracts>` (:gh:`3985`, :gh:`3988`)

*   When a :class:`@scrapes <scrapy.contracts.default.ScrapesContract>` spider
    contract fails, all missing fields are now reported (:gh:`766`,
    :gh:`3939`)

*   :ref:`Custom log formats <custom-log-formats>` can now drop messages by
    having the corresponding methods of the configured :setting:`LOG_FORMATTER`
    return ``None`` (:gh:`3984`, :gh:`3987`)

*   A much improved completion definition is now available for Zsh_
    (:gh:`4069`)


Bug fixes
~~~~~~~~~

*   :meth:`ItemLoader.load_item() <scrapy.loader.ItemLoader.load_item>` no
    longer makes later calls to :meth:`ItemLoader.get_output_value()
    <scrapy.loader.ItemLoader.get_output_value>` or
    :meth:`ItemLoader.load_item() <scrapy.loader.ItemLoader.load_item>` return
    empty data (:gh:`3804`, :gh:`3819`, :gh:`3897`, :gh:`3976`,
    :gh:`3998`, :gh:`4036`)

*   Fixed :class:`~scrapy.statscollectors.DummyStatsCollector` raising a
    :exc:`TypeError` exception (:gh:`4007`, :gh:`4052`)

*   :meth:`FilesPipeline.file_path
    <scrapy.pipelines.files.FilesPipeline.file_path>` and
    :meth:`ImagesPipeline.file_path
    <scrapy.pipelines.images.ImagesPipeline.file_path>` no longer choose
    file extensions that are not `registered with IANA`_ (:gh:`1287`,
    :gh:`3953`, :gh:`3954`)

*   When using botocore_ to persist files in S3, all botocore-supported headers
    are properly mapped now (:gh:`3904`, :gh:`3905`)

*   FTP passwords in :setting:`FEED_URI` containing percent-escaped characters
    are now properly decoded (:gh:`3941`)

*   A memory-handling and error-handling issue in
    :func:`scrapy.utils.ssl.get_temp_key_info` has been fixed (:gh:`3920`)


Documentation
~~~~~~~~~~~~~

*   The documentation now covers how to define and configure a :ref:`custom log
    format <custom-log-formats>` (:gh:`3616`, :gh:`3660`)

*   API documentation added for :class:`~scrapy.exporters.MarshalItemExporter`
    and :class:`~scrapy.exporters.PythonItemExporter` (:gh:`3973`)

*   API documentation added for :class:`~scrapy.item.BaseItem` and
    :class:`~scrapy.item.ItemMeta` (:gh:`3999`)

*   Minor documentation fixes (:gh:`2998`, :gh:`3398`, :gh:`3597`,
    :gh:`3894`, :gh:`3934`, :gh:`3978`, :gh:`3993`, :gh:`4022`,
    :gh:`4028`, :gh:`4033`, :gh:`4046`, :gh:`4050`, :gh:`4055`,
    :gh:`4056`, :gh:`4061`, :gh:`4072`, :gh:`4071`, :gh:`4079`,
    :gh:`4081`, :gh:`4089`, :gh:`4093`)


.. _1.8-deprecation-removals:

Deprecation removals
~~~~~~~~~~~~~~~~~~~~

*   ``scrapy.xlib`` has been removed (:gh:`4015`)


.. _1.8-deprecations:

Deprecations
~~~~~~~~~~~~

*   The LevelDB_ storage backend
    (``scrapy.extensions.httpcache.LeveldbCacheStorage``) of
    :class:`~scrapy.downloadermiddlewares.httpcache.HttpCacheMiddleware` is
    deprecated (:gh:`4085`, :gh:`4092`)

*   Use of the undocumented ``SCRAPY_PICKLED_SETTINGS_TO_OVERRIDE`` environment
    variable is deprecated (:gh:`3910`)

*   ``scrapy.item.DictItem`` is deprecated, use :class:`~scrapy.item.Item`
    instead (:gh:`3999`)


Other changes
~~~~~~~~~~~~~

*   Minimum versions of optional Scrapy requirements that are covered by
    continuous integration tests have been updated:

    *   botocore_ 1.3.23
    *   Pillow_ 3.4.2

    Lower versions of these optional requirements may work, but it is not
    guaranteed (:gh:`3892`)

*   GitHub templates for bug reports and feature requests (:gh:`3126`,
    :gh:`3471`, :gh:`3749`, :gh:`3754`)

*   Continuous integration fixes (:gh:`3923`)

*   Code cleanup (:gh:`3391`, :gh:`3907`, :gh:`3946`, :gh:`3950`,
    :gh:`4023`, :gh:`4031`)


.. _release-1.7.4:

Scrapy 1.7.4 (2019-10-21)
-------------------------

Revert the fix for :gh:`3804` (:gh:`3819`), which has a few undesired
side effects (:gh:`3897`, :gh:`3976`).

As a result, when an item loader is initialized with an item,
:meth:`ItemLoader.load_item() <scrapy.loader.ItemLoader.load_item>` once again
makes later calls to :meth:`ItemLoader.get_output_value()
<scrapy.loader.ItemLoader.get_output_value>` or :meth:`ItemLoader.load_item()
<scrapy.loader.ItemLoader.load_item>` return empty data.


.. _release-1.7.3:

Scrapy 1.7.3 (2019-08-01)
-------------------------

Enforce lxml 4.3.5 or lower for Python 3.4 (:gh:`3912`, :gh:`3918`).


.. _release-1.7.2:

Scrapy 1.7.2 (2019-07-23)
-------------------------

Fix Python 2 support (:gh:`3889`, :gh:`3893`, :gh:`3896`).


.. _release-1.7.1:

Scrapy 1.7.1 (2019-07-18)
-------------------------

Re-packaging of Scrapy 1.7.0, which was missing some changes in PyPI.


.. _release-1.7.0:

Scrapy 1.7.0 (2019-07-18)
-------------------------

.. note:: Make sure you install Scrapy 1.7.1. The Scrapy 1.7.0 package in PyPI
          is the result of an erroneous commit tagging and does not include all
          the changes described below.

Highlights:

* Improvements for crawls targeting multiple domains
* A cleaner way to pass arguments to callbacks
* A new class for JSON requests
* Improvements for rule-based spiders
* New features for feed exports

Backward-incompatible changes
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

*   ``429`` is now part of the :setting:`RETRY_HTTP_CODES` setting by default

    This change is **backward incompatible**. If you don’t want to retry
    ``429``, you must override :setting:`RETRY_HTTP_CODES` accordingly.

*   :class:`~scrapy.crawler.Crawler`,
    :meth:`CrawlerRunner.crawl <scrapy.crawler.CrawlerRunner.crawl>` and
    :meth:`CrawlerRunner.create_crawler <scrapy.crawler.CrawlerRunner.create_crawler>`
    no longer accept a :class:`~scrapy.spiders.Spider` subclass instance, they
    only accept a :class:`~scrapy.spiders.Spider` subclass now.

    :class:`~scrapy.spiders.Spider` subclass instances were never meant to
    work, and they were not working as one would expect: instead of using the
    passed :class:`~scrapy.spiders.Spider` subclass instance, their
    :class:`~scrapy.spiders.Spider.from_crawler` method was called to generate
    a new instance.

*   Non-default values for the :setting:`SCHEDULER_PRIORITY_QUEUE` setting
    may stop working. Scheduler priority queue classes now need to handle
    :class:`~scrapy.Request` objects instead of arbitrary Python data
    structures.

*   An additional ``crawler`` parameter has been added to the ``__init__``
    method of the :class:`~scrapy.core.scheduler.Scheduler` class. Custom
    scheduler subclasses which don't accept arbitrary parameters in their
    ``__init__`` method might break because of this change.

    For more information, see :setting:`SCHEDULER`.

See also :ref:`1.7-deprecation-removals` below.


New features
~~~~~~~~~~~~

*   A new scheduler priority queue,
    ``scrapy.pqueues.DownloaderAwarePriorityQueue``, may be
    :ref:`enabled <broad-crawls-scheduler-priority-queue>` for a significant
    scheduling improvement on crawls targeting multiple web domains, at the
    cost of no ``CONCURRENT_REQUESTS_PER_IP`` support (:gh:`3520`)

*   A new :attr:`.Request.cb_kwargs` attribute
    provides a cleaner way to pass keyword arguments to callback methods
    (:gh:`1138`, :gh:`3563`)

*   A new :class:`JSONRequest <scrapy.http.JsonRequest>` class offers a more
    convenient way to build JSON requests (:gh:`3504`, :gh:`3505`)

*   A ``process_request`` callback passed to the :class:`~scrapy.spiders.Rule`
    ``__init__`` method now receives the :class:`~scrapy.http.Response` object that
    originated the request as its second argument (:gh:`3682`)

*   A new ``restrict_text`` parameter for the
    :attr:`LinkExtractor <scrapy.linkextractors.lxmlhtml.LxmlLinkExtractor>`
    ``__init__`` method allows filtering links by linking text (:gh:`3622`,
    :gh:`3635`)

*   A new :setting:`FEED_STORAGE_S3_ACL` setting allows defining a custom ACL
    for feeds exported to Amazon S3 (:gh:`3607`)

*   A new :setting:`FEED_STORAGE_FTP_ACTIVE` setting allows using FTP’s active
    connection mode for feeds exported to FTP servers (:gh:`3829`)

*   A new :setting:`METAREFRESH_IGNORE_TAGS` setting allows overriding which
    HTML tags are ignored when searching a response for HTML meta tags that
    trigger a redirect (:gh:`1422`, :gh:`3768`)

*   A new :reqmeta:`redirect_reasons` request meta key exposes the reason
    (status code, meta refresh) behind every followed redirect (:gh:`3581`,
    :gh:`3687`)

*   The ``SCRAPY_CHECK`` variable is now set to the ``true`` string during runs
    of the :command:`check` command, which allows :ref:`detecting contract
    check runs from code <detecting-contract-check-runs>` (:gh:`3704`,
    :gh:`3739`)

*   A new :meth:`Item.deepcopy() <scrapy.item.Item.deepcopy>` method makes it
    easier to :ref:`deep-copy items <copying-items>` (:gh:`1493`,
    :gh:`3671`)

*   :class:`~scrapy.extensions.corestats.CoreStats` also logs
    ``elapsed_time_seconds`` now (:gh:`3638`)

*   Exceptions from :class:`~scrapy.loader.ItemLoader` :ref:`input and output
    processors <topics-loaders-processors>` are now more verbose
    (:gh:`3836`, :gh:`3840`)

*   :class:`~scrapy.crawler.Crawler`,
    :class:`CrawlerRunner.crawl <scrapy.crawler.CrawlerRunner.crawl>` and
    :class:`CrawlerRunner.create_crawler <scrapy.crawler.CrawlerRunner.create_crawler>`
    now fail gracefully if they receive a :class:`~scrapy.spiders.Spider`
    subclass instance instead of the subclass itself (:gh:`2283`,
    :gh:`3610`, :gh:`3872`)


Bug fixes
~~~~~~~~~

*   :meth:`~scrapy.spidermiddlewares.SpiderMiddleware.process_spider_exception`
    is now also invoked for generators (:gh:`220`, :gh:`2061`)

*   System exceptions like KeyboardInterrupt_ are no longer caught
    (:gh:`3726`)

*   :meth:`ItemLoader.load_item() <scrapy.loader.ItemLoader.load_item>` no
    longer makes later calls to :meth:`ItemLoader.get_output_value()
    <scrapy.loader.ItemLoader.get_output_value>` or
    :meth:`ItemLoader.load_item() <scrapy.loader.ItemLoader.load_item>` return
    empty data (:gh:`3804`, :gh:`3819`)

*   The images pipeline (:class:`~scrapy.pipelines.images.ImagesPipeline`) no
    longer ignores these Amazon S3 settings: :setting:`AWS_ENDPOINT_URL`,
    :setting:`AWS_REGION_NAME`, :setting:`AWS_USE_SSL`, :setting:`AWS_VERIFY`
    (:gh:`3625`)

*   Fixed a memory leak in ``scrapy.pipelines.media.MediaPipeline`` affecting,
    for example, non-200 responses and exceptions from custom middlewares
    (:gh:`3813`)

*   Requests with private callbacks are now correctly unserialized from disk
    (:gh:`3790`)

*   :meth:`.FormRequest.from_response`
    now handles invalid methods like major web browsers (:gh:`3777`,
    :gh:`3794`)


Documentation
~~~~~~~~~~~~~

*   A new topic, :ref:`topics-dynamic-content`, covers recommended approaches
    to read dynamically-loaded data (:gh:`3703`)

*   :ref:`topics-broad-crawls` now features information about memory usage
    (:gh:`1264`, :gh:`3866`)

*   The documentation of :class:`~scrapy.spiders.Rule` now covers how to access
    the text of a link when using :class:`~scrapy.spiders.CrawlSpider`
    (:gh:`3711`, :gh:`3712`)

*   A new section, :ref:`httpcache-storage-custom`, covers writing a custom
    cache storage backend for
    :class:`~scrapy.downloadermiddlewares.httpcache.HttpCacheMiddleware`
    (:gh:`3683`, :gh:`3692`)

*   A new :ref:`FAQ <faq>` entry, :ref:`faq-split-item`, explains what to do
    when you want to split an item into multiple items from an item pipeline
    (:gh:`2240`, :gh:`3672`)

*   Updated the :ref:`FAQ entry about crawl order <faq-bfo-dfo>` to explain why
    the first few requests rarely follow the desired order (:gh:`1739`,
    :gh:`3621`)

*   The :setting:`LOGSTATS_INTERVAL` setting (:gh:`3730`), the
    :meth:`FilesPipeline.file_path <scrapy.pipelines.files.FilesPipeline.file_path>`
    and
    :meth:`ImagesPipeline.file_path <scrapy.pipelines.images.ImagesPipeline.file_path>`
    methods (:gh:`2253`, :gh:`3609`) and the
    :meth:`Crawler.stop() <scrapy.crawler.Crawler.stop>` method (:gh:`3842`)
    are now documented

*   Some parts of the documentation that were confusing or misleading are now
    clearer (:gh:`1347`, :gh:`1789`, :gh:`2289`, :gh:`3069`,
    :gh:`3615`, :gh:`3626`, :gh:`3668`, :gh:`3670`, :gh:`3673`,
    :gh:`3728`, :gh:`3762`, :gh:`3861`, :gh:`3882`)

*   Minor documentation fixes (:gh:`3648`, :gh:`3649`, :gh:`3662`,
    :gh:`3674`, :gh:`3676`, :gh:`3694`, :gh:`3724`, :gh:`3764`,
    :gh:`3767`, :gh:`3791`, :gh:`3797`, :gh:`3806`, :gh:`3812`)

.. _1.7-deprecation-removals:

Deprecation removals
~~~~~~~~~~~~~~~~~~~~

The following deprecated APIs have been removed (:gh:`3578`):

*   ``scrapy.conf`` (use :attr:`Crawler.settings
    <scrapy.crawler.Crawler.settings>`)

*   From ``scrapy.core.downloader.handlers``:

    *   ``http.HttpDownloadHandler`` (use ``http10.HTTP10DownloadHandler``)

*   ``scrapy.loader.ItemLoader._get_values`` (use ``_get_xpathvalues``)

*   ``scrapy.loader.XPathItemLoader`` (use :class:`~scrapy.loader.ItemLoader`)

*   ``scrapy.log`` (see :ref:`topics-logging`)

*   From ``scrapy.pipelines``:

    *   ``files.FilesPipeline.file_key`` (use ``file_path``)

    *   ``images.ImagesPipeline.file_key`` (use ``file_path``)

    *   ``images.ImagesPipeline.image_key`` (use ``file_path``)

    *   ``images.ImagesPipeline.thumb_key`` (use ``thumb_path``)

*   From both ``scrapy.selector`` and ``scrapy.selector.lxmlsel``:

    *   ``HtmlXPathSelector`` (use :class:`~scrapy.Selector`)

    *   ``XmlXPathSelector`` (use :class:`~scrapy.Selector`)

    *   ``XPathSelector`` (use :class:`~scrapy.Selector`)

    *   ``XPathSelectorList`` (use :class:`~scrapy.Selector`)

*   From ``scrapy.selector.csstranslator``:

    *   ``ScrapyGenericTranslator`` (use parsel.csstranslator.GenericTranslator_)

    *   ``ScrapyHTMLTranslator`` (use parsel.csstranslator.HTMLTranslator_)

    *   ``ScrapyXPathExpr`` (use parsel.csstranslator.XPathExpr_)

*   From :class:`~scrapy.Selector`:

    *   ``_root`` (both the ``__init__`` method argument and the object property, use
        ``root``)

    *   ``extract_unquoted`` (use ``getall``)

    *   ``select`` (use ``xpath``)

*   From :class:`~scrapy.selector.SelectorList`:

    *   ``extract_unquoted`` (use ``getall``)

    *   ``select`` (use ``xpath``)

    *   ``x`` (use ``xpath``)

*   ``scrapy.spiders.BaseSpider`` (use :class:`~scrapy.spiders.Spider`)

*   From :class:`~scrapy.spiders.Spider` (and subclasses):

    *   ``DOWNLOAD_DELAY`` (use :ref:`download_delay
        <spider-download_delay-attribute>`)

    *   ``set_crawler`` (use :meth:`~scrapy.spiders.Spider.from_crawler`)

*   ``scrapy.spiders.spiders`` (use :class:`~scrapy.spiderloader.SpiderLoader`)

*   ``scrapy.telnet`` (use :mod:`scrapy.extensions.telnet`)

*   From ``scrapy.utils.python``:

    *   ``str_to_unicode`` (use ``to_unicode``)

    *   ``unicode_to_str`` (use ``to_bytes``)

*   ``scrapy.utils.response.body_or_str``

The following deprecated settings have also been removed (:gh:`3578`):

*   ``SPIDER_MANAGER_CLASS`` (use :setting:`SPIDER_LOADER_CLASS`)


.. _1.7-deprecations:

Deprecations
~~~~~~~~~~~~

*   The ``queuelib.PriorityQueue`` value for the
    :setting:`SCHEDULER_PRIORITY_QUEUE` setting is deprecated. Use
    ``scrapy.pqueues.ScrapyPriorityQueue`` instead.

*   ``process_request`` callbacks passed to :class:`~scrapy.spiders.Rule` that
    do not accept two arguments are deprecated.

*   The following modules are deprecated:

    *   ``scrapy.utils.http`` (use `w3lib.http`_)

    *   ``scrapy.utils.markup`` (use `w3lib.html`_)

    *   ``scrapy.utils.multipart`` (use `urllib3`_)

*   The ``scrapy.utils.datatypes.MergeDict`` class is deprecated for Python 3
    code bases. Use :class:`~collections.ChainMap` instead. (:gh:`3878`)

*   The ``scrapy.utils.gz.is_gzipped`` function is deprecated. Use
    ``scrapy.utils.gz.gzip_magic_number`` instead.

.. _urllib3: https://urllib3.readthedocs.io/en/latest/index.html
.. _w3lib.html: https://w3lib.readthedocs.io/en/latest/w3lib.html#module-w3lib.html
.. _w3lib.http: https://w3lib.readthedocs.io/en/latest/w3lib.html#module-w3lib.http


Other changes
~~~~~~~~~~~~~

*   It is now possible to run all tests from the same tox_ environment in
    parallel; the documentation now covers :ref:`this and other ways to run
    tests <running-tests>` (:gh:`3707`)

*   It is now possible to generate an API documentation coverage report
    (:gh:`3806`, :gh:`3810`, :gh:`3860`)

*   The :ref:`documentation policies <documentation-policies>` now require
    docstrings_ (:gh:`3701`) that follow `PEP 257`_ (:gh:`3748`)

*   Internal fixes and cleanup (:gh:`3629`, :gh:`3643`, :gh:`3684`,
    :gh:`3698`, :gh:`3734`, :gh:`3735`, :gh:`3736`, :gh:`3737`,
    :gh:`3809`, :gh:`3821`, :gh:`3825`, :gh:`3827`, :gh:`3833`,
    :gh:`3857`, :gh:`3877`)

.. _release-1.6.0:

Scrapy 1.6.0 (2019-01-30)
-------------------------

Highlights:

* better Windows support;
* Python 3.7 compatibility;
* big documentation improvements, including a switch
  from ``.extract_first()`` + ``.extract()`` API to ``.get()`` + ``.getall()``
  API;
* feed exports, FilePipeline and MediaPipeline improvements;
* better extensibility: :signal:`item_error` and
  :signal:`request_reached_downloader` signals; ``from_crawler`` support
  for feed exporters, feed storages and dupefilters.
* ``scrapy.contracts`` fixes and new features;
* telnet console security improvements, first released as a
  backport in :ref:`release-1.5.2`;
* clean-up of the deprecated code;
* various bug fixes, small new features and usability improvements across
  the codebase.

Selector API changes
~~~~~~~~~~~~~~~~~~~~

While these are not changes in Scrapy itself, but rather in the parsel_
library which Scrapy uses for xpath/css selectors, these changes are
worth mentioning here. Scrapy now depends on parsel >= 1.5, and
Scrapy documentation is updated to follow recent ``parsel`` API conventions.

Most visible change is that ``.get()`` and ``.getall()`` selector
methods are now preferred over ``.extract_first()`` and ``.extract()``.
We feel that these new methods result in a more concise and readable code.
See :ref:`old-extraction-api` for more details.

.. note::
    There are currently **no plans** to deprecate ``.extract()``
    and ``.extract_first()`` methods.

Another useful new feature is the introduction of ``Selector.attrib`` and
``SelectorList.attrib`` properties, which make it easier to get
attributes of HTML elements. See :ref:`selecting-attributes`.

CSS selectors are cached in parsel >= 1.5, which makes them faster
when the same CSS path is used many times. This is very common in
case of Scrapy spiders: callbacks are usually called several times,
on different pages.

If you're using custom ``Selector`` or ``SelectorList`` subclasses,
a **backward incompatible** change in parsel may affect your code.
See `parsel changelog`_ for a detailed description, as well as for the
full list of improvements.

.. _parsel changelog: https://parsel.readthedocs.io/en/latest/history.html

Telnet console
~~~~~~~~~~~~~~

**Backward incompatible**: Scrapy's telnet console now requires username
and password. See :ref:`topics-telnetconsole` for more details. This change
fixes a **security issue**; see :ref:`release-1.5.2` release notes for details.

New extensibility features
~~~~~~~~~~~~~~~~~~~~~~~~~~

* ``from_crawler`` support is added to feed exporters and feed storages. This,
  among other things, allows to access Scrapy settings from custom feed
  storages and exporters (:gh:`1605`, :gh:`3348`).
* ``from_crawler`` support is added to dupefilters (:gh:`2956`); this allows
  to access e.g. settings or a spider from a dupefilter.
* :signal:`item_error` is fired when an error happens in a pipeline
  (:gh:`3256`);
* :signal:`request_reached_downloader` is fired when Downloader gets
  a new Request; this signal can be useful e.g. for custom Schedulers
  (:gh:`3393`).
* new SitemapSpider :meth:`~.SitemapSpider.sitemap_filter` method which allows
  to select sitemap entries based on their attributes in SitemapSpider
  subclasses (:gh:`3512`).
* Lazy loading of Downloader Handlers is now optional; this enables better
  initialization error handling in custom Downloader Handlers (:gh:`3394`).

New FilePipeline and MediaPipeline features
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

* Expose more options for S3FilesStore: :setting:`AWS_ENDPOINT_URL`,
  :setting:`AWS_USE_SSL`, :setting:`AWS_VERIFY`, :setting:`AWS_REGION_NAME`.
  For example, this allows to use alternative or self-hosted
  AWS-compatible providers (:gh:`2609`, :gh:`3548`).
* ACL support for Google Cloud Storage: :setting:`FILES_STORE_GCS_ACL` and
  :setting:`IMAGES_STORE_GCS_ACL` (:gh:`3199`).

``scrapy.contracts`` improvements
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

* Exceptions in contracts code are handled better (:gh:`3377`);
* ``dont_filter=True`` is used for contract requests, which allows to test
  different callbacks with the same URL (:gh:`3381`);
* ``request_cls`` attribute in Contract subclasses allow to use different
  Request classes in contracts, for example FormRequest (:gh:`3383`).
* Fixed errback handling in contracts, e.g. for cases where a contract
  is executed for URL which returns non-200 response (:gh:`3371`).

Usability improvements
~~~~~~~~~~~~~~~~~~~~~~

* more stats for RobotsTxtMiddleware (:gh:`3100`)
* INFO log level is used to show telnet host/port (:gh:`3115`)
* a message is added to IgnoreRequest in RobotsTxtMiddleware (:gh:`3113`)
* better validation of ``url`` argument in ``Response.follow`` (:gh:`3131`)
* non-zero exit code is returned from Scrapy commands when error happens
  on spider initialization (:gh:`3226`)
* Link extraction improvements: "ftp" is added to scheme list (:gh:`3152`);
  "flv" is added to common video extensions (:gh:`3165`)
* better error message when an exporter is disabled (:gh:`3358`);
* ``scrapy shell --help`` mentions syntax required for local files
  (``./file.html``) - :gh:`3496`.
* Referer header value is added to RFPDupeFilter log messages (:gh:`3588`)

Bug fixes
~~~~~~~~~

* fixed issue with extra blank lines in .csv exports under Windows
  (:gh:`3039`);
* proper handling of pickling errors in Python 3 when serializing objects
  for disk queues (:gh:`3082`)
* flags are now preserved when copying Requests (:gh:`3342`);
* FormRequest.from_response clickdata shouldn't ignore elements with
  ``input[type=image]`` (:gh:`3153`).
* FormRequest.from_response should preserve duplicate keys (:gh:`3247`)

Documentation improvements
~~~~~~~~~~~~~~~~~~~~~~~~~~

* Docs are re-written to suggest .get/.getall API instead of
  .extract/.extract_first. Also, :ref:`topics-selectors` docs are updated
  and re-structured to match latest parsel docs; they now contain more topics,
  such as :ref:`selecting-attributes` or :ref:`topics-selectors-css-extensions`
  (:gh:`3390`).
* :ref:`topics-developer-tools` is a new tutorial which replaces
  old Firefox and Firebug tutorials (:gh:`3400`).
* SCRAPY_PROJECT environment variable is documented (:gh:`3518`);
* troubleshooting section is added to install instructions (:gh:`3517`);
* improved links to beginner resources in the tutorial
  (:gh:`3367`, :gh:`3468`);
* fixed :setting:`RETRY_HTTP_CODES` default values in docs (:gh:`3335`);
* remove unused ``DEPTH_STATS`` option from docs (:gh:`3245`);
* other cleanups (:gh:`3347`, :gh:`3350`, :gh:`3445`, :gh:`3544`,
  :gh:`3605`).

Deprecation removals
~~~~~~~~~~~~~~~~~~~~

Compatibility shims for pre-1.0 Scrapy module names are removed
(:gh:`3318`):

* ``scrapy.command``
* ``scrapy.contrib`` (with all submodules)
* ``scrapy.contrib_exp`` (with all submodules)
* ``scrapy.dupefilter``
* ``scrapy.linkextractor``
* ``scrapy.project``
* ``scrapy.spider``
* ``scrapy.spidermanager``
* ``scrapy.squeue``
* ``scrapy.stats``
* ``scrapy.statscol``
* ``scrapy.utils.decorator``

See :ref:`module-relocations` for more information, or use suggestions
from Scrapy 1.5.x deprecation warnings to update your code.

Other deprecation removals:

* Deprecated scrapy.interfaces.ISpiderManager is removed; please use
  scrapy.interfaces.ISpiderLoader.
* Deprecated ``CrawlerSettings`` class is removed (:gh:`3327`).
* Deprecated ``Settings.overrides`` and ``Settings.defaults`` attributes
  are removed (:gh:`3327`, :gh:`3359`).

Other improvements, cleanups
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

* All Scrapy tests now pass on Windows; Scrapy testing suite is executed
  in a Windows environment on CI (:gh:`3315`).
* Python 3.7 support (:gh:`3326`, :gh:`3150`, :gh:`3547`).
* Testing and CI fixes (:gh:`3526`, :gh:`3538`, :gh:`3308`,
  :gh:`3311`, :gh:`3309`, :gh:`3305`, :gh:`3210`, :gh:`3299`)
* ``scrapy.http.cookies.CookieJar.clear`` accepts "domain", "path" and "name"
  optional arguments (:gh:`3231`).
* additional files are included to sdist (:gh:`3495`);
* code style fixes (:gh:`3405`, :gh:`3304`);
* unneeded .strip() call is removed (:gh:`3519`);
* collections.deque is used to store MiddlewareManager methods instead
  of a list (:gh:`3476`)

.. _release-1.5.2:

Scrapy 1.5.2 (2019-01-22)
-------------------------

* *Security bugfix*: Telnet console extension can be easily exploited by rogue
  websites POSTing content to http://localhost:6023, we haven't found a way to
  exploit it from Scrapy, but it is very easy to trick a browser to do so and
  elevates the risk for local development environment.

  *The fix is backward incompatible*, it enables telnet user-password
  authentication by default with a random generated password. If you can't
  upgrade right away, please consider setting :setting:`TELNETCONSOLE_PORT`
  out of its default value.

  See :ref:`telnet console <topics-telnetconsole>` documentation for more info

* Backport CI build failure under GCE environment due to boto import error.

.. _release-1.5.1:

Scrapy 1.5.1 (2018-07-12)
-------------------------

This is a maintenance release with important bug fixes, but no new features:

* ``O(N^2)`` gzip decompression issue which affected Python 3 and PyPy
  is fixed (:gh:`3281`);
* skipping of TLS validation errors is improved (:gh:`3166`);
* Ctrl-C handling is fixed in Python 3.5+ (:gh:`3096`);
* testing fixes (:gh:`3092`, :gh:`3263`);
* documentation improvements (:gh:`3058`, :gh:`3059`, :gh:`3089`,
  :gh:`3123`, :gh:`3127`, :gh:`3189`, :gh:`3224`, :gh:`3280`,
  :gh:`3279`, :gh:`3201`, :gh:`3260`, :gh:`3284`, :gh:`3298`,
  :gh:`3294`).


.. _release-1.5.0:

Scrapy 1.5.0 (2017-12-29)
-------------------------

This release brings small new features and improvements across the codebase.
Some highlights:

* Google Cloud Storage is supported in FilesPipeline and ImagesPipeline.
* Crawling with proxy servers becomes more efficient, as connections
  to proxies can be reused now.
* Warnings, exception and logging messages are improved to make debugging
  easier.
* ``scrapy parse`` command now allows to set custom request meta via
  ``--meta`` argument.
* Compatibility with Python 3.6, PyPy and PyPy3 is improved;
  PyPy and PyPy3 are now supported officially, by running tests on CI.
* Better default handling of HTTP 308, 522 and 524 status codes.
* Documentation is improved, as usual.

Backward Incompatible Changes
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

* Scrapy 1.5 drops support for Python 3.3.
* Default Scrapy User-Agent now uses https link to scrapy.org (:gh:`2983`).
  **This is technically backward-incompatible**; override
  :setting:`USER_AGENT` if you relied on old value.
* Logging of settings overridden by ``custom_settings`` is fixed;
  **this is technically backward-incompatible** because the logger
  changes from ``[scrapy.utils.log]`` to ``[scrapy.crawler]``. If you're
  parsing Scrapy logs, please update your log parsers (:gh:`1343`).
* LinkExtractor now ignores ``m4v`` extension by default, this is change
  in behavior.
* 522 and 524 status codes are added to ``RETRY_HTTP_CODES`` (:gh:`2851`)

New features
~~~~~~~~~~~~

- Support ``<link>`` tags in ``Response.follow`` (:gh:`2785`)
- Support for ``ptpython`` REPL (:gh:`2654`)
- Google Cloud Storage support for FilesPipeline and ImagesPipeline
  (:gh:`2923`).
- New ``--meta`` option of the "scrapy parse" command allows to pass additional
  request.meta (:gh:`2883`)
- Populate spider variable when using ``shell.inspect_response`` (:gh:`2812`)
- Handle HTTP 308 Permanent Redirect (:gh:`2844`)
- Add 522 and 524 to ``RETRY_HTTP_CODES`` (:gh:`2851`)
- Log versions information at startup (:gh:`2857`)
- ``scrapy.mail.MailSender`` now works in Python 3 (it requires Twisted 17.9.0)
- Connections to proxy servers are reused (:gh:`2743`)
- Add template for a downloader middleware (:gh:`2755`)
- Explicit message for NotImplementedError when parse callback not defined
  (:gh:`2831`)
- CrawlerProcess got an option to disable installation of root log handler
  (:gh:`2921`)
- LinkExtractor now ignores ``m4v`` extension by default
- Better log messages for responses over :setting:`DOWNLOAD_WARNSIZE` and
  :setting:`DOWNLOAD_MAXSIZE` limits (:gh:`2927`)
- Show warning when a URL is put to ``Spider.allowed_domains`` instead of
  a domain (:gh:`2250`).

Bug fixes
~~~~~~~~~

- Fix logging of settings overridden by ``custom_settings``;
  **this is technically backward-incompatible** because the logger
  changes from ``[scrapy.utils.log]`` to ``[scrapy.crawler]``, so please
  update your log parsers if needed (:gh:`1343`)
- Default Scrapy User-Agent now uses https link to scrapy.org (:gh:`2983`).
  **This is technically backward-incompatible**; override
  :setting:`USER_AGENT` if you relied on old value.
- Fix PyPy and PyPy3 test failures, support them officially
  (:gh:`2793`, :gh:`2935`, :gh:`2990`, :gh:`3050`, :gh:`2213`,
  :gh:`3048`)
- Fix DNS resolver when ``DNSCACHE_ENABLED=False`` (:gh:`2811`)
- Add ``cryptography`` for Debian Jessie tox test env (:gh:`2848`)
- Add verification to check if Request callback is callable (:gh:`2766`)
- Port ``extras/qpsclient.py`` to Python 3 (:gh:`2849`)
- Use getfullargspec under the scenes for Python 3 to stop DeprecationWarning
  (:gh:`2862`)
- Update deprecated test aliases (:gh:`2876`)
- Fix ``SitemapSpider`` support for alternate links (:gh:`2853`)

Docs
~~~~

- Added missing bullet point for the ``AUTOTHROTTLE_TARGET_CONCURRENCY``
  setting. (:gh:`2756`)
- Update Contributing docs, document new support channels
  (:gh:`2762`, :gh:`3038`)
- Include references to Scrapy subreddit in the docs
- Fix broken links; use ``https://`` for external links
  (:gh:`2978`, :gh:`2982`, :gh:`2958`)
- Document CloseSpider extension better (:gh:`2759`)
- Use ``pymongo.collection.Collection.insert_one()`` in MongoDB example
  (:gh:`2781`)
- Spelling mistake and typos
  (:gh:`2828`, :gh:`2837`, :gh:`2884`, :gh:`2924`)
- Clarify ``CSVFeedSpider.headers`` documentation (:gh:`2826`)
- Document ``DontCloseSpider`` exception and clarify ``spider_idle``
  (:gh:`2791`)
- Update "Releases" section in README (:gh:`2764`)
- Fix rst syntax in ``DOWNLOAD_FAIL_ON_DATALOSS`` docs (:gh:`2763`)
- Small fix in description of startproject arguments (:gh:`2866`)
- Clarify data types in Response.body docs (:gh:`2922`)
- Add a note about ``request.meta['depth']`` to DepthMiddleware docs (:gh:`2374`)
- Add a note about ``request.meta['dont_merge_cookies']`` to CookiesMiddleware
  docs (:gh:`2999`)
- Up-to-date example of project structure (:gh:`2964`, :gh:`2976`)
- A better example of ItemExporters usage (:gh:`2989`)
- Document ``from_crawler`` methods for spider and downloader middlewares
  (:gh:`3019`)

.. _release-1.4.0:

Scrapy 1.4.0 (2017-05-18)
-------------------------

Scrapy 1.4 does not bring that many breathtaking new features
but quite a few handy improvements nonetheless.

Scrapy now supports anonymous FTP sessions with customizable user and
password via the new :setting:`FTP_USER` and :setting:`FTP_PASSWORD` settings.
And if you're using Twisted version 17.1.0 or above, FTP is now available
with Python 3.

There's a new :meth:`response.follow <scrapy.http.TextResponse.follow>` method
for creating requests; **it is now a recommended way to create Requests
in Scrapy spiders**. This method makes it easier to write correct
spiders; ``response.follow`` has several advantages over creating
``scrapy.Request`` objects directly:

* it handles relative URLs;
* it works properly with non-ascii URLs on non-UTF8 pages;
* in addition to absolute and relative URLs it supports Selectors;
  for ``<a>`` elements it can also extract their href values.

For example, instead of this::

    for href in response.css('li.page a::attr(href)').extract():
        url = response.urljoin(href)
        yield scrapy.Request(url, self.parse, encoding=response.encoding)

One can now write this::

    for a in response.css('li.page a'):
        yield response.follow(a, self.parse)

Link extractors are also improved. They work similarly to what a regular
modern browser would do: leading and trailing whitespace are removed
from attributes (think ``href="   http://example.com"``) when building
``Link`` objects. This whitespace-stripping also happens for ``action``
attributes with ``FormRequest``.

**Please also note that link extractors do not canonicalize URLs by default
anymore.** This was puzzling users every now and then, and it's not what
browsers do in fact, so we removed that extra transformation on extracted
links.

For those of you wanting more control on the ``Referer:`` header that Scrapy
sends when following links, you can set your own ``Referrer Policy``.
Prior to Scrapy 1.4, the default ``RefererMiddleware`` would simply and
blindly set it to the URL of the response that generated the HTTP request
(which could leak information on your URL seeds).
By default, Scrapy now behaves much like your regular browser does.
And this policy is fully customizable with W3C standard values
(or with something really custom of your own if you wish).
See :setting:`REFERRER_POLICY` for details.

To make Scrapy spiders easier to debug, Scrapy logs more stats by default
in 1.4: memory usage stats, detailed retry stats, detailed HTTP error code
stats. A similar change is that HTTP cache path is also visible in logs now.

Last but not least, Scrapy now has the option to make JSON and XML items
more human-readable, with newlines between items and even custom indenting
offset, using the new :setting:`FEED_EXPORT_INDENT` setting.

Enjoy! (Or read on for the rest of changes in this release.)

Deprecations and Backward Incompatible Changes
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- Default to ``canonicalize=False`` in
  :class:`scrapy.linkextractors.LinkExtractor
  <scrapy.linkextractors.lxmlhtml.LxmlLinkExtractor>`
  (:gh:`2537`, fixes :gh:`1941` and :gh:`1982`):
  **warning, this is technically backward-incompatible**
- Enable memusage extension by default (:gh:`2539`, fixes :gh:`2187`);
  **this is technically backward-incompatible** so please check if you have
  any non-default ``MEMUSAGE_***`` options set.
- ``EDITOR`` environment variable now takes precedence over ``EDITOR``
  option defined in settings.py (:gh:`1829`); Scrapy default settings
  no longer depend on environment variables. **This is technically a backward
  incompatible change**.
- ``Spider.make_requests_from_url`` is deprecated
  (:gh:`1728`, fixes :gh:`1495`).

New Features
~~~~~~~~~~~~

- Accept proxy credentials in :reqmeta:`proxy` request meta key (:gh:`2526`)
- Support `brotli-compressed`_ content; requires optional `brotlipy`_
  (:gh:`2535`)
- New :ref:`response.follow <response-follow-example>` shortcut
  for creating requests (:gh:`1940`)
- Added ``flags`` argument and attribute to :class:`~scrapy.Request`
  objects (:gh:`2047`)
- Support Anonymous FTP (:gh:`2342`)
- Added ``retry/count``, ``retry/max_reached`` and ``retry/reason_count/<reason>``
  stats to :class:`RetryMiddleware <scrapy.downloadermiddlewares.retry.RetryMiddleware>`
  (:gh:`2543`)
- Added ``httperror/response_ignored_count`` and ``httperror/response_ignored_status_count/<status>``
  stats to :class:`HttpErrorMiddleware <scrapy.spidermiddlewares.httperror.HttpErrorMiddleware>`
  (:gh:`2566`)
- Customizable :setting:`Referrer policy <REFERRER_POLICY>` in
  :class:`RefererMiddleware <scrapy.spidermiddlewares.referer.RefererMiddleware>`
  (:gh:`2306`)
- New ``data:`` URI download handler (:gh:`2334`, fixes :gh:`2156`)
- Log cache directory when HTTP Cache is used (:gh:`2611`, fixes :gh:`2604`)
- Warn users when project contains duplicate spider names (fixes :gh:`2181`)
- ``scrapy.utils.datatypes.CaselessDict`` now accepts ``Mapping`` instances and
  not only dicts (:gh:`2646`)
- :ref:`Media downloads <topics-media-pipeline>`, with
  :class:`~scrapy.pipelines.files.FilesPipeline` or
  :class:`~scrapy.pipelines.images.ImagesPipeline`, can now optionally handle
  HTTP redirects using the new :setting:`MEDIA_ALLOW_REDIRECTS` setting
  (:gh:`2616`, fixes :gh:`2004`)
- Accept non-complete responses from websites using a new
  :setting:`DOWNLOAD_FAIL_ON_DATALOSS` setting (:gh:`2590`, fixes :gh:`2586`)
- Optional pretty-printing of JSON and XML items via
  :setting:`FEED_EXPORT_INDENT` setting (:gh:`2456`, fixes :gh:`1327`)
- Allow dropping fields in ``FormRequest.from_response`` formdata when
  ``None`` value is passed (:gh:`667`)
- Per-request retry times with the new :reqmeta:`max_retry_times` meta key
  (:gh:`2642`)
- ``python -m scrapy`` as a more explicit alternative to ``scrapy`` command
  (:gh:`2740`)

.. _brotli-compressed: https://www.ietf.org/rfc/rfc7932.txt
.. _brotlipy: https://github.com/python-hyper/brotlipy/

Bug fixes
~~~~~~~~~

- LinkExtractor now strips leading and trailing whitespaces from attributes
  (:gh:`2547`, fixes :gh:`1614`)
- Properly handle whitespaces in action attribute in
  :class:`~scrapy.FormRequest` (:gh:`2548`)
- Buffer CONNECT response bytes from proxy until all HTTP headers are received
  (:gh:`2495`, fixes :gh:`2491`)
- FTP downloader now works on Python 3, provided you use Twisted>=17.1
  (:gh:`2599`)
- Use body to choose response type after decompressing content (:gh:`2393`,
  fixes :gh:`2145`)
- Always decompress ``Content-Encoding: gzip`` at :class:`HttpCompressionMiddleware
  <scrapy.downloadermiddlewares.httpcompression.HttpCompressionMiddleware>` stage (:gh:`2391`)
- Respect custom log level in ``Spider.custom_settings`` (:gh:`2581`,
  fixes :gh:`1612`)
- 'make htmlview' fix for macOS (:gh:`2661`)
- Remove "commands" from the command list  (:gh:`2695`)
- Fix duplicate Content-Length header for POST requests with empty body (:gh:`2677`)
- Properly cancel large downloads, i.e. above :setting:`DOWNLOAD_MAXSIZE` (:gh:`1616`)
- ImagesPipeline: fixed processing of transparent PNG images with palette
  (:gh:`2675`)

Cleanups & Refactoring
~~~~~~~~~~~~~~~~~~~~~~

- Tests: remove temp files and folders (:gh:`2570`),
  fixed ProjectUtilsTest on macOS (:gh:`2569`),
  use portable pypy for Linux on Travis CI (:gh:`2710`)
- Separate building request from ``_requests_to_follow`` in CrawlSpider (:gh:`2562`)
- Remove “Python 3 progress” badge (:gh:`2567`)
- Add a couple more lines to ``.gitignore`` (:gh:`2557`)
- Remove bumpversion prerelease configuration (:gh:`2159`)
- Add codecov.yml file (:gh:`2750`)
- Set context factory implementation based on Twisted version (:gh:`2577`,
  fixes :gh:`2560`)
- Add omitted ``self`` arguments in default project middleware template (:gh:`2595`)
- Remove redundant ``slot.add_request()`` call in ExecutionEngine (:gh:`2617`)
- Catch more specific ``os.error`` exception in
  ``scrapy.pipelines.files.FSFilesStore`` (:gh:`2644`)
- Change "localhost" test server certificate (:gh:`2720`)
- Remove unused ``MEMUSAGE_REPORT`` setting (:gh:`2576`)

Documentation
~~~~~~~~~~~~~

- Binary mode is required for exporters (:gh:`2564`, fixes :gh:`2553`)
- Mention issue with :meth:`.FormRequest.from_response` due to bug in lxml (:gh:`2572`)
- Use single quotes uniformly in templates (:gh:`2596`)
- Document :reqmeta:`ftp_user` and :reqmeta:`ftp_password` meta keys (:gh:`2587`)
- Removed section on deprecated ``contrib/`` (:gh:`2636`)
- Recommend Anaconda when installing Scrapy on Windows
  (:gh:`2477`, fixes :gh:`2475`)
- FAQ: rewrite note on Python 3 support on Windows (:gh:`2690`)
- Rearrange selector sections (:gh:`2705`)
- Remove ``__nonzero__`` from :class:`~scrapy.selector.SelectorList`
  docs (:gh:`2683`)
- Mention how to disable request filtering in documentation of
  :setting:`DUPEFILTER_CLASS` setting (:gh:`2714`)
- Add sphinx_rtd_theme to docs setup readme (:gh:`2668`)
- Open file in text mode in JSON item writer example (:gh:`2729`)
- Clarify ``allowed_domains`` example (:gh:`2670`)


.. _release-1.3.3:

Scrapy 1.3.3 (2017-03-10)
-------------------------

Bug fixes
~~~~~~~~~

- Make ``SpiderLoader`` raise ``ImportError`` again by default for missing
  dependencies and wrong :setting:`SPIDER_MODULES`.
  These exceptions were silenced as warnings since 1.3.0.
  A new setting is introduced to toggle between warning or exception if needed ;
  see :setting:`SPIDER_LOADER_WARN_ONLY` for details.

.. _release-1.3.2:

Scrapy 1.3.2 (2017-02-13)
-------------------------

Bug fixes
~~~~~~~~~

- Preserve request class when converting to/from dicts (utils.reqser) (:gh:`2510`).
- Use consistent selectors for author field in tutorial (:gh:`2551`).
- Fix TLS compatibility in Twisted 17+ (:gh:`2558`)

.. _release-1.3.1:

Scrapy 1.3.1 (2017-02-08)
-------------------------

New features
~~~~~~~~~~~~

- Support ``'True'`` and ``'False'`` string values for boolean settings (:gh:`2519`);
  you can now do something like ``scrapy crawl myspider -s REDIRECT_ENABLED=False``.
- Support kwargs with ``response.xpath()`` to use :ref:`XPath variables <topics-selectors-xpath-variables>`
  and ad-hoc namespaces declarations ;
  this requires at least Parsel v1.1 (:gh:`2457`).
- Add support for Python 3.6 (:gh:`2485`).
- Run tests on PyPy (warning: some tests still fail, so PyPy is not supported yet).

Bug fixes
~~~~~~~~~

- Enforce ``DNS_TIMEOUT`` setting (:gh:`2496`).
- Fix :command:`view` command ; it was a regression in v1.3.0 (:gh:`2503`).
- Fix tests regarding ``*_EXPIRES settings`` with Files/Images pipelines (:gh:`2460`).
- Fix name of generated pipeline class when using basic project template (:gh:`2466`).
- Fix compatibility with Twisted 17+ (:gh:`2496`, :gh:`2528`).
- Fix ``scrapy.Item`` inheritance on Python 3.6 (:gh:`2511`).
- Enforce numeric values for components order in ``SPIDER_MIDDLEWARES``,
  ``DOWNLOADER_MIDDLEWARES``, ``EXTENSIONS`` and ``SPIDER_CONTRACTS`` (:gh:`2420`).

Documentation
~~~~~~~~~~~~~

- Reword Code of Conduct section and upgrade to Contributor Covenant v1.4
  (:gh:`2469`).
- Clarify that passing spider arguments converts them to spider attributes
  (:gh:`2483`).
- Document ``formid`` argument on ``FormRequest.from_response()`` (:gh:`2497`).
- Add .rst extension to README files (:gh:`2507`).
- Mention LevelDB cache storage backend (:gh:`2525`).
- Use ``yield`` in sample callback code (:gh:`2533`).
- Add note about HTML entities decoding with ``.re()/.re_first()`` (:gh:`1704`).
- Typos (:gh:`2512`, :gh:`2534`, :gh:`2531`).

Cleanups
~~~~~~~~

- Remove redundant check in ``MetaRefreshMiddleware`` (:gh:`2542`).
- Faster checks in ``LinkExtractor`` for allow/deny patterns (:gh:`2538`).
- Remove dead code supporting old Twisted versions (:gh:`2544`).


.. _release-1.3.0:

Scrapy 1.3.0 (2016-12-21)
-------------------------

This release comes rather soon after 1.2.2 for one main reason:
it was found out that releases since 0.18 up to 1.2.2 (included) use
some backported code from Twisted (``scrapy.xlib.tx.*``),
even if newer Twisted modules are available.
Scrapy now uses ``twisted.web.client`` and ``twisted.internet.endpoints`` directly.
(See also cleanups below.)

As it is a major change, we wanted to get the bug fix out quickly
while not breaking any projects using the 1.2 series.

New Features
~~~~~~~~~~~~

- ``MailSender`` now accepts single strings as values for ``to`` and ``cc``
  arguments (:gh:`2272`)
- ``scrapy fetch url``, ``scrapy shell url`` and ``fetch(url)`` inside
  Scrapy shell now follow HTTP redirections by default (:gh:`2290`);
  See :command:`fetch` and :command:`shell` for details.
- ``HttpErrorMiddleware`` now logs errors with ``INFO`` level instead of ``DEBUG``;
  this is technically **backward incompatible** so please check your log parsers.
- By default, logger names now use a long-form path, e.g. ``[scrapy.extensions.logstats]``,
  instead of the shorter "top-level" variant of prior releases (e.g. ``[scrapy]``);
  this is **backward incompatible** if you have log parsers expecting the short
  logger name part. You can switch back to short logger names using :setting:`LOG_SHORT_NAMES`
  set to ``True``.

Dependencies & Cleanups
~~~~~~~~~~~~~~~~~~~~~~~

- Scrapy now requires Twisted >= 13.1 which is the case for many Linux
  distributions already.
- As a consequence, we got rid of ``scrapy.xlib.tx.*`` modules, which
  copied some of Twisted code for users stuck with an "old" Twisted version
- ``ChunkedTransferMiddleware`` is deprecated and removed from the default
  downloader middlewares.

.. _release-1.2.3:

Scrapy 1.2.3 (2017-03-03)
-------------------------

- Packaging fix: disallow unsupported Twisted versions in setup.py


.. _release-1.2.2:

Scrapy 1.2.2 (2016-12-06)
-------------------------

Bug fixes
~~~~~~~~~

- Fix a cryptic traceback when a pipeline fails on ``open_spider()`` (:gh:`2011`)
- Fix embedded IPython shell variables (fixing :gh:`396` that re-appeared
  in 1.2.0, fixed in :gh:`2418`)
- A couple of patches when dealing with robots.txt:

  - handle (non-standard) relative sitemap URLs (:gh:`2390`)
  - handle non-ASCII URLs and User-Agents in Python 2 (:gh:`2373`)

Documentation
~~~~~~~~~~~~~

- Document ``"download_latency"`` key in ``Request``'s ``meta`` dict (:gh:`2033`)
- Remove page on (deprecated & unsupported) Ubuntu packages from ToC (:gh:`2335`)
- A few fixed typos (:gh:`2346`, :gh:`2369`, :gh:`2369`, :gh:`2380`)
  and clarifications (:gh:`2354`, :gh:`2325`, :gh:`2414`)

Other changes
~~~~~~~~~~~~~

- Advertize `conda-forge`_ as Scrapy's official conda channel (:gh:`2387`)
- More helpful error messages when trying to use ``.css()`` or ``.xpath()``
  on non-Text Responses (:gh:`2264`)
- ``startproject`` command now generates a sample ``middlewares.py`` file (:gh:`2335`)
- Add more dependencies' version info in ``scrapy version`` verbose output (:gh:`2404`)
- Remove all ``*.pyc`` files from source distribution (:gh:`2386`)

.. _conda-forge: https://anaconda.org/conda-forge/scrapy


.. _release-1.2.1:

Scrapy 1.2.1 (2016-10-21)
-------------------------

Bug fixes
~~~~~~~~~

- Include OpenSSL's more permissive default ciphers when establishing
  TLS/SSL connections (:gh:`2314`).
- Fix "Location" HTTP header decoding on non-ASCII URL redirects (:gh:`2321`).

Documentation
~~~~~~~~~~~~~

- Fix JsonWriterPipeline example (:gh:`2302`).
- Various notes: :gh:`2330` on spider names,
  :gh:`2329` on middleware methods processing order,
  :gh:`2327` on getting multi-valued HTTP headers as lists.

Other changes
~~~~~~~~~~~~~

- Removed ``www.`` from ``start_urls`` in built-in spider templates (:gh:`2299`).


.. _release-1.2.0:

Scrapy 1.2.0 (2016-10-03)
-------------------------

New Features
~~~~~~~~~~~~

- New :setting:`FEED_EXPORT_ENCODING` setting to customize the encoding
  used when writing items to a file.
  This can be used to turn off ``\uXXXX`` escapes in JSON output.
  This is also useful for those wanting something else than UTF-8
  for XML or CSV output (:gh:`2034`).
- ``startproject`` command now supports an optional destination directory
  to override the default one based on the project name (:gh:`2005`).
- New :setting:`SCHEDULER_DEBUG` setting to log requests serialization
  failures (:gh:`1610`).
- JSON encoder now supports serialization of ``set`` instances (:gh:`2058`).
- Interpret ``application/json-amazonui-streaming`` as ``TextResponse`` (:gh:`1503`).
- ``scrapy`` is imported by default when using shell tools (:command:`shell`,
  :ref:`inspect_response <topics-shell-inspect-response>`) (:gh:`2248`).

Bug fixes
~~~~~~~~~

- DefaultRequestHeaders middleware now runs before UserAgent middleware
  (:gh:`2088`). **Warning: this is technically backward incompatible**,
  though we consider this a bug fix.
- HTTP cache extension and plugins that use the ``.scrapy`` data directory now
  work outside projects (:gh:`1581`).  **Warning: this is technically
  backward incompatible**, though we consider this a bug fix.
- ``Selector`` does not allow passing both ``response`` and ``text`` anymore
  (:gh:`2153`).
- Fixed logging of wrong callback name with ``scrapy parse`` (:gh:`2169`).
- Fix for an odd gzip decompression bug (:gh:`1606`).
- Fix for selected callbacks when using ``CrawlSpider`` with :command:`scrapy parse <parse>`
  (:gh:`2225`).
- Fix for invalid JSON and XML files when spider yields no items (:gh:`872`).
- Implement ``flush()`` for ``StreamLogger`` avoiding a warning in logs (:gh:`2125`).

Refactoring
~~~~~~~~~~~

- ``canonicalize_url`` has been moved to `w3lib.url`_ (:gh:`2168`).

.. _w3lib.url: https://w3lib.readthedocs.io/en/latest/w3lib.html#w3lib.url.canonicalize_url

Tests & Requirements
~~~~~~~~~~~~~~~~~~~~

Scrapy's new requirements baseline is Debian 8 "Jessie". It was previously
Ubuntu 12.04 Precise.
What this means in practice is that we run continuous integration tests
with these (main) packages versions at a minimum:
Twisted 14.0, pyOpenSSL 0.14, lxml 3.4.

Scrapy may very well work with older versions of these packages
(the code base still has switches for older Twisted versions for example)
but it is not guaranteed (because it's not tested anymore).

Documentation
~~~~~~~~~~~~~

- Grammar fixes: :gh:`2128`, :gh:`1566`.
- Download stats badge removed from README (:gh:`2160`).
- New Scrapy :ref:`architecture diagram <topics-architecture>` (:gh:`2165`).
- Updated ``Response`` parameters documentation (:gh:`2197`).
- Reworded misleading :setting:`RANDOMIZE_DOWNLOAD_DELAY` description (:gh:`2190`).
- Add StackOverflow as a support channel (:gh:`2257`).

.. _release-1.1.4:

Scrapy 1.1.4 (2017-03-03)
-------------------------

- Packaging fix: disallow unsupported Twisted versions in setup.py

.. _release-1.1.3:

Scrapy 1.1.3 (2016-09-22)
-------------------------

Bug fixes
~~~~~~~~~

- Class attributes for subclasses of ``ImagesPipeline`` and ``FilesPipeline``
  work as they did before 1.1.1 (:gh:`2243`, fixes :gh:`2198`)

Documentation
~~~~~~~~~~~~~

- :ref:`Overview <intro-overview>` and :ref:`tutorial <intro-tutorial>`
  rewritten to use http://toscrape.com websites
  (:gh:`2236`, :gh:`2249`, :gh:`2252`).

.. _release-1.1.2:

Scrapy 1.1.2 (2016-08-18)
-------------------------

Bug fixes
~~~~~~~~~

- Introduce a missing :setting:`IMAGES_STORE_S3_ACL` setting to override
  the default ACL policy in ``ImagesPipeline`` when uploading images to S3
  (note that default ACL policy is "private" -- instead of "public-read" --
  since Scrapy 1.1.0)
- :setting:`IMAGES_EXPIRES` default value set back to 90
  (the regression was introduced in 1.1.1)

.. _release-1.1.1:

Scrapy 1.1.1 (2016-07-13)
-------------------------

Bug fixes
~~~~~~~~~

- Add "Host" header in CONNECT requests to HTTPS proxies (:gh:`2069`)
- Use response ``body`` when choosing response class
  (:gh:`2001`, fixes :gh:`2000`)
- Do not fail on canonicalizing URLs with wrong netlocs
  (:gh:`2038`, fixes :gh:`2010`)
- a few fixes for ``HttpCompressionMiddleware`` (and ``SitemapSpider``):

  - Do not decode HEAD responses (:gh:`2008`, fixes :gh:`1899`)
  - Handle charset parameter in gzip Content-Type header
    (:gh:`2050`, fixes :gh:`2049`)
  - Do not decompress gzip octet-stream responses
    (:gh:`2065`, fixes :gh:`2063`)

- Catch (and ignore with a warning) exception when verifying certificate
  against IP-address hosts (:gh:`2094`, fixes :gh:`2092`)
- Make ``FilesPipeline`` and ``ImagesPipeline`` backward compatible again
  regarding the use of legacy class attributes for customization
  (:gh:`1989`, fixes :gh:`1985`)


New features
~~~~~~~~~~~~

- Enable genspider command outside project folder (:gh:`2052`)
- Retry HTTPS CONNECT ``TunnelError`` by default (:gh:`1974`)


Documentation
~~~~~~~~~~~~~

- ``FEED_TEMPDIR`` setting at lexicographical position (:commit:`9b3c72c`)
- Use idiomatic ``.extract_first()`` in overview (:gh:`1994`)
- Update years in copyright notice (:commit:`c2c8036`)
- Add information and example on errbacks (:gh:`1995`)
- Use "url" variable in downloader middleware example (:gh:`2015`)
- Grammar fixes (:gh:`2054`, :gh:`2120`)
- New FAQ entry on using BeautifulSoup in spider callbacks (:gh:`2048`)
- Add notes about Scrapy not working on Windows with Python 3 (:gh:`2060`)
- Encourage complete titles in pull requests (:gh:`2026`)

Tests
~~~~~

- Upgrade py.test requirement on Travis CI and Pin pytest-cov to 2.2.1 (:gh:`2095`)

.. _release-1.1.0:

Scrapy 1.1.0 (2016-05-11)
-------------------------

This 1.1 release brings a lot of interesting features and bug fixes:

- Scrapy 1.1 has beta Python 3 support (requires Twisted >= 15.5). See
  :ref:`news_betapy3` for more details and some limitations.
- Hot new features:

  - Item loaders now support nested loaders (:gh:`1467`).
  - ``FormRequest.from_response`` improvements (:gh:`1382`, :gh:`1137`).
  - Added setting :setting:`AUTOTHROTTLE_TARGET_CONCURRENCY` and improved
    AutoThrottle docs (:gh:`1324`).
  - Added ``response.text`` to get body as unicode (:gh:`1730`).
  - Anonymous S3 connections (:gh:`1358`).
  - Deferreds in downloader middlewares (:gh:`1473`). This enables better
    robots.txt handling (:gh:`1471`).
  - HTTP caching now follows RFC2616 more closely, added settings
    :setting:`HTTPCACHE_ALWAYS_STORE` and
    :setting:`HTTPCACHE_IGNORE_RESPONSE_CACHE_CONTROLS` (:gh:`1151`).
  - Selectors were extracted to the parsel_ library (:gh:`1409`). This means
    you can use Scrapy Selectors without Scrapy and also upgrade the
    selectors engine without needing to upgrade Scrapy.
  - HTTPS downloader now does TLS protocol negotiation by default,
    instead of forcing TLS 1.0. You can also set the SSL/TLS method
    using the new ``DOWNLOADER_CLIENT_TLS_METHOD`` setting.

- These bug fixes may require your attention:

  - Don't retry bad requests (HTTP 400) by default (:gh:`1289`).
    If you need the old behavior, add ``400`` to :setting:`RETRY_HTTP_CODES`.
  - Fix shell files argument handling (:gh:`1710`, :gh:`1550`).
    If you try ``scrapy shell index.html`` it will try to load the URL ``http://index.html``,
    use ``scrapy shell ./index.html`` to load a local file.
  - Robots.txt compliance is now enabled by default for newly-created projects
    (:gh:`1724`). Scrapy will also wait for robots.txt to be downloaded
    before proceeding with the crawl (:gh:`1735`). If you want to disable
    this behavior, update :setting:`ROBOTSTXT_OBEY` in ``settings.py`` file
    after creating a new project.
  - Exporters now work on unicode, instead of bytes by default (:gh:`1080`).
    If you use :class:`~scrapy.exporters.PythonItemExporter`, you may want to
    update your code to disable binary mode which is now deprecated.
  - Accept XML node names containing dots as valid (:gh:`1533`).
  - When uploading files or images to S3 (with ``FilesPipeline`` or
    ``ImagesPipeline``), the default ACL policy is now "private" instead
    of "public" **Warning: backward incompatible!**.
    You can use :setting:`FILES_STORE_S3_ACL` to change it.
  - We've reimplemented ``canonicalize_url()`` for more correct output,
    especially for URLs with non-ASCII characters (:gh:`1947`).
    This could change link extractors output compared to previous Scrapy versions.
    This may also invalidate some cache entries you could still have from pre-1.1 runs.
    **Warning: backward incompatible!**.

Keep reading for more details on other improvements and bug fixes.

.. _news_betapy3:

Beta Python 3 Support
~~~~~~~~~~~~~~~~~~~~~

We have been hard at work to make Scrapy run on Python 3. As a result, now
you can run spiders on Python 3.3, 3.4 and 3.5 (Twisted >= 15.5 required). Some
features are still missing (and some may never be ported).


Almost all builtin extensions/middlewares are expected to work.
However, we are aware of some limitations in Python 3:

- Scrapy does not work on Windows with Python 3
- Sending emails is not supported
- FTP download handler is not supported
- Telnet console is not supported

Additional New Features and Enhancements
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- Scrapy now has a `Code of Conduct`_ (:gh:`1681`).
- Command line tool now has completion for zsh (:gh:`934`).
- Improvements to ``scrapy shell``:

  - Support for bpython and configure preferred Python shell via
    ``SCRAPY_PYTHON_SHELL`` (:gh:`1100`, :gh:`1444`).
  - Support URLs without scheme (:gh:`1498`)
    **Warning: backward incompatible!**
  - Bring back support for relative file path (:gh:`1710`, :gh:`1550`).

- Added :setting:`MEMUSAGE_CHECK_INTERVAL_SECONDS` setting to change default check
  interval (:gh:`1282`).
- Download handlers are now lazy-loaded on first request using their
  scheme (:gh:`1390`, :gh:`1421`).
- HTTPS download handlers do not force TLS 1.0 anymore; instead,
  OpenSSL's ``SSLv23_method()/TLS_method()`` is used allowing to try
  negotiating with the remote hosts the highest TLS protocol version
  it can (:gh:`1794`, :gh:`1629`).
- ``RedirectMiddleware`` now skips the status codes from
  ``handle_httpstatus_list`` on spider attribute
  or in ``Request``'s ``meta`` key (:gh:`1334`, :gh:`1364`,
  :gh:`1447`).
- Form submission:

  - now works with ``<button>`` elements too (:gh:`1469`).
  - an empty string is now used for submit buttons without a value
    (:gh:`1472`)

- Dict-like settings now have per-key priorities
  (:gh:`1135`, :gh:`1149` and :gh:`1586`).
- Sending non-ASCII emails (:gh:`1662`)
- ``CloseSpider`` and ``SpiderState`` extensions now get disabled if no relevant
  setting is set (:gh:`1723`, :gh:`1725`).
- Added method ``ExecutionEngine.close`` (:gh:`1423`).
- Added method ``CrawlerRunner.create_crawler`` (:gh:`1528`).
- Scheduler priority queue can now be customized via
  :setting:`SCHEDULER_PRIORITY_QUEUE` (:gh:`1822`).
- ``.pps`` links are now ignored by default in link extractors (:gh:`1835`).
- temporary data folder for FTP and S3 feed storages can be customized
  using a new :setting:`FEED_TEMPDIR` setting (:gh:`1847`).
- ``FilesPipeline`` and ``ImagesPipeline`` settings are now instance attributes
  instead of class attributes, enabling spider-specific behaviors (:gh:`1891`).
- ``JsonItemExporter`` now formats opening and closing square brackets
  on their own line (first and last lines of output file) (:gh:`1950`).
- If available, ``botocore`` is used for ``S3FeedStorage``, ``S3DownloadHandler``
  and ``S3FilesStore`` (:gh:`1761`, :gh:`1883`).
- Tons of documentation updates and related fixes (:gh:`1291`, :gh:`1302`,
  :gh:`1335`, :gh:`1683`, :gh:`1660`, :gh:`1642`, :gh:`1721`,
  :gh:`1727`, :gh:`1879`).
- Other refactoring, optimizations and cleanup (:gh:`1476`, :gh:`1481`,
  :gh:`1477`, :gh:`1315`, :gh:`1290`, :gh:`1750`, :gh:`1881`).

.. _Code of Conduct: https://github.com/scrapy/scrapy/blob/master/CODE_OF_CONDUCT.md


Deprecations and Removals
~~~~~~~~~~~~~~~~~~~~~~~~~

- Added ``to_bytes`` and ``to_unicode``, deprecated ``str_to_unicode`` and
  ``unicode_to_str`` functions (:gh:`778`).
- ``binary_is_text`` is introduced, to replace use of ``isbinarytext``
  (but with inverse return value) (:gh:`1851`)
- The ``optional_features`` set has been removed (:gh:`1359`).
- The ``--lsprof`` command line option has been removed (:gh:`1689`).
  **Warning: backward incompatible**, but doesn't break user code.
- The following datatypes were deprecated (:gh:`1720`):

  + ``scrapy.utils.datatypes.MultiValueDictKeyError``
  + ``scrapy.utils.datatypes.MultiValueDict``
  + ``scrapy.utils.datatypes.SiteNode``

- The previously bundled ``scrapy.xlib.pydispatch`` library was deprecated and
  replaced by `pydispatcher <https://pypi.org/project/PyDispatcher/>`_.


Relocations
~~~~~~~~~~~

- ``telnetconsole`` was relocated to ``extensions/`` (:gh:`1524`).

  + Note: telnet is not enabled on Python 3
    (https://github.com/scrapy/scrapy/pull/1524#issuecomment-146985595)


Bugfixes
~~~~~~~~

- Scrapy does not retry requests that got a ``HTTP 400 Bad Request``
  response anymore (:gh:`1289`). **Warning: backward incompatible!**
- Support empty password for http_proxy config (:gh:`1274`).
- Interpret ``application/x-json`` as ``TextResponse`` (:gh:`1333`).
- Support link rel attribute with multiple values (:gh:`1201`).
- Fixed ``scrapy.FormRequest.from_response`` when there is a ``<base>``
  tag (:gh:`1564`).
- Fixed :setting:`TEMPLATES_DIR` handling (:gh:`1575`).
- Various ``FormRequest`` fixes (:gh:`1595`, :gh:`1596`, :gh:`1597`).
- Makes ``_monkeypatches`` more robust (:gh:`1634`).
- Fixed bug on ``XMLItemExporter`` with non-string fields in
  items (:gh:`1738`).
- Fixed startproject command in macOS (:gh:`1635`).
- Fixed :class:`~scrapy.exporters.PythonItemExporter` and CSVExporter for
  non-string item types (:gh:`1737`).
- Various logging related fixes (:gh:`1294`, :gh:`1419`, :gh:`1263`,
  :gh:`1624`, :gh:`1654`, :gh:`1722`, :gh:`1726` and :gh:`1303`).
- Fixed bug in ``utils.template.render_templatefile()`` (:gh:`1212`).
- sitemaps extraction from ``robots.txt`` is now case-insensitive (:gh:`1902`).
- HTTPS+CONNECT tunnels could get mixed up when using multiple proxies
  to same remote host (:gh:`1912`).

.. _release-1.0.7:

Scrapy 1.0.7 (2017-03-03)
-------------------------

- Packaging fix: disallow unsupported Twisted versions in setup.py

.. _release-1.0.6:

Scrapy 1.0.6 (2016-05-04)
-------------------------

- FIX: RetryMiddleware is now robust to non-standard HTTP status codes (:gh:`1857`)
- FIX: Filestorage HTTP cache was checking wrong modified time (:gh:`1875`)
- DOC: Support for Sphinx 1.4+ (:gh:`1893`)
- DOC: Consistency in selectors examples (:gh:`1869`)

.. _release-1.0.5:

Scrapy 1.0.5 (2016-02-04)
-------------------------

- FIX: [Backport] Ignore bogus links in LinkExtractors (fixes :gh:`907`, :commit:`108195e`)
- TST: Changed buildbot makefile to use 'pytest' (:commit:`1f3d90a`)
- DOC: Fixed typos in tutorial and media-pipeline (:commit:`808a9ea` and :commit:`803bd87`)
- DOC: Add AjaxCrawlMiddleware to DOWNLOADER_MIDDLEWARES_BASE in settings docs (:commit:`aa94121`)

.. _release-1.0.4:

Scrapy 1.0.4 (2015-12-30)
-------------------------

- Ignoring xlib/tx folder, depending on Twisted version. (:commit:`7dfa979`)
- Run on new travis-ci infra (:commit:`6e42f0b`)
- Spelling fixes (:commit:`823a1cc`)
- escape nodename in xmliter regex (:commit:`da3c155`)
- test xml nodename with dots (:commit:`4418fc3`)
- TST don't use broken Pillow version in tests (:commit:`a55078c`)
- disable log on version command. closes #1426 (:commit:`86fc330`)
- disable log on startproject command (:commit:`db4c9fe`)
- Add PyPI download stats badge (:commit:`df2b944`)
- don't run tests twice on Travis if a PR is made from a scrapy/scrapy branch (:commit:`a83ab41`)
- Add Python 3 porting status badge to the README (:commit:`73ac80d`)
- fixed RFPDupeFilter persistence (:commit:`97d080e`)
- TST a test to show that dupefilter persistence is not working (:commit:`97f2fb3`)
- explicit close file on file:// scheme handler (:commit:`d9b4850`)
- Disable dupefilter in shell (:commit:`c0d0734`)
- DOC: Add captions to toctrees which appear in sidebar (:commit:`aa239ad`)
- DOC Removed pywin32 from install instructions as it's already declared as dependency. (:commit:`10eb400`)
- Added installation notes about using Conda for Windows and other OSes. (:commit:`1c3600a`)
- Fixed minor grammar issues. (:commit:`7f4ddd5`)
- fixed a typo in the documentation. (:commit:`b71f677`)
- Version 1 now exists (:commit:`5456c0e`)
- fix another invalid xpath error (:commit:`0a1366e`)
- fix ValueError: Invalid XPath: //div/[id="not-exists"]/text() on selectors.rst (:commit:`ca8d60f`)
- Typos corrections (:commit:`7067117`)
- fix typos in downloader-middleware.rst and exceptions.rst, middlware -> middleware (:commit:`32f115c`)
- Add note to Ubuntu install section about Debian compatibility (:commit:`23fda69`)
- Replace alternative macOS install workaround with virtualenv (:commit:`98b63ee`)
- Reference Homebrew's homepage for installation instructions (:commit:`1925db1`)
- Add oldest supported tox version to contributing docs (:commit:`5d10d6d`)
- Note in install docs about pip being already included in python>=2.7.9 (:commit:`85c980e`)
- Add non-python dependencies to Ubuntu install section in the docs (:commit:`fbd010d`)
- Add macOS installation section to docs (:commit:`d8f4cba`)
- DOC(ENH): specify path to rtd theme explicitly (:commit:`de73b1a`)
- minor: scrapy.Spider docs grammar (:commit:`1ddcc7b`)
- Make common practices sample code match the comments (:commit:`1b85bcf`)
- nextcall repetitive calls (heartbeats). (:commit:`55f7104`)
- Backport fix compatibility with Twisted 15.4.0 (:commit:`b262411`)
- pin pytest to 2.7.3 (:commit:`a6535c2`)
- Merge pull request #1512 from mgedmin/patch-1 (:commit:`8876111`)
- Merge pull request #1513 from mgedmin/patch-2 (:commit:`5d4daf8`)
- Typo (:commit:`f8d0682`)
- Fix list formatting (:commit:`5f83a93`)
- fix Scrapy squeue tests after recent changes to queuelib (:commit:`3365c01`)
- Merge pull request #1475 from rweindl/patch-1 (:commit:`2d688cd`)
- Update tutorial.rst (:commit:`fbc1f25`)
- Merge pull request #1449 from rhoekman/patch-1 (:commit:`7d6538c`)
- Small grammatical change (:commit:`8752294`)
- Add openssl version to version command (:commit:`13c45ac`)

.. _release-1.0.3:

Scrapy 1.0.3 (2015-08-11)
-------------------------

- add service_identity to Scrapy install_requires (:commit:`cbc2501`)
- Workaround for travis#296 (:commit:`66af9cd`)

.. _release-1.0.2:

Scrapy 1.0.2 (2015-08-06)
-------------------------

- Twisted 15.3.0 does not raises PicklingError serializing lambda functions (:commit:`b04dd7d`)
- Minor method name fix (:commit:`6f85c7f`)
- minor: scrapy.Spider grammar and clarity (:commit:`9c9d2e0`)
- Put a blurb about support channels in CONTRIBUTING (:commit:`c63882b`)
- Fixed typos (:commit:`a9ae7b0`)
- Fix doc reference. (:commit:`7c8a4fe`)

.. _release-1.0.1:

Scrapy 1.0.1 (2015-07-01)
-------------------------

- Unquote request path before passing to FTPClient, it already escape paths (:commit:`cc00ad2`)
- include tests/ to source distribution in MANIFEST.in (:commit:`eca227e`)
- DOC Fix SelectJmes documentation (:commit:`b8567bc`)
- DOC Bring Ubuntu and Archlinux outside of Windows subsection (:commit:`392233f`)
- DOC remove version suffix from Ubuntu package (:commit:`5303c66`)
- DOC Update release date for 1.0 (:commit:`c89fa29`)

.. _release-1.0.0:

Scrapy 1.0.0 (2015-06-19)
-------------------------

You will find a lot of new features and bugfixes in this major release.  Make
sure to check our updated :ref:`overview <intro-overview>` to get a glance of
some of the changes, along with our brushed :ref:`tutorial <intro-tutorial>`.

Support for returning dictionaries in spiders
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Declaring and returning Scrapy Items is no longer necessary to collect the
scraped data from your spider, you can now return explicit dictionaries
instead.

*Classic version*

::

    class MyItem(scrapy.Item):
        url = scrapy.Field()

    class MySpider(scrapy.Spider):
        def parse(self, response):
            return MyItem(url=response.url)

*New version*

::

    class MySpider(scrapy.Spider):
        def parse(self, response):
            return {'url': response.url}

Per-spider settings (GSoC 2014)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Last Google Summer of Code project accomplished an important redesign of the
mechanism used for populating settings, introducing explicit priorities to
override any given setting. As an extension of that goal, we included a new
level of priority for settings that act exclusively for a single spider,
allowing them to redefine project settings.

Start using it by defining a :attr:`~scrapy.spiders.Spider.custom_settings`
class variable in your spider::

    class MySpider(scrapy.Spider):
        custom_settings = {
            "DOWNLOAD_DELAY": 5.0,
            "RETRY_ENABLED": False,
        }

Read more about settings population: :ref:`topics-settings`

Python Logging
~~~~~~~~~~~~~~

Scrapy 1.0 has moved away from Twisted logging to support Python built in’s
as default logging system. We’re maintaining backward compatibility for most
of the old custom interface to call logging functions, but you’ll get
warnings to switch to the Python logging API entirely.

*Old version*

::

    from scrapy import log
    log.msg('MESSAGE', log.INFO)

*New version*

::

    import logging
    logging.info('MESSAGE')

Logging with spiders remains the same, but on top of the
:meth:`~scrapy.spiders.Spider.log` method you’ll have access to a custom
:attr:`~scrapy.spiders.Spider.logger` created for the spider to issue log
events:

::

    class MySpider(scrapy.Spider):
        def parse(self, response):
            self.logger.info('Response received')

Read more in the logging documentation: :ref:`topics-logging`

Crawler API refactoring (GSoC 2014)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Another milestone for last Google Summer of Code was a refactoring of the
internal API, seeking a simpler and easier usage. Check new core interface
in: :ref:`topics-api`

A common situation where you will face these changes is while running Scrapy
from scripts. Here’s a quick example of how to run a Spider manually with the
new API:

::

    from scrapy.crawler import CrawlerProcess

    process = CrawlerProcess({
        'USER_AGENT': 'Mozilla/4.0 (compatible; MSIE 7.0; Windows NT 5.1)'
    })
    process.crawl(MySpider)
    process.start()

Bear in mind this feature is still under development and its API may change
until it reaches a stable status.

See more examples for scripts running Scrapy: :ref:`topics-practices`

.. _module-relocations:

Module Relocations
~~~~~~~~~~~~~~~~~~

There’s been a large rearrangement of modules trying to improve the general
structure of Scrapy. Main changes were separating various subpackages into
new projects and dissolving both ``scrapy.contrib`` and ``scrapy.contrib_exp``
into top level packages. Backward compatibility was kept among internal
relocations, while importing deprecated modules expect warnings indicating
their new place.

Full list of relocations
************************

Outsourced packages

.. note::
    These extensions went through some minor changes, e.g. some setting names
    were changed. Please check the documentation in each new repository to
    get familiar with the new usage.

+-------------------------------------+-------------------------------------+
| Old location                        | New location                        |
+=====================================+=====================================+
| scrapy.commands.deploy              | `scrapyd-client <https://github.com |
|                                     | /scrapy/scrapyd-client>`_           |
|                                     | (See other alternatives here:       |
|                                     | :ref:`topics-deploy`)               |
+-------------------------------------+-------------------------------------+
| scrapy.contrib.djangoitem           | `scrapy-djangoitem <https://github. |
|                                     | com/scrapy-plugins/scrapy-djangoite |
|                                     | m>`_                                |
+-------------------------------------+-------------------------------------+
| scrapy.webservice                   | `scrapy-jsonrpc <https://github.com |
|                                     | /scrapy-plugins/scrapy-jsonrpc>`_   |
+-------------------------------------+-------------------------------------+

``scrapy.contrib_exp`` and ``scrapy.contrib`` dissolutions

+-------------------------------------+-------------------------------------+
| Old location                        | New location                        |
+=====================================+=====================================+
| scrapy.contrib\_exp.downloadermidd\ | scrapy.downloadermiddlewares.decom\ |
| leware.decompression                | pression                            |
+-------------------------------------+-------------------------------------+
| scrapy.contrib\_exp.iterators       | scrapy.utils.iterators              |
+-------------------------------------+-------------------------------------+
| scrapy.contrib.downloadermiddleware | scrapy.downloadermiddlewares        |
+-------------------------------------+-------------------------------------+
| scrapy.contrib.exporter             | scrapy.exporters                    |
+-------------------------------------+-------------------------------------+
| scrapy.contrib.linkextractors       | scrapy.linkextractors               |
+-------------------------------------+-------------------------------------+
| scrapy.contrib.loader               | scrapy.loader                       |
+-------------------------------------+-------------------------------------+
| scrapy.contrib.loader.processor     | scrapy.loader.processors            |
+-------------------------------------+-------------------------------------+
| scrapy.contrib.pipeline             | scrapy.pipelines                    |
+-------------------------------------+-------------------------------------+
| scrapy.contrib.spidermiddleware     | scrapy.spidermiddlewares            |
+-------------------------------------+-------------------------------------+
| scrapy.contrib.spiders              | scrapy.spiders                      |
+-------------------------------------+-------------------------------------+
| * scrapy.contrib.closespider        | scrapy.extensions.\*                |
| * scrapy.contrib.corestats          |                                     |
| * scrapy.contrib.debug              |                                     |
| * scrapy.contrib.feedexport         |                                     |
| * scrapy.contrib.httpcache          |                                     |
| * scrapy.contrib.logstats           |                                     |
| * scrapy.contrib.memdebug           |                                     |
| * scrapy.contrib.memusage           |                                     |
| * scrapy.contrib.spiderstate        |                                     |
| * scrapy.contrib.statsmailer        |                                     |
| * scrapy.contrib.throttle           |                                     |
+-------------------------------------+-------------------------------------+

Plural renames and Modules unification

+-------------------------------------+-------------------------------------+
| Old location                        | New location                        |
+=====================================+=====================================+
| scrapy.command                      | scrapy.commands                     |
+-------------------------------------+-------------------------------------+
| scrapy.dupefilter                   | scrapy.dupefilters                  |
+-------------------------------------+-------------------------------------+
| scrapy.linkextractor                | scrapy.linkextractors               |
+-------------------------------------+-------------------------------------+
| scrapy.spider                       | scrapy.spiders                      |
+-------------------------------------+-------------------------------------+
| scrapy.squeue                       | scrapy.squeues                      |
+-------------------------------------+-------------------------------------+
| scrapy.statscol                     | scrapy.statscollectors              |
+-------------------------------------+-------------------------------------+
| scrapy.utils.decorator              | scrapy.utils.decorators             |
+-------------------------------------+-------------------------------------+

Class renames

+-------------------------------------+-------------------------------------+
| Old location                        | New location                        |
+=====================================+=====================================+
| scrapy.spidermanager.SpiderManager  | scrapy.spiderloader.SpiderLoader    |
+-------------------------------------+-------------------------------------+

Settings renames

+-------------------------------------+-------------------------------------+
| Old location                        | New location                        |
+=====================================+=====================================+
| SPIDER\_MANAGER\_CLASS              | SPIDER\_LOADER\_CLASS               |
+-------------------------------------+-------------------------------------+

Changelog
~~~~~~~~~

New Features and Enhancements

- Python logging (:gh:`1060`, :gh:`1235`, :gh:`1236`, :gh:`1240`,
  :gh:`1259`, :gh:`1278`, :gh:`1286`)
- FEED_EXPORT_FIELDS option (:gh:`1159`, :gh:`1224`)
- Dns cache size and timeout options (:gh:`1132`)
- support namespace prefix in xmliter_lxml (:gh:`963`)
- Reactor threadpool max size setting (:gh:`1123`)
- Allow spiders to return dicts. (:gh:`1081`)
- Add Response.urljoin() helper (:gh:`1086`)
- look in ~/.config/scrapy.cfg for user config (:gh:`1098`)
- handle TLS SNI (:gh:`1101`)
- Selectorlist extract first (:gh:`624`, :gh:`1145`)
- Added JmesSelect (:gh:`1016`)
- add gzip compression to filesystem http cache backend (:gh:`1020`)
- CSS support in link extractors (:gh:`983`)
- httpcache dont_cache meta #19 #689 (:gh:`821`)
- add signal to be sent when request is dropped by the scheduler
  (:gh:`961`)
- avoid download large response (:gh:`946`)
- Allow to specify the quotechar in CSVFeedSpider (:gh:`882`)
- Add referer to "Spider error processing" log message (:gh:`795`)
- process robots.txt once (:gh:`896`)
- GSoC Per-spider settings (:gh:`854`)
- Add project name validation (:gh:`817`)
- GSoC API cleanup (:gh:`816`, :gh:`1128`, :gh:`1147`,
  :gh:`1148`, :gh:`1156`, :gh:`1185`, :gh:`1187`, :gh:`1258`,
  :gh:`1268`, :gh:`1276`, :gh:`1285`, :gh:`1284`)
- Be more responsive with IO operations (:gh:`1074` and :gh:`1075`)
- Do leveldb compaction for httpcache on closing (:gh:`1297`)

Deprecations and Removals

- Deprecate htmlparser link extractor (:gh:`1205`)
- remove deprecated code from FeedExporter (:gh:`1155`)
- a leftover for.15 compatibility (:gh:`925`)
- drop support for CONCURRENT_REQUESTS_PER_SPIDER (:gh:`895`)
- Drop old engine code (:gh:`911`)
- Deprecate SgmlLinkExtractor (:gh:`777`)

Relocations

- Move exporters/__init__.py to exporters.py (:gh:`1242`)
- Move base classes to their packages (:gh:`1218`, :gh:`1233`)
- Module relocation (:gh:`1181`, :gh:`1210`)
- rename SpiderManager to SpiderLoader (:gh:`1166`)
- Remove djangoitem (:gh:`1177`)
- remove scrapy deploy command (:gh:`1102`)
- dissolve contrib_exp (:gh:`1134`)
- Deleted bin folder from root, fixes #913 (:gh:`914`)
- Remove jsonrpc based webservice (:gh:`859`)
- Move Test cases under project root dir (:gh:`827`, :gh:`841`)
- Fix backward incompatibility for relocated paths in settings
  (:gh:`1267`)

Documentation

- CrawlerProcess documentation (:gh:`1190`)
- Favoring web scraping over screen scraping in the descriptions
  (:gh:`1188`)
- Some improvements for Scrapy tutorial (:gh:`1180`)
- Documenting Files Pipeline together with Images Pipeline (:gh:`1150`)
- deployment docs tweaks (:gh:`1164`)
- Added deployment section covering scrapyd-deploy and shub (:gh:`1124`)
- Adding more settings to project template (:gh:`1073`)
- some improvements to overview page (:gh:`1106`)
- Updated link in docs/topics/architecture.rst (:gh:`647`)
- DOC reorder topics (:gh:`1022`)
- updating list of Request.meta special keys (:gh:`1071`)
- DOC document download_timeout (:gh:`898`)
- DOC simplify extension docs (:gh:`893`)
- Leaks docs (:gh:`894`)
- DOC document from_crawler method for item pipelines (:gh:`904`)
- Spider_error doesn't support deferreds (:gh:`1292`)
- Corrections & Sphinx related fixes (:gh:`1220`, :gh:`1219`,
  :gh:`1196`, :gh:`1172`, :gh:`1171`, :gh:`1169`, :gh:`1160`,
  :gh:`1154`, :gh:`1127`, :gh:`1112`, :gh:`1105`, :gh:`1041`,
  :gh:`1082`, :gh:`1033`, :gh:`944`, :gh:`866`, :gh:`864`,
  :gh:`796`, :gh:`1260`, :gh:`1271`, :gh:`1293`, :gh:`1298`)

Bugfixes

- Item multi inheritance fix (:gh:`353`, :gh:`1228`)
- ItemLoader.load_item: iterate over copy of fields (:gh:`722`)
- Fix Unhandled error in Deferred (RobotsTxtMiddleware) (:gh:`1131`,
  :gh:`1197`)
- Force to read DOWNLOAD_TIMEOUT as int (:gh:`954`)
- scrapy.utils.misc.load_object should print full traceback (:gh:`902`)
- Fix bug for ".local" host name (:gh:`878`)
- Fix for Enabled extensions, middlewares, pipelines info not printed
  anymore (:gh:`879`)
- fix dont_merge_cookies bad behaviour when set to false on meta
  (:gh:`846`)

Python 3 In Progress Support

- disable scrapy.telnet if twisted.conch is not available (:gh:`1161`)
- fix Python 3 syntax errors in ajaxcrawl.py (:gh:`1162`)
- more python3 compatibility changes for urllib (:gh:`1121`)
- assertItemsEqual was renamed to assertCountEqual in Python 3.
  (:gh:`1070`)
- Import unittest.mock if available. (:gh:`1066`)
- updated deprecated cgi.parse_qsl to use six's parse_qsl (:gh:`909`)
- Prevent Python 3 port regressions (:gh:`830`)
- PY3: use MutableMapping for python 3 (:gh:`810`)
- PY3: use six.BytesIO and six.moves.cStringIO (:gh:`803`)
- PY3: fix xmlrpclib and email imports (:gh:`801`)
- PY3: use six for robotparser and urlparse (:gh:`800`)
- PY3: use six.iterkeys, six.iteritems, and tempfile (:gh:`799`)
- PY3: fix has_key and use six.moves.configparser (:gh:`798`)
- PY3: use six.moves.cPickle (:gh:`797`)
- PY3 make it possible to run some tests in Python3 (:gh:`776`)

Tests

- remove unnecessary lines from py3-ignores (:gh:`1243`)
- Fix remaining warnings from pytest while collecting tests (:gh:`1206`)
- Add docs build to travis (:gh:`1234`)
- TST don't collect tests from deprecated modules. (:gh:`1165`)
- install service_identity package in tests to prevent warnings
  (:gh:`1168`)
- Fix deprecated settings API in tests (:gh:`1152`)
- Add test for webclient with POST method and no body given (:gh:`1089`)
- py3-ignores.txt supports comments (:gh:`1044`)
- modernize some of the asserts (:gh:`835`)
- selector.__repr__ test (:gh:`779`)

Code refactoring

- CSVFeedSpider cleanup: use iterate_spider_output (:gh:`1079`)
- remove unnecessary check from scrapy.utils.spider.iter_spider_output
  (:gh:`1078`)
- Pydispatch pep8 (:gh:`992`)
- Removed unused 'load=False' parameter from walk_modules() (:gh:`871`)
- For consistency, use ``job_dir`` helper in ``SpiderState`` extension.
  (:gh:`805`)
- rename "sflo" local variables to less cryptic "log_observer" (:gh:`775`)

Scrapy 0.24.6 (2015-04-20)
--------------------------

- encode invalid xpath with unicode_escape under PY2 (:commit:`07cb3e5`)
- fix IPython shell scope issue and load IPython user config (:commit:`2c8e573`)
- Fix small typo in the docs (:commit:`d694019`)
- Fix small typo (:commit:`f92fa83`)
- Converted sel.xpath() calls to response.xpath() in Extracting the data (:commit:`c2c6d15`)


Scrapy 0.24.5 (2015-02-25)
--------------------------

- Support new _getEndpoint Agent signatures on Twisted 15.0.0 (:commit:`540b9bc`)
- DOC a couple more references are fixed (:commit:`b4c454b`)
- DOC fix a reference (:commit:`e3c1260`)
- t.i.b.ThreadedResolver is now a new-style class (:commit:`9e13f42`)
- S3DownloadHandler: fix auth for requests with quoted paths/query params (:commit:`cdb9a0b`)
- fixed the variable types in mailsender documentation (:commit:`bb3a848`)
- Reset items_scraped instead of item_count (:commit:`edb07a4`)
- Tentative attention message about what document to read for contributions (:commit:`7ee6f7a`)
- mitmproxy 0.10.1 needs netlib 0.10.1 too (:commit:`874fcdd`)
- pin mitmproxy 0.10.1 as >0.11 does not work with tests (:commit:`c6b21f0`)
- Test the parse command locally instead of against an external url (:commit:`c3a6628`)
- Patches Twisted issue while closing the connection pool on HTTPDownloadHandler (:commit:`d0bf957`)
- Updates documentation on dynamic item classes. (:commit:`eeb589a`)
- Merge pull request #943 from Lazar-T/patch-3 (:commit:`5fdab02`)
- typo (:commit:`b0ae199`)
- pywin32 is required by Twisted. closes #937 (:commit:`5cb0cfb`)
- Update install.rst (:commit:`781286b`)
- Merge pull request #928 from Lazar-T/patch-1 (:commit:`b415d04`)
- comma instead of fullstop (:commit:`627b9ba`)
- Merge pull request #885 from jsma/patch-1 (:commit:`de909ad`)
- Update request-response.rst (:commit:`3f3263d`)
- SgmlLinkExtractor - fix for parsing <area> tag with Unicode present (:commit:`49b40f0`)

Scrapy 0.24.4 (2014-08-09)
--------------------------

- pem file is used by mockserver and required by scrapy bench (:commit:`5eddc68b63`)
- scrapy bench needs scrapy.tests* (:commit:`d6cb999`)

Scrapy 0.24.3 (2014-08-09)
--------------------------

- no need to waste travis-ci time on py3 for 0.24 (:commit:`8e080c1`)
- Update installation docs (:commit:`1d0c096`)
- There is a trove classifier for Scrapy framework! (:commit:`4c701d7`)
- update other places where w3lib version is mentioned (:commit:`d109c13`)
- Update w3lib requirement to 1.8.0 (:commit:`39d2ce5`)
- Use w3lib.html.replace_entities() (remove_entities() is deprecated) (:commit:`180d3ad`)
- set zip_safe=False (:commit:`a51ee8b`)
- do not ship tests package (:commit:`ee3b371`)
- scrapy.bat is not needed anymore (:commit:`c3861cf`)
- Modernize setup.py (:commit:`362e322`)
- headers can not handle non-string values (:commit:`94a5c65`)
- fix ftp test cases (:commit:`a274a7f`)
- The sum up of travis-ci builds are taking like 50min to complete (:commit:`ae1e2cc`)
- Update shell.rst typo (:commit:`e49c96a`)
- removes weird indentation in the shell results (:commit:`1ca489d`)
- improved explanations, clarified blog post as source, added link for XPath string functions in the spec (:commit:`65c8f05`)
- renamed UserTimeoutError and ServerTimeouterror #583 (:commit:`037f6ab`)
- adding some xpath tips to selectors docs (:commit:`2d103e0`)
- fix tests to account for https://github.com/scrapy/w3lib/pull/23 (:commit:`f8d366a`)
- get_func_args maximum recursion fix #728 (:commit:`81344ea`)
- Updated input/output processor example according to #560. (:commit:`f7c4ea8`)
- Fixed Python syntax in tutorial. (:commit:`db59ed9`)
- Add test case for tunneling proxy (:commit:`f090260`)
- Bugfix for leaking Proxy-Authorization header to remote host when using tunneling (:commit:`d8793af`)
- Extract links from XHTML documents with MIME-Type "application/xml" (:commit:`ed1f376`)
- Merge pull request #793 from roysc/patch-1 (:commit:`91a1106`)
- Fix typo in commands.rst (:commit:`743e1e2`)
- better testcase for settings.overrides.setdefault (:commit:`e22daaf`)
- Using CRLF as line marker according to http 1.1 definition (:commit:`5ec430b`)

Scrapy 0.24.2 (2014-07-08)
--------------------------

- Use a mutable mapping to proxy deprecated settings.overrides and settings.defaults attribute (:commit:`e5e8133`)
- there is not support for python3 yet (:commit:`3cd6146`)
- Update python compatible version set to Debian packages (:commit:`fa5d76b`)
- DOC fix formatting in release notes (:commit:`c6a9e20`)

Scrapy 0.24.1 (2014-06-27)
--------------------------

- Fix deprecated CrawlerSettings and increase backward compatibility with
  .defaults attribute (:commit:`8e3f20a`)


Scrapy 0.24.0 (2014-06-26)
--------------------------

Enhancements
~~~~~~~~~~~~

- Improve Scrapy top-level namespace (:gh:`494`, :gh:`684`)
- Add selector shortcuts to responses (:gh:`554`, :gh:`690`)
- Add new lxml based LinkExtractor to replace unmaintained SgmlLinkExtractor
  (:gh:`559`, :gh:`761`, :gh:`763`)
- Cleanup settings API - part of per-spider settings **GSoC project** (:gh:`737`)
- Add UTF8 encoding header to templates (:gh:`688`, :gh:`762`)
- Telnet console now binds to 127.0.0.1 by default (:gh:`699`)
- Update Debian/Ubuntu install instructions (:gh:`509`, :gh:`549`)
- Disable smart strings in lxml XPath evaluations (:gh:`535`)
- Restore filesystem based cache as default for http
  cache middleware (:gh:`541`, :gh:`500`, :gh:`571`)
- Expose current crawler in Scrapy shell (:gh:`557`)
- Improve testsuite comparing CSV and XML exporters (:gh:`570`)
- New ``offsite/filtered`` and ``offsite/domains`` stats (:gh:`566`)
- Support process_links as generator in CrawlSpider (:gh:`555`)
- Verbose logging and new stats counters for DupeFilter (:gh:`553`)
- Add a mimetype parameter to ``MailSender.send()`` (:gh:`602`)
- Generalize file pipeline log messages (:gh:`622`)
- Replace unencodeable codepoints with html entities in SGMLLinkExtractor (:gh:`565`)
- Converted SEP documents to rst format (:gh:`629`, :gh:`630`,
  :gh:`638`, :gh:`632`, :gh:`636`, :gh:`640`, :gh:`635`,
  :gh:`634`, :gh:`639`, :gh:`637`, :gh:`631`, :gh:`633`,
  :gh:`641`, :gh:`642`)
- Tests and docs for clickdata's nr index in FormRequest (:gh:`646`, :gh:`645`)
- Allow to disable a downloader handler just like any other component (:gh:`650`)
- Log when a request is discarded after too many redirections (:gh:`654`)
- Log error responses if they are not handled by spider callbacks
  (:gh:`612`, :gh:`656`)
- Add content-type check to http compression mw (:gh:`193`, :gh:`660`)
- Run pypy tests using latest pypi from ppa (:gh:`674`)
- Run test suite using pytest instead of trial (:gh:`679`)
- Build docs and check for dead links in tox environment (:gh:`687`)
- Make scrapy.version_info a tuple of integers (:gh:`681`, :gh:`692`)
- Infer exporter's output format from filename extensions
  (:gh:`546`, :gh:`659`, :gh:`760`)
- Support case-insensitive domains in ``url_is_from_any_domain()`` (:gh:`693`)
- Remove pep8 warnings in project and spider templates (:gh:`698`)
- Tests and docs for ``request_fingerprint`` function (:gh:`597`)
- Update SEP-19 for GSoC project ``per-spider settings`` (:gh:`705`)
- Set exit code to non-zero when contracts fails (:gh:`727`)
- Add a setting to control what class is instantiated as Downloader component
  (:gh:`738`)
- Pass response in ``item_dropped`` signal (:gh:`724`)
- Improve ``scrapy check`` contracts command (:gh:`733`, :gh:`752`)
- Document ``spider.closed()`` shortcut (:gh:`719`)
- Document ``request_scheduled`` signal (:gh:`746`)
- Add a note about reporting security issues (:gh:`697`)
- Add LevelDB http cache storage backend (:gh:`626`, :gh:`500`)
- Sort spider list output of ``scrapy list`` command (:gh:`742`)
- Multiple documentation enhancements and fixes
  (:gh:`575`, :gh:`587`, :gh:`590`, :gh:`596`, :gh:`610`,
  :gh:`617`, :gh:`618`, :gh:`627`, :gh:`613`, :gh:`643`,
  :gh:`654`, :gh:`675`, :gh:`663`, :gh:`711`, :gh:`714`)

Bugfixes
~~~~~~~~

- Encode unicode URL value when creating Links in RegexLinkExtractor (:gh:`561`)
- Ignore None values in ItemLoader processors (:gh:`556`)
- Fix link text when there is an inner tag in SGMLLinkExtractor and
  HtmlParserLinkExtractor (:gh:`485`, :gh:`574`)
- Fix wrong checks on subclassing of deprecated classes
  (:gh:`581`, :gh:`584`)
- Handle errors caused by inspect.stack() failures (:gh:`582`)
- Fix a reference to unexistent engine attribute (:gh:`593`, :gh:`594`)
- Fix dynamic itemclass example usage of type() (:gh:`603`)
- Use lucasdemarchi/codespell to fix typos (:gh:`628`)
- Fix default value of attrs argument in SgmlLinkExtractor to be tuple (:gh:`661`)
- Fix XXE flaw in sitemap reader (:gh:`676`)
- Fix engine to support filtered start requests (:gh:`707`)
- Fix offsite middleware case on urls with no hostnames (:gh:`745`)
- Testsuite doesn't require PIL anymore (:gh:`585`)


Scrapy 0.22.2 (released 2014-02-14)
-----------------------------------

- fix a reference to unexistent engine.slots. closes #593 (:commit:`13c099a`)
- downloaderMW doc typo (spiderMW doc copy remnant) (:commit:`8ae11bf`)
- Correct typos (:commit:`1346037`)

Scrapy 0.22.1 (released 2014-02-08)
-----------------------------------

- localhost666 can resolve under certain circumstances (:commit:`2ec2279`)
- test inspect.stack failure (:commit:`cc3eda3`)
- Handle cases when inspect.stack() fails (:commit:`8cb44f9`)
- Fix wrong checks on subclassing of deprecated classes. closes #581 (:commit:`46d98d6`)
- Docs: 4-space indent for final spider example (:commit:`13846de`)
- Fix HtmlParserLinkExtractor and tests after #485 merge (:commit:`368a946`)
- BaseSgmlLinkExtractor: Fixed the missing space when the link has an inner tag (:commit:`b566388`)
- BaseSgmlLinkExtractor: Added unit test of a link with an inner tag (:commit:`c1cb418`)
- BaseSgmlLinkExtractor: Fixed unknown_endtag() so that it only set current_link=None when the end tag match the opening tag (:commit:`7e4d627`)
- Fix tests for Travis-CI build (:commit:`76c7e20`)
- replace unencodeable codepoints with html entities. fixes #562 and #285 (:commit:`5f87b17`)
- RegexLinkExtractor: encode URL unicode value when creating Links (:commit:`d0ee545`)
- Updated the tutorial crawl output with latest output. (:commit:`8da65de`)
- Updated shell docs with the crawler reference and fixed the actual shell output. (:commit:`875b9ab`)
- PEP8 minor edits. (:commit:`f89efaf`)
- Expose current crawler in the Scrapy shell. (:commit:`5349cec`)
- Unused re import and PEP8 minor edits. (:commit:`387f414`)
- Ignore None's values when using the ItemLoader. (:commit:`0632546`)
- DOC Fixed HTTPCACHE_STORAGE typo in the default value which is now Filesystem instead Dbm. (:commit:`cde9a8c`)
- show Ubuntu setup instructions as literal code (:commit:`fb5c9c5`)
- Update Ubuntu installation instructions (:commit:`70fb105`)
- Merge pull request #550 from stray-leone/patch-1 (:commit:`6f70b6a`)
- modify the version of Scrapy Ubuntu package (:commit:`725900d`)
- fix 0.22.0 release date (:commit:`af0219a`)
- fix typos in news.rst and remove (not released yet) header (:commit:`b7f58f4`)

Scrapy 0.22.0 (released 2014-01-17)
-----------------------------------

Enhancements
~~~~~~~~~~~~

- [**Backward incompatible**] Switched HTTPCacheMiddleware backend to filesystem (:gh:`541`)
  To restore old backend set ``HTTPCACHE_STORAGE`` to ``scrapy.contrib.httpcache.DbmCacheStorage``
- Proxy \https:// urls using CONNECT method (:gh:`392`, :gh:`397`)
- Add a middleware to crawl ajax crawlable pages as defined by google (:gh:`343`)
- Rename scrapy.spider.BaseSpider to scrapy.spider.Spider (:gh:`510`, :gh:`519`)
- Selectors register EXSLT namespaces by default (:gh:`472`)
- Unify item loaders similar to selectors renaming (:gh:`461`)
- Make ``RFPDupeFilter`` class easily subclassable (:gh:`533`)
- Improve test coverage and forthcoming Python 3 support (:gh:`525`)
- Promote startup info on settings and middleware to INFO level (:gh:`520`)
- Support partials in ``get_func_args`` util (:gh:`506`, :gh:`504`)
- Allow running individual tests via tox (:gh:`503`)
- Update extensions ignored by link extractors (:gh:`498`)
- Add middleware methods to get files/images/thumbs paths (:gh:`490`)
- Improve offsite middleware tests (:gh:`478`)
- Add a way to skip default Referer header set by RefererMiddleware (:gh:`475`)
- Do not send ``x-gzip`` in default ``Accept-Encoding`` header (:gh:`469`)
- Support defining http error handling using settings (:gh:`466`)
- Use modern python idioms wherever you find legacies (:gh:`497`)
- Improve and correct documentation
  (:gh:`527`, :gh:`524`, :gh:`521`, :gh:`517`, :gh:`512`, :gh:`505`,
  :gh:`502`, :gh:`489`, :gh:`465`, :gh:`460`, :gh:`425`, :gh:`536`)

Fixes
~~~~~

- Update Selector class imports in CrawlSpider template (:gh:`484`)
- Fix unexistent reference to ``engine.slots`` (:gh:`464`)
- Do not try to call ``body_as_unicode()`` on a non-TextResponse instance (:gh:`462`)
- Warn when subclassing XPathItemLoader, previously it only warned on
  instantiation. (:gh:`523`)
- Warn when subclassing XPathSelector, previously it only warned on
  instantiation. (:gh:`537`)
- Multiple fixes to memory stats (:gh:`531`, :gh:`530`, :gh:`529`)
- Fix overriding url in ``FormRequest.from_response()`` (:gh:`507`)
- Fix tests runner under pip 1.5 (:gh:`513`)
- Fix logging error when spider name is unicode (:gh:`479`)

Scrapy 0.20.2 (released 2013-12-09)
-----------------------------------

- Update CrawlSpider Template with Selector changes (:commit:`6d1457d`)
- fix method name in tutorial. closes GH-480 (:commit:`b4fc359`

Scrapy 0.20.1 (released 2013-11-28)
-----------------------------------

- include_package_data is required to build wheels from published sources (:commit:`5ba1ad5`)
- process_parallel was leaking the failures on its internal deferreds.  closes #458 (:commit:`419a780`)

Scrapy 0.20.0 (released 2013-11-08)
-----------------------------------

Enhancements
~~~~~~~~~~~~

- New Selector's API including CSS selectors (:gh:`395` and :gh:`426`),
- Request/Response url/body attributes are now immutable
  (modifying them had been deprecated for a long time)
- :setting:`ITEM_PIPELINES` is now defined as a dict (instead of a list)
- Sitemap spider can fetch alternate URLs (:gh:`360`)
- ``Selector.remove_namespaces()`` now remove namespaces from element's attributes. (:gh:`416`)
- Paved the road for Python 3.3+ (:gh:`435`, :gh:`436`, :gh:`431`, :gh:`452`)
- New item exporter using native python types with nesting support (:gh:`366`)
- Tune HTTP1.1 pool size so it matches concurrency defined by settings (:commit:`b43b5f575`)
- scrapy.mail.MailSender now can connect over TLS or upgrade using STARTTLS (:gh:`327`)
- New FilesPipeline with functionality factored out from ImagesPipeline (:gh:`370`, :gh:`409`)
- Recommend Pillow instead of PIL for image handling (:gh:`317`)
- Added Debian packages for Ubuntu Quantal and Raring (:commit:`86230c0`)
- Mock server (used for tests) can listen for HTTPS requests (:gh:`410`)
- Remove multi spider support from multiple core components
  (:gh:`422`, :gh:`421`, :gh:`420`, :gh:`419`, :gh:`423`, :gh:`418`)
- Travis-CI now tests Scrapy changes against development versions of ``w3lib`` and ``queuelib`` python packages.
- Add pypy 2.1 to continuous integration tests (:commit:`ecfa7431`)
- Pylinted, pep8 and removed old-style exceptions from source (:gh:`430`, :gh:`432`)
- Use importlib for parametric imports (:gh:`445`)
- Handle a regression introduced in Python 2.7.5 that affects XmlItemExporter (:gh:`372`)
- Bugfix crawling shutdown on SIGINT (:gh:`450`)
- Do not submit ``reset`` type inputs in FormRequest.from_response (:commit:`b326b87`)
- Do not silence download errors when request errback raises an exception (:commit:`684cfc0`)

Bugfixes
~~~~~~~~

- Fix tests under Django 1.6 (:commit:`b6bed44c`)
- Lot of bugfixes to retry middleware under disconnections using HTTP 1.1 download handler
- Fix inconsistencies among Twisted releases (:gh:`406`)
- Fix Scrapy shell bugs (:gh:`418`, :gh:`407`)
- Fix invalid variable name in setup.py (:gh:`429`)
- Fix tutorial references (:gh:`387`)
- Improve request-response docs (:gh:`391`)
- Improve best practices docs (:gh:`399`, :gh:`400`, :gh:`401`, :gh:`402`)
- Improve django integration docs (:gh:`404`)
- Document ``bindaddress`` request meta (:commit:`37c24e01d7`)
- Improve ``Request`` class documentation (:gh:`226`)

Other
~~~~~

- Dropped Python 2.6 support (:gh:`448`)
- Add :doc:`cssselect <cssselect:index>` python package as install dependency
- Drop libxml2 and multi selector's backend support, `lxml`_ is required from now on.
- Minimum Twisted version increased to 10.0.0, dropped Twisted 8.0 support.
- Running test suite now requires ``mock`` python library (:gh:`390`)


Thanks
~~~~~~

Thanks to everyone who contribute to this release!

List of contributors sorted by number of commits::

     69 Daniel Graña <dangra@...>
     37 Pablo Hoffman <pablo@...>
     13 Mikhail Korobov <kmike84@...>
      9 Alex Cepoi <alex.cepoi@...>
      9 alexanderlukanin13 <alexander.lukanin.13@...>
      8 Rolando Espinoza La fuente <darkrho@...>
      8 Lukasz Biedrycki <lukasz.biedrycki@...>
      6 Nicolas Ramirez <nramirez.uy@...>
      3 Paul Tremberth <paul.tremberth@...>
      2 Martin Olveyra <molveyra@...>
      2 Stefan <misc@...>
      2 Rolando Espinoza <darkrho@...>
      2 Loren Davie <loren@...>
      2 irgmedeiros <irgmedeiros@...>
      1 Stefan Koch <taikano@...>
      1 Stefan <cct@...>
      1 scraperdragon <dragon@...>
      1 Kumara Tharmalingam <ktharmal@...>
      1 Francesco Piccinno <stack.box@...>
      1 Marcos Campal <duendex@...>
      1 Dragon Dave <dragon@...>
      1 Capi Etheriel <barraponto@...>
      1 cacovsky <amarquesferraz@...>
      1 Berend Iwema <berend@...>

Scrapy 0.18.4 (released 2013-10-10)
-----------------------------------

- IPython refuses to update the namespace. fix #396 (:commit:`3d32c4f`)
- Fix AlreadyCalledError replacing a request in shell command. closes #407 (:commit:`b1d8919`)
- Fix ``start_requests()`` laziness and early hangs (:commit:`89faf52`)

Scrapy 0.18.3 (released 2013-10-03)
-----------------------------------

- fix regression on lazy evaluation of start requests (:commit:`12693a5`)
- forms: do not submit reset inputs (:commit:`e429f63`)
- increase unittest timeouts to decrease travis false positive failures (:commit:`912202e`)
- backport master fixes to json exporter (:commit:`cfc2d46`)
- Fix permission and set umask before generating sdist tarball (:commit:`06149e0`)

Scrapy 0.18.2 (released 2013-09-03)
-----------------------------------

- Backport ``scrapy check`` command fixes and backward compatible multi
  crawler process(:gh:`339`)

Scrapy 0.18.1 (released 2013-08-27)
-----------------------------------

- remove extra import added by cherry picked changes (:commit:`d20304e`)
- fix crawling tests under twisted pre 11.0.0 (:commit:`1994f38`)
- py26 can not format zero length fields {} (:commit:`abf756f`)
- test PotentiaDataLoss errors on unbound responses (:commit:`b15470d`)
- Treat responses without content-length or Transfer-Encoding as good responses (:commit:`c4bf324`)
- do no include ResponseFailed if http11 handler is not enabled (:commit:`6cbe684`)
- New HTTP client wraps connection lost in ResponseFailed exception. fix #373 (:commit:`1a20bba`)
- limit travis-ci build matrix (:commit:`3b01bb8`)
- Merge pull request #375 from peterarenot/patch-1 (:commit:`fa766d7`)
- Fixed so it refers to the correct folder (:commit:`3283809`)
- added Quantal & Raring to support Ubuntu releases (:commit:`1411923`)
- fix retry middleware which didn't retry certain connection errors after the upgrade to http1 client, closes GH-373 (:commit:`bb35ed0`)
- fix XmlItemExporter in Python 2.7.4 and 2.7.5 (:commit:`de3e451`)
- minor updates to 0.18 release notes (:commit:`c45e5f1`)
- fix contributors list format (:commit:`0b60031`)

Scrapy 0.18.0 (released 2013-08-09)
-----------------------------------

- Lot of improvements to testsuite run using Tox, including a way to test on pypi
- Handle GET parameters for AJAX crawlable urls (:commit:`3fe2a32`)
- Use lxml recover option to parse sitemaps (:gh:`347`)
- Bugfix cookie merging by hostname and not by netloc (:gh:`352`)
- Support disabling ``HttpCompressionMiddleware`` using a flag setting (:gh:`359`)
- Support xml namespaces using ``iternodes`` parser in ``XMLFeedSpider`` (:gh:`12`)
- Support ``dont_cache`` request meta flag (:gh:`19`)
- Bugfix ``scrapy.utils.gz.gunzip`` broken by changes in python 2.7.4 (:commit:`4dc76e`)
- Bugfix url encoding on ``SgmlLinkExtractor`` (:gh:`24`)
- Bugfix ``TakeFirst`` processor shouldn't discard zero (0) value (:gh:`59`)
- Support nested items in xml exporter (:gh:`66`)
- Improve cookies handling performance (:gh:`77`)
- Log dupe filtered requests once (:gh:`105`)
- Split redirection middleware into status and meta based middlewares (:gh:`78`)
- Use HTTP1.1 as default downloader handler (:gh:`109` and :gh:`318`)
- Support xpath form selection on ``FormRequest.from_response`` (:gh:`185`)
- Bugfix unicode decoding error on ``SgmlLinkExtractor`` (:gh:`199`)
- Bugfix signal dispatching on pypi interpreter (:gh:`205`)
- Improve request delay and concurrency handling (:gh:`206`)
- Add RFC2616 cache policy to ``HttpCacheMiddleware`` (:gh:`212`)
- Allow customization of messages logged by engine (:gh:`214`)
- Multiples improvements to ``DjangoItem`` (:gh:`217`, :gh:`218`, :gh:`221`)
- Extend Scrapy commands using setuptools entry points (:gh:`260`)
- Allow spider ``allowed_domains`` value to be set/tuple (:gh:`261`)
- Support ``settings.getdict`` (:gh:`269`)
- Simplify internal ``scrapy.core.scraper`` slot handling (:gh:`271`)
- Added ``Item.copy`` (:gh:`290`)
- Collect idle downloader slots (:gh:`297`)
- Add ``ftp://`` scheme downloader handler (:gh:`329`)
- Added downloader benchmark webserver and spider tools :ref:`benchmarking`
- Moved persistent (on disk) queues to a separate project (queuelib_) which Scrapy now depends on
- Add Scrapy commands using external libraries (:gh:`260`)
- Added ``--pdb`` option to ``scrapy`` command line tool
- Added :meth:`XPathSelector.remove_namespaces <scrapy.Selector.remove_namespaces>` which allows to remove all namespaces from XML documents for convenience (to work with namespace-less XPaths). Documented in :ref:`topics-selectors`.
- Several improvements to spider contracts
- New default middleware named MetaRefreshMiddleware that handles meta-refresh html tag redirections,
- MetaRefreshMiddleware and RedirectMiddleware have different priorities to address #62
- added from_crawler method to spiders
- added system tests with mock server
- more improvements to macOS compatibility (thanks Alex Cepoi)
- several more cleanups to singletons and multi-spider support (thanks Nicolas Ramirez)
- support custom download slots
- added --spider option to "shell" command.
- log overridden settings when Scrapy starts

Thanks to everyone who contribute to this release. Here is a list of
contributors sorted by number of commits::

    130 Pablo Hoffman <pablo@...>
     97 Daniel Graña <dangra@...>
     20 Nicolás Ramírez <nramirez.uy@...>
     13 Mikhail Korobov <kmike84@...>
     12 Pedro Faustino <pedrobandim@...>
     11 Steven Almeroth <sroth77@...>
      5 Rolando Espinoza La fuente <darkrho@...>
      4 Michal Danilak <mimino.coder@...>
      4 Alex Cepoi <alex.cepoi@...>
      4 Alexandr N Zamaraev (aka tonal) <tonal@...>
      3 paul <paul.tremberth@...>
      3 Martin Olveyra <molveyra@...>
      3 Jordi Llonch <llonchj@...>
      3 arijitchakraborty <myself.arijit@...>
      2 Shane Evans <shane.evans@...>
      2 joehillen <joehillen@...>
      2 Hart <HartSimha@...>
      2 Dan <ellisd23@...>
      1 Zuhao Wan <wanzuhao@...>
      1 whodatninja <blake@...>
      1 vkrest <v.krestiannykov@...>
      1 tpeng <pengtaoo@...>
      1 Tom Mortimer-Jones <tom@...>
      1 Rocio Aramberri <roschegel@...>
      1 Pedro <pedro@...>
      1 notsobad <wangxiaohugg@...>
      1 Natan L <kuyanatan.nlao@...>
      1 Mark Grey <mark.grey@...>
      1 Luan <luanpab@...>
      1 Libor Nenadál <libor.nenadal@...>
      1 Juan M Uys <opyate@...>
      1 Jonas Brunsgaard <jonas.brunsgaard@...>
      1 Ilya Baryshev <baryshev@...>
      1 Hasnain Lakhani <m.hasnain.lakhani@...>
      1 Emanuel Schorsch <emschorsch@...>
      1 Chris Tilden <chris.tilden@...>
      1 Capi Etheriel <barraponto@...>
      1 cacovsky <amarquesferraz@...>
      1 Berend Iwema <berend@...>


Scrapy 0.16.5 (released 2013-05-30)
-----------------------------------

- obey request method when Scrapy deploy is redirected to a new endpoint (:commit:`8c4fcee`)
- fix inaccurate downloader middleware documentation. refs #280 (:commit:`40667cb`)
- doc: remove links to diveintopython.org, which is no longer available. closes #246 (:commit:`bd58bfa`)
- Find form nodes in invalid html5 documents (:commit:`e3d6945`)
- Fix typo labeling attrs type bool instead of list (:commit:`a274276`)

Scrapy 0.16.4 (released 2013-01-23)
-----------------------------------

- fixes spelling errors in documentation (:commit:`6d2b3aa`)
- add doc about disabling an extension. refs #132 (:commit:`c90de33`)
- Fixed error message formatting. log.err() doesn't support cool formatting and when error occurred, the message was:    "ERROR: Error processing %(item)s" (:commit:`c16150c`)
- lint and improve images pipeline error logging (:commit:`56b45fc`)
- fixed doc typos (:commit:`243be84`)
- add documentation topics: Broad Crawls & Common Practices (:commit:`1fbb715`)
- fix bug in Scrapy parse command when spider is not specified explicitly. closes #209 (:commit:`c72e682`)
- Update docs/topics/commands.rst (:commit:`28eac7a`)

Scrapy 0.16.3 (released 2012-12-07)
-----------------------------------

- Remove concurrency limitation when using download delays and still ensure inter-request delays are enforced (:commit:`487b9b5`)
- add error details when image pipeline fails (:commit:`8232569`)
- improve macOS compatibility (:commit:`8dcf8aa`)
- setup.py: use README.rst to populate long_description (:commit:`7b5310d`)
- doc: removed obsolete references to ClientForm (:commit:`80f9bb6`)
- correct docs for default storage backend (:commit:`2aa491b`)
- doc: removed broken proxyhub link from FAQ (:commit:`bdf61c4`)
- Fixed docs typo in SpiderOpenCloseLogging example (:commit:`7184094`)


Scrapy 0.16.2 (released 2012-11-09)
-----------------------------------

- Scrapy contracts: python2.6 compat (:commit:`a4a9199`)
- Scrapy contracts verbose option (:commit:`ec41673`)
- proper unittest-like output for Scrapy contracts (:commit:`86635e4`)
- added open_in_browser to debugging doc (:commit:`c9b690d`)
- removed reference to global Scrapy stats from settings doc (:commit:`dd55067`)
- Fix SpiderState bug in Windows platforms (:commit:`58998f4`)


Scrapy 0.16.1 (released 2012-10-26)
-----------------------------------

- fixed LogStats extension, which got broken after a wrong merge before the 0.16 release (:commit:`8c780fd`)
- better backward compatibility for scrapy.conf.settings (:commit:`3403089`)
- extended documentation on how to access crawler stats from extensions (:commit:`c4da0b5`)
- removed .hgtags (no longer needed now that Scrapy uses git) (:commit:`d52c188`)
- fix dashes under rst headers (:commit:`fa4f7f9`)
- set release date for 0.16.0 in news (:commit:`e292246`)


Scrapy 0.16.0 (released 2012-10-18)
-----------------------------------

Scrapy changes:

- added :ref:`topics-contracts`, a mechanism for testing spiders in a formal/reproducible way
- added options ``-o`` and ``-t`` to the :command:`runspider` command
- documented :doc:`topics/autothrottle` and added to extensions installed by default. You still need to enable it with :setting:`AUTOTHROTTLE_ENABLED`
- major Stats Collection refactoring: removed separation of global/per-spider stats, removed stats-related signals (``stats_spider_opened``, etc). Stats are much simpler now, backward compatibility is kept on the Stats Collector API and signals.
- added a ``process_start_requests()`` method to spider middlewares
- dropped Signals singleton. Signals should now be accessed through the Crawler.signals attribute. See the signals documentation for more info.
- dropped Stats Collector singleton. Stats can now be accessed through the Crawler.stats attribute. See the stats collection documentation for more info.
- documented :ref:`topics-api`
- ``lxml`` is now the default selectors backend instead of ``libxml2``
- ported FormRequest.from_response() to use `lxml`_ instead of `ClientForm`_
- removed modules: ``scrapy.xlib.BeautifulSoup`` and ``scrapy.xlib.ClientForm``
- SitemapSpider: added support for sitemap urls ending in .xml and .xml.gz, even if they advertise a wrong content type (:commit:`10ed28b`)
- StackTraceDump extension: also dump trackref live references (:commit:`fe2ce93`)
- nested items now fully supported in JSON and JSONLines exporters
- added :reqmeta:`cookiejar` Request meta key to support multiple cookie sessions per spider
- decoupled encoding detection code to `w3lib.encoding`_, and ported Scrapy code to use that module
- dropped support for Python 2.5. See https://www.zyte.com/blog/scrapy-0-15-dropping-support-for-python-2-5/
- dropped support for Twisted 2.5
- added :setting:`REFERER_ENABLED` setting, to control referer middleware
- changed default user agent to: ``Scrapy/VERSION (+http://scrapy.org)``
- removed (undocumented) ``HTMLImageLinkExtractor`` class from ``scrapy.contrib.linkextractors.image``
- removed per-spider settings (to be replaced by instantiating multiple crawler objects)
- ``USER_AGENT`` spider attribute will no longer work, use ``user_agent`` attribute instead
- ``DOWNLOAD_TIMEOUT`` spider attribute will no longer work, use ``download_timeout`` attribute instead
- removed ``ENCODING_ALIASES`` setting, as encoding auto-detection has been moved to the `w3lib`_ library
- promoted :ref:`topics-djangoitem` to main contrib
- LogFormatter method now return dicts(instead of strings) to support lazy formatting (:gh:`164`, :commit:`dcef7b0`)
- downloader handlers (:setting:`DOWNLOAD_HANDLERS` setting) now receive settings as the first argument of the ``__init__`` method
- replaced memory usage accounting with (more portable) `resource`_ module, removed ``scrapy.utils.memory`` module
- removed signal: ``scrapy.mail.mail_sent``
- removed ``TRACK_REFS`` setting, now :ref:`trackrefs <topics-leaks-trackrefs>` is always enabled
- DBM is now the default storage backend for HTTP cache middleware
- number of log messages (per level) are now tracked through Scrapy stats (stat name: ``log_count/LEVEL``)
- number received responses are now tracked through Scrapy stats (stat name: ``response_received_count``)
- removed ``scrapy.log.started`` attribute

Scrapy 0.14.4
-------------

- added precise to supported Ubuntu distros (:commit:`b7e46df`)
- fixed bug in json-rpc webservice reported in https://groups.google.com/forum/#!topic/scrapy-users/qgVBmFybNAQ/discussion. also removed no longer supported 'run' command from extras/scrapy-ws.py (:commit:`340fbdb`)
- meta tag attributes for content-type http equiv can be in any order. #123 (:commit:`0cb68af`)
- replace "import Image" by more standard "from PIL import Image". closes #88 (:commit:`4d17048`)
- return trial status as bin/runtests.sh exit value. #118 (:commit:`b7b2e7f`)

Scrapy 0.14.3
-------------

- forgot to include pydispatch license. #118 (:commit:`fd85f9c`)
- include egg files used by testsuite in source distribution. #118 (:commit:`c897793`)
- update docstring in project template to avoid confusion with genspider command, which may be considered as an advanced feature. refs #107 (:commit:`2548dcc`)
- added note to docs/topics/firebug.rst about google directory being shut down (:commit:`668e352`)
- don't discard slot when empty, just save in another dict in order to recycle if needed again. (:commit:`8e9f607`)
- do not fail handling unicode xpaths in libxml2 backed selectors (:commit:`b830e95`)
- fixed minor mistake in Request objects documentation (:commit:`bf3c9ee`)
- fixed minor defect in link extractors documentation (:commit:`ba14f38`)
- removed some obsolete remaining code related to sqlite support in Scrapy (:commit:`0665175`)

Scrapy 0.14.2
-------------

- move buffer pointing to start of file before computing checksum. refs #92 (:commit:`6a5bef2`)
- Compute image checksum before persisting images. closes #92 (:commit:`9817df1`)
- remove leaking references in cached failures (:commit:`673a120`)
- fixed bug in MemoryUsage extension: get_engine_status() takes exactly 1 argument (0 given) (:commit:`11133e9`)
- fixed struct.error on http compression middleware. closes #87 (:commit:`1423140`)
- ajax crawling wasn't expanding for unicode urls (:commit:`0de3fb4`)
- Catch ``start_requests()`` iterator errors. refs #83 (:commit:`454a21d`)
- Speed-up libxml2 XPathSelector (:commit:`2fbd662`)
- updated versioning doc according to recent changes (:commit:`0a070f5`)
- scrapyd: fixed documentation link (:commit:`2b4e4c3`)
- extras/makedeb.py: no longer obtaining version from git (:commit:`caffe0e`)

Scrapy 0.14.1
-------------

- extras/makedeb.py: no longer obtaining version from git (:commit:`caffe0e`)
- bumped version to 0.14.1 (:commit:`6cb9e1c`)
- fixed reference to tutorial directory (:commit:`4b86bd6`)
- doc: removed duplicated callback argument from Request.replace() (:commit:`1aeccdd`)
- fixed formatting of scrapyd doc (:commit:`8bf19e6`)
- Dump stacks for all running threads and fix engine status dumped by StackTraceDump extension (:commit:`14a8e6e`)
- added comment about why we disable ssl on boto images upload (:commit:`5223575`)
- SSL handshaking hangs when doing too many parallel connections to S3 (:commit:`63d583d`)
- change tutorial to follow changes on dmoz site (:commit:`bcb3198`)
- Avoid _disconnectedDeferred AttributeError exception in Twisted>=11.1.0 (:commit:`98f3f87`)
- allow spider to set autothrottle max concurrency (:commit:`175a4b5`)

Scrapy 0.14
-----------

New features and settings
~~~~~~~~~~~~~~~~~~~~~~~~~

- Support for AJAX crawlable urls
- New persistent scheduler that stores requests on disk, allowing to suspend and resume crawls (:rev:`2737`)
- added ``-o`` option to ``scrapy crawl``, a shortcut for dumping scraped items into a file (or standard output using ``-``)
- Added support for passing custom settings to Scrapyd ``schedule.json`` api (:rev:`2779`, :rev:`2783`)
- New ``ChunkedTransferMiddleware`` (enabled by default) to support `chunked transfer encoding`_ (:rev:`2769`)
- Add boto 2.0 support for S3 downloader handler (:rev:`2763`)
- Added `marshal`_ to formats supported by feed exports (:rev:`2744`)
- In request errbacks, offending requests are now received in ``failure.request`` attribute (:rev:`2738`)
- Big downloader refactoring to support per domain/ip concurrency limits (:rev:`2732`)
   - ``CONCURRENT_REQUESTS_PER_SPIDER`` setting has been deprecated and replaced by:
      - :setting:`CONCURRENT_REQUESTS`, :setting:`CONCURRENT_REQUESTS_PER_DOMAIN`, ``CONCURRENT_REQUESTS_PER_IP``
   - check the documentation for more details
- Added builtin caching DNS resolver (:rev:`2728`)
- Moved Amazon AWS-related components/extensions (SQS spider queue, SimpleDB stats collector) to a separate project: [scaws](https://github.com/scrapinghub/scaws) (:rev:`2706`, :rev:`2714`)
- Moved spider queues to scrapyd: ``scrapy.spiderqueue`` -> ``scrapyd.spiderqueue`` (:rev:`2708`)
- Moved sqlite utils to scrapyd: ``scrapy.utils.sqlite`` -> ``scrapyd.sqlite`` (:rev:`2781`)
- Real support for returning iterators on ``start_requests()`` method. The iterator is now consumed during the crawl when the spider is getting idle (:rev:`2704`)
- Added :setting:`REDIRECT_ENABLED` setting to quickly enable/disable the redirect middleware (:rev:`2697`)
- Added :setting:`RETRY_ENABLED` setting to quickly enable/disable the retry middleware (:rev:`2694`)
- Added ``CloseSpider`` exception to manually close spiders (:rev:`2691`)
- Improved encoding detection by adding support for HTML5 meta charset declaration (:rev:`2690`)
- Refactored close spider behavior to wait for all downloads to finish and be processed by spiders, before closing the spider (:rev:`2688`)
- Added ``SitemapSpider`` (see documentation in Spiders page) (:rev:`2658`)
- Added ``LogStats`` extension for periodically logging basic stats (like crawled pages and scraped items) (:rev:`2657`)
- Make handling of gzipped responses more robust (#319, :rev:`2643`). Now Scrapy will try and decompress as much as possible from a gzipped response, instead of failing with an ``IOError``.
- Simplified !MemoryDebugger extension to use stats for dumping memory debugging info (:rev:`2639`)
- Added new command to edit spiders: ``scrapy edit`` (:rev:`2636`) and ``-e`` flag to ``genspider`` command that uses it (:rev:`2653`)
- Changed default representation of items to pretty-printed dicts. (:rev:`2631`). This improves default logging by making log more readable in the default case, for both Scraped and Dropped lines.
- Added :signal:`spider_error` signal (:rev:`2628`)
- Added :setting:`COOKIES_ENABLED` setting (:rev:`2625`)
- Stats are now dumped to Scrapy log (default value of :setting:`STATS_DUMP` setting has been changed to ``True``). This is to make Scrapy users more aware of Scrapy stats and the data that is collected there.
- Added support for dynamically adjusting download delay and maximum concurrent requests (:rev:`2599`)
- Added new DBM HTTP cache storage backend (:rev:`2576`)
- Added ``listjobs.json`` API to Scrapyd (:rev:`2571`)
- ``CsvItemExporter``: added ``join_multivalued`` parameter (:rev:`2578`)
- Added namespace support to ``xmliter_lxml`` (:rev:`2552`)
- Improved cookies middleware by making ``COOKIES_DEBUG`` nicer and documenting it (:rev:`2579`)
- Several improvements to Scrapyd and Link extractors

Code rearranged and removed
~~~~~~~~~~~~~~~~~~~~~~~~~~~

- Merged item passed and item scraped concepts, as they have often proved confusing in the past. This means: (:rev:`2630`)
   - original item_scraped signal was removed
   - original item_passed signal was renamed to item_scraped
   - old log lines ``Scraped Item...`` were removed
   - old log lines ``Passed Item...`` were renamed to ``Scraped Item...`` lines and downgraded to ``DEBUG`` level
- Reduced Scrapy codebase by striping part of Scrapy code into two new libraries:
   - `w3lib`_ (several functions from ``scrapy.utils.{http,markup,multipart,response,url}``, done in :rev:`2584`)
   - `scrapely`_ (was ``scrapy.contrib.ibl``, done in :rev:`2586`)
- Removed unused function: ``scrapy.utils.request.request_info()`` (:rev:`2577`)
- Removed googledir project from ``examples/googledir``. There's now a new example project called ``dirbot`` available on GitHub: https://github.com/scrapy/dirbot
- Removed support for default field values in Scrapy items (:rev:`2616`)
- Removed experimental crawlspider v2 (:rev:`2632`)
- Removed scheduler middleware to simplify architecture. Duplicates filter is now done in the scheduler itself, using the same dupe filtering class as before (``DUPEFILTER_CLASS`` setting) (:rev:`2640`)
- Removed support for passing urls to ``scrapy crawl`` command (use ``scrapy parse`` instead) (:rev:`2704`)
- Removed deprecated Execution Queue (:rev:`2704`)
- Removed (undocumented) spider context extension (from scrapy.contrib.spidercontext) (:rev:`2780`)
- removed ``CONCURRENT_SPIDERS`` setting (use scrapyd maxproc instead) (:rev:`2789`)
- Renamed attributes of core components: downloader.sites -> downloader.slots, scraper.sites -> scraper.slots (:rev:`2717`, :rev:`2718`)
- Renamed setting ``CLOSESPIDER_ITEMPASSED`` to :setting:`CLOSESPIDER_ITEMCOUNT` (:rev:`2655`). Backward compatibility kept.

Scrapy 0.12
-----------

The numbers like #NNN reference tickets in the old issue tracker (Trac) which is no longer available.

New features and improvements
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- Passed item is now sent in the ``item`` argument of the :signal:`item_passed
  <item_scraped>` (#273)
- Added verbose option to ``scrapy version`` command, useful for bug reports (#298)
- HTTP cache now stored by default in the project data dir (#279)
- Added project data storage directory (#276, #277)
- Documented file structure of Scrapy projects (see command-line tool doc)
- New lxml backend for XPath selectors (#147)
- Per-spider settings (#245)
- Support exit codes to signal errors in Scrapy commands (#248)
- Added ``-c`` argument to ``scrapy shell`` command
- Made ``libxml2`` optional (#260)
- New ``deploy`` command (#261)
- Added :setting:`CLOSESPIDER_PAGECOUNT` setting (#253)
- Added :setting:`CLOSESPIDER_ERRORCOUNT` setting (#254)

Scrapyd changes
~~~~~~~~~~~~~~~

- Scrapyd now uses one process per spider
- It stores one log file per spider run, and rotate them keeping the latest 5 logs per spider (by default)
- A minimal web ui was added, available at http://localhost:6800 by default
- There is now a ``scrapy server`` command to start a Scrapyd server of the current project

Changes to settings
~~~~~~~~~~~~~~~~~~~

- added ``HTTPCACHE_ENABLED`` setting (False by default) to enable HTTP cache middleware
- changed ``HTTPCACHE_EXPIRATION_SECS`` semantics: now zero means "never expire".

Deprecated/obsoleted functionality
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- Deprecated ``runserver`` command in favor of ``server`` command which starts a Scrapyd server. See also: Scrapyd changes
- Deprecated ``queue`` command in favor of using Scrapyd ``schedule.json`` API. See also: Scrapyd changes
- Removed the !LxmlItemLoader (experimental contrib which never graduated to main contrib)

Scrapy 0.10
-----------

The numbers like #NNN reference tickets in the old issue tracker (Trac) which is no longer available.

New features and improvements
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- New Scrapy service called ``scrapyd`` for deploying Scrapy crawlers in production (#218) (documentation available)
- Simplified Images pipeline usage which doesn't require subclassing your own images pipeline now (#217)
- Scrapy shell now shows the Scrapy log by default (#206)
- Refactored execution queue in a common base code and pluggable backends called "spider queues" (#220)
- New persistent spider queue (based on SQLite) (#198), available by default, which allows to start Scrapy in server mode and then schedule spiders to run.
- Added documentation for Scrapy command-line tool and all its available sub-commands. (documentation available)
- Feed exporters with pluggable backends (#197) (documentation available)
- Deferred signals (#193)
- Added two new methods to item pipeline open_spider(), close_spider() with deferred support (#195)
- Support for overriding default request headers per spider (#181)
- Replaced default Spider Manager with one with similar functionality but not depending on Twisted Plugins (#186)
- Split Debian package into two packages - the library and the service (#187)
- Scrapy log refactoring (#188)
- New extension for keeping persistent spider contexts among different runs (#203)
- Added ``dont_redirect`` request.meta key for avoiding redirects (#233)
- Added ``dont_retry`` request.meta key for avoiding retries (#234)

Command-line tool changes
~~~~~~~~~~~~~~~~~~~~~~~~~

- New ``scrapy`` command which replaces the old ``scrapy-ctl.py`` (#199)
  - there is only one global ``scrapy`` command now, instead of one ``scrapy-ctl.py`` per project
  - Added ``scrapy.bat`` script for running more conveniently from Windows
- Added bash completion to command-line tool (#210)
- Renamed command ``start`` to ``runserver`` (#209)

API changes
~~~~~~~~~~~

- ``url`` and ``body`` attributes of Request objects are now read-only (#230)
- ``Request.copy()`` and ``Request.replace()`` now also copies their ``callback`` and ``errback`` attributes (#231)
- Removed ``UrlFilterMiddleware`` from ``scrapy.contrib`` (already disabled by default)
- Offsite middleware doesn't filter out any request coming from a spider that doesn't have a allowed_domains attribute (#225)
- Removed Spider Manager ``load()`` method. Now spiders are loaded in the ``__init__`` method itself.
- Changes to Scrapy Manager (now called "Crawler"):
   - ``scrapy.core.manager.ScrapyManager`` class renamed to ``scrapy.crawler.Crawler``
   - ``scrapy.core.manager.scrapymanager`` singleton moved to ``scrapy.project.crawler``
- Moved module: ``scrapy.contrib.spidermanager`` to ``scrapy.spidermanager``
- Spider Manager singleton moved from ``scrapy.spider.spiders`` to the ``spiders`` attribute of ``scrapy.project.crawler`` singleton.
- moved Stats Collector classes: (#204)
   - ``scrapy.stats.collector.StatsCollector`` to ``scrapy.statscol.StatsCollector``
   - ``scrapy.stats.collector.SimpledbStatsCollector`` to ``scrapy.contrib.statscol.SimpledbStatsCollector``
- default per-command settings are now specified in the ``default_settings`` attribute of command object class (#201)
- changed arguments of Item pipeline ``process_item()`` method from ``(spider, item)`` to ``(item, spider)``
   - backward compatibility kept (with deprecation warning)
- moved ``scrapy.core.signals`` module to ``scrapy.signals``
   - backward compatibility kept (with deprecation warning)
- moved ``scrapy.core.exceptions`` module to ``scrapy.exceptions``
   - backward compatibility kept (with deprecation warning)
- added ``handles_request()`` class method to ``BaseSpider``
- dropped ``scrapy.log.exc()`` function (use ``scrapy.log.err()`` instead)
- dropped ``component`` argument of ``scrapy.log.msg()`` function
- dropped ``scrapy.log.log_level`` attribute
- Added ``from_settings()`` class methods to Spider Manager, and Item Pipeline Manager

Changes to settings
~~~~~~~~~~~~~~~~~~~

- Added ``HTTPCACHE_IGNORE_SCHEMES`` setting to ignore certain schemes on !HttpCacheMiddleware (#225)
- Added ``SPIDER_QUEUE_CLASS`` setting which defines the spider queue to use (#220)
- Added ``KEEP_ALIVE`` setting (#220)
- Removed ``SERVICE_QUEUE`` setting (#220)
- Removed ``COMMANDS_SETTINGS_MODULE`` setting (#201)
- Renamed ``REQUEST_HANDLERS`` to ``DOWNLOAD_HANDLERS`` and make download handlers classes (instead of functions)

Scrapy 0.9
----------

The numbers like #NNN reference tickets in the old issue tracker (Trac) which is no longer available.

New features and improvements
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- Added SMTP-AUTH support to scrapy.mail
- New settings added: ``MAIL_USER``, ``MAIL_PASS`` (:rev:`2065` | #149)
- Added new scrapy-ctl view command - To view URL in the browser, as seen by Scrapy (:rev:`2039`)
- Added web service for controlling Scrapy process (this also deprecates the web console. (:rev:`2053` | #167)
- Support for running Scrapy as a service, for production systems (:rev:`1988`, :rev:`2054`, :rev:`2055`, :rev:`2056`, :rev:`2057` | #168)
- Added wrapper induction library (documentation only available in source code for now). (:rev:`2011`)
- Simplified and improved response encoding support (:rev:`1961`, :rev:`1969`)
- Added ``LOG_ENCODING`` setting (:rev:`1956`, documentation available)
- Added ``RANDOMIZE_DOWNLOAD_DELAY`` setting (enabled by default) (:rev:`1923`, doc available)
- ``MailSender`` is no longer IO-blocking (:rev:`1955` | #146)
- Linkextractors and new Crawlspider now handle relative base tag urls (:rev:`1960` | #148)
- Several improvements to Item Loaders and processors (:rev:`2022`, :rev:`2023`, :rev:`2024`, :rev:`2025`, :rev:`2026`, :rev:`2027`, :rev:`2028`, :rev:`2029`, :rev:`2030`)
- Added support for adding variables to telnet console (:rev:`2047` | #165)
- Support for requests without callbacks (:rev:`2050` | #166)

API changes
~~~~~~~~~~~

- Change ``Spider.domain_name`` to ``Spider.name`` (SEP-012, :rev:`1975`)
- ``Response.encoding`` is now the detected encoding (:rev:`1961`)
- ``HttpErrorMiddleware`` now returns None or raises an exception (:rev:`2006` | #157)
- ``scrapy.command`` modules relocation (:rev:`2035`, :rev:`2036`, :rev:`2037`)
- Added ``ExecutionQueue`` for feeding spiders to scrape (:rev:`2034`)
- Removed ``ExecutionEngine`` singleton (:rev:`2039`)
- Ported ``S3ImagesStore`` (images pipeline) to use boto and threads (:rev:`2033`)
- Moved module: ``scrapy.management.telnet`` to ``scrapy.telnet`` (:rev:`2047`)

Changes to default settings
~~~~~~~~~~~~~~~~~~~~~~~~~~~

- Changed default ``SCHEDULER_ORDER`` to ``DFO`` (:rev:`1939`)

Scrapy 0.8
----------

The numbers like #NNN reference tickets in the old issue tracker (Trac) which is no longer available.

New features
~~~~~~~~~~~~

- Added DEFAULT_RESPONSE_ENCODING setting (:rev:`1809`)
- Added ``dont_click`` argument to ``FormRequest.from_response()`` method (:rev:`1813`, :rev:`1816`)
- Added ``clickdata`` argument to ``FormRequest.from_response()`` method (:rev:`1802`, :rev:`1803`)
- Added support for HTTP proxies (``HttpProxyMiddleware``) (:rev:`1781`, :rev:`1785`)
- Offsite spider middleware now logs messages when filtering out requests (:rev:`1841`)

Backward-incompatible changes
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- Changed ``scrapy.utils.response.get_meta_refresh()`` signature (:rev:`1804`)
- Removed deprecated ``scrapy.item.ScrapedItem`` class - use ``scrapy.item.Item instead`` (:rev:`1838`)
- Removed deprecated ``scrapy.xpath`` module - use ``scrapy.selector`` instead. (:rev:`1836`)
- Removed deprecated ``core.signals.domain_open`` signal - use ``core.signals.domain_opened`` instead (:rev:`1822`)
- ``log.msg()`` now receives a ``spider`` argument (:rev:`1822`)
   - Old domain argument has been deprecated and will be removed in 0.9. For spiders, you should always use the ``spider`` argument and pass spider references. If you really want to pass a string, use the ``component`` argument instead.
- Changed core signals ``domain_opened``, ``domain_closed``, ``domain_idle``
- Changed Item pipeline to use spiders instead of domains
   -  The ``domain`` argument of  ``process_item()`` item pipeline method was changed to  ``spider``, the new signature is: ``process_item(spider, item)`` (:rev:`1827` | #105)
   - To quickly port your code (to work with Scrapy 0.8) just use ``spider.domain_name`` where you previously used ``domain``.
- Changed Stats API to use spiders instead of domains (:rev:`1849` | #113)
   - ``StatsCollector`` was changed to receive spider references (instead of domains) in its methods (``set_value``, ``inc_value``, etc).
   - added ``StatsCollector.iter_spider_stats()`` method
   - removed ``StatsCollector.list_domains()`` method
   - Also, Stats signals were renamed and now pass around spider references (instead of domains). Here's a summary of the changes:
   - To quickly port your code (to work with Scrapy 0.8) just use ``spider.domain_name`` where you previously used ``domain``. ``spider_stats`` contains exactly the same data as ``domain_stats``.
- ``CloseDomain`` extension moved to ``scrapy.contrib.closespider.CloseSpider`` (:rev:`1833`)
   - Its settings were also renamed:
      - ``CLOSEDOMAIN_TIMEOUT`` to ``CLOSESPIDER_TIMEOUT``
      - ``CLOSEDOMAIN_ITEMCOUNT`` to ``CLOSESPIDER_ITEMCOUNT``
- Removed deprecated ``SCRAPYSETTINGS_MODULE`` environment variable - use ``SCRAPY_SETTINGS_MODULE`` instead (:rev:`1840`)
- Renamed setting: ``REQUESTS_PER_DOMAIN`` to ``CONCURRENT_REQUESTS_PER_SPIDER`` (:rev:`1830`, :rev:`1844`)
- Renamed setting: ``CONCURRENT_DOMAINS`` to ``CONCURRENT_SPIDERS`` (:rev:`1830`)
- Refactored HTTP Cache middleware
- HTTP Cache middleware has been heavily refactored, retaining the same functionality except for the domain sectorization which was removed. (:rev:`1843` )
- Renamed exception: ``DontCloseDomain`` to ``DontCloseSpider`` (:rev:`1859` | #120)
- Renamed extension: ``DelayedCloseDomain`` to ``SpiderCloseDelay`` (:rev:`1861` | #121)
- Removed obsolete ``scrapy.utils.markup.remove_escape_chars`` function - use ``scrapy.utils.markup.replace_escape_chars`` instead (:rev:`1865`)

Scrapy 0.7
----------

First release of Scrapy.


.. _boto3: https://github.com/boto/boto3
.. _botocore: https://github.com/boto/botocore
.. _chunked transfer encoding: https://en.wikipedia.org/wiki/Chunked_transfer_encoding
.. _ClientForm: https://pypi.org/project/ClientForm/
.. _Creating a pull request: https://help.github.com/en/articles/creating-a-pull-request
.. _cryptography: https://cryptography.io/en/latest/
.. _docstrings: https://docs.python.org/3/glossary.html#term-docstring
.. _KeyboardInterrupt: https://docs.python.org/3/library/exceptions.html#KeyboardInterrupt
.. _LevelDB: https://github.com/google/leveldb
.. _lxml: https://lxml.de/
.. _marshal: https://docs.python.org/2/library/marshal.html
.. _parsel: https://github.com/scrapy/parsel
.. _parsel.csstranslator.GenericTranslator: https://parsel.readthedocs.io/en/latest/parsel.html#parsel.csstranslator.GenericTranslator
.. _parsel.csstranslator.HTMLTranslator: https://parsel.readthedocs.io/en/latest/parsel.html#parsel.csstranslator.HTMLTranslator
.. _parsel.csstranslator.XPathExpr: https://parsel.readthedocs.io/en/latest/parsel.html#parsel.csstranslator.XPathExpr
.. _PEP 257: https://peps.python.org/pep-0257/
.. _Pillow: https://github.com/python-pillow/Pillow
.. _pyOpenSSL: https://www.pyopenssl.org/en/stable/
.. _queuelib: https://github.com/scrapy/queuelib
.. _registered with IANA: https://www.iana.org/assignments/media-types/media-types.xhtml
.. _resource: https://docs.python.org/2/library/resource.html
.. _robots.txt: https://www.robotstxt.org/
.. _scrapely: https://github.com/scrapy/scrapely
.. _scrapy-bench: https://github.com/scrapy/scrapy-bench
.. _service_identity: https://service-identity.readthedocs.io/en/stable/
.. _six: https://six.readthedocs.io/
.. _tox: https://pypi.org/project/tox/
.. _Twisted: https://twisted.org/
.. _w3lib: https://github.com/scrapy/w3lib
.. _w3lib.encoding: https://github.com/scrapy/w3lib/blob/master/w3lib/encoding.py
.. _What is cacheable: https://www.w3.org/Protocols/rfc2616/rfc2616-sec14.html#sec14.9.1
.. _zope.interface: https://zopeinterface.readthedocs.io/en/latest/
.. _Zsh: https://www.zsh.org/
.. _zstandard: https://pypi.org/project/zstandard/
