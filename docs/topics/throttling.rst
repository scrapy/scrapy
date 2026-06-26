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

-   .. setting:: CONCURRENT_REQUESTS_PER_DOMAIN

    :setting:`CONCURRENT_REQUESTS_PER_DOMAIN` (default: ``1`` (:ref:`fallback <default-settings>`: ``8``))

    Maximum number of simultaneous requests per domain.

    It defines a number of “slots” per domain. Each slot can send 1 request at
    a time: it sends a request, waits for the response, then sends the next
    request, and so on.

-   .. setting:: DOWNLOAD_DELAY

    :setting:`DOWNLOAD_DELAY` (default: ``1`` (:ref:`fallback <default-settings>`: ``0``))

    Minimum seconds between any two requests to the same domain.

    Even if you have multiple slots, requests to the same domain cannot be sent
    more frequently than this delay.

    To target a specific number of requests per minute (RPM) *per domain*, set
    this to ``60 / RPM``. For example, ``DOWNLOAD_DELAY = 1.0`` for 60 RPM, or
    ``DOWNLOAD_DELAY = 2.0`` for 30 RPM.

-   .. setting:: DOWNLOAD_DELAY_PER_SLOT

    :setting:`DOWNLOAD_DELAY_PER_SLOT` (default: ``None``)

    Minimum seconds to wait between two consecutive requests sent to the same
    download slot. Unlike :setting:`DOWNLOAD_DELAY`, which applies per domain
    (:ref:`throttling scope <throttling-scopes>`), this delay is per slot.

    When ``None`` (default), the per-slot delay falls back to
    :setting:`DOWNLOAD_DELAY`, preserving the historical behavior where
    :setting:`DOWNLOAD_DELAY` was enforced per slot.

    The wait time is measured from when the previous request was sent.

For example, with ``DOWNLOAD_DELAY = 1.0`` (and, by default, a single download
slot per domain), requests to the same domain are sent at most once per second:

.. code-block:: text

    T=0.0s: Request 1 sent
    T=1.0s: Request 2 sent
    T=2.0s: Request 3 sent

:setting:`DOWNLOAD_DELAY` (per :ref:`throttling scope <throttling-scopes>`) and
:setting:`DOWNLOAD_DELAY_PER_SLOT` (per download slot) are enforced
independently. By default each domain is both its own scope and its own
download slot, so both apply to the same requests and the effective minimum
spacing is the larger of the two; they only differ when requests are grouped
into custom :ref:`scopes <throttling-scopes>` or download slots (via the
``download_slot`` request meta key).

When configuring these settings, note that:

-   :setting:`CONCURRENT_REQUESTS` caps ``CONCURRENT_REQUESTS_PER_DOMAIN``.

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

It is a dict that maps scope names to
:class:`~scrapy.throttling.ThrottlingScopeConfig` dicts.

Its default value allows faster crawling of the testing website using during
the :ref:`tutorial <intro-tutorial>` while maintaining conservative defaults
for other domains:

.. code-block:: python

    THROTTLING_SCOPES = {
        "quotes.toscrape.com": {"concurrency": 16, "delay": 0.0},
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

    HTTP response status codes that trigger backoff.

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

Every :ref:`throttling scope <throttling-scopes>` keeps a current delay that
starts at its configured value (``0`` by default, or :setting:`DOWNLOAD_DELAY`
for the default per-domain scopes).

A **backoff trigger** is a response whose status code is in
:setting:`BACKOFF_HTTP_CODES` or a download exception whose type is in
:setting:`BACKOFF_EXCEPTIONS`. On each trigger:

#.  If the response carries a :ref:`Retry-After or RateLimit-Reset
    <rate-limiting-headers>` value, that value (capped at
    :setting:`BACKOFF_MAX_DELAY`) is honored as a hard minimum: no request is
    sent for the scope until it elapses.

#.  Otherwise the delay grows exponentially:

    .. code-block:: text

        delay = min(BACKOFF_MAX_DELAY, max(BACKOFF_MIN_DELAY, delay * BACKOFF_DELAY_FACTOR))

    :setting:`BACKOFF_JITTER` is then applied so that requests that backed off
    together do not retry in lockstep.

**Recovery** is linear: after a scope goes a full :setting:`BACKOFF_WINDOW`
without a new trigger, its delay drops by one :setting:`BACKOFF_DELAY_FACTOR`
step toward the configured value, and keeps dropping one step per quiet window
until it is back to the configured value. A new trigger resets the countdown.

This exponential-increase / linear-decrease pattern, similar to TCP congestion
control, makes a scope back off quickly when a server is unhappy and return to
full speed gradually once it recovers. To keep a scope hovering around a target
rate instead of repeatedly probing and backing off, enable :ref:`rampup
<rampup>`.

.. _per-scope-backoff:

Per-scope backoff configuration
-------------------------------

The global ``BACKOFF_*`` settings can be overridden per scope with the
``"backoff"`` key of a :setting:`THROTTLING_SCOPES` entry, an instance of
:class:`~scrapy.throttling.BackoffConfig`:

.. code-block:: python
    :caption: ``settings.py``

    THROTTLING_SCOPES = {
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

Any key left out falls back to the matching global ``BACKOFF_*`` setting.

.. _rampup:

Rampup
======

When using APIs that charge per request, like web scraping APIs, you often want
to maximize throughput while staying within rate limits. To do that, set
``"rampup"`` to ``True`` in :setting:`THROTTLING_SCOPES`:

.. code-block:: python
    :caption: ``settings.py``

    THROTTLING_SCOPES = {
        "api.toscrape.com": {
            "rampup": True,
        },
    }

Rampup increases concurrency or lowers delay as needed based on the following
setting:

-   .. setting:: RAMPUP_BACKOFF_TARGET

    :setting:`RAMPUP_BACKOFF_TARGET` (default: ``1``)

    Target number of backoff responses per :setting:`BACKOFF_WINDOW` that
    :ref:`rampup <rampup>` aims for when probing the rate limit of a scope.
    Can be a range like ``[1, 3]``.

For every :setting:`BACKOFF_WINDOW` that stays **below**
:setting:`RAMPUP_BACKOFF_TARGET` backoff triggers, rampup increases throughput
one step: it first lowers the delay, and once the delay reaches its minimum it
raises the concurrency limit above the ``"min_concurrency"`` floor of the
scope. Windows that hit the target hold the current rate, and windows that
exceed it let normal :ref:`backoff <backoff>` reduce the rate. The result is a
rate that converges on roughly :setting:`RAMPUP_BACKOFF_TARGET` rate-limit
responses per window — the most throughput a scope allows without being
penalized.

Rampup behavior can be fine-tuned per scope by giving ``"rampup"`` a dict
instead of ``True``:

.. code-block:: python
    :caption: ``settings.py``

    THROTTLING_SCOPES = {
        "api.toscrape.com": {
            "rampup": {
                "backoff_target": [1, 3],  # overrides RAMPUP_BACKOFF_TARGET
                "delay_factor": 0.5,  # multiply the delay by this on each ramp-up step
                "min_delay": 0.05,  # do not ramp the delay below this
            },
        },
    }


.. _retry-after:
.. _rate-limiting-headers:

Rate limiting headers
=====================

Servers may include `Retry-After
<https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Retry-After>`__
or `RateLimit-Reset
<https://www.ietf.org/archive/id/draft-polli-ratelimit-headers-02.html#name-ratelimit-reset>`__
headers to indicate when you should make your next request. These headers are
respected automatically during :ref:`backoff <backoff>`, using their values as
minimum delays (capped at :setting:`BACKOFF_MAX_DELAY`).

.. seealso:: :setting:`REDIRECT_MAX_DELAY`

.. _crawl-delay:

robots.txt
==========

`Crawl-Delay <https://en.wikipedia.org/wiki/Robots.txt#Crawl-delay_directive>`__
is a non-standard ``robots.txt`` directive that indicates a number of seconds
to wait between requests.

.. setting:: THROTTLING_ROBOTSTXT_OBEY
.. setting:: THROTTLING_ROBOTSTXT_MAX_DELAY

If :setting:`ROBOTSTXT_OBEY` and :setting:`THROTTLING_ROBOTSTXT_OBEY` are
``True`` (default), valid ``Crawl-Delay`` directives override
:setting:`CONCURRENT_REQUESTS_PER_DOMAIN` and :setting:`DOWNLOAD_DELAY`. Concurrency
is set to ``1`` and delay is set to the value of ``Crawl-Delay``, capped at
:setting:`THROTTLING_ROBOTSTXT_MAX_DELAY` (default: ``60.0``).

If :setting:`THROTTLING_SCOPES` defines a different concurrency or delay, it
will be respected, but a warning will be logged about the discrepancy with
``Crawl-Delay``. Set ``ignore_robots_txt`` to ``True`` to silence this warning.

.. _delay-scope:

Delaying a scope programmatically
=================================

You can delay a :ref:`throttling scope <throttling-scopes>` on demand through
:meth:`crawler.throttler.delay_scope()
<scrapy.throttling.ThrottlingManagerProtocol.delay_scope>`:

.. code-block:: python

    crawler.throttler.delay_scope("example.com", 30.0)

This holds back every request of the scope for at least the given number of
seconds, counted as a :ref:`backoff <backoff>` trigger.

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
    :caption: ``settings.py``

    THROTTLING_SCOPES = {
        "api": {"concurrency": 2},
        "users": {"delay": 5.0},
    }

.. note:: These custom throttling groups persist through redirects. For
    redirect-aware throttling assignment, see :ref:`custom-throttling-scopes`.

.. reqmeta:: throttling_delay

Delaying a single request
-------------------------

To hold a single request for a fixed number of seconds before it is sent,
regardless of its scopes, set the ``throttling_delay`` request metadata key:

.. code-block:: python

    Request("https://example.com/slow", meta={"throttling_delay": 5.0})

The delay is applied once, the first time the request reaches the throttling
gate.

``throttling_delay`` defines only the *earliest* time the request may be sent,
not the exact time: once the delay elapses, the request still competes with
every other pending request for its scopes. If you want it sent **as soon as**
its delay elapses, give it a higher :attr:`~scrapy.Request.priority` too:

.. code-block:: python

    Request("https://example.com/slow", meta={"throttling_delay": 5.0}, priority=1)

Without a higher priority, a backlog of requests ahead of it in a FIFO queue
could keep it waiting well past the configured delay; a higher priority puts it
at the front of the queue, so it goes out right after its delay.

.. reqmeta:: throttling_dont_track

Excluding a request from throttling state
-----------------------------------------

Some requests (authentication flows, one-off API calls, file downloads) should
not influence throttling state even if they get a :setting:`BACKOFF_HTTP_CODES`
response or raise a :setting:`BACKOFF_EXCEPTIONS` exception. Set the
``throttling_dont_track`` request metadata key to ``True`` to process such a
request normally without letting its outcome trigger :ref:`backoff <backoff>`:

.. code-block:: python

    Request("https://example.com/login", meta={"throttling_dont_track": True})

.. _throttling-scopes:

Throttling scopes
=================

Throttling scopes represent aspects of requests that can be throttled
independently.

..
    For future reference, the “throttling scope” name was taken from
    https://www.ietf.org/archive/id/draft-polli-ratelimit-headers-02.html#section-1.4-4.4

.. _custom-throttling-scopes:

Customizing throttling scopes
------------------------------

There are 2 ways to customize throttling scopes.

To **configure existing scopes**, use the :setting:`THROTTLING_SCOPES` setting.
Its keys are scope names and its values are
:class:`~scrapy.throttling.ThrottlingScopeConfig` dicts, which accept the
following keys:

``concurrency`` (:class:`int`)
    Maximum number of concurrent requests for the scope. When unset, the
    per-domain concurrency (:setting:`CONCURRENT_REQUESTS_PER_DOMAIN`) applies
    instead.

``min_concurrency`` (:class:`int`)
    Concurrency floor that :ref:`backoff <backoff>` and :ref:`rampup <rampup>`
    never drop below. Defaults to ``1``.

``delay`` (:class:`float`)
    Minimum seconds between requests for the scope. Defaults to
    :setting:`DOWNLOAD_DELAY`.

``jitter`` (:class:`float` or 2-:class:`list`)
    Per-scope override of :setting:`RANDOMIZE_DOWNLOAD_DELAY`.

``quota`` (:class:`float`)
    Maximum :ref:`quota <throttling-quotas>` consumed per ``window``.

``window`` (:class:`float`)
    Quota window in seconds. Defaults to :setting:`THROTTLING_WINDOW`.

``rampup`` (:class:`bool` or :class:`dict`)
    Enables :ref:`rampup <rampup>` for the scope.

``backoff`` (:class:`~scrapy.throttling.BackoffConfig`)
    Per-scope :ref:`backoff overrides <per-scope-backoff>`.

``manager`` (:class:`str` or :class:`type`)
    Import path or class of a :ref:`custom scope manager
    <custom-throttling-scope-managers>` for the scope.

``ignore_robots_txt`` (:class:`bool`)
    Silences the warning logged when this configuration is more aggressive than
    a :ref:`robots.txt Crawl-delay <crawl-delay>`.

.. setting:: THROTTLING_MANAGER

To **change how scopes are assigned** (or anything beyond per-scope settings),
set :setting:`THROTTLING_MANAGER` (default:
:class:`~scrapy.throttling.ThrottlingManager`) to a :ref:`component
<topics-components>` that implements the
:class:`~scrapy.throttling.ThrottlingManagerProtocol` protocol (or its import
path as a string):

.. code-block:: python
    :caption: ``settings.py``

    THROTTLING_MANAGER = "myproject.throttling.MyThrottlingManager"

.. _multiple-throttling-scopes:

Handling of multiple throttling scopes
--------------------------------------

When a request has multiple throttling scopes, it is not sent until all of its
throttling scopes allow it.

.. _throttling-quotas:

Throttling quotas
-----------------

When different requests can consume different amounts of a throttling scope,
you can express this using **throttling quotas**.

.. setting:: THROTTLING_WINDOW

Use the :setting:`THROTTLING_WINDOW` setting (default: ``60.0``) or the ``"window"``
key in the :setting:`THROTTLING_SCOPES` setting to define the time window after
which throttling quotas are reset.

Then use the :setting:`THROTTLING_SCOPES` setting to define the throttling
quotas for each throttling scope:

.. code-block:: python
    :caption: ``settings.py``

    THROTTLING_SCOPES = {
        "api.toscrape.com": {
            "quota": 500.0,
        },
    }

Then, in the :reqmeta:`throttling_scopes` request metadata key or in the return
value of the :meth:`~scrapy.throttling.ThrottlingManagerProtocol.get_scopes`
method, define a :class:`dict` where keys are throttling scopes and values are
:class:`float` values that indicate the expected quota consumption (it does not
need to be exact).

Everything else being equal, :class:`~scrapy.pqueues.ScrapyPriorityQueue` will
prioritize requests that consume a higher portion of the available throttling
quota, to minimize the risk of those requests getting stuck.

.. _custom-throttling-scope-managers:

Customizing throttling scope managers
-------------------------------------

.. setting:: THROTTLING_SCOPE_MANAGER

The :setting:`THROTTLING_SCOPE_MANAGER` setting (default:
:class:`~scrapy.throttling.ThrottlingScopeManager`) is a :ref:`component
<topics-components>` that implements the
:class:`~scrapy.throttling.ThrottlingScopeManagerProtocol` (or its import path
as a string):

.. code-block:: python
    :caption: ``settings.py``

    THROTTLING_SCOPE_MANAGER = "myproject.throttling.MyThrottlingScopeManager"

For each throttling scope, an instance of this class is created to manage any
gradual :ref:`backoff <backoff>` or :ref:`rampup <rampup>` required at run
time.

You can implement your own throttling scope manager if you wish to change the
backoff or rampup behavior beyond what settings allow.

You can also define a custom throttling scope manager for a specific throttling
scope by setting the ``"manager"`` key in the :setting:`THROTTLING_SCOPES`
setting:

.. code-block:: python
    :caption: ``settings.py``

    THROTTLING_SCOPES = {
        "api.toscrape.com": {
            "manager": "myproject.throttling.MyThrottlingScopeManager",
        },
    }

A scope manager only needs to implement the
:class:`~scrapy.throttling.ThrottlingScopeManagerProtocol`. For example, the
following manager enforces a fixed quota per time window without any delay or
exponential backoff, similar to a fixed-window rate limiter:

.. code-block:: python
    :caption: ``myproject/throttling.py``

    import time


    class FixedWindowScopeManager:
        def __init__(self, crawler, config):
            self.limit = config["quota"]
            self.window = config.get("window", 60.0)
            self.reset_at = None
            self.used = 0.0
            self.active = 0

        @classmethod
        def from_crawler(cls, crawler, config):
            return cls(crawler, config)

        def can_send(self, now=None, amount=None):
            now = now if now is not None else time.monotonic()
            if self.reset_at is not None and now >= self.reset_at:
                self.reset_at, self.used = None, 0.0
            if self.used and self.used + (amount or 0) > self.limit:
                return self.reset_at - now
            return 0.0

        def record_sent(self, now=None, amount=None):
            now = now if now is not None else time.monotonic()
            if self.reset_at is None:
                self.reset_at = now + self.window
            self.used += amount or 0
            self.active += 1

        def record_done(self, now=None):
            self.active = max(0, self.active - 1)

        def record_backoff(self, delay=None, now=None):
            pass  # this manager does not back off

        def reconcile_quota(self, consumed=None, remaining=None, now=None):
            if remaining is not None:
                self.used = max(0.0, self.limit - remaining)
            elif consumed is not None:
                self.used = max(0.0, self.used + consumed)

        def set_base_delay(self, delay):
            pass

        def set_concurrency(self, concurrency):
            pass

        def is_idle(self, now, max_idle):
            return self.active == 0

.. _throttling-aware-scheduler:

Throttling-aware scheduling
===========================

By default, throttling is enforced at the engine, where a request waiting on
its :ref:`throttling scopes <throttling-scopes>` holds a concurrency slot. In a
crawl that mixes heavily-throttled scopes with unthrottled ones, this can let
throttled requests starve unthrottled ones that could be sent right away
(**head-of-line blocking**; Scrapy logs a warning, see
:setting:`DELAYED_REQUESTS_WARN_THRESHOLD`).

:class:`~scrapy.core.scheduler.ThrottlingAwareScheduler` avoids this. To enable
it:

.. code-block:: python
    :caption: ``settings.py``

    SCHEDULER = "scrapy.core.scheduler.ThrottlingAwareScheduler"
    SCHEDULER_PRIORITY_QUEUE = "scrapy.pqueues.ThrottlingAwarePriorityQueue"

.. autoclass:: scrapy.core.scheduler.ThrottlingAwareScheduler

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
        :caption: ``settings.py``

        import tldextract
        from scrapy.utils.httpobj import urlparse_cached


        class MyThrottlingManager:

            def get_request_scopes(self, request):
                extracted = tldextract.extract(request.url)
                if extracted.domain and extracted.suffix:
                    return f"{extracted.domain}.{extracted.suffix}"
                return urlparse_cached(request).netloc


        THROTTLING_MANAGER = MyThrottlingManager

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
        :caption: ``settings.py``

        import tldextract
        from scrapy.utils.httpobj import urlparse_cached


        class MyThrottlingManager:

            def get_request_scopes(self, request):
                extracted = tldextract.extract(request.url)
                if not (extracted.domain and extracted.suffix):
                    return urlparse_cached(request).netloc
                scopes = set()
                registrable_domain = f"{extracted.domain}.{extracted.suffix}"
                scopes.add(registrable_domain)
                if extracted.subdomain:
                    subdomain_parts = extracted.subdomain.split(".")
                    for i in range(len(subdomain_parts)):
                        subdomain = ".".join(subdomain_parts[i:])
                        full_domain = f"{subdomain}.{registrable_domain}"
                        scopes.add(full_domain)
                return scopes


        THROTTLING_MANAGER = MyThrottlingManager
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

-   Implement a :ref:`throttling manager <custom-throttling-scopes>` that sets
    endpoint-specific throttling scopes for that domain:

    .. code-block:: python

        from scrapy.throttling import ThrottlingManager, scope_cache
        from scrapy.utils.httpobj import urlparse_cached


        class MyThrottlingManager(ThrottlingManager):
            @scope_cache
            async def get_scopes(self, request):
                parsed_url = urlparse_cached(request)
                if parsed_url.netloc != "api.toscrape.com":
                    return await super().get_scopes(request)
                return f"{parsed_url.netloc}{parsed_url.path}"

-   Use the :setting:`THROTTLING_SCOPES` setting to set different throttling
    settings per endpoint:

    .. code-block:: python
        :caption: ``settings.py``

        THROTTLING_SCOPES = {
            "api.toscrape.com/fast-endpoint": {"concurrency": 1000, "delay": 0.08},
            "api.toscrape.com/slow-endpoint": {"delay": 5.0},
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
        :caption: ``settings.py``

        THROTTLING_SCOPES = {
            "api.toscrape.com": {"concurrency": 1000, "delay": 0.08},
        }

-   Implement a :ref:`throttling manager <custom-throttling-scopes>` that:

    -   Adds a throttling scope for the URL being scraped.

        For example, if you request
        ``https://api.toscrape.com/?url=https://example.com``, by default it
        will get a ``api.toscrape.com`` throttling scope, but it should also
        get the ``example.com`` throttling scope:

        .. code-block:: python

            from urllib.parse import urlparse

            from scrapy.throttling import add_scope, ThrottlingManager, scope_cache
            from scrapy.utils.httpobj import urlparse_cached
            from w3lib.url import url_query_parameter


            class MyThrottlingManager(ThrottlingManager):
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

    -   Can differentiate between exhaustion of the target website and
        exhaustion of the API itself. For example:

        .. code-block:: python

            from scrapy.throttling import ThrottlingManager
            from scrapy.utils.httpobj import urlparse_cached


            class MyThrottlingManager(ThrottlingManager):
                async def get_response_backoff(self, response):
                    if (
                        urlparse_cached(response.request).netloc != "api.toscrape.com"
                        or response.status != 200
                    ):
                        return await super().get_response_backoff(response)
                    upstream_status_code = int(
                        response.headers.get("X-Upstream-Status-Code", b"200")
                    )
                    upstream_response = response.__class__(
                        response.url,
                        status=upstream_status_code,
                        headers=response.headers,
                        body=response.body,
                    )
                    return await super().get_response_backoff(upstream_response)


.. _cost-smoothing-throttling:

Cost-capped throttling
----------------------

Imagine you are using an API that charges different requests differently, e.g.
based on the features used, and you want to limit how much you spend per time
window (:setting:`BACKOFF_WINDOW`). You can use :ref:`throttling quotas
<throttling-quotas>` for that:

-   Implement a :ref:`throttling manager <custom-throttling-scopes>` that:

    -   Sets a ``cost`` throttling scope on each request to some estimation
        based e.g. on request URL parameters:

        .. code-block:: python

            from scrapy.utils.httpobj import urlparse_cached
            from scrapy.throttling import ThrottlingManager, scope_cache


            class MyThrottlingManager(ThrottlingManager):
                @scope_cache
                async def get_scopes(self, request):
                    scopes = await super().get_scopes(request)
                    parsed_url = urlparse_cached(request)
                    if parsed_url.netloc != "api.toscrape.com":
                        return scopes
                    return add_scope(scopes, "cost", estimate_request_cost(request))

    -   Reconciles the estimated cost with the actual cost reported by the
        response, so that the quota tracks real spending:

        .. code-block:: python

            from scrapy.throttling import ThrottlingManager, update_scope_backoff


            class MyThrottlingManager(ThrottlingManager):
                async def get_response_backoff(self, response):
                    backoff = await super().get_response_backoff(response)
                    if response.headers.get("X-Actual-Cost") is None:
                        return backoff
                    estimated = estimate_request_cost(response.request)
                    actual = float(response.headers[b"X-Actual-Cost"])
                    # Report the difference between actual and estimated cost.
                    return update_scope_backoff(backoff, "cost", consumed=actual - estimated)

-   Use the :setting:`THROTTLING_SCOPES` setting to set a maximum cost per time
    window:

    .. code-block:: python
        :caption: ``settings.py``

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
:ref:`multiple-throttling-scopes`).

-   Implement a :ref:`throttling manager <custom-throttling-scopes>` that adds
    the request's IP as a second scope:

    .. code-block:: python

        import socket

        from scrapy.throttling import ThrottlingManager, add_scope, scope_cache
        from scrapy.utils.asyncio import run_in_thread
        from scrapy.utils.httpobj import urlparse_cached


        class IPThrottlingManager(ThrottlingManager):
            @scope_cache
            async def get_scopes(self, request):
                scopes = await super().get_scopes(request)
                host = urlparse_cached(request).hostname
                address = await run_in_thread(socket.gethostbyname, host)
                return add_scope(scopes, address)

.. _throttling-settings:

Additional settings
===================
-   .. setting:: BACKOFF_EXCEPTIONS

    :setting:`BACKOFF_EXCEPTIONS`

    Default:

    -   :exc:`~scrapy.exceptions.DownloadFailedError`
    -   :exc:`~scrapy.exceptions.DownloadTimeoutError`
    -   :exc:`~scrapy.exceptions.ResponseDataLossError`

    List of exception classes that trigger backoff when raised while
    downloading a request. Strings are interpreted as import paths.

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

    Time window, in seconds, used by :ref:`backoff <backoff>` and
    :ref:`rampup <rampup>`. During backoff, a :ref:`throttling scope
    <throttling-scopes>` must go this many seconds without a new backoff
    trigger (an HTTP error code from :setting:`BACKOFF_HTTP_CODES` or an
    exception from :setting:`BACKOFF_EXCEPTIONS`) before its delay decreases
    by one :setting:`BACKOFF_DELAY_FACTOR` step toward the configured value.
    A new trigger resets the countdown.

-   .. setting:: DELAYED_REQUESTS_WARN_THRESHOLD

    :setting:`DELAYED_REQUESTS_WARN_THRESHOLD` (default: ``500``)

    Number of requests held back by :ref:`throttling <throttling>` at which
    Scrapy logs a warning, to help detect throttling configurations that hold
    back more requests than expected.

    While throttled, requests in the :ref:`scheduler <topics-scheduler>`
    remain in the scheduler. However, requests sent with :meth:`engine.download()
    <scrapy.core.engine.ExecutionEngine.download>` bypass the scheduler,
    including requests sent by some built-in :ref:`components
    <topics-components>` and :ref:`inline requests <inline-requests>`. When
    such requests are throttled, they are paused and kept in memory, along
    with any run time context from the code that is sending them. If they
    accumulate, they can become a memory issue.

-   .. setting:: RANDOMIZE_DOWNLOAD_DELAY

    :setting:`RANDOMIZE_DOWNLOAD_DELAY` (default: ``True``)

    Randomize delays by this factor, e.g. if ``0.2`` randomize delays between
    ``delay*0.8`` and ``delay*1.2``.

    It can be set to a 2-item list with low and high factors, e.g.
    ``[-0.1, 0.3]`` to randomize delays between ``delay*0.9`` and
    ``delay*1.3``.

    If ``True``, ``0.5`` (i.e. ±50%) is used as the randomization factor. If
    ``False``, no randomization is applied.

-   .. setting:: THROTTLING_DEBUG

    :setting:`THROTTLING_DEBUG` (default: ``False``)

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

.. _autothrottle-migration:

Migrating from AutoThrottle
===========================

The ``AutoThrottle`` extension is deprecated in favor of the throttling and
:ref:`backoff <backoff>` system described here, which is always active and does
not need to be enabled.

Setting :setting:`AUTOTHROTTLE_ENABLED` to ``True`` still works but logs a
deprecation warning. To migrate, drop the ``AUTOTHROTTLE_*`` settings and use
the following equivalents:

.. list-table::
    :header-rows: 1

    * - AutoThrottle
      - Throttling
    * - ``AUTOTHROTTLE_ENABLED = True``
      - No equivalent; throttling is always active.
    * - ``AUTOTHROTTLE_START_DELAY``
      - :setting:`DOWNLOAD_DELAY`
    * - ``AUTOTHROTTLE_MAX_DELAY``
      - :setting:`BACKOFF_MAX_DELAY`
    * - ``AUTOTHROTTLE_TARGET_CONCURRENCY``
      - :ref:`rampup <rampup>` (``"rampup": True``)
    * - ``AUTOTHROTTLE_DEBUG = True``
      - :setting:`THROTTLING_DEBUG` ``= True``
    * - ``autothrottle_dont_adjust_delay`` (request meta)
      - :reqmeta:`throttling_dont_track` (request meta)

AutoThrottle adjusted the delay of each download slot based on response
latency. The new system does not measure latency; instead, it reacts to
explicit rate-limit signals (:setting:`BACKOFF_HTTP_CODES`,
:setting:`BACKOFF_EXCEPTIONS`, :ref:`Retry-After / RateLimit-Reset
<rate-limiting-headers>`) and, with :ref:`rampup <rampup>`, probes for the
fastest rate a scope tolerates. If you specifically need latency-based control,
implement a custom :ref:`throttling scope manager
<custom-throttling-scope-managers>`.


.. _throttling-api:

API
===

.. autoclass:: scrapy.throttling.ThrottlingManagerProtocol
    :members:
    :member-order: bysource

.. autoclass:: scrapy.throttling.ThrottlingManager
    :members: get_response_delay

.. autoclass:: scrapy.throttling.ThrottlingScopeManagerProtocol
    :members:
    :member-order: bysource

.. autoclass:: scrapy.throttling.ThrottlingScopeManager

.. autoclass:: scrapy.pqueues.ThrottlingAwarePriorityQueue

.. autoclass:: scrapy.throttling.ThrottlingScopeConfig

.. autoclass:: scrapy.throttling.BackoffConfig

.. autofunction:: scrapy.throttling.scope_cache
.. autofunction:: scrapy.throttling.add_scope
.. autofunction:: scrapy.throttling.update_scope_backoff
