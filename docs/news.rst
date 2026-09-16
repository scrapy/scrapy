.. _news:

Release notes
=============

Scrapy VERSION (unreleased)
---------------------------

Backward-incompatible changes
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

-   New projects created with the :command:`startproject` command define their
    configuration in a :file:`pyproject.toml` file, instead of the now
    deprecated :file:`scrapy.cfg` file.

    To deploy such a project you need ``scrapyd`` TODO or higher,
    ``scrapyd-client`` TODO or higher, or ``shub`` TODO or higher. Earlier
    versions of those tools only read :file:`scrapy.cfg` files.
    (:issue:`7030`)

..  TODO: Fill in the ``scrapyd``, ``scrapyd-client`` and ``shub`` versions
    above. Those releases, with support for the ``[tool.scrapy]`` table of
    :file:`pyproject.toml`, must happen before this Scrapy release.

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


.. _aiohttp: https://docs.aiohttp.org/en/stable/
.. _botocore: https://github.com/boto/botocore
.. _charset-normalizer: https://charset-normalizer.readthedocs.io/en/latest/
.. _cryptography: https://cryptography.io/en/latest/
.. _ipdb: https://github.com/gotcha/ipdb
.. _lxml: https://lxml.de/
.. _parso: https://github.com/davidhalter/parso
.. _platformdirs: https://platformdirs.readthedocs.io/en/latest/
.. _Pillow: https://github.com/python-pillow/Pillow
.. _pyOpenSSL: https://www.pyopenssl.org/en/stable/
.. _queuelib: https://github.com/scrapy/queuelib
.. _service_identity: https://service-identity.readthedocs.io/en/stable/
.. _w3lib: https://github.com/scrapy/w3lib
.. _zope.interface: https://zopeinterface.readthedocs.io/en/latest/
