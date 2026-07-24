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

-   .. setting:: THROTTLING_SCOPE_CONCURRENCY

    :setting:`THROTTLING_SCOPE_CONCURRENCY` (default: ``1``)

    Default maximum number of simultaneous requests per :ref:`throttling scope
    <throttling-scopes>`. Requests are grouped by domain by default, so this is
    the maximum number of simultaneous requests per domain.

-   .. setting:: DOWNLOAD_DELAY

    :setting:`DOWNLOAD_DELAY` (default: ``1``
    (:ref:`fallback <default-settings>`: ``0``))

    Minimum seconds between any two requests to the same domain.

    To target a specific number of requests per minute (RPM) *per domain*, set
    this to ``60 / RPM``. For example, ``DOWNLOAD_DELAY = 1.0`` for 60 RPM, or
    ``DOWNLOAD_DELAY = 2.0`` for 30 RPM.

When configuring these settings, note that:

-   :setting:`CONCURRENT_REQUESTS` caps :setting:`THROTTLING_SCOPE_CONCURRENCY`.

-   If ``DOWNLOAD_DELAY`` ≥ response time, concurrency is effectively ``1``,
    because the next request to the domain is not sent until the delay elapses,
    by which time the previous response has already arrived.

.. [1] You can :ref:`customize <throttling-scopes>` how requests are grouped
    for throttling, but domain-based throttling works well in most cases. For
    more complex domain grouping strategies, see
    :ref:`alternative-domain-throttling`.

.. setting:: THROTTLING_SCOPES

.. _per-domain-throttling:

Per-domain throttling
=====================

The :setting:`THROTTLING_SCOPES` setting allows you to customize throttling
behavior for specific domains [1]_.

It is a dict that maps scope IDs to
:class:`~scrapy.throttler.ThrottlingScopeConfig` dicts. It is empty by default.

For example, you can crawl domains you own (or that are meant for scraping)
faster, while the :ref:`conservative defaults <basic-throttling>` still apply to
other domains:

.. code-block:: python

    THROTTLING_SCOPES = {
        "books.toscrape.com": {"concurrency": 32, "delay": 0.1},
        "quotes.toscrape.com": {"concurrency": 16, "delay": 0.1},
    }

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

-   .. setting:: BACKOFF_MAX_DELAY

    :setting:`BACKOFF_MAX_DELAY` (default: ``300.0``)

    Maximum delay, in seconds, that backoff can reach. Also caps
    :ref:`Retry-After <retry-after>` and :ref:`RateLimit-Reset
    <rate-limiting-headers>` delays.

See :ref:`throttling-settings` for additional backoff settings.

.. _backoff-algorithm:

How backoff works
-----------------

Every :ref:`throttling scope <throttling-scopes>` keeps a current delay that
starts at its configured ``"delay"`` (:setting:`DOWNLOAD_DELAY` by default).

A **backoff trigger** is a response whose status code is in
:setting:`BACKOFF_HTTP_CODES` or a download exception whose type is in
:setting:`BACKOFF_EXCEPTIONS` (both :ref:`overridable per scope
<per-scope-backoff>`). On each trigger the scope's delay grows
**exponentially**, bounded above by :setting:`BACKOFF_MAX_DELAY`, until the
triggers stop — so a scope that starts getting throttled quickly slows down to
a rate the server accepts.

Once things are quiet again, the delay **drifts back down**, probing for the
lowest delay that does not trigger backoff and settling around it. It keeps
tracking that ideal as it changes over the course of a crawl, rather than
snapping back to the configured delay and having to ramp up all over again. If
a response carries a :ref:`Retry-After or RateLimit-Reset
<rate-limiting-headers>` value, the scope also honors it as a one-time delay
before its next request.

Backoff only ever *tightens* a scope: the delay can grow above the configured
``"delay"`` and recover back down to it, but never below it, and backoff never
raises the concurrency limit. So set the ``"delay"`` and ``"concurrency"`` you
actually want for a scope; backoff makes things gentler from there when a server
pushes back, and returns to them once it recovers.

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
``"backoff"`` key of a :setting:`THROTTLING_SCOPES` entry, an instance of
:class:`~scrapy.throttler.BackoffConfig`:

.. code-block:: python
    :caption: :file:`settings.py`

    THROTTLING_SCOPES = {
        "example.com": {
            "backoff": {
                "http_codes": [429, 503],
                "exceptions": ["builtins.IOError"],
                "max_delay": 180.0,
            },
        },
    }

Every key overrides the matching global ``BACKOFF_*`` setting for that scope
(``http_codes`` overrides :setting:`BACKOFF_HTTP_CODES`, ``exceptions``
overrides :setting:`BACKOFF_EXCEPTIONS`, ``max_delay`` overrides
:setting:`BACKOFF_MAX_DELAY`), and any key left out falls back to
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
:setting:`DOWNLOAD_DELAY`. The delay is raised to at least the ``Crawl-Delay``
value (a larger configured delay is kept), capped at
:setting:`THROTTLER_ROBOTSTXT_MAX_DELAY` (default: ``60.0``).

If :setting:`THROTTLING_SCOPES` defines a smaller (more aggressive) delay, it
will be respected, but a warning will be logged about the discrepancy with
``Crawl-Delay``. Set ``ignore_robots_txt`` to ``True`` to silence this warning.

.. _delay-scope:

Delaying a scope programmatically
=================================

You can delay a :ref:`throttling scope <throttling-scopes>` on demand through
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

.. reqmeta:: throttling_scopes

Use the ``throttling_scopes`` request metadata to assign requests to custom
throttling groups:

.. invisible-code-block: python

    from scrapy.http import Request

.. code-block:: python

    Request("https://api.example/", meta={"throttling_scopes": "api"})

You can also assign multiple throttling groups to a single request:

.. code-block:: python

    Request("https://api.example/users", meta={"throttling_scopes": {"api", "users"}})

You can then use the :setting:`THROTTLING_SCOPES` setting to customize
throttling for such requests:

.. code-block:: python
    :caption: :file:`settings.py`

    THROTTLING_SCOPES = {
        "api": {"concurrency": 2},
        "users": {"delay": 5.0},
    }

.. note:: These custom throttling groups persist through redirects. For
    redirect-aware throttling assignment, see :ref:`custom-throttling-scopes`.

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

.. _throttling-scopes:

Throttling scopes
=================

`Throttling scopes
<https://www.ietf.org/archive/id/draft-polli-ratelimit-headers-02.html#section-1.4-4.4>`__
represent aspects of requests that can be throttled independently.

When a request has multiple throttling scopes, it is not sent until all of its
throttling scopes allow it.

.. _custom-throttling-scopes:

Customizing throttling scopes
-----------------------------

There are 2 ways to customize throttling scopes.

To **configure existing scopes**, use the :setting:`THROTTLING_SCOPES` setting.
Its keys are scope IDs and its values are
:class:`~scrapy.throttler.ThrottlingScopeConfig` dicts, which accept the
following keys:

``concurrency`` (:class:`int`)
    Maximum number of concurrent requests for the scope. Defaults to
    :setting:`THROTTLING_SCOPE_CONCURRENCY`.

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
    <custom-throttling-scope-managers>` for the scope.

``ignore_robots_txt`` (:class:`bool`)
    Silences the warning logged when this configuration is more aggressive than
    a :ref:`robots.txt Crawl-delay <crawl-delay>`.

.. setting:: THROTTLER

To **change how scopes are assigned** (or anything beyond per-scope settings),
set :setting:`THROTTLER` (default:
:class:`~scrapy.throttler.Throttler`) to a :ref:`component
<topics-components>` that implements
:class:`~scrapy.throttler.ThrottlerProtocol` (or its import
path as a string):

.. code-block:: python
    :caption: :file:`settings.py`

    THROTTLER = "myproject.throttling.MyThrottler"

.. _throttler-quotas:

Throttler quotas
----------------

When different requests can consume different amounts of a throttling scope,
you can express this using **throttler quotas** to optimize request scheduling.

.. setting:: THROTTLER_WINDOW

Use the :setting:`THROTTLER_WINDOW` setting (default: ``60.0``) or the ``"window"``
key in the :setting:`THROTTLING_SCOPES` setting to define the time window after
which throttler quotas are reset.

Then use the :setting:`THROTTLING_SCOPES` setting to define the throttling
quotas for each throttling scope:

.. code-block:: python
    :caption: :file:`settings.py`

    THROTTLING_SCOPES = {
        "api.example": {
            "quota": 500.0,
        },
    }

Then, in the :reqmeta:`throttling_scopes` request metadata key or in the return
value of the :meth:`~scrapy.throttler.ThrottlerProtocol.get_scopes`
method, define a :class:`dict` where keys are scope IDs and values are
:class:`float` values that indicate the expected quota consumption (it does not
need to be exact).

.. _custom-throttling-scope-managers:

Customizing throttling scope managers
-------------------------------------

.. setting:: THROTTLING_SCOPE_MANAGER

The :setting:`THROTTLING_SCOPE_MANAGER` setting (default:
:class:`~scrapy.throttler.ThrottlingScopeManager`) is a :ref:`component
<topics-components>` that implements the
:class:`~scrapy.throttler.ThrottlingScopeManagerProtocol` (or its import path
as a string):

.. code-block:: python
    :caption: :file:`settings.py`

    THROTTLING_SCOPE_MANAGER = "myproject.throttling.MyThrottlingScopeManager"

For each throttling scope, an instance of this class manages that scope's
run-time throttling state: its delay and concurrency limits, its quota, and any
gradual :ref:`backoff <backoff>`.

You can implement your own throttling scope manager if you wish to change the
throttling behavior beyond what settings allow.

You can also define a custom throttling scope manager for a specific throttling
scope by setting the ``"manager"`` key in the :setting:`THROTTLING_SCOPES`
setting:

.. code-block:: python
    :caption: :file:`settings.py`

    THROTTLING_SCOPES = {
        "api.example": {
            "manager": "myproject.throttling.MyThrottlingScopeManager",
        },
    }

The simplest approach is to subclass the default
:class:`~scrapy.throttler.ThrottlingScopeManager` and override only the methods
whose behavior you want to change; implementing the
:class:`~scrapy.throttler.ThrottlingScopeManagerProtocol` from scratch is also
supported. For example, this manager disables exponential :ref:`backoff
<backoff>`, so a scope relies solely on its configured delay and quota:

.. code-block:: python
    :caption: :file:`myproject/throttling.py`

    from scrapy.throttler import ThrottlingScopeManager


    class FixedWindowScopeManager(ThrottlingScopeManager):
        def record_backoff(self, *args, **kwargs):
            pass  # never back off

.. _throttler-aware-scheduler:

Throttling-aware scheduling
===========================

By default, throttling is enforced at the engine, where a request waiting on
its :ref:`throttling scopes <throttling-scopes>` holds a concurrency slot. In a
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

If you are not happy with the :ref:`default throttling scope behavior
<basic-throttling>` with regards to domains and subdomains, you can change it.

Alternative approaches include:

-   Using the **highest-level registrable domain** as the throttling scope,
    e.g. https://books.toscrape.com and https://toscrape.com both get a
    ``toscrape.com`` throttling scope.

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

-   Using **multiple throttling scopes per request**, one per registrable
    domain and for every higher-level subdomain, e.g.
    https://books.toscrape.com and https://toscrape.com both get a
    ``toscrape.com`` throttling scope, but https://books.toscrape.com also
    gets a ``books.toscrape.com`` throttling scope.

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
        THROTTLING_SCOPES = {
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

-   Implement a :ref:`throttler <custom-throttling-scopes>` that sets
    endpoint-specific throttling scopes for that domain:

    .. code-block:: python

        from scrapy.throttler import Throttler, scope_cache
        from scrapy.utils.httpobj import urlparse_cached


        class MyThrottler(Throttler):
            @scope_cache
            async def get_scopes(self, request):
                parsed_url = urlparse_cached(request)
                if parsed_url.netloc != "api.example":
                    return await super().get_scopes(request)
                return f"{parsed_url.netloc}{parsed_url.path}"

-   Use the :setting:`THROTTLING_SCOPES` setting to set different throttling
    settings per endpoint:

    .. code-block:: python
        :caption: :file:`settings.py`

        THROTTLING_SCOPES = {
            "api.example/fast-endpoint": {"concurrency": 1000, "delay": 0.08},
            "api.example/slow-endpoint": {"delay": 5.0},
        }


.. _web-scraping-api-throttling:

Web scraping API throttling
---------------------------

Imagine you are sending requests to a web scraping API, e.g. to avoid bans.
Unless that API provides a Scrapy plugin to make it easier to use, you may want
to:

-   Use the :setting:`THROTTLING_SCOPES` setting to increase concurrency for
    API requests. For example:

    .. code-block:: python
        :caption: :file:`settings.py`

        THROTTLING_SCOPES = {
            "api.example": {"concurrency": 1000, "delay": 0.08},
        }

-   Implement a :ref:`throttler <custom-throttling-scopes>` that:

    -   Adds a throttling scope for the URL being scraped.

        For example, if you request
        ``https://api.example/?url=https://example.com``, by default it
        will get a ``api.example`` throttling scope, but it should also
        get the ``example.com`` throttling scope:

        .. code-block:: python

            from urllib.parse import urlparse

            from scrapy.throttler import add_scope, Throttler, scope_cache
            from scrapy.utils.httpobj import urlparse_cached
            from w3lib.url import url_query_parameter


            class MyThrottler(Throttler):
                @scope_cache
                async def get_scopes(self, request):
                    scopes = await super().get_scopes(request)
                    if urlparse_cached(request).netloc != "api.example":
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
                if urlparse_cached(request).netloc == "api.example":
                    upstream_status = int(
                        response.headers.get("X-Upstream-Status-Code", b"200")
                    )
                    if upstream_status in self.backoff_codes:
                        scopes = [
                            scope
                            for scope in iter_scopes(
                                self.throttler.get_resolved_scopes(request)
                            )
                            if scope != "api.example"
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

-   Implement a :ref:`throttler <custom-throttling-scopes>` that:

    -   Sets a ``cost`` throttling scope on each request to some estimation
        based e.g. on request URL parameters:

        .. code-block:: python

            from scrapy.utils.httpobj import urlparse_cached
            from scrapy.throttler import Throttler, scope_cache


            class MyThrottler(Throttler):
                @scope_cache
                async def get_scopes(self, request):
                    scopes = await super().get_scopes(request)
                    parsed_url = urlparse_cached(request)
                    if parsed_url.netloc != "api.example":
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

-   Use the :setting:`THROTTLING_SCOPES` setting to set a maximum cost per time
    window:

    .. code-block:: python
        :caption: :file:`settings.py`

        THROTTLING_SCOPES = {
            "cost": {"quota": 100.0},
        }

    This will allow you to spend up to 100.0 units of cost per time window
    (default: 60 seconds) before throttling kicks in.

.. _throttling-per-ip:

Per-IP concurrency limiting
---------------------------

A concurrency limit keyed by IP is just a throttling scope whose id is the
request's IP, with a ``concurrency`` limit. A request then carries two scopes,
its domain and its IP, and is only sent when **both** allow it (see
:ref:`throttling-scopes`).

-   Implement a :ref:`throttler <custom-throttling-scopes>` that adds
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

-   .. setting:: THROTTLING_SCOPE_LIMIT

    :setting:`THROTTLING_SCOPE_LIMIT` (default: ``100000``)

    Maximum number of :ref:`throttling scope <throttling-scopes>` states kept
    in memory at once, to bound memory usage on broad crawls that touch a large
    number of scopes (e.g. domains).

    When the limit is exceeded, the least-recently-used idle scopes are evicted
    (an evicted scope is recreated from its configuration the next time it is
    needed). Scopes with in-flight requests or in active backoff are never
    evicted, so the limit may be temporarily exceeded if that many scopes are
    busy at once. Set to ``0`` to disable the limit.

    This complements :setting:`THROTTLING_SCOPE_MAX_IDLE`, which evicts scopes
    by inactivity time rather than by count.

-   .. setting:: THROTTLING_SCOPE_MAX_IDLE

    :setting:`THROTTLING_SCOPE_MAX_IDLE` (default: ``3600.0``)

    Seconds of inactivity after which the state of a :ref:`throttling scope
    <throttling-scopes>` is evicted from memory to bound memory usage on
    long-running crawls. Set to ``0`` to never evict. Scopes in active backoff
    are never evicted.

.. _throttling-api:

API
===

.. autoclass:: scrapy.throttler.ThrottlerProtocol
    :members:
    :member-order: bysource

.. autoclass:: scrapy.throttler.Throttler

.. autoclass:: scrapy.throttler.ThrottlingScopeManagerProtocol
    :members:
    :member-order: bysource

.. autoclass:: scrapy.throttler.ThrottlingScopeManager

.. autoclass:: scrapy.pqueues.ThrottlerAwarePriorityQueue

.. autoclass:: scrapy.throttler.ThrottlingScopeConfig

.. autoclass:: scrapy.throttler.BackoffConfig

.. autofunction:: scrapy.throttler.scope_cache
.. autofunction:: scrapy.throttler.add_scope
.. autofunction:: scrapy.throttler.iter_scopes
