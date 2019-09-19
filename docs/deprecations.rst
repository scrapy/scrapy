.. _deprecations:

Deprecations
============

This document outlines the Scrapy deprecation policy, how to handle deprecation
warnings, and lists when various pieces of Scrapy have been removed or altered
in a backward incompatible way, following their deprecation.

.. _deprecation-policy:

Deprecation policy
------------------

Scrapy features may be deprecated in any version of Scrapy.

After a Scrapy feature is deprecated in a non-bugfix release (see *release
number* in :ref:`versioning`), that feature may be removed in any later
Scrapy release.

For example, a feature of ``1.0.0`` deprecated in ``1.1.0`` may stop working in
``1.2.0`` or in any later version.


.. _deprecation-warnings:

Deprecation warnings
--------------------

When you use a deprecated feature, Scrapy issues a Python warning (see
:mod:`warnings`).

Scrapy deprecation warnings use the following :ref:`warning category
<python:warning-categories>`:

.. autoclass:: scrapy.exceptions.ScrapyDeprecationWarning

.. _filtering-out-deprecation-warnings:

Filtering out deprecation warnings
''''''''''''''''''''''''''''''''''

Filtering out only Scrapy warnings is not easy due to a `Python issue`_.

If you do not mind filtering out all warnings, not only Scrapy deprecation
warnings, apply the ``ignore`` :ref:`warning filter <python:warning-filter>`
with :python:option:`-W` or :python:envvar:`PYTHONWARNINGS`. For example::

    $ export PYTHONWARNINGS=ignore

.. _Python issue: https://bugs.python.org/issue22543


.. _current-deprecations:

Upcoming changes
----------------

The changes below will be required in a future version of Scrapy. We encourage
you to apply any change that is applicable to your version of Scrapy.

Applicable since 1.4.0
''''''''''''''''''''''

-   ``Spider.make_requests_from_url`` is removed, use
    :meth:`Spider.start_requests <scrapy.spiders.Spider.start_requests>`
    instead.


Applicable since 1.3.0
''''''''''''''''''''''

-   ``ChunkedTransferMiddleware`` is removed, chunked transfers are
    supported by default.


Applicable since 1.1.0
''''''''''''''''''''''

-   ``scrapy.utils.python.isbinarytext`` is removed. Use
    ``scrapy.utils.python.binary_is_text`` instead, but mind that it
    returns the inverse value (``isbinarytext() == not binary_is_text()``).

-   In ``scrapy.utils.datatypes``, the ``MultiValueDictKeyError`` exception
    and classes ``MultiValueDict`` and ``SiteNode`` are removed.

-   The previously bundled ``scrapy.xlib.pydispatch`` library is replaced by
    `pydispatcher <https://pypi.python.org/pypi/PyDispatcher>`_.


Applicable since 1.0.0
''''''''''''''''''''''

-   The following classes are removed in favor of
    :class:`~scrapy.linkextractors.LinkExtractor`::

        scrapy.linkextractors.htmlparser.HtmlParserLinkExtractor
        scrapy.contrib.linkextractors.sgml.BaseSgmlLinkExtractor
        scrapy.contrib.linkextractors.sgml.SgmlLinkExtractor

-   The ``scrapy.crawler.Crawler.spiders`` is removed, use
    :attr:`CrawlerRunner.spider_loader
    <scrapy.crawler.CrawlerRunner.spider_loader>` or instantiate
    :class:`~scrapy.spiderloader.SpiderLoader` with your settings.


.. _deprecations-1.7.0:

1.7.0
-----

-   ``429`` is part of the :setting:`RETRY_HTTP_CODES` setting by default.

-   :class:`~scrapy.crawler.Crawler`,
    :class:`CrawlerRunner.crawl <scrapy.crawler.CrawlerRunner.crawl>` and
    :class:`CrawlerRunner.create_crawler <scrapy.crawler.CrawlerRunner.create_crawler>`
    do not accept a :class:`~scrapy.spiders.Spider` subclass instance, use a
    :class:`~scrapy.spiders.Spider` subclass.

-   Custom scheduler priority queues (see :setting:`SCHEDULER_PRIORITY_QUEUE`)
    must handle :class:`~scrapy.http.Request` objects instead of arbitrary
    Python data structures.

-   The ``scrapy.log`` module is replaced by Python’s `logging
    <https://docs.python.org/library/logging.html>`_ module. See
    :ref:`topics-logging`.

-   The ``SPIDER_MANAGER_CLASS`` setting is renamed to
    :setting:`SPIDER_LOADER_CLASS`.

-   In ``scrapy.utils.python``, the ``str_to_unicode`` and
    ``unicode_to_str`` functions are replaced by ``to_unicode`` and
    ``to_bytes``, respectively.

-   ``scrapy.spiders.spiders`` is removed, instantiate
    :class:`~scrapy.spiderloader.SpiderLoader` with your settings.

-   The ``scrapy.telnet`` module is moved to ``scrapy.extensions.telnet``.

-   The ``scrapy.conf`` module is removed, use :attr:`Crawler.settings
    <scrapy.crawler.Crawler.settings>`.

-   In ``scrapy.core.downloader.handlers``, ``http.HttpDownloadHandler`` is
    removed, use ``http10.HTTP10DownloadHandler``.

-   In ``scrapy.loader.ItemLoader``, ``_get_values`` is removed, use
    ``_get_xpathvalues``.

-   In ``scrapy.loader``, ``XPathItemLoader`` is removed, use
    :class:`~scrapy.loader.ItemLoader`.

-   In ``scrapy.pipelines.files.FilesPipeline``, ``file_key`` is removed, use
    ``file_path``.

-   In ``scrapy.pipelines.images.ImagesPipeline``:

    -   ``file_key`` is removed, use ``file_path``

    -   ``image_key`` is removed, use ``file_path``

    -   ``thumb_key`` is removed, use ``thumb_path``

-   In both ``scrapy.selector`` and ``scrapy.selector.lxmlsel``,
    ``HtmlXPathSelector``, ``XmlXPathSelector``, ``XPathSelector``, and
    ``XPathSelectorList`` are removed, use :class:`~scrapy.selector.Selector`.

-   In ``scrapy.selector.csstranslator``:

    -   ``ScrapyGenericTranslator`` is removed, use
        ``parsel.csstranslator.GenericTranslator_``

    -   ``ScrapyHTMLTranslator`` is removed, use
        ``parsel.csstranslator.HTMLTranslator_``

    -   ``ScrapyXPathExpr`` is removed, use
        ``parsel.csstranslator.XPathExpr_``

-   In :class:`~scrapy.selector.Selector`:

    -   ``_root``, both the constructor argument and the object property, are
        removed; , use ``root``

    -   ``extract_unquoted`` is removed, use ``getall``

    -   ``select`` is removed, use ``xpath``

-   In :class:`~scrapy.selector.SelectorList`:

    -   ``extract_unquoted`` is removed, use ``getall``

    -   ``select`` is removed, use ``xpath``

    -   ``x`` is removed, use ``xpath``

-   ``scrapy.spiders.BaseSpider`` is removed, use
    :class:`~scrapy.spiders.Spider`

-   In :class:`~scrapy.spiders.Spider` and subclasses:

    -   ``DOWNLOAD_DELAY`` is removed, use :ref:`download_delay
        <spider-download_delay-attribute>`

    -   ``set_crawler`` is removed, use
        :meth:`~scrapy.spiders.Spider.from_crawler`

-   ``scrapy.utils.response.body_or_str`` is removed


.. _deprecations-1.6.0:

1.6.0
-----

-   The following modules are removed:

    -   ``scrapy.command``
    -   ``scrapy.contrib`` (with all submodules)
    -   ``scrapy.contrib_exp`` (with all submodules)
    -   ``scrapy.dupefilter``
    -   ``scrapy.linkextractor``
    -   ``scrapy.project``
    -   ``scrapy.spider``
    -   ``scrapy.spidermanager``
    -   ``scrapy.squeue``
    -   ``scrapy.stats``
    -   ``scrapy.statscol``
    -   ``scrapy.utils.decorator``

    See :ref:`module-relocations` for more information.

-   The ``scrapy.interfaces.ISpiderManager`` interface is removed, use
    :class:`scrapy.interfaces.ISpiderLoader <scrapy.loader.SpiderLoader>`
    instead.

-   The ``scrapy.settings.CrawlerSettings`` class is removed, use
    :class:`scrapy.settings.Settings` instead.

-   The ``scrapy.settings.Settings.overrides`` property is removed, use
    ``Settings.set(name, value, priority='cmdline')`` instead (see
    :meth:`Settings.set <scrapy.settings.BaseSettings.set>`).

-   The ``scrapy.settings.Settings.defaults`` property is removed, use
    ``Settings.set(name, value, priority='default')`` instead (see
    :meth:`Settings.set <scrapy.settings.BaseSettings.set>`).

-   Scrapy requires parsel_ ≥ 1.5. Custom :class:`~scrapy.selector.Selector`
    subclasses may be affected by backward incompatible `changes in parsel
    1.5`_.

-   A non-zero exit code is returned from Scrapy commands when an error happens
    on spider inititalization.

.. _changes in parsel 1.5: https://parsel.readthedocs.io/en/latest/history.html#id2
.. _parsel: https://parsel.readthedocs.io


.. _deprecations-1.5.2:

1.5.2
-----

-   Scrapy’s telnet console requires username and password. See
    :ref:`topics-telnetconsole` for more details.


.. _deprecations-1.5.0:

1.5.0
-----

-   Python 3.3 is not supported anymore.

-   The default Scrapy user agent string uses an HTTPS link to `scrapy.org
    <https://scrapy.org/>`_. Override :setting:`USER_AGENT` if you relied on
    the old value.

-   The logging of settings overridden by
    :attr:`~scrapy.spiders.Spider.custom_settings` changes from
    ``[scrapy.utils.log]`` to ``[scrapy.crawler]``.

-   :class:`LinkExtractor <scrapy.linkextractors.lxmlhtml.LxmlLinkExtractor>`
    ignores the ``m4v`` extension by default. Use the ``deny_extensions``
    parameter of the
    :class:`LinkExtractor <scrapy.linkextractors.lxmlhtml.LxmlLinkExtractor>`
    constructor to override this behavior.

-   The ``522`` and ``524`` status codes are added to
    :setting:`RETRY_HTTP_CODES`.


.. _deprecations-1.4.0:

1.4.0
-----

-   :class:`LinkExtractor <scrapy.linkextractors.lxmlhtml.LxmlLinkExtractor>`
    does not canonicalize URLs by default. Pass ``canonicalize=True`` to the
    :class:`LinkExtractor <scrapy.linkextractors.lxmlhtml.LxmlLinkExtractor>`
    constructor to override this behavior.

-   The :class:`~scrapy.extensions.memusage.MemoryUsage` extension is enabled
    by default.

-   The ``EDITOR`` environment variable takes precedence over the
    :setting:`EDITOR` setting.


.. _deprecations-1.3.0:

1.3.0
-----

-   :class:`~scrapy.spidermiddlewares.httperror.HttpErrorMiddleware` logs
    errors with ``INFO`` level instead of ``DEBUG``.

-   By default, logger names now use a long-form path, e.g.
    ``[scrapy.extensions.logstats]``, instead of the shorter "top-level"
    variant of prior releases (e.g. ``[scrapy]``). You can switch back to short
    logger names setting :setting:`LOG_SHORT_NAMES` to ``True``.

-   ``ChunkedTransferMiddleware`` is removed from
    :setting:`DOWNLOADER_MIDDLEWARES`, chunked transfers are supported by
    default.


.. _deprecations-1.2.0:

1.2.0
-----

-   :class:`~scrapy.downloadermiddlewares.defaultheaders.DefaultHeadersMiddleware`
    runs before
    :class:`~scrapy.downloadermiddlewares.useragent.UserAgentMiddleware` in
    :setting:`DOWNLOADER_MIDDLEWARES` by default.

-   The HTTP cache extension and plugins that use the ``.scrapy`` data
    directory now work outside projects.

-   The :class:`~scrapy.selector.Selector` constructor does not allow passing
    both ``response`` and ``text`` arguments.

-   The ``scrapy.utils.url.canonicalize_url`` function has been moved to
    `w3lib.url.canonicalize_url`_.

.. _w3lib.url.canonicalize_url: https://w3lib.readthedocs.io/en/latest/w3lib.html#w3lib.url.canonicalize_url


.. _deprecations-1.1.0:

1.1.0
-----

-   Response status code ``400`` is not retried by default. If you need the old
    behavior, add ``400`` to :setting:`RETRY_HTTP_CODES`.

-   When :ref:`uploading files or images <topics-media-pipeline>` to S3, the
    default ACL policy is now "private" instead of "public". You can use
    :setting:`FILES_STORE_S3_ACL` to change it.

-   :class:`LinkExtractor <scrapy.linkextractors.lxmlhtml.LxmlLinkExtractor>`
    ignores the ``pps`` extension by default. Use the ``deny_extensions``
    parameter of the
    :class:`LinkExtractor <scrapy.linkextractors.lxmlhtml.LxmlLinkExtractor>`
    constructor to override this behavior.

-   In the output of the ``scrapy.utils.url.canonicalize_url`` function,
    non-ASCII query arguments are now encoded using the corresponding encoding,
    instead of forcing UTF-8. This could change the output of link extractors
    and invalidate some cache entries from older Scrapy versions.

-   Responses with ``application/x-json`` as ``Content-Type`` are parsed as
    :class:`~scrapy.http.TextResponse` objects.

-   The ``scrapy.optional_features`` set is removed.

-   The global command-line option ``--lsprof`` is removed.

-   ``scrapy shell`` supports URLs without scheme.

    For example, if you use ``scrapy shell example.com``,
    ``http://example.com`` is fetched in the shell. To fetch a local file
    called ``example.com`` instead, you must either use explicit relative
    syntax (``./example.com``) or an absolute path.


.. _deprecations-1.0.0:

1.0.0
-----

-   The ``scrapy.webservice`` module is removed, use `scrapy-jsonrpc
    <https://github.com/scrapy-plugins/scrapy-jsonrpc>`_ instead.

-   :class:`~extensions.feedexport.FeedExporter` subclasses must accept a
    ``settings`` first argument.

-   The :signal:`spider_closed` signal does not receive a ``spider_stats``
    argument.

-   The ``CONCURRENT_REQUESTS_PER_SPIDER`` setting is removed, use
    :setting:`CONCURRENT_REQUESTS_PER_DOMAIN` instead.

-   The ``CONCURRENT_SPIDERS`` setting is removed, use the `max_proc
    <https://scrapyd.readthedocs.io/en/stable/config.html#max-proc>`_ setting
    of `scrapyd <https://scrapyd.readthedocs.io>`_ instead.

-   The ``scrapy.utils.python.FixedSGMLParser`` class is removed as part of the
    deprecation of the ``BaseSgmlLinkExtractor`` and ``SgmlLinkExtractor``
    classes of the ``scrapy.contrib.linkextractors.sgml`` module.

-   The default value of the ``SPIDER_MANAGER_CLASS`` setting becomes
    ``scrapy.spiderloader.SpiderLoader``.

-   The ``spiders`` :ref:`Telnet variable <telnet-variables>` is removed.

-   The ``spidermanager`` argument of the
    :meth:`~scrapy.utils.spider.spidercls_for_request` function is renamed to
    ``spider_loader``.

-   The ``scrapy.contrib.djangoitem`` module is removed, use `scrapy-djangoitem
    <https://github.com/scrapy/scrapy-djangoitem>`_ instead.

-   The ``scrapy deploy`` :ref:`command <topics-shell>` is removed in favor of
    the ``scrapyd-deploy`` command from `scrapyd-client
    <https://github.com/scrapy/scrapyd-client>`_.
