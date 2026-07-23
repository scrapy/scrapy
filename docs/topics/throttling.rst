.. _throttling:

==========
Throttling
==========

.. versionadded:: VERSION

Sending too many requests too quickly can `overwhelm websites`_.
:ref:`Throttling <basic-throttling>` and :ref:`backoff <backoff>` aim to
prevent that.

.. _overwhelm websites: https://en.wikipedia.org/wiki/Denial-of-service_attack

.. _basic-throttling:

Concurrency and delay
=====================

Requests are throttled on a **per-domain basis** by default [1]_. This allows
efficient crawling of multiple sites simultaneously.

Each domain and subdomain is treated separately: requests to
``books.toscrape.com`` and ``quotes.toscrape.com`` each have their own
throttling limits, as do ``toscrape.com`` and ``books.toscrape.com``.

The main throttling :ref:`settings <topics-settings>` are:

-   .. setting:: THROTTLER_SCOPE_CONCURRENCY

    :setting:`THROTTLER_SCOPE_CONCURRENCY` (default: ``1``)

    Default maximum number of simultaneous requests per :ref:`throttler scope
    <throttler-scopes>`. Requests are grouped by domain by default, so this is
    the maximum number of simultaneous requests per domain.

-   .. setting:: DOWNLOAD_DELAY

    :setting:`DOWNLOAD_DELAY` (default: ``1``
    (:ref:`fallback <default-settings>`: ``0``))

    Minimum seconds between any two requests to the same domain.

    To target a specific number of requests per minute (RPM) *per domain*, set
    this to ``60 / RPM``. For example, ``DOWNLOAD_DELAY = 1.0`` for 60 RPM, or
    ``DOWNLOAD_DELAY = 2.0`` for 30 RPM.

When configuring these settings, note that:

-   :setting:`CONCURRENT_REQUESTS` caps :setting:`THROTTLER_SCOPE_CONCURRENCY`.

-   If ``DOWNLOAD_DELAY`` ≥ response time, concurrency is effectively ``1``,
    because the next request to the domain is not sent until the delay elapses,
    by which time the previous response has already arrived.

.. [1] You can :ref:`customize <throttler-scopes>` how requests are grouped
    for throttling, but domain-based throttling works well in most cases. For
    more complex domain grouping strategies, see
    :ref:`alternative-domain-throttling`.

.. setting:: THROTTLER_SCOPES

.. _per-domain-throttling:

Per-domain throttling
=====================

The :setting:`THROTTLER_SCOPES` setting allows you to customize throttling
behavior for specific domains [1]_.

It is a dict that maps scope IDs to
:class:`~scrapy.throttler.ThrottlerScopeConfig` dicts. It is empty by default.

For example, you can crawl domains you own (or that are meant for scraping)
faster, while the :ref:`conservative defaults <basic-throttling>` still apply to
other domains:

.. code-block:: python

    THROTTLER_SCOPES = {
        "books.toscrape.com": {"concurrency": 32, "delay": 0.1},
        "quotes.toscrape.com": {"concurrency": 16, "delay": 0.1},
    }

Additional keys like ``"jitter"`` and ``"backoff"`` can be used here and are
covered later on.

.. _backoff:

Backoff
=======

When servers respond with rate limiting errors (like HTTP 429) or network
timeouts occur, request rate is automatically reduced using `exponential
backoff`_.

.. _exponential backoff: https://en.wikipedia.org/wiki/Exponential_backoff

The key settings are:

-   .. setting:: BACKOFF_HTTP_CODES

    :setting:`BACKOFF_HTTP_CODES` (default: ``[429, 502, 503, 504, 520, 521, 522, 523, 524]``)

    HTTP response status codes that trigger backoff. Can be overridden per
    scope with the ``http_codes`` key (see :ref:`per-scope-backoff`).

-   .. setting:: BACKOFF_DELAY_FACTOR

    :setting:`BACKOFF_DELAY_FACTOR` (default: ``2.0``)

    Factor by which the delay of a scope is multiplied on each backoff step
    (2×, 4×, 8×, etc.).

-   .. setting:: BACKOFF_MAX_DELAY

    :setting:`BACKOFF_MAX_DELAY` (default: ``300.0``)

    Maximum delay, in seconds, that backoff can reach. Also caps
    :ref:`Retry-After <retry-after>` and :ref:`RateLimit-Reset
    <rate-limiting-headers>` delays.

See :ref:`throttling-settings` for :setting:`BACKOFF_EXCEPTIONS`,
:setting:`BACKOFF_JITTER`, :setting:`BACKOFF_MIN_DELAY` and
:setting:`BACKOFF_WINDOW`.

.. _backoff-algorithm:

How backoff works
-----------------

Every :ref:`throttler scope <throttler-scopes>` keeps a current delay that
starts at its configured ``"delay"`` (:setting:`DOWNLOAD_DELAY` by default).

A **backoff trigger** is a response whose status code is in
:setting:`BACKOFF_HTTP_CODES` or a download exception whose type is in
:setting:`BACKOFF_EXCEPTIONS`. Both can be :ref:`overridden per scope
<per-scope-backoff>` (through the ``http_codes`` and ``exceptions`` keys), so
the same response or exception may trigger backoff for one scope and not for
another. On each trigger:

#.  The delay grows exponentially:

    .. code-block:: text

        delay = min(BACKOFF_MAX_DELAY, max(BACKOFF_MIN_DELAY, delay * BACKOFF_DELAY_FACTOR))

    :setting:`BACKOFF_JITTER` is then applied so that requests that backed off
    together do not retry in lockstep.

#.  If the response carries a :ref:`Retry-After or RateLimit-Reset
    <rate-limiting-headers>` value, the scope is *also* held back until that
    time (capped at :setting:`BACKOFF_MAX_DELAY`) before its next request. This
    is a one-time gate, on top of the exponential step above: it honors the
    header for the next request without turning a short header value into a
    long-standing delay for every later request.

**Recovery** is linear: after a scope goes a full :setting:`BACKOFF_WINDOW`
without a new trigger, its delay drops by one :setting:`BACKOFF_DELAY_FACTOR`
step toward the configured value, and keeps dropping one step per quiet window
until it is back to the configured value. A new trigger resets the countdown.

This exponential-increase / linear-decrease pattern, similar to TCP congestion
control, makes a scope back off quickly when a server is unhappy and return to
full speed gradually once it recovers.

Backoff only ever *tightens* a scope, and recovery never goes past the
configured value: the delay can grow above the configured ``"delay"`` and then
recover back down to it, but never below it, and backoff never raises the
concurrency limit. So set the ``"delay"`` and ``"concurrency"`` you actually
want for a scope; backoff makes things gentler from there when a server pushes
back, and returns to those values once it recovers.

Backoff triggers are detected by the
:class:`~scrapy.downloadermiddlewares.backoff.BackoffMiddleware`, a built-in
:ref:`downloader middleware <topics-downloader-middleware>` enabled by default.
Any component can also trigger backoff programmatically for arbitrary scopes —
e.g. based on the response body of a specific site — through
:meth:`crawler.throttler.back_off()
<scrapy.throttler.ThrottlerProtocol.back_off>`.

.. _per-scope-backoff:

Per-scope backoff configuration
-------------------------------

The global ``BACKOFF_*`` settings can be overridden per scope with the
``"backoff"`` key of a :setting:`THROTTLER_SCOPES` entry, an instance of
:class:`~scrapy.throttler.BackoffConfig`:

.. code-block:: python
    :caption: :file:`settings.py`

    THROTTLER_SCOPES = {
        "example.com": {
            "backoff": {
                "http_codes": [429, 503],
                "exceptions": ["builtins.IOError"],
                "delay_factor": 1.2,
                "max_delay": 180.0,
                "min_delay": 5.0,
                "jitter": [0.01, 0.33],
            },
        },
    }

Every key overrides the matching global ``BACKOFF_*`` setting for that scope
(``http_codes`` overrides :setting:`BACKOFF_HTTP_CODES`, ``exceptions``
overrides :setting:`BACKOFF_EXCEPTIONS`, ``delay_factor`` overrides
:setting:`BACKOFF_DELAY_FACTOR`, and so on), and any key left out falls back to
it. So a scope can, for example, treat an extra status code as a backoff
trigger, or stop treating one of the defaults as a trigger, independently of
every other scope.

.. _retry-after:
.. _rate-limiting-headers:

Rate limiting headers
=====================

Servers may include `Retry-After
<https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Retry-After>`__
or `RateLimit-Reset
<https://www.ietf.org/archive/id/draft-polli-ratelimit-headers-02.html#name-ratelimit-reset>`__
headers to indicate when you should make your next request. These headers are
respected automatically during :ref:`backoff <backoff>`: the scope's next
request is held back until the indicated time (capped at
:setting:`BACKOFF_MAX_DELAY`), on top of the usual exponential backoff step.

.. seealso:: :setting:`REDIRECT_MAX_DELAY`

.. _crawl-delay:

robots.txt
==========

`Crawl-Delay <https://en.wikipedia.org/wiki/Robots.txt#Crawl-delay_directive>`__
is a non-standard :file:`robots.txt` directive that indicates a number of seconds
to wait between requests.

.. setting:: THROTTLER_ROBOTSTXT_OBEY
.. setting:: THROTTLER_ROBOTSTXT_MAX_DELAY

If :setting:`ROBOTSTXT_OBEY` and :setting:`THROTTLER_ROBOTSTXT_OBEY` are
``True`` (default), valid ``Crawl-Delay`` directives override
:setting:`THROTTLER_SCOPE_CONCURRENCY` and :setting:`DOWNLOAD_DELAY`.
Concurrency is set to ``1`` and the delay is raised to at least the
``Crawl-Delay`` value (a larger configured delay is kept), capped at
:setting:`THROTTLER_ROBOTSTXT_MAX_DELAY` (default: ``60.0``).

If :setting:`THROTTLER_SCOPES` defines a different concurrency or delay, it
will be respected, but a warning will be logged about the discrepancy with
``Crawl-Delay``. Set ``ignore_robots_txt`` to ``True`` to silence this warning.

.. _delay-scope:

Delaying a scope programmatically
=================================

You can delay a :ref:`throttler scope <throttler-scopes>` on demand through
:meth:`crawler.throttler.delay_scope()
<scrapy.throttler.ThrottlerProtocol.delay_scope>`:

.. skip: next

.. code-block:: python

    crawler.throttler.delay_scope("example.com", 30.0)

This holds back the scope's next request for at least the given number of
seconds and registers a :ref:`backoff <backoff>` trigger. Like a
``Retry-After`` header, it is a one-time delay rather than a permanent one (the
scope's delay also grows by one backoff step and then recovers); call it again,
e.g. on each matching response, to keep a scope slowed down for longer.

It is useful to react to situations that :ref:`automatic backoff <backoff>`
cannot detect on its own, such as a soft block that comes back as a ``200``
response. For example, a spider callback can slow down the whole domain when it
detects a maintenance page, and reschedule the current request:

.. code-block:: python

    from scrapy import Request, Spider
    from scrapy.utils.httpobj import urlparse_cached


    class MySpider(Spider):
        name = "myspider"
        start_urls = ["https://example.com/"]

        def parse(self, response):
            if "under maintenance" in response.text:
                scope = urlparse_cached(response).netloc
                self.crawler.throttler.delay_scope(scope, 600.0)
                yield response.request.replace(dont_filter=True)
                return
            # Normal parsing follows.

Unlike :ref:`untrusted delays <rate-limiting-headers>`, this delay is **not**
capped at :setting:`BACKOFF_MAX_DELAY`.

.. _per-request-throttling:

Per-request throttling
======================

Sometimes you need different throttling behavior for individual requests or for
request groups that are not tied to a specific domain.

For example, you might want to throttle API endpoints differently than web
pages on the same domain, group requests by content type (images vs HTML), or
apply different throttling based on request priority.

.. reqmeta:: throttler_scopes

Use the ``throttler_scopes`` request metadata to assign requests to custom
throttling groups:

.. invisible-code-block: python

    from scrapy.http import Request

.. code-block:: python

    Request("https://api.example/", meta={"throttler_scopes": "api"})

You can also assign multiple throttling groups to a single request:

.. code-block:: python

    Request("https://api.example/users", meta={"throttler_scopes": {"api", "users"}})

You can then use the :setting:`THROTTLER_SCOPES` setting to customize
throttling for such requests:

.. code-block:: python
    :caption: :file:`settings.py`

    THROTTLER_SCOPES = {
        "api": {"concurrency": 2},
        "users": {"delay": 5.0},
    }

.. note:: These custom throttling groups persist through redirects. For
    redirect-aware throttling assignment, see :ref:`custom-throttler-scopes`.

.. reqmeta:: delay

Delaying a single request
-------------------------

To hold a single request for a fixed number of seconds before it is sent,
regardless of its scopes, set the ``delay`` request metadata key:

.. code-block:: python

    Request("https://example.com/slow", meta={"delay": 5.0})

The delay is applied once, the first time the request reaches the throttling
gate.

``delay`` defines only the *earliest* time the request may be sent,
not the exact time: once the delay elapses, the request still competes with
every other pending request for its scopes. If you want it sent **as soon as**
its delay elapses, give it a higher :attr:`~scrapy.Request.priority` too:

.. code-block:: python

    Request("https://example.com/slow", meta={"delay": 5.0}, priority=1)

Without a higher priority, a backlog of requests ahead of it in a FIFO queue
could keep it waiting well past the configured delay; a higher priority puts it
at the front of the queue, so it goes out right after its delay.

.. reqmeta:: dont_throttle

Excluding a request from throttling state
-----------------------------------------

Some requests (authentication flows, one-off API calls, file downloads) should
not influence throttling state even if they get a :setting:`BACKOFF_HTTP_CODES`
response or raise a :setting:`BACKOFF_EXCEPTIONS` exception. Set the
:reqmeta:`dont_throttle` request metadata key to ``True`` to process such a
request normally without letting its outcome trigger :ref:`backoff <backoff>`:

.. code-block:: python

    Request("https://example.com/login", meta={"dont_throttle": True})

.. _throttler-scopes:

Throttler scopes
================

Throttler scopes represent aspects of requests that can be throttled
independently.

..
    For future reference, the “throttler scope” name was taken from
    https://www.ietf.org/archive/id/draft-polli-ratelimit-headers-02.html#section-1.4-4.4

.. _custom-throttler-scopes:

Customizing throttler scopes
------------------------------

There are 2 ways to customize throttler scopes.

To **configure existing scopes**, use the :setting:`THROTTLER_SCOPES` setting.
Its keys are scope IDs and its values are
:class:`~scrapy.throttler.ThrottlerScopeConfig` dicts, which accept the
following keys:

``concurrency`` (:class:`int`)
    Maximum number of concurrent requests for the scope. Defaults to
    :setting:`THROTTLER_SCOPE_CONCURRENCY`.

``delay`` (:class:`float`)
    Minimum seconds between requests for the scope. Defaults to
    :setting:`DOWNLOAD_DELAY`.

``jitter`` (:class:`float` or 2-:class:`list`)
    Magnitude of the random variation applied to ``delay``; the per-scope
    override of :setting:`RANDOMIZE_DOWNLOAD_DELAY`. ``0`` disables it, ``0.5``
    means ±50% (the default when :setting:`RANDOMIZE_DOWNLOAD_DELAY` is on), and
    a ``[low, high]`` pair multiplies the delay by ``1 + uniform(low, high)``.

``quota`` (:class:`float`)
    Maximum :ref:`quota <throttler-quotas>` consumed per ``window``.

``window`` (:class:`float`)
    Quota window in seconds. Defaults to :setting:`THROTTLER_WINDOW`.

``backoff`` (:class:`~scrapy.throttler.BackoffConfig`)
    Per-scope :ref:`backoff overrides <per-scope-backoff>`.

``manager`` (:class:`str` or :class:`type`)
    Import path or class of a :ref:`custom scope manager
    <custom-throttler-scope-managers>` for the scope.

``ignore_robots_txt`` (:class:`bool`)
    Silences the warning logged when this configuration is more aggressive than
    a :ref:`robots.txt Crawl-delay <crawl-delay>`.

.. setting:: THROTTLER

To **change how scopes are assigned** (or anything beyond per-scope settings),
set :setting:`THROTTLER` (default:
:class:`~scrapy.throttler.Throttler`) to a :ref:`component
<topics-components>` that implements the
:class:`~scrapy.throttler.ThrottlerProtocol` protocol (or its import
path as a string):

.. code-block:: python
    :caption: :file:`settings.py`

    THROTTLER = "myproject.throttling.MyThrottler"

.. _multiple-throttler-scopes:

Handling of multiple throttler scopes
--------------------------------------

When a request has multiple throttler scopes, it is not sent until all of its
throttler scopes allow it.

.. _throttler-quotas:

Throttler quotas
----------------

When different requests can consume different amounts of a throttler scope,
you can express this using **throttler quotas**.

.. setting:: THROTTLER_WINDOW

Use the :setting:`THROTTLER_WINDOW` setting (default: ``60.0``) or the ``"window"``
key in the :setting:`THROTTLER_SCOPES` setting to define the time window after
which throttler quotas are reset.

Then use the :setting:`THROTTLER_SCOPES` setting to define the throttling
quotas for each throttler scope:

.. code-block:: python
    :caption: :file:`settings.py`

    THROTTLER_SCOPES = {
        "api.toscrape.com": {
            "quota": 500.0,
        },
    }

Then, in the :reqmeta:`throttler_scopes` request metadata key or in the return
value of the :meth:`~scrapy.throttler.ThrottlerProtocol.get_scopes`
method, define a :class:`dict` where keys are scope IDs and values are
:class:`float` values that indicate the expected quota consumption (it does not
need to be exact).

.. _custom-throttler-scope-managers:

Customizing throttler scope managers
-------------------------------------

.. setting:: THROTTLER_SCOPE_MANAGER

The :setting:`THROTTLER_SCOPE_MANAGER` setting (default:
:class:`~scrapy.throttler.ThrottlerScopeManager`) is a :ref:`component
<topics-components>` that implements the
:class:`~scrapy.throttler.ThrottlerScopeManagerProtocol` (or its import path
as a string):

.. code-block:: python
    :caption: :file:`settings.py`

    THROTTLER_SCOPE_MANAGER = "myproject.throttling.MyThrottlerScopeManager"

For each throttler scope, an instance of this class is created to manage any
gradual :ref:`backoff <backoff>` required at run time.

You can implement your own throttler scope manager if you wish to change the
backoff behavior beyond what settings allow.

You can also define a custom throttler scope manager for a specific throttling
scope by setting the ``"manager"`` key in the :setting:`THROTTLER_SCOPES`
setting:

.. code-block:: python
    :caption: :file:`settings.py`

    THROTTLER_SCOPES = {
        "api.toscrape.com": {
            "manager": "myproject.throttling.MyThrottlerScopeManager",
        },
    }

Most custom scope managers subclass the default
:class:`~scrapy.throttler.ThrottlerScopeManager` and override only the methods
whose behavior they want to change; implementing the
:class:`~scrapy.throttler.ThrottlerScopeManagerProtocol` from scratch is also
supported. For example, this manager disables exponential :ref:`backoff
<backoff>`, so a scope relies solely on its configured delay and quota:

.. code-block:: python
    :caption: :file:`myproject/throttling.py`

    from scrapy.throttler import ThrottlerScopeManager


    class FixedWindowScopeManager(ThrottlerScopeManager):
        def record_backoff(self, *args, **kwargs):
            pass  # never back off

.. _throttler-aware-scheduler:

Throttling-aware scheduling
===========================

By default, throttling is enforced at the engine, where a request waiting on
its :ref:`throttler scopes <throttler-scopes>` holds a concurrency slot. In a
crawl that mixes heavily-throttled scopes with unthrottled ones, this can let
throttled requests starve unthrottled ones that could be sent right away
(**head-of-line blocking**; Scrapy logs a warning the first time throttled
requests start consuming the global concurrency budget while they wait).

:class:`~scrapy.core.scheduler.ThrottlerAwareScheduler` avoids this. To enable
it:

.. code-block:: python
    :caption: :file:`settings.py`

    SCHEDULER = "scrapy.core.scheduler.ThrottlerAwareScheduler"
    SCHEDULER_PRIORITY_QUEUE = "scrapy.pqueues.ThrottlerAwarePriorityQueue"

.. autoclass:: scrapy.core.scheduler.ThrottlerAwareScheduler

.. _throttling-examples:

Examples
========

.. _alternative-domain-throttling:

Alternative domain throttling
-----------------------------

If you are not happy with the :ref:`default throttler scope behavior
<basic-throttling>` with regards to domains and subdomains, you can change it.

Alternative approaches include:

-   Using the **highest-level registrable domain** as the throttler scope,
    e.g. https://books.toscrape.com and https://toscrape.com both get a
    ``toscrape.com`` throttler scope.

    This allows to apply the same throttling settings to all subdomains of a
    registrable domain.

    For example:

    .. code-block:: python
        :caption: :file:`settings.py`

        import tldextract
        from scrapy.throttler import Throttler, scope_cache
        from scrapy.utils.httpobj import urlparse_cached


        class MyThrottler(Throttler):
            @scope_cache
            async def get_scopes(self, request):
                extracted = tldextract.extract(request.url)
                return extracted.registered_domain or urlparse_cached(request).netloc


        THROTTLER = MyThrottler

-   Using **multiple throttler scopes per request**, one per registrable
    domain and for every higher-level subdomain, e.g.
    https://books.toscrape.com and https://toscrape.com both get a
    ``toscrape.com`` throttler scope, but https://books.toscrape.com also
    gets a ``books.toscrape.com`` throttler scope.

    This allows to apply the same throttling settings to all subdomains of a
    registrable domain, but also allows applying further restrictions on each
    or on some subdomains.

    For example:

    .. code-block:: python
        :caption: :file:`settings.py`

        import tldextract
        from scrapy.throttler import Throttler, scope_cache
        from scrapy.utils.httpobj import urlparse_cached


        class MyThrottler(Throttler):
            @scope_cache
            async def get_scopes(self, request):
                extracted = tldextract.extract(request.url)
                if not extracted.registered_domain:
                    return urlparse_cached(request).netloc
                # The registrable domain, plus the full host for a subdomain.
                return {extracted.registered_domain, extracted.fqdn}


        THROTTLER = MyThrottler
        THROTTLER_SCOPES = {
            "toscrape.com": {"concurrency": 32},
            "books.toscrape.com": {"concurrency": 24},
            "quotes.toscrape.com": {"concurrency": 16},
        }

    Here ``books.toscrape.com`` requests can reach 24 concurrency and
    ``quotes.toscrape.com`` requests can reach 16 concurrency, but never both
    at the same time, because that would sum 40 concurrency, and
    ``toscrape.com`` requests are limited to 32.

.. _endpoints-throttling:

Endpoint-specific throttling
----------------------------

To apply different throttling settings to different endpoints of the same
domain and not enforce any common throttling, effectively treating them as
different domains:

-   Implement a :ref:`throttler <custom-throttler-scopes>` that sets
    endpoint-specific throttler scopes for that domain:

    .. code-block:: python

        from scrapy.throttler import Throttler, scope_cache
        from scrapy.utils.httpobj import urlparse_cached


        class MyThrottler(Throttler):
            @scope_cache
            async def get_scopes(self, request):
                parsed_url = urlparse_cached(request)
                if parsed_url.netloc != "api.toscrape.com":
                    return await super().get_scopes(request)
                return f"{parsed_url.netloc}{parsed_url.path}"

-   Use the :setting:`THROTTLER_SCOPES` setting to set different throttling
    settings per endpoint:

    .. code-block:: python
        :caption: :file:`settings.py`

        THROTTLER_SCOPES = {
            "api.toscrape.com/fast-endpoint": {"concurrency": 1000, "delay": 0.08},
            "api.toscrape.com/slow-endpoint": {"delay": 5.0},
        }


.. _web-scraping-api-throttling:

Web scraping API throttling
---------------------------

Imagine you are sending requests to a web scraping API, e.g. to avoid bans.
Unless that API provides a Scrapy plugin to make it easier to use, you may want
to:

-   Use the :setting:`THROTTLER_SCOPES` setting to increase concurrency for
    API requests. For example:

    .. code-block:: python
        :caption: :file:`settings.py`

        THROTTLER_SCOPES = {
            "api.toscrape.com": {"concurrency": 1000, "delay": 0.08},
        }

-   Implement a :ref:`throttler <custom-throttler-scopes>` that:

    -   Adds a throttler scope for the URL being scraped.

        For example, if you request
        ``https://api.toscrape.com/?url=https://example.com``, by default it
        will get a ``api.toscrape.com`` throttler scope, but it should also
        get the ``example.com`` throttler scope:

        .. code-block:: python

            from urllib.parse import urlparse

            from scrapy.throttler import add_scope, Throttler, scope_cache
            from scrapy.utils.httpobj import urlparse_cached
            from w3lib.url import url_query_parameter


            class MyThrottler(Throttler):
                @scope_cache
                async def get_scopes(self, request):
                    scopes = await super().get_scopes(request)
                    if urlparse_cached(request).netloc != "api.toscrape.com":
                        return scopes
                    target_url = url_query_parameter(request.url, "url")
                    if not target_url:
                        return scopes
                    target_domain = urlparse(target_url).netloc
                    return add_scope(scopes, target_domain)

-   Add a :ref:`downloader middleware <topics-downloader-middleware>` that
    differentiates between exhaustion of the target website and exhaustion of
    the API itself. The API returns ``200`` even when the target website
    rate-limits it, reporting the upstream status in a header; the middleware
    backs off the **target-website** scope (not the API scope) in that case,
    checking the upstream status against :setting:`BACKOFF_HTTP_CODES`:

    .. code-block:: python

        from scrapy.throttler import iter_scopes
        from scrapy.utils.httpobj import urlparse_cached


        class UpstreamBackoffMiddleware:
            def __init__(self, crawler):
                self.throttler = crawler.throttler
                self.backoff_codes = {
                    int(code) for code in crawler.settings.getlist("BACKOFF_HTTP_CODES")
                }

            @classmethod
            def from_crawler(cls, crawler):
                return cls(crawler)

            def process_response(self, request, response, spider):
                if urlparse_cached(request).netloc == "api.toscrape.com":
                    upstream_status = int(
                        response.headers.get("X-Upstream-Status-Code", b"200")
                    )
                    if upstream_status in self.backoff_codes:
                        scopes = [
                            scope
                            for scope in iter_scopes(
                                self.throttler.get_resolved_scopes(request)
                            )
                            if scope != "api.toscrape.com"
                        ]
                        self.throttler.back_off(scopes)
                return response


.. _cost-smoothing-throttling:

Cost-capped throttling
----------------------

Imagine you are using an API that charges different requests differently, e.g.
based on the features used, and you want to limit how much you spend per time
window (:setting:`THROTTLER_WINDOW`). You can use :ref:`throttler quotas
<throttler-quotas>` for that:

-   Implement a :ref:`throttler <custom-throttler-scopes>` that:

    -   Sets a ``cost`` throttler scope on each request to some estimation
        based e.g. on request URL parameters:

        .. code-block:: python

            from scrapy.utils.httpobj import urlparse_cached
            from scrapy.throttler import Throttler, scope_cache


            class MyThrottler(Throttler):
                @scope_cache
                async def get_scopes(self, request):
                    scopes = await super().get_scopes(request)
                    parsed_url = urlparse_cached(request)
                    if parsed_url.netloc != "api.toscrape.com":
                        return scopes
                    return add_scope(scopes, "cost", estimate_request_cost(request))

-   Add a :ref:`downloader middleware <topics-downloader-middleware>` that
    reconciles the estimated cost with the actual cost reported by the
    response, so that the quota tracks real spending:

    .. code-block:: python

        class CostReconcileMiddleware:
            def __init__(self, crawler):
                self.throttler = crawler.throttler

            @classmethod
            def from_crawler(cls, crawler):
                return cls(crawler)

            def process_response(self, request, response, spider):
                if response.headers.get("X-Actual-Cost") is not None:
                    estimated = estimate_request_cost(request)
                    actual = float(response.headers[b"X-Actual-Cost"])
                    # Report the difference between actual and estimated cost.
                    self.throttler.reconcile_quota("cost", consumed=actual - estimated)
                return response

-   Use the :setting:`THROTTLER_SCOPES` setting to set a maximum cost per time
    window:

    .. code-block:: python
        :caption: :file:`settings.py`

        THROTTLER_SCOPES = {
            "cost": {"quota": 100.0},
        }

    This will allow you to spend up to 100.0 units of cost per time window
    (default: 60 seconds) before throttling kicks in.

.. _throttling-per-ip:

Per-IP concurrency limiting
---------------------------

A concurrency limit keyed by IP is just a throttler scope whose id is the
request's IP, with a ``concurrency`` limit. A request then carries two scopes,
its domain and its IP, and is only sent when **both** allow it (see
:ref:`multiple-throttler-scopes`).

-   Implement a :ref:`throttler <custom-throttler-scopes>` that adds
    the request's IP as a second scope:

    .. code-block:: python

        import socket

        from scrapy.throttler import Throttler, add_scope, scope_cache
        from scrapy.utils.asyncio import run_in_thread
        from scrapy.utils.httpobj import urlparse_cached


        class IPThrottler(Throttler):
            @scope_cache
            async def get_scopes(self, request):
                scopes = await super().get_scopes(request)
                host = urlparse_cached(request).hostname
                address = await run_in_thread(socket.gethostbyname, host)
                return add_scope(scopes, address)

.. _throttling-settings:

Additional settings
===================

-   .. setting:: BACKOFF_ENABLED

    :setting:`BACKOFF_ENABLED` (default: ``True``)

    Whether to enable the :class:`~scrapy.downloadermiddlewares.backoff.BackoffMiddleware`,
    which drives :ref:`backoff <backoff>` from download outcomes. Set it to
    ``False`` to disable backoff without having to remove the middleware from
    :setting:`DOWNLOADER_MIDDLEWARES`.

-   .. setting:: BACKOFF_EXCEPTIONS

    :setting:`BACKOFF_EXCEPTIONS`

    Default:

    -   :exc:`~scrapy.exceptions.DownloadFailedError`
    -   :exc:`~scrapy.exceptions.DownloadTimeoutError`
    -   :exc:`~scrapy.exceptions.ResponseDataLossError`

    List of exception classes that trigger backoff when raised while
    downloading a request. Strings are interpreted as import paths. Can be
    overridden per scope with the ``exceptions`` key (see
    :ref:`per-scope-backoff`).

    .. seealso:: :setting:`RETRY_EXCEPTIONS`

-   .. setting:: BACKOFF_JITTER

    :setting:`BACKOFF_JITTER` (default: ``0.1``)

    Random jitter applied to each backoff delay, as a fraction of the delay.
    With the default value of ``0.1`` the delay is randomized by ±10%.
    Overrides :setting:`RANDOMIZE_DOWNLOAD_DELAY` during backoff.

-   .. setting:: BACKOFF_MIN_DELAY

    :setting:`BACKOFF_MIN_DELAY` (default: ``1.0``)

    Delay, in seconds, applied on the first backoff step (and the minimum
    delay during backoff).

-   .. setting:: BACKOFF_WINDOW

    :setting:`BACKOFF_WINDOW` (default: ``60.0``)

    Time window, in seconds, used by :ref:`backoff <backoff>`. A
    :ref:`throttler scope <throttler-scopes>` must go this many seconds
    without a new backoff
    trigger (an HTTP error code from :setting:`BACKOFF_HTTP_CODES` or an
    exception from :setting:`BACKOFF_EXCEPTIONS`) before its delay decreases
    by one :setting:`BACKOFF_DELAY_FACTOR` step toward the configured value.
    A new trigger resets the countdown.

-   .. setting:: RANDOMIZE_DOWNLOAD_DELAY

    :setting:`RANDOMIZE_DOWNLOAD_DELAY` (default: ``True``)

    Randomize delays by this factor, e.g. if ``0.2`` randomize delays between
    ``delay*0.8`` and ``delay*1.2``.

    It can be set to a 2-item list with low and high factors, e.g.
    ``[-0.1, 0.3]`` to randomize delays between ``delay*0.9`` and
    ``delay*1.3``.

    If ``True``, ``0.5`` (i.e. ±50%) is used as the randomization factor. If
    ``False``, no randomization is applied.

-   .. setting:: THROTTLER_DEBUG

    :setting:`THROTTLER_DEBUG` (default: ``False``)

    Whether to log :ref:`throttling <throttling>` decisions (per-scope delays,
    backoff steps and recoveries) for debugging.

-   .. setting:: THROTTLER_SCOPE_LIMIT

    :setting:`THROTTLER_SCOPE_LIMIT` (default: ``100000``)

    Maximum number of :ref:`throttler scope <throttler-scopes>` states kept
    in memory at once, to bound memory usage on broad crawls that touch a large
    number of scopes (e.g. domains).

    When the limit is exceeded, the least-recently-used idle scopes are evicted
    (an evicted scope is recreated from its configuration the next time it is
    needed). Scopes with in-flight requests or in active backoff are never
    evicted, so the limit may be temporarily exceeded if that many scopes are
    busy at once. Set to ``0`` to disable the limit.

    This complements :setting:`THROTTLER_SCOPE_MAX_IDLE`, which evicts scopes
    by inactivity time rather than by count.

-   .. setting:: THROTTLER_SCOPE_MAX_IDLE

    :setting:`THROTTLER_SCOPE_MAX_IDLE` (default: ``3600.0``)

    Seconds of inactivity after which the state of a :ref:`throttler scope
    <throttler-scopes>` is evicted from memory to bound memory usage on
    long-running crawls. Set to ``0`` to never evict. Scopes in active backoff
    are never evicted.

.. _throttling-api:

API
===

.. autoclass:: scrapy.throttler.ThrottlerProtocol
    :members:
    :member-order: bysource

.. autoclass:: scrapy.throttler.Throttler

.. autoclass:: scrapy.throttler.ThrottlerScopeManagerProtocol
    :members:
    :member-order: bysource

.. autoclass:: scrapy.throttler.ThrottlerScopeManager

.. autoclass:: scrapy.pqueues.ThrottlerAwarePriorityQueue

.. autoclass:: scrapy.throttler.ThrottlerScopeConfig

.. autoclass:: scrapy.throttler.BackoffConfig

.. autofunction:: scrapy.throttler.scope_cache
.. autofunction:: scrapy.throttler.add_scope
.. autofunction:: scrapy.throttler.iter_scopes
