.. _news:

Release notes
=============

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

    (:issue:`4440`)


Deprecation removals
~~~~~~~~~~~~~~~~~~~~

*   The ``LOG_UNSERIALIZABLE_REQUESTS`` setting is no longer supported, use
    :setting:`SCHEDULER_DEBUG` instead (:issue:`4385`)

*   The ``REDIRECT_MAX_METAREFRESH_DELAY`` setting is no longer supported, use
    :setting:`METAREFRESH_MAXDELAY` instead (:issue:`4385`)

*   The :class:`~scrapy.downloadermiddlewares.chunked.ChunkedTransferMiddleware`
    middleware has been removed, including the entire
    :class:`scrapy.downloadermiddlewares.chunked` module; chunked transfers
    work out of the box (:issue:`4431`)

*   The ``spiders`` property has been removed from
    :class:`~scrapy.crawler.Crawler`, use :class:`CrawlerRunner.spider_loader
    <scrapy.crawler.CrawlerRunner.spider_loader>` or instantiate
    :setting:`SPIDER_LOADER_CLASS` with your settings instead (:issue:`4398`)

*   The ``MultiValueDict``, ``MultiValueDictKeyError``, and ``SiteNode``
    classes have been removed from :mod:`scrapy.utils.datatypes`
    (:issue:`4400`)


Deprecations
~~~~~~~~~~~~

*   The ``FEED_FORMAT`` and ``FEED_URI`` settings have been deprecated in
    favor of the new :setting:`FEEDS` setting (:issue:`1336`, :issue:`3858`,
    :issue:`4507`)


New features
~~~~~~~~~~~~

*   A new setting, :setting:`FEEDS`, allows configuring multiple output feeds
    with different settings each (:issue:`1336`, :issue:`3858`, :issue:`4507`)

*   The :command:`crawl` and :command:`runspider` commands now support multiple
    ``-o`` parameters (:issue:`1336`, :issue:`3858`, :issue:`4507`)

*   The :command:`crawl` and :command:`runspider` commands now support
    specifying an output format by appending ``:<format>`` to the output file
    (:issue:`1336`, :issue:`3858`, :issue:`4507`)

*   The new :attr:`Response.ip_address <scrapy.http.Response.ip_address>`
    attribute gives access to the IP address that originated a response
    (:issue:`3903`, :issue:`3940`)

*   A warning is now issued when a value in
    :attr:`~scrapy.spiders.Spider.allowed_domains` includes a port
    (:issue:`50`, :issue:`3198`, :issue:`4413`)

*   Zsh completion now excludes used option aliases from the completion list
    (:issue:`4438`)


Bug fixes
~~~~~~~~~

*   :ref:`Request serialization <request-serialization>` no longer breaks for
    callbacks that are spider attributes which are assigned a function with a
    different name (:issue:`4500`)

*   ``None`` values in :attr:`~scrapy.spiders.Spider.allowed_domains` no longer
    cause a :exc:`TypeError` exception (:issue:`4410`)

*   Zsh completion no longer allows options after arguments (:issue:`4438`)

*   zope.interface 5.0.0 and later versions are now supported
    (:issue:`4447`, :issue:`4448`)

*   :meth:`Spider.make_requests_from_url
    <scrapy.spiders.Spider.make_requests_from_url>`, deprecated in Scrapy
    1.4.0, now issues a warning when used (:issue:`4412`)


Documentation
~~~~~~~~~~~~~

*   Improved the documentation about signals that allow their handlers to
    return a :class:`~twisted.internet.defer.Deferred` (:issue:`4295`,
    :issue:`4390`)

*   Our PyPI entry now includes links for our documentation, our source code
    repository and our issue tracker (:issue:`4456`)

*   Covered the `curl2scrapy <https://michael-shub.github.io/curl2scrapy/>`_
    service in the documentation (:issue:`4206`, :issue:`4455`)

*   Removed references to the Guppy library, which only works in Python 2
    (:issue:`4285`, :issue:`4343`)

*   Extended use of InterSphinx to link to Python 3 documentation
    (:issue:`4444`, :issue:`4445`)

*   Added support for Sphinx 3.0 and later (:issue:`4475`, :issue:`4480`,
    :issue:`4496`, :issue:`4503`)


Quality assurance
~~~~~~~~~~~~~~~~~

*   Removed warnings about using old, removed settings (:issue:`4404`)

*   Removed a warning about importing
    :class:`~twisted.internet.testing.StringTransport` from
    ``twisted.test.proto_helpers`` in Twisted 19.7.0 or newer (:issue:`4409`)

*   Removed outdated Debian package build files (:issue:`4384`)

*   Removed :class:`object` usage as a base class (:issue:`4430`)

*   Removed code that added support for old versions of Twisted that we no
    longer support (:issue:`4472`)

*   Fixed code style issues (:issue:`4468`, :issue:`4469`, :issue:`4471`,
    :issue:`4481`)

*   Removed :func:`twisted.internet.defer.returnValue` calls (:issue:`4443`,
    :issue:`4446`, :issue:`4489`)


.. _release-2.0.1:

Scrapy 2.0.1 (2020-03-18)
-------------------------

*   :meth:`Response.follow_all <scrapy.http.Response.follow_all>` now supports
    an empty URL iterable as input (:issue:`4408`, :issue:`4420`)

*   Removed top-level :mod:`~twisted.internet.reactor` imports to prevent
    errors about the wrong Twisted reactor being installed when setting a
    different Twisted reactor using :setting:`TWISTED_REACTOR` (:issue:`4401`,
    :issue:`4406`)

*   Fixed tests (:issue:`4422`)


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
* IPv6 support through :setting:`DNS_RESOLVER`

Backward-incompatible changes
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

*   Python 2 support has been removed, following `Python 2 end-of-life on
    January 1, 2020`_ (:issue:`4091`, :issue:`4114`, :issue:`4115`,
    :issue:`4121`, :issue:`4138`, :issue:`4231`, :issue:`4242`, :issue:`4304`,
    :issue:`4309`, :issue:`4373`)

*   Retry gaveups (see :setting:`RETRY_TIMES`) are now logged as errors instead
    of as debug information (:issue:`3171`, :issue:`3566`)

*   File extensions that
    :class:`LinkExtractor <scrapy.linkextractors.lxmlhtml.LxmlLinkExtractor>`
    ignores by default now also include ``7z``, ``7zip``, ``apk``, ``bz2``,
    ``cdr``, ``dmg``, ``ico``, ``iso``, ``tar``, ``tar.gz``, ``webm``, and
    ``xz`` (:issue:`1837`, :issue:`2067`, :issue:`4066`)

*   The :setting:`METAREFRESH_IGNORE_TAGS` setting is now an empty list by
    default, following web browser behavior (:issue:`3844`, :issue:`4311`)

*   The
    :class:`~scrapy.downloadermiddlewares.httpcompression.HttpCompressionMiddleware`
    now includes spaces after commas in the value of the ``Accept-Encoding``
    header that it sets, following web browser behavior (:issue:`4293`)

*   The ``__init__`` method of custom download handlers (see
    :setting:`DOWNLOAD_HANDLERS`) or subclasses of the following downloader
    handlers  no longer receives a ``settings`` parameter:

    *   :class:`scrapy.core.downloader.handlers.datauri.DataURIDownloadHandler`

    *   :class:`scrapy.core.downloader.handlers.file.FileDownloadHandler`

    Use the ``from_settings`` or ``from_crawler`` class methods to expose such
    a parameter to your custom download handlers.

    (:issue:`4126`)

*   We have refactored the :class:`scrapy.core.scheduler.Scheduler` class and
    related queue classes (see :setting:`SCHEDULER_PRIORITY_QUEUE`,
    :setting:`SCHEDULER_DISK_QUEUE` and :setting:`SCHEDULER_MEMORY_QUEUE`) to
    make it easier to implement custom scheduler queue classes. See
    :ref:`2-0-0-scheduler-queue-changes` below for details.

*   Overridden settings are now logged in a different format. This is more in
    line with similar information logged at startup (:issue:`4199`)

.. _Python 2 end-of-life on January 1, 2020: https://www.python.org/doc/sunset-python-2/


Deprecation removals
~~~~~~~~~~~~~~~~~~~~

*   The :ref:`Scrapy shell <topics-shell>` no longer provides a `sel` proxy
    object, use :meth:`response.selector <scrapy.http.Response.selector>`
    instead (:issue:`4347`)

*   LevelDB support has been removed (:issue:`4112`)

*   The following functions have been removed from :mod:`scrapy.utils.python`:
    ``isbinarytext``, ``is_writable``, ``setattr_default``, ``stringify_dict``
    (:issue:`4362`)


Deprecations
~~~~~~~~~~~~

*   Using environment variables prefixed with ``SCRAPY_`` to override settings
    is deprecated (:issue:`4300`, :issue:`4374`, :issue:`4375`)

*   :class:`scrapy.linkextractors.FilteringLinkExtractor` is deprecated, use
    :class:`scrapy.linkextractors.LinkExtractor
    <scrapy.linkextractors.lxmlhtml.LxmlLinkExtractor>` instead (:issue:`4045`)

*   The ``noconnect`` query string argument of proxy URLs is deprecated and
    should be removed from proxy URLs (:issue:`4198`)

*   The :meth:`next <scrapy.utils.python.MutableChain.next>` method of
    :class:`scrapy.utils.python.MutableChain` is deprecated, use the global
    :func:`next` function or :meth:`MutableChain.__next__
    <scrapy.utils.python.MutableChain.__next__>` instead (:issue:`4153`)


New features
~~~~~~~~~~~~

*   Added :doc:`partial support <topics/coroutines>` for Python’s
    :ref:`coroutine syntax <async>` and :doc:`experimental support
    <topics/asyncio>` for :mod:`asyncio` and :mod:`asyncio`-powered libraries
    (:issue:`4010`, :issue:`4259`, :issue:`4269`, :issue:`4270`, :issue:`4271`,
    :issue:`4316`, :issue:`4318`)

*   The new :meth:`Response.follow_all <scrapy.http.Response.follow_all>`
    method offers the same functionality as
    :meth:`Response.follow <scrapy.http.Response.follow>` but supports an
    iterable of URLs as input and returns an iterable of requests
    (:issue:`2582`, :issue:`4057`, :issue:`4286`)

*   :ref:`Media pipelines <topics-media-pipeline>` now support :ref:`FTP
    storage <media-pipeline-ftp>` (:issue:`3928`, :issue:`3961`)

*   The new :attr:`Response.certificate <scrapy.http.Response.certificate>`
    attribute exposes the SSL certificate of the server as a
    :class:`twisted.internet.ssl.Certificate` object for HTTPS responses
    (:issue:`2726`, :issue:`4054`)

*   A new :setting:`DNS_RESOLVER` setting allows enabling IPv6 support
    (:issue:`1031`, :issue:`4227`)

*   A new :setting:`SCRAPER_SLOT_MAX_ACTIVE_SIZE` setting allows configuring
    the existing soft limit that pauses request downloads when the total
    response data being processed is too high (:issue:`1410`, :issue:`3551`)

*   A new :setting:`TWISTED_REACTOR` setting allows customizing the
    :mod:`~twisted.internet.reactor` that Scrapy uses, allowing to
    :doc:`enable asyncio support <topics/asyncio>` or deal with a
    :ref:`common macOS issue <faq-specific-reactor>` (:issue:`2905`,
    :issue:`4294`)

*   Scheduler disk and memory queues may now use the class methods
    ``from_crawler`` or ``from_settings`` (:issue:`3884`)

*   The new :attr:`Response.cb_kwargs <scrapy.http.Response.cb_kwargs>`
    attribute serves as a shortcut for :attr:`Response.request.cb_kwargs
    <scrapy.http.Request.cb_kwargs>` (:issue:`4331`)

*   :meth:`Response.follow <scrapy.http.Response.follow>` now supports a
    ``flags`` parameter, for consistency with :class:`~scrapy.http.Request`
    (:issue:`4277`, :issue:`4279`)

*   :ref:`Item loader processors <topics-loaders-processors>` can now be
    regular functions, they no longer need to be methods (:issue:`3899`)

*   :class:`~scrapy.spiders.Rule` now accepts an ``errback`` parameter
    (:issue:`4000`)

*   :class:`~scrapy.http.Request` no longer requires a ``callback`` parameter
    when an ``errback`` parameter is specified (:issue:`3586`, :issue:`4008`)

*   :class:`~scrapy.logformatter.LogFormatter` now supports some additional
    methods:

    *   :class:`~scrapy.logformatter.LogFormatter.download_error` for
        download errors

    *   :class:`~scrapy.logformatter.LogFormatter.item_error` for exceptions
        raised during item processing by :ref:`item pipelines
        <topics-item-pipeline>`

    *   :class:`~scrapy.logformatter.LogFormatter.spider_error` for exceptions
        raised from :ref:`spider callbacks <topics-spiders>`

    (:issue:`374`, :issue:`3986`, :issue:`3989`, :issue:`4176`, :issue:`4188`)

*   The :setting:`FEED_URI` setting now supports :class:`pathlib.Path` values
    (:issue:`3731`, :issue:`4074`)

*   A new :signal:`request_left_downloader` signal is sent when a request
    leaves the downloader (:issue:`4303`)

*   Scrapy logs a warning when it detects a request callback or errback that
    uses ``yield`` but also returns a value, since the returned value would be
    lost (:issue:`3484`, :issue:`3869`)

*   :class:`~scrapy.spiders.Spider` objects now raise an :exc:`AttributeError`
    exception if they do not have a :class:`~scrapy.spiders.Spider.start_urls`
    attribute nor reimplement :class:`~scrapy.spiders.Spider.start_requests`,
    but have a ``start_url`` attribute (:issue:`4133`, :issue:`4170`)

*   :class:`~scrapy.exporters.BaseItemExporter` subclasses may now use
    ``super().__init__(**kwargs)`` instead of ``self._configure(kwargs)`` in
    their ``__init__`` method, passing ``dont_fail=True`` to the parent
    ``__init__`` method if needed, and accessing ``kwargs`` at ``self._kwargs``
    after calling their parent ``__init__`` method (:issue:`4193`,
    :issue:`4370`)

*   A new ``keep_fragments`` parameter of
    :func:`scrapy.utils.request.request_fingerprint` allows to generate
    different fingerprints for requests with different fragments in their URL
    (:issue:`4104`)

*   Download handlers (see :setting:`DOWNLOAD_HANDLERS`) may now use the
    ``from_settings`` and ``from_crawler`` class methods that other Scrapy
    components already supported (:issue:`4126`)

*   :class:`scrapy.utils.python.MutableChain.__iter__` now returns ``self``,
    `allowing it to be used as a sequence <https://lgtm.com/rules/4850080/>`_
    (:issue:`4153`)


Bug fixes
~~~~~~~~~

*   The :command:`crawl` command now also exits with exit code 1 when an
    exception happens before the crawling starts (:issue:`4175`, :issue:`4207`)

*   :class:`LinkExtractor.extract_links
    <scrapy.linkextractors.lxmlhtml.LxmlLinkExtractor.extract_links>` no longer
    re-encodes the query string or URLs from non-UTF-8 responses in UTF-8
    (:issue:`998`, :issue:`1403`, :issue:`1949`, :issue:`4321`)

*   The first spider middleware (see :setting:`SPIDER_MIDDLEWARES`) now also
    processes exceptions raised from callbacks that are generators
    (:issue:`4260`, :issue:`4272`)

*   Redirects to URLs starting with 3 slashes (``///``) are now supported
    (:issue:`4032`, :issue:`4042`)

*   :class:`~scrapy.http.Request` no longer accepts strings as ``url`` simply
    because they have a colon (:issue:`2552`, :issue:`4094`)

*   The correct encoding is now used for attach names in
    :class:`~scrapy.mail.MailSender` (:issue:`4229`, :issue:`4239`)

*   :class:`~scrapy.dupefilters.RFPDupeFilter`, the default
    :setting:`DUPEFILTER_CLASS`, no longer writes an extra ``\r`` character on
    each line in Windows, which made the size of the ``requests.seen`` file
    unnecessarily large on that platform (:issue:`4283`)

*   Z shell auto-completion now looks for ``.html`` files, not ``.http`` files,
    and covers the ``-h`` command-line switch (:issue:`4122`, :issue:`4291`)

*   Adding items to a :class:`scrapy.utils.datatypes.LocalCache` object
    without a ``limit`` defined no longer raises a :exc:`TypeError` exception
    (:issue:`4123`)

*   Fixed a typo in the message of the :exc:`ValueError` exception raised when
    :func:`scrapy.utils.misc.create_instance` gets both ``settings`` and
    ``crawler`` set to ``None`` (:issue:`4128`)


Documentation
~~~~~~~~~~~~~

*   API documentation now links to an online, syntax-highlighted view of the
    corresponding source code (:issue:`4148`)

*   Links to unexisting documentation pages now allow access to the sidebar
    (:issue:`4152`, :issue:`4169`)

*   Cross-references within our documentation now display a tooltip when
    hovered (:issue:`4173`, :issue:`4183`)

*   Improved the documentation about :meth:`LinkExtractor.extract_links
    <scrapy.linkextractors.lxmlhtml.LxmlLinkExtractor.extract_links>` and
    simplified :ref:`topics-link-extractors` (:issue:`4045`)

*   Clarified how :class:`ItemLoader.item <scrapy.loader.ItemLoader.item>`
    works (:issue:`3574`, :issue:`4099`)

*   Clarified that :func:`logging.basicConfig` should not be used when also
    using :class:`~scrapy.crawler.CrawlerProcess` (:issue:`2149`,
    :issue:`2352`, :issue:`3146`, :issue:`3960`)

*   Clarified the requirements for :class:`~scrapy.http.Request` objects
    :ref:`when using persistence <request-serialization>` (:issue:`4124`,
    :issue:`4139`)

*   Clarified how to install a :ref:`custom image pipeline
    <media-pipeline-example>` (:issue:`4034`, :issue:`4252`)

*   Fixed the signatures of the ``file_path`` method in :ref:`media pipeline
    <topics-media-pipeline>` examples (:issue:`4290`)

*   Covered a backward-incompatible change in Scrapy 1.7.0 affecting custom
    :class:`scrapy.core.scheduler.Scheduler` subclasses (:issue:`4274`)

*   Improved the ``README.rst`` and ``CODE_OF_CONDUCT.md`` files
    (:issue:`4059`)

*   Documentation examples are now checked as part of our test suite and we
    have fixed some of the issues detected (:issue:`4142`, :issue:`4146`,
    :issue:`4171`, :issue:`4184`, :issue:`4190`)

*   Fixed logic issues, broken links and typos (:issue:`4247`, :issue:`4258`,
    :issue:`4282`, :issue:`4288`, :issue:`4305`, :issue:`4308`, :issue:`4323`,
    :issue:`4338`, :issue:`4359`, :issue:`4361`)

*   Improved consistency when referring to the ``__init__`` method of an object
    (:issue:`4086`, :issue:`4088`)

*   Fixed an inconsistency between code and output in :ref:`intro-overview`
    (:issue:`4213`)

*   Extended :mod:`~sphinx.ext.intersphinx` usage (:issue:`4147`,
    :issue:`4172`, :issue:`4185`, :issue:`4194`, :issue:`4197`)

*   We now use a recent version of Python to build the documentation
    (:issue:`4140`, :issue:`4249`)

*   Cleaned up documentation (:issue:`4143`, :issue:`4275`)


Quality assurance
~~~~~~~~~~~~~~~~~

*   Re-enabled proxy ``CONNECT`` tests (:issue:`2545`, :issue:`4114`)

*   Added Bandit_ security checks to our test suite (:issue:`4162`,
    :issue:`4181`)

*   Added Flake8_ style checks to our test suite and applied many of the
    corresponding changes (:issue:`3944`, :issue:`3945`, :issue:`4137`,
    :issue:`4157`, :issue:`4167`, :issue:`4174`, :issue:`4186`, :issue:`4195`,
    :issue:`4238`, :issue:`4246`, :issue:`4355`, :issue:`4360`, :issue:`4365`)

*   Improved test coverage (:issue:`4097`, :issue:`4218`, :issue:`4236`)

*   Started reporting slowest tests, and improved the performance of some of
    them (:issue:`4163`, :issue:`4164`)

*   Fixed broken tests and refactored some tests (:issue:`4014`, :issue:`4095`,
    :issue:`4244`, :issue:`4268`, :issue:`4372`)

*   Modified the :doc:`tox <tox:index>` configuration to allow running tests
    with any Python version, run Bandit_ and Flake8_ tests by default, and
    enforce a minimum tox version programmatically (:issue:`4179`)

*   Cleaned up code (:issue:`3937`, :issue:`4208`, :issue:`4209`,
    :issue:`4210`, :issue:`4212`, :issue:`4369`, :issue:`4376`, :issue:`4378`)

.. _Bandit: https://bandit.readthedocs.io/
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
        :setting:`JOB_DIR` value for disk queues.

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

(:issue:`3884`)


.. _release-1.8.0:

Scrapy 1.8.0 (2019-10-28)
-------------------------

Highlights:

* Dropped Python 3.4 support and updated minimum requirements; made Python 3.8
  support official
* New :meth:`Request.from_curl <scrapy.http.Request.from_curl>` class method
* New :setting:`ROBOTSTXT_PARSER` and :setting:`ROBOTSTXT_USER_AGENT` settings
* New :setting:`DOWNLOADER_CLIENT_TLS_CIPHERS` and
  :setting:`DOWNLOADER_CLIENT_TLS_VERBOSE_LOGGING` settings

Backward-incompatible changes
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

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

    (:issue:`3892`)

*   ``JSONRequest`` is now called :class:`~scrapy.http.JsonRequest` for
    consistency with similar classes (:issue:`3929`, :issue:`3982`)

*   If you are using a custom context factory
    (:setting:`DOWNLOADER_CLIENTCONTEXTFACTORY`), its ``__init__`` method must
    accept two new parameters: ``tls_verbose_logging`` and ``tls_ciphers``
    (:issue:`2111`, :issue:`3392`, :issue:`3442`, :issue:`3450`)

*   :class:`~scrapy.loader.ItemLoader` now turns the values of its input item
    into lists:

    >>> item = MyItem()
    >>> item['field'] = 'value1'
    >>> loader = ItemLoader(item=item)
    >>> item['field']
    ['value1']

    This is needed to allow adding values to existing fields
    (``loader.add_value('field', 'value2')``).

    (:issue:`3804`, :issue:`3819`, :issue:`3897`, :issue:`3976`, :issue:`3998`,
    :issue:`4036`)

See also :ref:`1.8-deprecation-removals` below.


New features
~~~~~~~~~~~~

*   A new :meth:`Request.from_curl <scrapy.http.Request.from_curl>` class
    method allows :ref:`creating a request from a cURL command
    <requests-from-curl>` (:issue:`2985`, :issue:`3862`)

*   A new :setting:`ROBOTSTXT_PARSER` setting allows choosing which robots.txt_
    parser to use. It includes built-in support for
    :ref:`RobotFileParser <python-robotfileparser>`,
    :ref:`Protego <protego-parser>` (default), :ref:`Reppy <reppy-parser>`, and
    :ref:`Robotexclusionrulesparser <rerp-parser>`, and allows you to
    :ref:`implement support for additional parsers
    <support-for-new-robots-parser>` (:issue:`754`, :issue:`2669`,
    :issue:`3796`, :issue:`3935`, :issue:`3969`, :issue:`4006`)

*   A new :setting:`ROBOTSTXT_USER_AGENT` setting allows defining a separate
    user agent string to use for robots.txt_ parsing (:issue:`3931`,
    :issue:`3966`)

*   :class:`~scrapy.spiders.Rule` no longer requires a :class:`LinkExtractor
    <scrapy.linkextractors.lxmlhtml.LxmlLinkExtractor>` parameter
    (:issue:`781`, :issue:`4016`)

*   Use the new :setting:`DOWNLOADER_CLIENT_TLS_CIPHERS` setting to customize
    the TLS/SSL ciphers used by the default HTTP/1.1 downloader (:issue:`3392`,
    :issue:`3442`)

*   Set the new :setting:`DOWNLOADER_CLIENT_TLS_VERBOSE_LOGGING` setting to
    ``True`` to enable debug-level messages about TLS connection parameters
    after establishing HTTPS connections (:issue:`2111`, :issue:`3450`)

*   Callbacks that receive keyword arguments
    (see :attr:`Request.cb_kwargs <scrapy.http.Request.cb_kwargs>`) can now be
    tested using the new :class:`@cb_kwargs
    <scrapy.contracts.default.CallbackKeywordArgumentsContract>`
    :ref:`spider contract <topics-contracts>` (:issue:`3985`, :issue:`3988`)

*   When a :class:`@scrapes <scrapy.contracts.default.ScrapesContract>` spider
    contract fails, all missing fields are now reported (:issue:`766`,
    :issue:`3939`)

*   :ref:`Custom log formats <custom-log-formats>` can now drop messages by
    having the corresponding methods of the configured :setting:`LOG_FORMATTER`
    return ``None`` (:issue:`3984`, :issue:`3987`)

*   A much improved completion definition is now available for Zsh_
    (:issue:`4069`)


Bug fixes
~~~~~~~~~

*   :meth:`ItemLoader.load_item() <scrapy.loader.ItemLoader.load_item>` no
    longer makes later calls to :meth:`ItemLoader.get_output_value()
    <scrapy.loader.ItemLoader.get_output_value>` or
    :meth:`ItemLoader.load_item() <scrapy.loader.ItemLoader.load_item>` return
    empty data (:issue:`3804`, :issue:`3819`, :issue:`3897`, :issue:`3976`,
    :issue:`3998`, :issue:`4036`)

*   Fixed :class:`~scrapy.statscollectors.DummyStatsCollector` raising a
    :exc:`TypeError` exception (:issue:`4007`, :issue:`4052`)

*   :meth:`FilesPipeline.file_path
    <scrapy.pipelines.files.FilesPipeline.file_path>` and
    :meth:`ImagesPipeline.file_path
    <scrapy.pipelines.images.ImagesPipeline.file_path>` no longer choose
    file extensions that are not `registered with IANA`_ (:issue:`1287`,
    :issue:`3953`, :issue:`3954`)

*   When using botocore_ to persist files in S3, all botocore-supported headers
    are properly mapped now (:issue:`3904`, :issue:`3905`)

*   FTP passwords in :setting:`FEED_URI` containing percent-escaped characters
    are now properly decoded (:issue:`3941`)

*   A memory-handling and error-handling issue in
    :func:`scrapy.utils.ssl.get_temp_key_info` has been fixed (:issue:`3920`)


Documentation
~~~~~~~~~~~~~

*   The documentation now covers how to define and configure a :ref:`custom log
    format <custom-log-formats>` (:issue:`3616`, :issue:`3660`)

*   API documentation added for :class:`~scrapy.exporters.MarshalItemExporter`
    and :class:`~scrapy.exporters.PythonItemExporter` (:issue:`3973`)

*   API documentation added for :class:`~scrapy.item.BaseItem` and
    :class:`~scrapy.item.ItemMeta` (:issue:`3999`)

*   Minor documentation fixes (:issue:`2998`, :issue:`3398`, :issue:`3597`,
    :issue:`3894`, :issue:`3934`, :issue:`3978`, :issue:`3993`, :issue:`4022`,
    :issue:`4028`, :issue:`4033`, :issue:`4046`, :issue:`4050`, :issue:`4055`,
    :issue:`4056`, :issue:`4061`, :issue:`4072`, :issue:`4071`, :issue:`4079`,
    :issue:`4081`, :issue:`4089`, :issue:`4093`)


.. _1.8-deprecation-removals:

Deprecation removals
~~~~~~~~~~~~~~~~~~~~

*   ``scrapy.xlib`` has been removed (:issue:`4015`)


Deprecations
~~~~~~~~~~~~

*   The LevelDB_ storage backend
    (``scrapy.extensions.httpcache.LeveldbCacheStorage``) of
    :class:`~scrapy.downloadermiddlewares.httpcache.HttpCacheMiddleware` is
    deprecated (:issue:`4085`, :issue:`4092`)

*   Use of the undocumented ``SCRAPY_PICKLED_SETTINGS_TO_OVERRIDE`` environment
    variable is deprecated (:issue:`3910`)

*   ``scrapy.item.DictItem`` is deprecated, use :class:`~scrapy.item.Item`
    instead (:issue:`3999`)


Other changes
~~~~~~~~~~~~~

*   Minimum versions of optional Scrapy requirements that are covered by
    continuous integration tests have been updated:

    *   botocore_ 1.3.23
    *   Pillow_ 3.4.2

    Lower versions of these optional requirements may work, but it is not
    guaranteed (:issue:`3892`)

*   GitHub templates for bug reports and feature requests (:issue:`3126`,
    :issue:`3471`, :issue:`3749`, :issue:`3754`)

*   Continuous integration fixes (:issue:`3923`)

*   Code cleanup (:issue:`3391`, :issue:`3907`, :issue:`3946`, :issue:`3950`,
    :issue:`4023`, :issue:`4031`)


.. _release-1.7.4:

Scrapy 1.7.4 (2019-10-21)
-------------------------

Revert the fix for :issue:`3804` (:issue:`3819`), which has a few undesired
side effects (:issue:`3897`, :issue:`3976`).

As a result, when an item loader is initialized with an item,
:meth:`ItemLoader.load_item() <scrapy.loader.ItemLoader.load_item>` once again
makes later calls to :meth:`ItemLoader.get_output_value()
<scrapy.loader.ItemLoader.get_output_value>` or :meth:`ItemLoader.load_item()
<scrapy.loader.ItemLoader.load_item>` return empty data.


.. _release-1.7.3:

Scrapy 1.7.3 (2019-08-01)
-------------------------

Enforce lxml 4.3.5 or lower for Python 3.4 (:issue:`3912`, :issue:`3918`).


.. _release-1.7.2:

Scrapy 1.7.2 (2019-07-23)
-------------------------

Fix Python 2 support (:issue:`3889`, :issue:`3893`, :issue:`3896`).


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
    :class:`CrawlerRunner.crawl <scrapy.crawler.CrawlerRunner.crawl>` and
    :class:`CrawlerRunner.create_crawler <scrapy.crawler.CrawlerRunner.create_crawler>`
    no longer accept a :class:`~scrapy.spiders.Spider` subclass instance, they
    only accept a :class:`~scrapy.spiders.Spider` subclass now.

    :class:`~scrapy.spiders.Spider` subclass instances were never meant to
    work, and they were not working as one would expect: instead of using the
    passed :class:`~scrapy.spiders.Spider` subclass instance, their
    :class:`~scrapy.spiders.Spider.from_crawler` method was called to generate
    a new instance.

*   Non-default values for the :setting:`SCHEDULER_PRIORITY_QUEUE` setting
    may stop working. Scheduler priority queue classes now need to handle
    :class:`~scrapy.http.Request` objects instead of arbitrary Python data
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
    scheduling improvement on crawls targetting multiple web domains, at the
    cost of no :setting:`CONCURRENT_REQUESTS_PER_IP` support (:issue:`3520`)

*   A new :attr:`Request.cb_kwargs <scrapy.http.Request.cb_kwargs>` attribute
    provides a cleaner way to pass keyword arguments to callback methods
    (:issue:`1138`, :issue:`3563`)

*   A new :class:`JSONRequest <scrapy.http.JsonRequest>` class offers a more
    convenient way to build JSON requests (:issue:`3504`, :issue:`3505`)

*   A ``process_request`` callback passed to the :class:`~scrapy.spiders.Rule`
    ``__init__`` method now receives the :class:`~scrapy.http.Response` object that
    originated the request as its second argument (:issue:`3682`)

*   A new ``restrict_text`` parameter for the
    :attr:`LinkExtractor <scrapy.linkextractors.lxmlhtml.LxmlLinkExtractor>`
    ``__init__`` method allows filtering links by linking text (:issue:`3622`,
    :issue:`3635`)

*   A new :setting:`FEED_STORAGE_S3_ACL` setting allows defining a custom ACL
    for feeds exported to Amazon S3 (:issue:`3607`)

*   A new :setting:`FEED_STORAGE_FTP_ACTIVE` setting allows using FTP’s active
    connection mode for feeds exported to FTP servers (:issue:`3829`)

*   A new :setting:`METAREFRESH_IGNORE_TAGS` setting allows overriding which
    HTML tags are ignored when searching a response for HTML meta tags that
    trigger a redirect (:issue:`1422`, :issue:`3768`)

*   A new :reqmeta:`redirect_reasons` request meta key exposes the reason
    (status code, meta refresh) behind every followed redirect (:issue:`3581`,
    :issue:`3687`)

*   The ``SCRAPY_CHECK`` variable is now set to the ``true`` string during runs
    of the :command:`check` command, which allows :ref:`detecting contract
    check runs from code <detecting-contract-check-runs>` (:issue:`3704`,
    :issue:`3739`)

*   A new :meth:`Item.deepcopy() <scrapy.item.Item.deepcopy>` method makes it
    easier to :ref:`deep-copy items <copying-items>` (:issue:`1493`,
    :issue:`3671`)

*   :class:`~scrapy.extensions.corestats.CoreStats` also logs
    ``elapsed_time_seconds`` now (:issue:`3638`)

*   Exceptions from :class:`~scrapy.loader.ItemLoader` :ref:`input and output
    processors <topics-loaders-processors>` are now more verbose
    (:issue:`3836`, :issue:`3840`)

*   :class:`~scrapy.crawler.Crawler`,
    :class:`CrawlerRunner.crawl <scrapy.crawler.CrawlerRunner.crawl>` and
    :class:`CrawlerRunner.create_crawler <scrapy.crawler.CrawlerRunner.create_crawler>`
    now fail gracefully if they receive a :class:`~scrapy.spiders.Spider`
    subclass instance instead of the subclass itself (:issue:`2283`,
    :issue:`3610`, :issue:`3872`)


Bug fixes
~~~~~~~~~

*   :meth:`~scrapy.spidermiddlewares.SpiderMiddleware.process_spider_exception`
    is now also invoked for generators (:issue:`220`, :issue:`2061`)

*   System exceptions like KeyboardInterrupt_ are no longer caught
    (:issue:`3726`)

*   :meth:`ItemLoader.load_item() <scrapy.loader.ItemLoader.load_item>` no
    longer makes later calls to :meth:`ItemLoader.get_output_value()
    <scrapy.loader.ItemLoader.get_output_value>` or
    :meth:`ItemLoader.load_item() <scrapy.loader.ItemLoader.load_item>` return
    empty data (:issue:`3804`, :issue:`3819`)

*   The images pipeline (:class:`~scrapy.pipelines.images.ImagesPipeline`) no
    longer ignores these Amazon S3 settings: :setting:`AWS_ENDPOINT_URL`,
    :setting:`AWS_REGION_NAME`, :setting:`AWS_USE_SSL`, :setting:`AWS_VERIFY`
    (:issue:`3625`)

*   Fixed a memory leak in ``scrapy.pipelines.media.MediaPipeline`` affecting,
    for example, non-200 responses and exceptions from custom middlewares
    (:issue:`3813`)

*   Requests with private callbacks are now correctly unserialized from disk
    (:issue:`3790`)

*   :meth:`FormRequest.from_response() <scrapy.http.FormRequest.from_response>`
    now handles invalid methods like major web browsers (:issue:`3777`,
    :issue:`3794`)


Documentation
~~~~~~~~~~~~~

*   A new topic, :ref:`topics-dynamic-content`, covers recommended approaches
    to read dynamically-loaded data (:issue:`3703`)

*   :ref:`topics-broad-crawls` now features information about memory usage
    (:issue:`1264`, :issue:`3866`)

*   The documentation of :class:`~scrapy.spiders.Rule` now covers how to access
    the text of a link when using :class:`~scrapy.spiders.CrawlSpider`
    (:issue:`3711`, :issue:`3712`)

*   A new section, :ref:`httpcache-storage-custom`, covers writing a custom
    cache storage backend for
    :class:`~scrapy.downloadermiddlewares.httpcache.HttpCacheMiddleware`
    (:issue:`3683`, :issue:`3692`)

*   A new :ref:`FAQ <faq>` entry, :ref:`faq-split-item`, explains what to do
    when you want to split an item into multiple items from an item pipeline
    (:issue:`2240`, :issue:`3672`)

*   Updated the :ref:`FAQ entry about crawl order <faq-bfo-dfo>` to explain why
    the first few requests rarely follow the desired order (:issue:`1739`,
    :issue:`3621`)

*   The :setting:`LOGSTATS_INTERVAL` setting (:issue:`3730`), the
    :meth:`FilesPipeline.file_path <scrapy.pipelines.files.FilesPipeline.file_path>`
    and
    :meth:`ImagesPipeline.file_path <scrapy.pipelines.images.ImagesPipeline.file_path>`
    methods (:issue:`2253`, :issue:`3609`) and the
    :meth:`Crawler.stop() <scrapy.crawler.Crawler.stop>` method (:issue:`3842`)
    are now documented

*   Some parts of the documentation that were confusing or misleading are now
    clearer (:issue:`1347`, :issue:`1789`, :issue:`2289`, :issue:`3069`,
    :issue:`3615`, :issue:`3626`, :issue:`3668`, :issue:`3670`, :issue:`3673`,
    :issue:`3728`, :issue:`3762`, :issue:`3861`, :issue:`3882`)

*   Minor documentation fixes (:issue:`3648`, :issue:`3649`, :issue:`3662`,
    :issue:`3674`, :issue:`3676`, :issue:`3694`, :issue:`3724`, :issue:`3764`,
    :issue:`3767`, :issue:`3791`, :issue:`3797`, :issue:`3806`, :issue:`3812`)

.. _1.7-deprecation-removals:

Deprecation removals
~~~~~~~~~~~~~~~~~~~~

The following deprecated APIs have been removed (:issue:`3578`):

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

    *   ``HtmlXPathSelector`` (use :class:`~scrapy.selector.Selector`)

    *   ``XmlXPathSelector`` (use :class:`~scrapy.selector.Selector`)

    *   ``XPathSelector`` (use :class:`~scrapy.selector.Selector`)

    *   ``XPathSelectorList`` (use :class:`~scrapy.selector.Selector`)

*   From ``scrapy.selector.csstranslator``:

    *   ``ScrapyGenericTranslator`` (use parsel.csstranslator.GenericTranslator_)

    *   ``ScrapyHTMLTranslator`` (use parsel.csstranslator.HTMLTranslator_)

    *   ``ScrapyXPathExpr`` (use parsel.csstranslator.XPathExpr_)

*   From :class:`~scrapy.selector.Selector`:

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

The following deprecated settings have also been removed (:issue:`3578`):

*   ``SPIDER_MANAGER_CLASS`` (use :setting:`SPIDER_LOADER_CLASS`)


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
    code bases. Use :class:`~collections.ChainMap` instead. (:issue:`3878`)

*   The ``scrapy.utils.gz.is_gzipped`` function is deprecated. Use
    ``scrapy.utils.gz.gzip_magic_number`` instead.

.. _urllib3: https://urllib3.readthedocs.io/en/latest/index.html
.. _w3lib.html: https://w3lib.readthedocs.io/en/latest/w3lib.html#module-w3lib.html
.. _w3lib.http: https://w3lib.readthedocs.io/en/latest/w3lib.html#module-w3lib.http


Other changes
~~~~~~~~~~~~~

*   It is now possible to run all tests from the same tox_ environment in
    parallel; the documentation now covers :ref:`this and other ways to run
    tests <running-tests>` (:issue:`3707`)

*   It is now possible to generate an API documentation coverage report
    (:issue:`3806`, :issue:`3810`, :issue:`3860`)

*   The :ref:`documentation policies <documentation-policies>` now require
    docstrings_ (:issue:`3701`) that follow `PEP 257`_ (:issue:`3748`)

*   Internal fixes and cleanup (:issue:`3629`, :issue:`3643`, :issue:`3684`,
    :issue:`3698`, :issue:`3734`, :issue:`3735`, :issue:`3736`, :issue:`3737`,
    :issue:`3809`, :issue:`3821`, :issue:`3825`, :issue:`3827`, :issue:`3833`,
    :issue:`3857`, :issue:`3877`)

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
  storages and exporters (:issue:`1605`, :issue:`3348`).
* ``from_crawler`` support is added to dupefilters (:issue:`2956`); this allows
  to access e.g. settings or a spider from a dupefilter.
* :signal:`item_error` is fired when an error happens in a pipeline
  (:issue:`3256`);
* :signal:`request_reached_downloader` is fired when Downloader gets
  a new Request; this signal can be useful e.g. for custom Schedulers
  (:issue:`3393`).
* new SitemapSpider :meth:`~.SitemapSpider.sitemap_filter` method which allows
  to select sitemap entries based on their attributes in SitemapSpider
  subclasses (:issue:`3512`).
* Lazy loading of Downloader Handlers is now optional; this enables better
  initialization error handling in custom Downloader Handlers (:issue:`3394`).

New FilePipeline and MediaPipeline features
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

* Expose more options for S3FilesStore: :setting:`AWS_ENDPOINT_URL`,
  :setting:`AWS_USE_SSL`, :setting:`AWS_VERIFY`, :setting:`AWS_REGION_NAME`.
  For example, this allows to use alternative or self-hosted
  AWS-compatible providers (:issue:`2609`, :issue:`3548`).
* ACL support for Google Cloud Storage: :setting:`FILES_STORE_GCS_ACL` and
  :setting:`IMAGES_STORE_GCS_ACL` (:issue:`3199`).

``scrapy.contracts`` improvements
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

* Exceptions in contracts code are handled better (:issue:`3377`);
* ``dont_filter=True`` is used for contract requests, which allows to test
  different callbacks with the same URL (:issue:`3381`);
* ``request_cls`` attribute in Contract subclasses allow to use different
  Request classes in contracts, for example FormRequest (:issue:`3383`).
* Fixed errback handling in contracts, e.g. for cases where a contract
  is executed for URL which returns non-200 response (:issue:`3371`).

Usability improvements
~~~~~~~~~~~~~~~~~~~~~~

* more stats for RobotsTxtMiddleware (:issue:`3100`)
* INFO log level is used to show telnet host/port (:issue:`3115`)
* a message is added to IgnoreRequest in RobotsTxtMiddleware (:issue:`3113`)
* better validation of ``url`` argument in ``Response.follow`` (:issue:`3131`)
* non-zero exit code is returned from Scrapy commands when error happens
  on spider initialization (:issue:`3226`)
* Link extraction improvements: "ftp" is added to scheme list (:issue:`3152`);
  "flv" is added to common video extensions (:issue:`3165`)
* better error message when an exporter is disabled (:issue:`3358`);
* ``scrapy shell --help`` mentions syntax required for local files
  (``./file.html``) - :issue:`3496`.
* Referer header value is added to RFPDupeFilter log messages (:issue:`3588`)

Bug fixes
~~~~~~~~~

* fixed issue with extra blank lines in .csv exports under Windows
  (:issue:`3039`);
* proper handling of pickling errors in Python 3 when serializing objects
  for disk queues (:issue:`3082`)
* flags are now preserved when copying Requests (:issue:`3342`);
* FormRequest.from_response clickdata shouldn't ignore elements with
  ``input[type=image]`` (:issue:`3153`).
* FormRequest.from_response should preserve duplicate keys (:issue:`3247`)

Documentation improvements
~~~~~~~~~~~~~~~~~~~~~~~~~~

* Docs are re-written to suggest .get/.getall API instead of
  .extract/.extract_first. Also, :ref:`topics-selectors` docs are updated
  and re-structured to match latest parsel docs; they now contain more topics,
  such as :ref:`selecting-attributes` or :ref:`topics-selectors-css-extensions`
  (:issue:`3390`).
* :ref:`topics-developer-tools` is a new tutorial which replaces
  old Firefox and Firebug tutorials (:issue:`3400`).
* SCRAPY_PROJECT environment variable is documented (:issue:`3518`);
* troubleshooting section is added to install instructions (:issue:`3517`);
* improved links to beginner resources in the tutorial
  (:issue:`3367`, :issue:`3468`);
* fixed :setting:`RETRY_HTTP_CODES` default values in docs (:issue:`3335`);
* remove unused ``DEPTH_STATS`` option from docs (:issue:`3245`);
* other cleanups (:issue:`3347`, :issue:`3350`, :issue:`3445`, :issue:`3544`,
  :issue:`3605`).

Deprecation removals
~~~~~~~~~~~~~~~~~~~~

Compatibility shims for pre-1.0 Scrapy module names are removed
(:issue:`3318`):

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
* Deprecated ``CrawlerSettings`` class is removed (:issue:`3327`).
* Deprecated ``Settings.overrides`` and ``Settings.defaults`` attributes
  are removed (:issue:`3327`, :issue:`3359`).

Other improvements, cleanups
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

* All Scrapy tests now pass on Windows; Scrapy testing suite is executed
  in a Windows environment on CI (:issue:`3315`).
* Python 3.7 support (:issue:`3326`, :issue:`3150`, :issue:`3547`).
* Testing and CI fixes (:issue:`3526`, :issue:`3538`, :issue:`3308`,
  :issue:`3311`, :issue:`3309`, :issue:`3305`, :issue:`3210`, :issue:`3299`)
* ``scrapy.http.cookies.CookieJar.clear`` accepts "domain", "path" and "name"
  optional arguments (:issue:`3231`).
* additional files are included to sdist (:issue:`3495`);
* code style fixes (:issue:`3405`, :issue:`3304`);
* unneeded .strip() call is removed (:issue:`3519`);
* collections.deque is used to store MiddlewareManager methods instead
  of a list (:issue:`3476`)

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
  is fixed (:issue:`3281`);
* skipping of TLS validation errors is improved (:issue:`3166`);
* Ctrl-C handling is fixed in Python 3.5+ (:issue:`3096`);
* testing fixes (:issue:`3092`, :issue:`3263`);
* documentation improvements (:issue:`3058`, :issue:`3059`, :issue:`3089`,
  :issue:`3123`, :issue:`3127`, :issue:`3189`, :issue:`3224`, :issue:`3280`,
  :issue:`3279`, :issue:`3201`, :issue:`3260`, :issue:`3284`, :issue:`3298`,
  :issue:`3294`).


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
* Default Scrapy User-Agent now uses https link to scrapy.org (:issue:`2983`).
  **This is technically backward-incompatible**; override
  :setting:`USER_AGENT` if you relied on old value.
* Logging of settings overridden by ``custom_settings`` is fixed;
  **this is technically backward-incompatible** because the logger
  changes from ``[scrapy.utils.log]`` to ``[scrapy.crawler]``. If you're
  parsing Scrapy logs, please update your log parsers (:issue:`1343`).
* LinkExtractor now ignores ``m4v`` extension by default, this is change
  in behavior.
* 522 and 524 status codes are added to ``RETRY_HTTP_CODES`` (:issue:`2851`)

New features
~~~~~~~~~~~~

- Support ``<link>`` tags in ``Response.follow`` (:issue:`2785`)
- Support for ``ptpython`` REPL (:issue:`2654`)
- Google Cloud Storage support for FilesPipeline and ImagesPipeline
  (:issue:`2923`).
- New ``--meta`` option of the "scrapy parse" command allows to pass additional
  request.meta (:issue:`2883`)
- Populate spider variable when using ``shell.inspect_response`` (:issue:`2812`)
- Handle HTTP 308 Permanent Redirect (:issue:`2844`)
- Add 522 and 524 to ``RETRY_HTTP_CODES`` (:issue:`2851`)
- Log versions information at startup (:issue:`2857`)
- ``scrapy.mail.MailSender`` now works in Python 3 (it requires Twisted 17.9.0)
- Connections to proxy servers are reused (:issue:`2743`)
- Add template for a downloader middleware (:issue:`2755`)
- Explicit message for NotImplementedError when parse callback not defined
  (:issue:`2831`)
- CrawlerProcess got an option to disable installation of root log handler
  (:issue:`2921`)
- LinkExtractor now ignores ``m4v`` extension by default
- Better log messages for responses over :setting:`DOWNLOAD_WARNSIZE` and
  :setting:`DOWNLOAD_MAXSIZE` limits (:issue:`2927`)
- Show warning when a URL is put to ``Spider.allowed_domains`` instead of
  a domain (:issue:`2250`).

Bug fixes
~~~~~~~~~

- Fix logging of settings overridden by ``custom_settings``;
  **this is technically backward-incompatible** because the logger
  changes from ``[scrapy.utils.log]`` to ``[scrapy.crawler]``, so please
  update your log parsers if needed (:issue:`1343`)
- Default Scrapy User-Agent now uses https link to scrapy.org (:issue:`2983`).
  **This is technically backward-incompatible**; override
  :setting:`USER_AGENT` if you relied on old value.
- Fix PyPy and PyPy3 test failures, support them officially
  (:issue:`2793`, :issue:`2935`, :issue:`2990`, :issue:`3050`, :issue:`2213`,
  :issue:`3048`)
- Fix DNS resolver when ``DNSCACHE_ENABLED=False`` (:issue:`2811`)
- Add ``cryptography`` for Debian Jessie tox test env (:issue:`2848`)
- Add verification to check if Request callback is callable (:issue:`2766`)
- Port ``extras/qpsclient.py`` to Python 3 (:issue:`2849`)
- Use getfullargspec under the scenes for Python 3 to stop DeprecationWarning
  (:issue:`2862`)
- Update deprecated test aliases (:issue:`2876`)
- Fix ``SitemapSpider`` support for alternate links (:issue:`2853`)

Docs
~~~~

- Added missing bullet point for the ``AUTOTHROTTLE_TARGET_CONCURRENCY``
  setting. (:issue:`2756`)
- Update Contributing docs, document new support channels
  (:issue:`2762`, issue:`3038`)
- Include references to Scrapy subreddit in the docs
- Fix broken links; use https:// for external links
  (:issue:`2978`, :issue:`2982`, :issue:`2958`)
- Document CloseSpider extension better (:issue:`2759`)
- Use ``pymongo.collection.Collection.insert_one()`` in MongoDB example
  (:issue:`2781`)
- Spelling mistake and typos
  (:issue:`2828`, :issue:`2837`, :issue:`2884`, :issue:`2924`)
- Clarify ``CSVFeedSpider.headers`` documentation (:issue:`2826`)
- Document ``DontCloseSpider`` exception and clarify ``spider_idle``
  (:issue:`2791`)
- Update "Releases" section in README (:issue:`2764`)
- Fix rst syntax in ``DOWNLOAD_FAIL_ON_DATALOSS`` docs (:issue:`2763`)
- Small fix in description of startproject arguments (:issue:`2866`)
- Clarify data types in Response.body docs (:issue:`2922`)
- Add a note about ``request.meta['depth']`` to DepthMiddleware docs (:issue:`2374`)
- Add a note about ``request.meta['dont_merge_cookies']`` to CookiesMiddleware
  docs (:issue:`2999`)
- Up-to-date example of project structure (:issue:`2964`, :issue:`2976`)
- A better example of ItemExporters usage (:issue:`2989`)
- Document ``from_crawler`` methods for spider and downloader middlewares
  (:issue:`3019`)

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
  (:issue:`2537`, fixes :issue:`1941` and :issue:`1982`):
  **warning, this is technically backward-incompatible**
- Enable memusage extension by default (:issue:`2539`, fixes :issue:`2187`);
  **this is technically backward-incompatible** so please check if you have
  any non-default ``MEMUSAGE_***`` options set.
- ``EDITOR`` environment variable now takes precedence over ``EDITOR``
  option defined in settings.py (:issue:`1829`); Scrapy default settings
  no longer depend on environment variables. **This is technically a backward
  incompatible change**.
- ``Spider.make_requests_from_url`` is deprecated
  (:issue:`1728`, fixes :issue:`1495`).

New Features
~~~~~~~~~~~~

- Accept proxy credentials in :reqmeta:`proxy` request meta key (:issue:`2526`)
- Support `brotli`_-compressed content; requires optional `brotlipy`_
  (:issue:`2535`)
- New :ref:`response.follow <response-follow-example>` shortcut
  for creating requests (:issue:`1940`)
- Added ``flags`` argument and attribute to :class:`Request <scrapy.http.Request>`
  objects (:issue:`2047`)
- Support Anonymous FTP (:issue:`2342`)
- Added ``retry/count``, ``retry/max_reached`` and ``retry/reason_count/<reason>``
  stats to :class:`RetryMiddleware <scrapy.downloadermiddlewares.retry.RetryMiddleware>`
  (:issue:`2543`)
- Added ``httperror/response_ignored_count`` and ``httperror/response_ignored_status_count/<status>``
  stats to :class:`HttpErrorMiddleware <scrapy.spidermiddlewares.httperror.HttpErrorMiddleware>`
  (:issue:`2566`)
- Customizable :setting:`Referrer policy <REFERRER_POLICY>` in
  :class:`RefererMiddleware <scrapy.spidermiddlewares.referer.RefererMiddleware>`
  (:issue:`2306`)
- New ``data:`` URI download handler (:issue:`2334`, fixes :issue:`2156`)
- Log cache directory when HTTP Cache is used (:issue:`2611`, fixes :issue:`2604`)
- Warn users when project contains duplicate spider names (fixes :issue:`2181`)
- ``scrapy.utils.datatypes.CaselessDict`` now accepts ``Mapping`` instances and
  not only dicts (:issue:`2646`)
- :ref:`Media downloads <topics-media-pipeline>`, with
  :class:`~scrapy.pipelines.files.FilesPipeline` or
  :class:`~scrapy.pipelines.images.ImagesPipeline`, can now optionally handle
  HTTP redirects using the new :setting:`MEDIA_ALLOW_REDIRECTS` setting
  (:issue:`2616`, fixes :issue:`2004`)
- Accept non-complete responses from websites using a new
  :setting:`DOWNLOAD_FAIL_ON_DATALOSS` setting (:issue:`2590`, fixes :issue:`2586`)
- Optional pretty-printing of JSON and XML items via
  :setting:`FEED_EXPORT_INDENT` setting (:issue:`2456`, fixes :issue:`1327`)
- Allow dropping fields in ``FormRequest.from_response`` formdata when
  ``None`` value is passed (:issue:`667`)
- Per-request retry times with the new :reqmeta:`max_retry_times` meta key
  (:issue:`2642`)
- ``python -m scrapy`` as a more explicit alternative to ``scrapy`` command
  (:issue:`2740`)

.. _brotli: https://github.com/google/brotli
.. _brotlipy: https://github.com/python-hyper/brotlipy/

Bug fixes
~~~~~~~~~

- LinkExtractor now strips leading and trailing whitespaces from attributes
  (:issue:`2547`, fixes :issue:`1614`)
- Properly handle whitespaces in action attribute in
  :class:`~scrapy.http.FormRequest` (:issue:`2548`)
- Buffer CONNECT response bytes from proxy until all HTTP headers are received
  (:issue:`2495`, fixes :issue:`2491`)
- FTP downloader now works on Python 3, provided you use Twisted>=17.1
  (:issue:`2599`)
- Use body to choose response type after decompressing content (:issue:`2393`,
  fixes :issue:`2145`)
- Always decompress ``Content-Encoding: gzip`` at :class:`HttpCompressionMiddleware
  <scrapy.downloadermiddlewares.httpcompression.HttpCompressionMiddleware>` stage (:issue:`2391`)
- Respect custom log level in ``Spider.custom_settings`` (:issue:`2581`,
  fixes :issue:`1612`)
- 'make htmlview' fix for macOS (:issue:`2661`)
- Remove "commands" from the command list  (:issue:`2695`)
- Fix duplicate Content-Length header for POST requests with empty body (:issue:`2677`)
- Properly cancel large downloads, i.e. above :setting:`DOWNLOAD_MAXSIZE` (:issue:`1616`)
- ImagesPipeline: fixed processing of transparent PNG images with palette
  (:issue:`2675`)

Cleanups & Refactoring
~~~~~~~~~~~~~~~~~~~~~~

- Tests: remove temp files and folders (:issue:`2570`),
  fixed ProjectUtilsTest on macOS (:issue:`2569`),
  use portable pypy for Linux on Travis CI (:issue:`2710`)
- Separate building request from ``_requests_to_follow`` in CrawlSpider (:issue:`2562`)
- Remove “Python 3 progress” badge (:issue:`2567`)
- Add a couple more lines to ``.gitignore`` (:issue:`2557`)
- Remove bumpversion prerelease configuration (:issue:`2159`)
- Add codecov.yml file (:issue:`2750`)
- Set context factory implementation based on Twisted version (:issue:`2577`,
  fixes :issue:`2560`)
- Add omitted ``self`` arguments in default project middleware template (:issue:`2595`)
- Remove redundant ``slot.add_request()`` call in ExecutionEngine (:issue:`2617`)
- Catch more specific ``os.error`` exception in
  ``scrapy.pipelines.files.FSFilesStore`` (:issue:`2644`)
- Change "localhost" test server certificate (:issue:`2720`)
- Remove unused ``MEMUSAGE_REPORT`` setting (:issue:`2576`)

Documentation
~~~~~~~~~~~~~

- Binary mode is required for exporters (:issue:`2564`, fixes :issue:`2553`)
- Mention issue with :meth:`FormRequest.from_response
  <scrapy.http.FormRequest.from_response>` due to bug in lxml (:issue:`2572`)
- Use single quotes uniformly in templates (:issue:`2596`)
- Document :reqmeta:`ftp_user` and :reqmeta:`ftp_password` meta keys (:issue:`2587`)
- Removed section on deprecated ``contrib/`` (:issue:`2636`)
- Recommend Anaconda when installing Scrapy on Windows
  (:issue:`2477`, fixes :issue:`2475`)
- FAQ: rewrite note on Python 3 support on Windows (:issue:`2690`)
- Rearrange selector sections (:issue:`2705`)
- Remove ``__nonzero__`` from :class:`~scrapy.selector.SelectorList`
  docs (:issue:`2683`)
- Mention how to disable request filtering in documentation of
  :setting:`DUPEFILTER_CLASS` setting (:issue:`2714`)
- Add sphinx_rtd_theme to docs setup readme (:issue:`2668`)
- Open file in text mode in JSON item writer example (:issue:`2729`)
- Clarify ``allowed_domains`` example (:issue:`2670`)


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

- Preserve request class when converting to/from dicts (utils.reqser) (:issue:`2510`).
- Use consistent selectors for author field in tutorial (:issue:`2551`).
- Fix TLS compatibility in Twisted 17+ (:issue:`2558`)

.. _release-1.3.1:

Scrapy 1.3.1 (2017-02-08)
-------------------------

New features
~~~~~~~~~~~~

- Support ``'True'`` and ``'False'`` string values for boolean settings (:issue:`2519`);
  you can now do something like ``scrapy crawl myspider -s REDIRECT_ENABLED=False``.
- Support kwargs with ``response.xpath()`` to use :ref:`XPath variables <topics-selectors-xpath-variables>`
  and ad-hoc namespaces declarations ;
  this requires at least Parsel v1.1 (:issue:`2457`).
- Add support for Python 3.6 (:issue:`2485`).
- Run tests on PyPy (warning: some tests still fail, so PyPy is not supported yet).

Bug fixes
~~~~~~~~~

- Enforce ``DNS_TIMEOUT`` setting (:issue:`2496`).
- Fix :command:`view` command ; it was a regression in v1.3.0 (:issue:`2503`).
- Fix tests regarding ``*_EXPIRES settings`` with Files/Images pipelines (:issue:`2460`).
- Fix name of generated pipeline class when using basic project template (:issue:`2466`).
- Fix compatibility with Twisted 17+ (:issue:`2496`, :issue:`2528`).
- Fix ``scrapy.Item`` inheritance on Python 3.6 (:issue:`2511`).
- Enforce numeric values for components order in ``SPIDER_MIDDLEWARES``,
  ``DOWNLOADER_MIDDLEWARES``, ``EXTENIONS`` and ``SPIDER_CONTRACTS`` (:issue:`2420`).

Documentation
~~~~~~~~~~~~~

- Reword Code of Conduct section and upgrade to Contributor Covenant v1.4
  (:issue:`2469`).
- Clarify that passing spider arguments converts them to spider attributes
  (:issue:`2483`).
- Document ``formid`` argument on ``FormRequest.from_response()`` (:issue:`2497`).
- Add .rst extension to README files (:issue:`2507`).
- Mention LevelDB cache storage backend (:issue:`2525`).
- Use ``yield`` in sample callback code (:issue:`2533`).
- Add note about HTML entities decoding with ``.re()/.re_first()`` (:issue:`1704`).
- Typos (:issue:`2512`, :issue:`2534`, :issue:`2531`).

Cleanups
~~~~~~~~

- Remove redundant check in ``MetaRefreshMiddleware`` (:issue:`2542`).
- Faster checks in ``LinkExtractor`` for allow/deny patterns (:issue:`2538`).
- Remove dead code supporting old Twisted versions (:issue:`2544`).


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
  arguments (:issue:`2272`)
- ``scrapy fetch url``, ``scrapy shell url`` and ``fetch(url)`` inside
  Scrapy shell now follow HTTP redirections by default (:issue:`2290`);
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

- Fix a cryptic traceback when a pipeline fails on ``open_spider()`` (:issue:`2011`)
- Fix embedded IPython shell variables (fixing :issue:`396` that re-appeared
  in 1.2.0, fixed in :issue:`2418`)
- A couple of patches when dealing with robots.txt:

  - handle (non-standard) relative sitemap URLs (:issue:`2390`)
  - handle non-ASCII URLs and User-Agents in Python 2 (:issue:`2373`)

Documentation
~~~~~~~~~~~~~

- Document ``"download_latency"`` key in ``Request``'s ``meta`` dict (:issue:`2033`)
- Remove page on (deprecated & unsupported) Ubuntu packages from ToC (:issue:`2335`)
- A few fixed typos (:issue:`2346`, :issue:`2369`, :issue:`2369`, :issue:`2380`)
  and clarifications (:issue:`2354`, :issue:`2325`, :issue:`2414`)

Other changes
~~~~~~~~~~~~~

- Advertize `conda-forge`_ as Scrapy's official conda channel (:issue:`2387`)
- More helpful error messages when trying to use ``.css()`` or ``.xpath()``
  on non-Text Responses (:issue:`2264`)
- ``startproject`` command now generates a sample ``middlewares.py`` file (:issue:`2335`)
- Add more dependencies' version info in ``scrapy version`` verbose output (:issue:`2404`)
- Remove all ``*.pyc`` files from source distribution (:issue:`2386`)

.. _conda-forge: https://anaconda.org/conda-forge/scrapy


.. _release-1.2.1:

Scrapy 1.2.1 (2016-10-21)
-------------------------

Bug fixes
~~~~~~~~~

- Include OpenSSL's more permissive default ciphers when establishing
  TLS/SSL connections (:issue:`2314`).
- Fix "Location" HTTP header decoding on non-ASCII URL redirects (:issue:`2321`).

Documentation
~~~~~~~~~~~~~

- Fix JsonWriterPipeline example (:issue:`2302`).
- Various notes: :issue:`2330` on spider names,
  :issue:`2329` on middleware methods processing order,
  :issue:`2327` on getting multi-valued HTTP headers as lists.

Other changes
~~~~~~~~~~~~~

- Removed ``www.`` from ``start_urls`` in built-in spider templates (:issue:`2299`).


.. _release-1.2.0:

Scrapy 1.2.0 (2016-10-03)
-------------------------

New Features
~~~~~~~~~~~~

- New :setting:`FEED_EXPORT_ENCODING` setting to customize the encoding
  used when writing items to a file.
  This can be used to turn off ``\uXXXX`` escapes in JSON output.
  This is also useful for those wanting something else than UTF-8
  for XML or CSV output (:issue:`2034`).
- ``startproject`` command now supports an optional destination directory
  to override the default one based on the project name (:issue:`2005`).
- New :setting:`SCHEDULER_DEBUG` setting to log requests serialization
  failures (:issue:`1610`).
- JSON encoder now supports serialization of ``set`` instances (:issue:`2058`).
- Interpret ``application/json-amazonui-streaming`` as ``TextResponse`` (:issue:`1503`).
- ``scrapy`` is imported by default when using shell tools (:command:`shell`,
  :ref:`inspect_response <topics-shell-inspect-response>`) (:issue:`2248`).

Bug fixes
~~~~~~~~~

- DefaultRequestHeaders middleware now runs before UserAgent middleware
  (:issue:`2088`). **Warning: this is technically backward incompatible**,
  though we consider this a bug fix.
- HTTP cache extension and plugins that use the ``.scrapy`` data directory now
  work outside projects (:issue:`1581`).  **Warning: this is technically
  backward incompatible**, though we consider this a bug fix.
- ``Selector`` does not allow passing both ``response`` and ``text`` anymore
  (:issue:`2153`).
- Fixed logging of wrong callback name with ``scrapy parse`` (:issue:`2169`).
- Fix for an odd gzip decompression bug (:issue:`1606`).
- Fix for selected callbacks when using ``CrawlSpider`` with :command:`scrapy parse <parse>`
  (:issue:`2225`).
- Fix for invalid JSON and XML files when spider yields no items (:issue:`872`).
- Implement ``flush()`` fpr ``StreamLogger`` avoiding a warning in logs (:issue:`2125`).

Refactoring
~~~~~~~~~~~

- ``canonicalize_url`` has been moved to `w3lib.url`_ (:issue:`2168`).

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

- Grammar fixes: :issue:`2128`, :issue:`1566`.
- Download stats badge removed from README (:issue:`2160`).
- New Scrapy :ref:`architecture diagram <topics-architecture>` (:issue:`2165`).
- Updated ``Response`` parameters documentation (:issue:`2197`).
- Reworded misleading :setting:`RANDOMIZE_DOWNLOAD_DELAY` description (:issue:`2190`).
- Add StackOverflow as a support channel (:issue:`2257`).

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
  work as they did before 1.1.1 (:issue:`2243`, fixes :issue:`2198`)

Documentation
~~~~~~~~~~~~~

- :ref:`Overview <intro-overview>` and :ref:`tutorial <intro-tutorial>`
  rewritten to use http://toscrape.com websites
  (:issue:`2236`, :issue:`2249`, :issue:`2252`).

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

- Add "Host" header in CONNECT requests to HTTPS proxies (:issue:`2069`)
- Use response ``body`` when choosing response class
  (:issue:`2001`, fixes :issue:`2000`)
- Do not fail on canonicalizing URLs with wrong netlocs
  (:issue:`2038`, fixes :issue:`2010`)
- a few fixes for ``HttpCompressionMiddleware`` (and ``SitemapSpider``):

  - Do not decode HEAD responses (:issue:`2008`, fixes :issue:`1899`)
  - Handle charset parameter in gzip Content-Type header
    (:issue:`2050`, fixes :issue:`2049`)
  - Do not decompress gzip octet-stream responses
    (:issue:`2065`, fixes :issue:`2063`)

- Catch (and ignore with a warning) exception when verifying certificate
  against IP-address hosts (:issue:`2094`, fixes :issue:`2092`)
- Make ``FilesPipeline`` and ``ImagesPipeline`` backward compatible again
  regarding the use of legacy class attributes for customization
  (:issue:`1989`, fixes :issue:`1985`)


New features
~~~~~~~~~~~~

- Enable genspider command outside project folder (:issue:`2052`)
- Retry HTTPS CONNECT ``TunnelError`` by default (:issue:`1974`)


Documentation
~~~~~~~~~~~~~

- ``FEED_TEMPDIR`` setting at lexicographical position (:commit:`9b3c72c`)
- Use idiomatic ``.extract_first()`` in overview (:issue:`1994`)
- Update years in copyright notice (:commit:`c2c8036`)
- Add information and example on errbacks (:issue:`1995`)
- Use "url" variable in downloader middleware example (:issue:`2015`)
- Grammar fixes (:issue:`2054`, :issue:`2120`)
- New FAQ entry on using BeautifulSoup in spider callbacks (:issue:`2048`)
- Add notes about Scrapy not working on Windows with Python 3 (:issue:`2060`)
- Encourage complete titles in pull requests (:issue:`2026`)

Tests
~~~~~

- Upgrade py.test requirement on Travis CI and Pin pytest-cov to 2.2.1 (:issue:`2095`)

.. _release-1.1.0:

Scrapy 1.1.0 (2016-05-11)
-------------------------

This 1.1 release brings a lot of interesting features and bug fixes:

- Scrapy 1.1 has beta Python 3 support (requires Twisted >= 15.5). See
  :ref:`news_betapy3` for more details and some limitations.
- Hot new features:

  - Item loaders now support nested loaders (:issue:`1467`).
  - ``FormRequest.from_response`` improvements (:issue:`1382`, :issue:`1137`).
  - Added setting :setting:`AUTOTHROTTLE_TARGET_CONCURRENCY` and improved
    AutoThrottle docs (:issue:`1324`).
  - Added ``response.text`` to get body as unicode (:issue:`1730`).
  - Anonymous S3 connections (:issue:`1358`).
  - Deferreds in downloader middlewares (:issue:`1473`). This enables better
    robots.txt handling (:issue:`1471`).
  - HTTP caching now follows RFC2616 more closely, added settings
    :setting:`HTTPCACHE_ALWAYS_STORE` and
    :setting:`HTTPCACHE_IGNORE_RESPONSE_CACHE_CONTROLS` (:issue:`1151`).
  - Selectors were extracted to the parsel_ library (:issue:`1409`). This means
    you can use Scrapy Selectors without Scrapy and also upgrade the
    selectors engine without needing to upgrade Scrapy.
  - HTTPS downloader now does TLS protocol negotiation by default,
    instead of forcing TLS 1.0. You can also set the SSL/TLS method
    using the new :setting:`DOWNLOADER_CLIENT_TLS_METHOD`.

- These bug fixes may require your attention:

  - Don't retry bad requests (HTTP 400) by default (:issue:`1289`).
    If you need the old behavior, add ``400`` to :setting:`RETRY_HTTP_CODES`.
  - Fix shell files argument handling (:issue:`1710`, :issue:`1550`).
    If you try ``scrapy shell index.html`` it will try to load the URL http://index.html,
    use ``scrapy shell ./index.html`` to load a local file.
  - Robots.txt compliance is now enabled by default for newly-created projects
    (:issue:`1724`). Scrapy will also wait for robots.txt to be downloaded
    before proceeding with the crawl (:issue:`1735`). If you want to disable
    this behavior, update :setting:`ROBOTSTXT_OBEY` in ``settings.py`` file
    after creating a new project.
  - Exporters now work on unicode, instead of bytes by default (:issue:`1080`).
    If you use :class:`~scrapy.exporters.PythonItemExporter`, you may want to
    update your code to disable binary mode which is now deprecated.
  - Accept XML node names containing dots as valid (:issue:`1533`).
  - When uploading files or images to S3 (with ``FilesPipeline`` or
    ``ImagesPipeline``), the default ACL policy is now "private" instead
    of "public" **Warning: backward incompatible!**.
    You can use :setting:`FILES_STORE_S3_ACL` to change it.
  - We've reimplemented ``canonicalize_url()`` for more correct output,
    especially for URLs with non-ASCII characters (:issue:`1947`).
    This could change link extractors output compared to previous Scrapy versions.
    This may also invalidate some cache entries you could still have from pre-1.1 runs.
    **Warning: backward incompatible!**.

Keep reading for more details on other improvements and bug fixes.

.. _news_betapy3:

Beta Python 3 Support
~~~~~~~~~~~~~~~~~~~~~

We have been `hard at work to make Scrapy run on Python 3
<https://github.com/scrapy/scrapy/wiki/Python-3-Porting>`_. As a result, now
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

- Scrapy now has a `Code of Conduct`_ (:issue:`1681`).
- Command line tool now has completion for zsh (:issue:`934`).
- Improvements to ``scrapy shell``:

  - Support for bpython and configure preferred Python shell via
    ``SCRAPY_PYTHON_SHELL`` (:issue:`1100`, :issue:`1444`).
  - Support URLs without scheme (:issue:`1498`)
    **Warning: backward incompatible!**
  - Bring back support for relative file path (:issue:`1710`, :issue:`1550`).

- Added :setting:`MEMUSAGE_CHECK_INTERVAL_SECONDS` setting to change default check
  interval (:issue:`1282`).
- Download handlers are now lazy-loaded on first request using their
  scheme (:issue:`1390`, :issue:`1421`).
- HTTPS download handlers do not force TLS 1.0 anymore; instead,
  OpenSSL's ``SSLv23_method()/TLS_method()`` is used allowing to try
  negotiating with the remote hosts the highest TLS protocol version
  it can (:issue:`1794`, :issue:`1629`).
- ``RedirectMiddleware`` now skips the status codes from
  ``handle_httpstatus_list`` on spider attribute
  or in ``Request``'s ``meta`` key (:issue:`1334`, :issue:`1364`,
  :issue:`1447`).
- Form submission:

  - now works with ``<button>`` elements too (:issue:`1469`).
  - an empty string is now used for submit buttons without a value
    (:issue:`1472`)

- Dict-like settings now have per-key priorities
  (:issue:`1135`, :issue:`1149` and :issue:`1586`).
- Sending non-ASCII emails (:issue:`1662`)
- ``CloseSpider`` and ``SpiderState`` extensions now get disabled if no relevant
  setting is set (:issue:`1723`, :issue:`1725`).
- Added method ``ExecutionEngine.close`` (:issue:`1423`).
- Added method ``CrawlerRunner.create_crawler`` (:issue:`1528`).
- Scheduler priority queue can now be customized via
  :setting:`SCHEDULER_PRIORITY_QUEUE` (:issue:`1822`).
- ``.pps`` links are now ignored by default in link extractors (:issue:`1835`).
- temporary data folder for FTP and S3 feed storages can be customized
  using a new :setting:`FEED_TEMPDIR` setting (:issue:`1847`).
- ``FilesPipeline`` and ``ImagesPipeline`` settings are now instance attributes
  instead of class attributes, enabling spider-specific behaviors (:issue:`1891`).
- ``JsonItemExporter`` now formats opening and closing square brackets
  on their own line (first and last lines of output file) (:issue:`1950`).
- If available, ``botocore`` is used for ``S3FeedStorage``, ``S3DownloadHandler``
  and ``S3FilesStore`` (:issue:`1761`, :issue:`1883`).
- Tons of documentation updates and related fixes (:issue:`1291`, :issue:`1302`,
  :issue:`1335`, :issue:`1683`, :issue:`1660`, :issue:`1642`, :issue:`1721`,
  :issue:`1727`, :issue:`1879`).
- Other refactoring, optimizations and cleanup (:issue:`1476`, :issue:`1481`,
  :issue:`1477`, :issue:`1315`, :issue:`1290`, :issue:`1750`, :issue:`1881`).

.. _`Code of Conduct`: https://github.com/scrapy/scrapy/blob/master/CODE_OF_CONDUCT.md


Deprecations and Removals
~~~~~~~~~~~~~~~~~~~~~~~~~

- Added ``to_bytes`` and ``to_unicode``, deprecated ``str_to_unicode`` and
  ``unicode_to_str`` functions (:issue:`778`).
- ``binary_is_text`` is introduced, to replace use of ``isbinarytext``
  (but with inverse return value) (:issue:`1851`)
- The ``optional_features`` set has been removed (:issue:`1359`).
- The ``--lsprof`` command line option has been removed (:issue:`1689`).
  **Warning: backward incompatible**, but doesn't break user code.
- The following datatypes were deprecated (:issue:`1720`):

  + ``scrapy.utils.datatypes.MultiValueDictKeyError``
  + ``scrapy.utils.datatypes.MultiValueDict``
  + ``scrapy.utils.datatypes.SiteNode``

- The previously bundled ``scrapy.xlib.pydispatch`` library was deprecated and
  replaced by `pydispatcher <https://pypi.org/project/PyDispatcher/>`_.


Relocations
~~~~~~~~~~~

- ``telnetconsole`` was relocated to ``extensions/`` (:issue:`1524`).

  + Note: telnet is not enabled on Python 3
    (https://github.com/scrapy/scrapy/pull/1524#issuecomment-146985595)

.. _parsel: https://github.com/scrapy/parsel


Bugfixes
~~~~~~~~

- Scrapy does not retry requests that got a ``HTTP 400 Bad Request``
  response anymore (:issue:`1289`). **Warning: backward incompatible!**
- Support empty password for http_proxy config (:issue:`1274`).
- Interpret ``application/x-json`` as ``TextResponse`` (:issue:`1333`).
- Support link rel attribute with multiple values (:issue:`1201`).
- Fixed ``scrapy.http.FormRequest.from_response`` when there is a ``<base>``
  tag (:issue:`1564`).
- Fixed :setting:`TEMPLATES_DIR` handling (:issue:`1575`).
- Various ``FormRequest`` fixes (:issue:`1595`, :issue:`1596`, :issue:`1597`).
- Makes ``_monkeypatches`` more robust (:issue:`1634`).
- Fixed bug on ``XMLItemExporter`` with non-string fields in
  items (:issue:`1738`).
- Fixed startproject command in macOS (:issue:`1635`).
- Fixed :class:`~scrapy.exporters.PythonItemExporter` and CSVExporter for
  non-string item types (:issue:`1737`).
- Various logging related fixes (:issue:`1294`, :issue:`1419`, :issue:`1263`,
  :issue:`1624`, :issue:`1654`, :issue:`1722`, :issue:`1726` and :issue:`1303`).
- Fixed bug in ``utils.template.render_templatefile()`` (:issue:`1212`).
- sitemaps extraction from ``robots.txt`` is now case-insensitive (:issue:`1902`).
- HTTPS+CONNECT tunnels could get mixed up when using multiple proxies
  to same remote host (:issue:`1912`).

.. _release-1.0.7:

Scrapy 1.0.7 (2017-03-03)
-------------------------

- Packaging fix: disallow unsupported Twisted versions in setup.py

.. _release-1.0.6:

Scrapy 1.0.6 (2016-05-04)
-------------------------

- FIX: RetryMiddleware is now robust to non-standard HTTP status codes (:issue:`1857`)
- FIX: Filestorage HTTP cache was checking wrong modified time (:issue:`1875`)
- DOC: Support for Sphinx 1.4+ (:issue:`1893`)
- DOC: Consistency in selectors examples (:issue:`1869`)

.. _release-1.0.5:

Scrapy 1.0.5 (2016-02-04)
-------------------------

- FIX: [Backport] Ignore bogus links in LinkExtractors (fixes :issue:`907`, :commit:`108195e`)
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

- Python logging (:issue:`1060`, :issue:`1235`, :issue:`1236`, :issue:`1240`,
  :issue:`1259`, :issue:`1278`, :issue:`1286`)
- FEED_EXPORT_FIELDS option (:issue:`1159`, :issue:`1224`)
- Dns cache size and timeout options (:issue:`1132`)
- support namespace prefix in xmliter_lxml (:issue:`963`)
- Reactor threadpool max size setting (:issue:`1123`)
- Allow spiders to return dicts. (:issue:`1081`)
- Add Response.urljoin() helper (:issue:`1086`)
- look in ~/.config/scrapy.cfg for user config (:issue:`1098`)
- handle TLS SNI (:issue:`1101`)
- Selectorlist extract first (:issue:`624`, :issue:`1145`)
- Added JmesSelect (:issue:`1016`)
- add gzip compression to filesystem http cache backend (:issue:`1020`)
- CSS support in link extractors (:issue:`983`)
- httpcache dont_cache meta #19 #689 (:issue:`821`)
- add signal to be sent when request is dropped by the scheduler
  (:issue:`961`)
- avoid download large response (:issue:`946`)
- Allow to specify the quotechar in CSVFeedSpider (:issue:`882`)
- Add referer to "Spider error processing" log message (:issue:`795`)
- process robots.txt once (:issue:`896`)
- GSoC Per-spider settings (:issue:`854`)
- Add project name validation (:issue:`817`)
- GSoC API cleanup (:issue:`816`, :issue:`1128`, :issue:`1147`,
  :issue:`1148`, :issue:`1156`, :issue:`1185`, :issue:`1187`, :issue:`1258`,
  :issue:`1268`, :issue:`1276`, :issue:`1285`, :issue:`1284`)
- Be more responsive with IO operations (:issue:`1074` and :issue:`1075`)
- Do leveldb compaction for httpcache on closing (:issue:`1297`)

Deprecations and Removals

- Deprecate htmlparser link extractor (:issue:`1205`)
- remove deprecated code from FeedExporter (:issue:`1155`)
- a leftover for.15 compatibility (:issue:`925`)
- drop support for CONCURRENT_REQUESTS_PER_SPIDER (:issue:`895`)
- Drop old engine code (:issue:`911`)
- Deprecate SgmlLinkExtractor (:issue:`777`)

Relocations

- Move exporters/__init__.py to exporters.py (:issue:`1242`)
- Move base classes to their packages (:issue:`1218`, :issue:`1233`)
- Module relocation (:issue:`1181`, :issue:`1210`)
- rename SpiderManager to SpiderLoader (:issue:`1166`)
- Remove djangoitem (:issue:`1177`)
- remove scrapy deploy command (:issue:`1102`)
- dissolve contrib_exp (:issue:`1134`)
- Deleted bin folder from root, fixes #913 (:issue:`914`)
- Remove jsonrpc based webservice (:issue:`859`)
- Move Test cases under project root dir (:issue:`827`, :issue:`841`)
- Fix backward incompatibility for relocated paths in settings
  (:issue:`1267`)

Documentation

- CrawlerProcess documentation (:issue:`1190`)
- Favoring web scraping over screen scraping in the descriptions
  (:issue:`1188`)
- Some improvements for Scrapy tutorial (:issue:`1180`)
- Documenting Files Pipeline together with Images Pipeline (:issue:`1150`)
- deployment docs tweaks (:issue:`1164`)
- Added deployment section covering scrapyd-deploy and shub (:issue:`1124`)
- Adding more settings to project template (:issue:`1073`)
- some improvements to overview page (:issue:`1106`)
- Updated link in docs/topics/architecture.rst (:issue:`647`)
- DOC reorder topics (:issue:`1022`)
- updating list of Request.meta special keys (:issue:`1071`)
- DOC document download_timeout (:issue:`898`)
- DOC simplify extension docs (:issue:`893`)
- Leaks docs (:issue:`894`)
- DOC document from_crawler method for item pipelines (:issue:`904`)
- Spider_error doesn't support deferreds (:issue:`1292`)
- Corrections & Sphinx related fixes (:issue:`1220`, :issue:`1219`,
  :issue:`1196`, :issue:`1172`, :issue:`1171`, :issue:`1169`, :issue:`1160`,
  :issue:`1154`, :issue:`1127`, :issue:`1112`, :issue:`1105`, :issue:`1041`,
  :issue:`1082`, :issue:`1033`, :issue:`944`, :issue:`866`, :issue:`864`,
  :issue:`796`, :issue:`1260`, :issue:`1271`, :issue:`1293`, :issue:`1298`)

Bugfixes

- Item multi inheritance fix (:issue:`353`, :issue:`1228`)
- ItemLoader.load_item: iterate over copy of fields (:issue:`722`)
- Fix Unhandled error in Deferred (RobotsTxtMiddleware) (:issue:`1131`,
  :issue:`1197`)
- Force to read DOWNLOAD_TIMEOUT as int (:issue:`954`)
- scrapy.utils.misc.load_object should print full traceback (:issue:`902`)
- Fix bug for ".local" host name (:issue:`878`)
- Fix for Enabled extensions, middlewares, pipelines info not printed
  anymore (:issue:`879`)
- fix dont_merge_cookies bad behaviour when set to false on meta
  (:issue:`846`)

Python 3 In Progress Support

- disable scrapy.telnet if twisted.conch is not available (:issue:`1161`)
- fix Python 3 syntax errors in ajaxcrawl.py (:issue:`1162`)
- more python3 compatibility changes for urllib (:issue:`1121`)
- assertItemsEqual was renamed to assertCountEqual in Python 3.
  (:issue:`1070`)
- Import unittest.mock if available. (:issue:`1066`)
- updated deprecated cgi.parse_qsl to use six's parse_qsl (:issue:`909`)
- Prevent Python 3 port regressions (:issue:`830`)
- PY3: use MutableMapping for python 3 (:issue:`810`)
- PY3: use six.BytesIO and six.moves.cStringIO (:issue:`803`)
- PY3: fix xmlrpclib and email imports (:issue:`801`)
- PY3: use six for robotparser and urlparse (:issue:`800`)
- PY3: use six.iterkeys, six.iteritems, and tempfile (:issue:`799`)
- PY3: fix has_key and use six.moves.configparser (:issue:`798`)
- PY3: use six.moves.cPickle (:issue:`797`)
- PY3 make it possible to run some tests in Python3 (:issue:`776`)

Tests

- remove unnecessary lines from py3-ignores (:issue:`1243`)
- Fix remaining warnings from pytest while collecting tests (:issue:`1206`)
- Add docs build to travis (:issue:`1234`)
- TST don't collect tests from deprecated modules. (:issue:`1165`)
- install service_identity package in tests to prevent warnings
  (:issue:`1168`)
- Fix deprecated settings API in tests (:issue:`1152`)
- Add test for webclient with POST method and no body given (:issue:`1089`)
- py3-ignores.txt supports comments (:issue:`1044`)
- modernize some of the asserts (:issue:`835`)
- selector.__repr__ test (:issue:`779`)

Code refactoring

- CSVFeedSpider cleanup: use iterate_spider_output (:issue:`1079`)
- remove unnecessary check from scrapy.utils.spider.iter_spider_output
  (:issue:`1078`)
- Pydispatch pep8 (:issue:`992`)
- Removed unused 'load=False' parameter from walk_modules() (:issue:`871`)
- For consistency, use ``job_dir`` helper in ``SpiderState`` extension.
  (:issue:`805`)
- rename "sflo" local variables to less cryptic "log_observer" (:issue:`775`)

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

- pem file is used by mockserver and required by scrapy bench (:commit:`5eddc68`)
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
- Updated input/ouput processor example according to #560. (:commit:`f7c4ea8`)
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

- Improve Scrapy top-level namespace (:issue:`494`, :issue:`684`)
- Add selector shortcuts to responses (:issue:`554`, :issue:`690`)
- Add new lxml based LinkExtractor to replace unmaintained SgmlLinkExtractor
  (:issue:`559`, :issue:`761`, :issue:`763`)
- Cleanup settings API - part of per-spider settings **GSoC project** (:issue:`737`)
- Add UTF8 encoding header to templates (:issue:`688`, :issue:`762`)
- Telnet console now binds to 127.0.0.1 by default (:issue:`699`)
- Update Debian/Ubuntu install instructions (:issue:`509`, :issue:`549`)
- Disable smart strings in lxml XPath evaluations (:issue:`535`)
- Restore filesystem based cache as default for http
  cache middleware (:issue:`541`, :issue:`500`, :issue:`571`)
- Expose current crawler in Scrapy shell (:issue:`557`)
- Improve testsuite comparing CSV and XML exporters (:issue:`570`)
- New ``offsite/filtered`` and ``offsite/domains`` stats (:issue:`566`)
- Support process_links as generator in CrawlSpider (:issue:`555`)
- Verbose logging and new stats counters for DupeFilter (:issue:`553`)
- Add a mimetype parameter to ``MailSender.send()`` (:issue:`602`)
- Generalize file pipeline log messages (:issue:`622`)
- Replace unencodeable codepoints with html entities in SGMLLinkExtractor (:issue:`565`)
- Converted SEP documents to rst format (:issue:`629`, :issue:`630`,
  :issue:`638`, :issue:`632`, :issue:`636`, :issue:`640`, :issue:`635`,
  :issue:`634`, :issue:`639`, :issue:`637`, :issue:`631`, :issue:`633`,
  :issue:`641`, :issue:`642`)
- Tests and docs for clickdata's nr index in FormRequest (:issue:`646`, :issue:`645`)
- Allow to disable a downloader handler just like any other component (:issue:`650`)
- Log when a request is discarded after too many redirections (:issue:`654`)
- Log error responses if they are not handled by spider callbacks
  (:issue:`612`, :issue:`656`)
- Add content-type check to http compression mw (:issue:`193`, :issue:`660`)
- Run pypy tests using latest pypi from ppa (:issue:`674`)
- Run test suite using pytest instead of trial (:issue:`679`)
- Build docs and check for dead links in tox environment (:issue:`687`)
- Make scrapy.version_info a tuple of integers (:issue:`681`, :issue:`692`)
- Infer exporter's output format from filename extensions
  (:issue:`546`, :issue:`659`, :issue:`760`)
- Support case-insensitive domains in ``url_is_from_any_domain()`` (:issue:`693`)
- Remove pep8 warnings in project and spider templates (:issue:`698`)
- Tests and docs for ``request_fingerprint`` function (:issue:`597`)
- Update SEP-19 for GSoC project ``per-spider settings`` (:issue:`705`)
- Set exit code to non-zero when contracts fails (:issue:`727`)
- Add a setting to control what class is instantiated as Downloader component
  (:issue:`738`)
- Pass response in ``item_dropped`` signal (:issue:`724`)
- Improve ``scrapy check`` contracts command (:issue:`733`, :issue:`752`)
- Document ``spider.closed()`` shortcut (:issue:`719`)
- Document ``request_scheduled`` signal (:issue:`746`)
- Add a note about reporting security issues (:issue:`697`)
- Add LevelDB http cache storage backend (:issue:`626`, :issue:`500`)
- Sort spider list output of ``scrapy list`` command (:issue:`742`)
- Multiple documentation enhancements and fixes
  (:issue:`575`, :issue:`587`, :issue:`590`, :issue:`596`, :issue:`610`,
  :issue:`617`, :issue:`618`, :issue:`627`, :issue:`613`, :issue:`643`,
  :issue:`654`, :issue:`675`, :issue:`663`, :issue:`711`, :issue:`714`)

Bugfixes
~~~~~~~~

- Encode unicode URL value when creating Links in RegexLinkExtractor (:issue:`561`)
- Ignore None values in ItemLoader processors (:issue:`556`)
- Fix link text when there is an inner tag in SGMLLinkExtractor and
  HtmlParserLinkExtractor (:issue:`485`, :issue:`574`)
- Fix wrong checks on subclassing of deprecated classes
  (:issue:`581`, :issue:`584`)
- Handle errors caused by inspect.stack() failures (:issue:`582`)
- Fix a reference to unexistent engine attribute (:issue:`593`, :issue:`594`)
- Fix dynamic itemclass example usage of type() (:issue:`603`)
- Use lucasdemarchi/codespell to fix typos (:issue:`628`)
- Fix default value of attrs argument in SgmlLinkExtractor to be tuple (:issue:`661`)
- Fix XXE flaw in sitemap reader (:issue:`676`)
- Fix engine to support filtered start requests (:issue:`707`)
- Fix offsite middleware case on urls with no hostnames (:issue:`745`)
- Testsuite doesn't require PIL anymore (:issue:`585`)


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
- replace unencodable codepoints with html entities. fixes #562 and #285 (:commit:`5f87b17`)
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

- [**Backward incompatible**] Switched HTTPCacheMiddleware backend to filesystem (:issue:`541`)
  To restore old backend set ``HTTPCACHE_STORAGE`` to ``scrapy.contrib.httpcache.DbmCacheStorage``
- Proxy \https:// urls using CONNECT method (:issue:`392`, :issue:`397`)
- Add a middleware to crawl ajax crawleable pages as defined by google (:issue:`343`)
- Rename scrapy.spider.BaseSpider to scrapy.spider.Spider (:issue:`510`, :issue:`519`)
- Selectors register EXSLT namespaces by default (:issue:`472`)
- Unify item loaders similar to selectors renaming (:issue:`461`)
- Make ``RFPDupeFilter`` class easily subclassable (:issue:`533`)
- Improve test coverage and forthcoming Python 3 support (:issue:`525`)
- Promote startup info on settings and middleware to INFO level (:issue:`520`)
- Support partials in ``get_func_args`` util (:issue:`506`, issue:`504`)
- Allow running individual tests via tox (:issue:`503`)
- Update extensions ignored by link extractors (:issue:`498`)
- Add middleware methods to get files/images/thumbs paths (:issue:`490`)
- Improve offsite middleware tests (:issue:`478`)
- Add a way to skip default Referer header set by RefererMiddleware (:issue:`475`)
- Do not send ``x-gzip`` in default ``Accept-Encoding`` header (:issue:`469`)
- Support defining http error handling using settings (:issue:`466`)
- Use modern python idioms wherever you find legacies (:issue:`497`)
- Improve and correct documentation
  (:issue:`527`, :issue:`524`, :issue:`521`, :issue:`517`, :issue:`512`, :issue:`505`,
  :issue:`502`, :issue:`489`, :issue:`465`, :issue:`460`, :issue:`425`, :issue:`536`)

Fixes
~~~~~

- Update Selector class imports in CrawlSpider template (:issue:`484`)
- Fix unexistent reference to ``engine.slots`` (:issue:`464`)
- Do not try to call ``body_as_unicode()`` on a non-TextResponse instance (:issue:`462`)
- Warn when subclassing XPathItemLoader, previously it only warned on
  instantiation. (:issue:`523`)
- Warn when subclassing XPathSelector, previously it only warned on
  instantiation. (:issue:`537`)
- Multiple fixes to memory stats (:issue:`531`, :issue:`530`, :issue:`529`)
- Fix overriding url in ``FormRequest.from_response()`` (:issue:`507`)
- Fix tests runner under pip 1.5 (:issue:`513`)
- Fix logging error when spider name is unicode (:issue:`479`)

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

- New Selector's API including CSS selectors (:issue:`395` and :issue:`426`),
- Request/Response url/body attributes are now immutable
  (modifying them had been deprecated for a long time)
- :setting:`ITEM_PIPELINES` is now defined as a dict (instead of a list)
- Sitemap spider can fetch alternate URLs (:issue:`360`)
- ``Selector.remove_namespaces()`` now remove namespaces from element's attributes. (:issue:`416`)
- Paved the road for Python 3.3+ (:issue:`435`, :issue:`436`, :issue:`431`, :issue:`452`)
- New item exporter using native python types with nesting support (:issue:`366`)
- Tune HTTP1.1 pool size so it matches concurrency defined by settings (:commit:`b43b5f575`)
- scrapy.mail.MailSender now can connect over TLS or upgrade using STARTTLS (:issue:`327`)
- New FilesPipeline with functionality factored out from ImagesPipeline (:issue:`370`, :issue:`409`)
- Recommend Pillow instead of PIL for image handling (:issue:`317`)
- Added Debian packages for Ubuntu Quantal and Raring (:commit:`86230c0`)
- Mock server (used for tests) can listen for HTTPS requests (:issue:`410`)
- Remove multi spider support from multiple core components
  (:issue:`422`, :issue:`421`, :issue:`420`, :issue:`419`, :issue:`423`, :issue:`418`)
- Travis-CI now tests Scrapy changes against development versions of ``w3lib`` and ``queuelib`` python packages.
- Add pypy 2.1 to continuous integration tests (:commit:`ecfa7431`)
- Pylinted, pep8 and removed old-style exceptions from source (:issue:`430`, :issue:`432`)
- Use importlib for parametric imports (:issue:`445`)
- Handle a regression introduced in Python 2.7.5 that affects XmlItemExporter (:issue:`372`)
- Bugfix crawling shutdown on SIGINT (:issue:`450`)
- Do not submit ``reset`` type inputs in FormRequest.from_response (:commit:`b326b87`)
- Do not silence download errors when request errback raises an exception (:commit:`684cfc0`)

Bugfixes
~~~~~~~~

- Fix tests under Django 1.6 (:commit:`b6bed44c`)
- Lot of bugfixes to retry middleware under disconnections using HTTP 1.1 download handler
- Fix inconsistencies among Twisted releases (:issue:`406`)
- Fix Scrapy shell bugs (:issue:`418`, :issue:`407`)
- Fix invalid variable name in setup.py (:issue:`429`)
- Fix tutorial references (:issue:`387`)
- Improve request-response docs (:issue:`391`)
- Improve best practices docs (:issue:`399`, :issue:`400`, :issue:`401`, :issue:`402`)
- Improve django integration docs (:issue:`404`)
- Document ``bindaddress`` request meta (:commit:`37c24e01d7`)
- Improve ``Request`` class documentation (:issue:`226`)

Other
~~~~~

- Dropped Python 2.6 support (:issue:`448`)
- Add :doc:`cssselect <cssselect:index>` python package as install dependency
- Drop libxml2 and multi selector's backend support, `lxml`_ is required from now on.
- Minimum Twisted version increased to 10.0.0, dropped Twisted 8.0 support.
- Running test suite now requires ``mock`` python library (:issue:`390`)


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
- Fix start_requests laziness and early hangs (:commit:`89faf52`)

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
  crawler process(:issue:`339`)

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
- Handle GET parameters for AJAX crawleable urls (:commit:`3fe2a32`)
- Use lxml recover option to parse sitemaps (:issue:`347`)
- Bugfix cookie merging by hostname and not by netloc (:issue:`352`)
- Support disabling ``HttpCompressionMiddleware`` using a flag setting (:issue:`359`)
- Support xml namespaces using ``iternodes`` parser in ``XMLFeedSpider`` (:issue:`12`)
- Support ``dont_cache`` request meta flag (:issue:`19`)
- Bugfix ``scrapy.utils.gz.gunzip`` broken by changes in python 2.7.4 (:commit:`4dc76e`)
- Bugfix url encoding on ``SgmlLinkExtractor`` (:issue:`24`)
- Bugfix ``TakeFirst`` processor shouldn't discard zero (0) value (:issue:`59`)
- Support nested items in xml exporter (:issue:`66`)
- Improve cookies handling performance (:issue:`77`)
- Log dupe filtered requests once (:issue:`105`)
- Split redirection middleware into status and meta based middlewares (:issue:`78`)
- Use HTTP1.1 as default downloader handler (:issue:`109` and :issue:`318`)
- Support xpath form selection on ``FormRequest.from_response`` (:issue:`185`)
- Bugfix unicode decoding error on ``SgmlLinkExtractor`` (:issue:`199`)
- Bugfix signal dispatching on pypi interpreter (:issue:`205`)
- Improve request delay and concurrency handling (:issue:`206`)
- Add RFC2616 cache policy to ``HttpCacheMiddleware`` (:issue:`212`)
- Allow customization of messages logged by engine (:issue:`214`)
- Multiples improvements to ``DjangoItem`` (:issue:`217`, :issue:`218`, :issue:`221`)
- Extend Scrapy commands using setuptools entry points (:issue:`260`)
- Allow spider ``allowed_domains`` value to be set/tuple (:issue:`261`)
- Support ``settings.getdict`` (:issue:`269`)
- Simplify internal ``scrapy.core.scraper`` slot handling (:issue:`271`)
- Added ``Item.copy`` (:issue:`290`)
- Collect idle downloader slots (:issue:`297`)
- Add ``ftp://`` scheme downloader handler (:issue:`329`)
- Added downloader benchmark webserver and spider tools :ref:`benchmarking`
- Moved persistent (on disk) queues to a separate project (queuelib_) which Scrapy now depends on
- Add Scrapy commands using external libraries (:issue:`260`)
- Added ``--pdb`` option to ``scrapy`` command line tool
- Added :meth:`XPathSelector.remove_namespaces <scrapy.selector.Selector.remove_namespaces>` which allows to remove all namespaces from XML documents for convenience (to work with namespace-less XPaths). Documented in :ref:`topics-selectors`.
- Several improvements to spider contracts
- New default middleware named MetaRefreshMiddldeware that handles meta-refresh html tag redirections,
- MetaRefreshMiddldeware and RedirectMiddleware have different priorities to address #62
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
- added :meth:`~scrapy.spidermiddlewares.SpiderMiddleware.process_start_requests` method to spider middlewares
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
- dropped support for Python 2.5. See https://blog.scrapinghub.com/2012/02/27/scrapy-0-15-dropping-support-for-python-2-5/
- dropped support for Twisted 2.5
- added :setting:`REFERER_ENABLED` setting, to control referer middleware
- changed default user agent to: ``Scrapy/VERSION (+http://scrapy.org)``
- removed (undocumented) ``HTMLImageLinkExtractor`` class from ``scrapy.contrib.linkextractors.image``
- removed per-spider settings (to be replaced by instantiating multiple crawler objects)
- ``USER_AGENT`` spider attribute will no longer work, use ``user_agent`` attribute instead
- ``DOWNLOAD_TIMEOUT`` spider attribute will no longer work, use ``download_timeout`` attribute instead
- removed ``ENCODING_ALIASES`` setting, as encoding auto-detection has been moved to the `w3lib`_ library
- promoted :ref:`topics-djangoitem` to main contrib
- LogFormatter method now return dicts(instead of strings) to support lazy formatting (:issue:`164`, :commit:`dcef7b0`)
- downloader handlers (:setting:`DOWNLOAD_HANDLERS` setting) now receive settings as the first argument of the ``__init__`` method
- replaced memory usage acounting with (more portable) `resource`_ module, removed ``scrapy.utils.memory`` module
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
- Catch start_requests iterator errors. refs #83 (:commit:`454a21d`)
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

- Support for `AJAX crawleable urls`_
- New persistent scheduler that stores requests on disk, allowing to suspend and resume crawls (:rev:`2737`)
- added ``-o`` option to ``scrapy crawl``, a shortcut for dumping scraped items into a file (or standard output using ``-``)
- Added support for passing custom settings to Scrapyd ``schedule.json`` api (:rev:`2779`, :rev:`2783`)
- New ``ChunkedTransferMiddleware`` (enabled by default) to support `chunked transfer encoding`_ (:rev:`2769`)
- Add boto 2.0 support for S3 downloader handler (:rev:`2763`)
- Added `marshal`_ to formats supported by feed exports (:rev:`2744`)
- In request errbacks, offending requests are now received in ``failure.request`` attribute (:rev:`2738`)
- Big downloader refactoring to support per domain/ip concurrency limits (:rev:`2732`)
   - ``CONCURRENT_REQUESTS_PER_SPIDER`` setting has been deprecated and replaced by:
      - :setting:`CONCURRENT_REQUESTS`, :setting:`CONCURRENT_REQUESTS_PER_DOMAIN`, :setting:`CONCURRENT_REQUESTS_PER_IP`
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
- Removed scheduler middleware to simplify architecture. Duplicates filter is now done in the scheduler itself, using the same dupe fltering class as before (``DUPEFILTER_CLASS`` setting) (:rev:`2640`)
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
- It stores one log file per spider run, and rotate them keeping the lastest 5 logs per spider (by default)
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
- Splitted Debian package into two packages - the library and the service (#187)
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
- Offsite middelware doesn't filter out any request coming from a spider that doesn't have a allowed_domains attribute (#225)
- Removed Spider Manager ``load()`` method. Now spiders are loaded in the ``__init__`` method itself.
- Changes to Scrapy Manager (now called "Crawler"):
   - ``scrapy.core.manager.ScrapyManager`` class renamed to ``scrapy.crawler.Crawler``
   - ``scrapy.core.manager.scrapymanager`` singleton moved to ``scrapy.project.crawler``
- Moved module: ``scrapy.contrib.spidermanager`` to ``scrapy.spidermanager``
- Spider Manager singleton moved from ``scrapy.spider.spiders`` to the ``spiders` attribute of ``scrapy.project.crawler`` singleton.
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
- HTTP Cache middleware has been heavilty refactored, retaining the same functionality except for the domain sectorization which was removed. (:rev:`1843` )
- Renamed exception: ``DontCloseDomain`` to ``DontCloseSpider`` (:rev:`1859` | #120)
- Renamed extension: ``DelayedCloseDomain`` to ``SpiderCloseDelay`` (:rev:`1861` | #121)
- Removed obsolete ``scrapy.utils.markup.remove_escape_chars`` function - use ``scrapy.utils.markup.replace_escape_chars`` instead (:rev:`1865`)

Scrapy 0.7
----------

First release of Scrapy.


.. _AJAX crawleable urls: https://developers.google.com/search/docs/ajax-crawling/docs/getting-started?csw=1
.. _botocore: https://github.com/boto/botocore
.. _chunked transfer encoding: https://en.wikipedia.org/wiki/Chunked_transfer_encoding
.. _ClientForm: http://wwwsearch.sourceforge.net/old/ClientForm/
.. _Creating a pull request: https://help.github.com/en/articles/creating-a-pull-request
.. _cryptography: https://cryptography.io/en/latest/
.. _docstrings: https://docs.python.org/3/glossary.html#term-docstring
.. _KeyboardInterrupt: https://docs.python.org/3/library/exceptions.html#KeyboardInterrupt
.. _LevelDB: https://github.com/google/leveldb
.. _lxml: https://lxml.de/
.. _marshal: https://docs.python.org/2/library/marshal.html
.. _parsel.csstranslator.GenericTranslator: https://parsel.readthedocs.io/en/latest/parsel.html#parsel.csstranslator.GenericTranslator
.. _parsel.csstranslator.HTMLTranslator: https://parsel.readthedocs.io/en/latest/parsel.html#parsel.csstranslator.HTMLTranslator
.. _parsel.csstranslator.XPathExpr: https://parsel.readthedocs.io/en/latest/parsel.html#parsel.csstranslator.XPathExpr
.. _PEP 257: https://www.python.org/dev/peps/pep-0257/
.. _Pillow: https://python-pillow.org/
.. _pyOpenSSL: https://www.pyopenssl.org/en/stable/
.. _queuelib: https://github.com/scrapy/queuelib
.. _registered with IANA: https://www.iana.org/assignments/media-types/media-types.xhtml
.. _resource: https://docs.python.org/2/library/resource.html
.. _robots.txt: https://www.robotstxt.org/
.. _scrapely: https://github.com/scrapy/scrapely
.. _service_identity: https://service-identity.readthedocs.io/en/stable/
.. _six: https://six.readthedocs.io/
.. _tox: https://pypi.org/project/tox/
.. _Twisted: https://twistedmatrix.com/trac/
.. _Twisted - hello, asynchronous programming: http://jessenoller.com/blog/2009/02/11/twisted-hello-asynchronous-programming/
.. _w3lib: https://github.com/scrapy/w3lib
.. _w3lib.encoding: https://github.com/scrapy/w3lib/blob/master/w3lib/encoding.py
.. _What is cacheable: https://www.w3.org/Protocols/rfc2616/rfc2616-sec14.html#sec14.9.1
.. _zope.interface: https://zopeinterface.readthedocs.io/en/latest/
.. _Zsh: https://www.zsh.org/
