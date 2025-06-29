.. _throttling:

==========
Throttling
==========

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

    :setting:`CONCURRENT_REQUESTS_PER_DOMAIN` (default: ``1``)

    Maximum number of simultaneous requests per domain.

    It defines a number of “slots” per domain. Each slot can send 1 request at
    a time: it sends a request, waits for the response, then sends the next
    request, and so on.

-   .. setting:: DOWNLOAD_DELAY

    :setting:`DOWNLOAD_DELAY` (default: ``1.0``)

    Minimum seconds between any two requests to the same domain.

    Even if you have multiple slots, requests to the same domain cannot be sent
    more frequently than this delay.

-   .. setting:: DOWNLOAD_DELAY_PER_SLOT

    :setting:`DOWNLOAD_DELAY_PER_SLOT` (default: ``1.0``)

    Minimum seconds between requests in the same slot.

    If a slot sends a request and receives its response before this delay has
    elapsed, it must wait before sending the next request. The wait time is
    measured from when the previous request was sent.

For example, with ``CONCURRENT_REQUESTS_PER_DOMAIN = 2``, ``DOWNLOAD_DELAY = 0.3``,
and ``DOWNLOAD_DELAY_PER_SLOT = 1.0``, sending 3 requests to the same domain
would result in:

.. code-block:: text

    T=0.0s: Request 1 sent (slot 1)
    T=0.3s: Request 2 sent (slot 2, respects same-domain delay)
    T=0.6s: Request 3 must wait (same-domain delay satisfied, but slot 1 needs 1.0s)
    T=1.0s: Request 3 sent (slot 1 can now be reused)

When configuring these settings, note that:

-   :setting:`CONCURRENT_REQUESTS` caps ``CONCURRENT_REQUESTS_PER_DOMAIN``.

-   If ``DOWNLOAD_DELAY`` ≥ response time, concurrency is effectively ``1``.
    This happens because all slots must wait for the delay between requests,
    preventing them from sending requests simultaneously.

.. [1] You can :ref:`customize <throttling-scopes>` how requests are grouped
    for throttling, but domain-based throttling works well in most cases. For
    more complex domain grouping strategies, see
    :ref:`alternative-domain-throttling`.


.. setting:: THROTTLING_SCOPES
.. _per-domain-throttling:

Per-domain throttling
=====================

The :setting:`THROTTLING_SCOPES` setting allows you to customize throttling behavior
for specific domains [1]_.

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

    HTTP status codes that trigger backoff.

-   .. setting:: BACKOFF_DELAY_FACTOR

    :setting:`BACKOFF_DELAY_FACTOR` (default: ``2.0``)

    Each backoff multiplies delay by this factor (2x, 4x, 8x, etc.).

-   .. setting:: BACKOFF_MAX_DELAY

    :setting:`BACKOFF_MAX_DELAY` (default: ``300.0``)

    Maximum delay cap to prevent excessively long waits.


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

    Target number of backoff responses per rampup window, indicating optimal
    throughput. Can be a range like ``[1, 3]``.


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

.. setting:: THROTTLING_MANAGER

For anything else, set :setting:`THROTTLING_MANAGER` (default:
:class:`~scrapy.throttling.ThrottlingManager`) to a :ref:`component
<topics-components>` that implements the
:class:`~scrapy.throttling.ThrottlingManagerProtocol` protocol (or its import
path as a string):

.. code-block:: python
    :caption: ``settings.py``

    THROTTLING_MANAGER = "myproject.throttling.MyThrottlingManager"


.. _multi-throttling-scopes:

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

    -   Sets a ``cost`` throttling scope on each request to some estimation based
        e.g. on request URL parameters:

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

    -   Reports the actual cost during response parsing:

        .. code-block:: python

            from scrapy.throttling import ThrottlingManager


            class MyThrottlingManager(ThrottlingManager):
                async def get_response_backoff(self, response):
                    scopes = await super().get_response_backoff(response)
                    if "cost" not in scopes:
                        return scopes
                    actual_cost = float(response.headers.get("X-Actual-Cost", b"0"))
                    return update_scope_backoff(scopes, "cost", consumed_quota=actual_cost)

-   Use the :setting:`THROTTLING_SCOPES` setting to set a maximum cost per time
    window:

    .. code-block:: python
        :caption: ``settings.py``

        THROTTLING_SCOPES = {
            "cost": {"quota": 100.0},
        }

    This will allow you to spend up to 100.0 units of cost per time window
    (default: 60 seconds) before throttling kicks in.


.. _throttling-settings:

Additional settings
===================
-   .. setting:: BACKOFF_EXCEPTIONS

    :setting:`BACKOFF_EXCEPTIONS`

    Default:

    .. code-block:: python

        [
            "twisted.internet.defer.TimeoutError",
            "twisted.internet.error.TimeoutError",
            "twisted.internet.error.TCPTimedOutError",
            "twisted.web.client.ResponseFailed",
        ]

    Exception classes that trigger backoff. Strings are interpreted as import
    paths.

    .. seealso:: :setting:`RETRY_EXCEPTIONS`

-   .. setting:: BACKOFF_JITTER

    :setting:`BACKOFF_JITTER` (default: ``0.1``)

    Overrides :setting:`RANDOMIZE_DOWNLOAD_DELAY` during backoff.

-   .. setting:: BACKOFF_MIN_DELAY

    :setting:`BACKOFF_MIN_DELAY` (default: ``1.0``)

    Minimum delay during :ref:`backoff <backoff>`.

-   .. setting:: BACKOFF_WINDOW

    :setting:`BACKOFF_WINDOW` (default: ``60.0``)

    During :ref:`backoff <backoff>`, after a non-backoff response is received,
    do not take the next step in backoff reduction until this amount of time
    has passed and no new backoff feedback has been received.

    The number of seconds that need to pass since the last non-backoff response
    without any other for the backoff to move towards the original throttling
    configuration.

-   .. setting:: DELAYED_REQUESTS_WARN_THRESHOLD

    :setting:`DELAYED_REQUESTS_WARN_THRESHOLD` (default: ``500``)

    While throttled, requests in the :ref:`scheduler <topics-scheduler>` remain
    in the scheduler.

    However, requests sent with :meth:`engine.download()
    <scrapy.core.engine.ExecutionEngine.download>` bypass the scheduler. This
    includes requests sent by some built-in :ref:`components
    <topics-components>` and :ref:`inline requests <inline-requests>`.

    When such requests are throttled, they are paused and kept in memory, along
    with any run time context from the code that is sending them. If they
    accumulate, they can become a memory issue that may require you to rethink
    your throttling parameters or crawl strategy.

    :setting:`DELAYED_REQUESTS_WARN_THRESHOLD` defines a threshold for such
    requests. The first time that this many such requests are being throttled
    at the same time, a warning is issued.

-   .. setting:: RANDOMIZE_DOWNLOAD_DELAY

    :setting:`RANDOMIZE_DOWNLOAD_DELAY` (default: ``True``)

    Randomize delays by this factor, e.g. if ``0.2`` randomize delays between
    ``delay*0.8`` and ``delay*1.2``.

    It can be set to a 2-item list with low and high factors, e.g.
    ``[-0.1, 0.3]`` to randomize delays between ``delay*0.9`` and
    ``delay*1.3``.

    If ``True``, ``0.5`` (i.e. ±50%) is used as the randomization factor. If
    ``False``, no randomization is applied.


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

.. autofunction:: scrapy.throttling.scope_cache
.. autofunction:: scrapy.throttling.add_scope
.. autofunction:: scrapy.throttling.update_scope_backoff






..
        When a throttling scope is configured with a **concurrency higher than 1**,
        backoff is handled separately per slot. If at some point all
        slots reach the maximum backoff delay, a “concurrency backoff”
        starts, controlled by the following setting:

        -   .. setting:: BACKOFF_CONCURRENCY_DECREASE_FACTOR

            :setting:`BACKOFF_CONCURRENCY_FACTOR` (default: ``0.5``)

            The factor by which the concurrency is decreased during concurrency
            backoff.

    .. _scope-backoff:

    Backoff settings can be overridden per throttling scope using
    :setting:`THROTTLING_SCOPES`:

    .. code-block:: python

        {
            "example.com": {
                "backoff": {
                    "http_codes": [429, 503],
                    "exceptions": ["builtins.IOError"],
                    "delay_factor": 1.2,
                    "max_delay": 180.0,
                    "min_delay": 5.0,
                    "jitter": [0.01, 0.33],
                    "concurrency_factor": 0.8,
                }
            },
        }

..
    TODO: Continue from here

..
    TODO: Support backoff in THROTTLING_SCOPES having a cls key with a class
    or its import path as a string, and arbitraty kwargs to pass to its
    __init__ method, to implement a custom backoff strategy.


..
    TODO: Make sure that the API is flexible enough to support scrapy-zyte-api
    use cases.

..
    TODO: Try to figure out the implementation for the entire feature, and how
    that may affect the user-facing API.

..
    TODO: Think about:
    - How backoff state is handled.
    - Implement a setting that allows customizing the backoff window, which
      should be 60.0 seconds by default, and should be overridable per scope.
    - How backoff could be fine-tuned to deal with scenarios where it is
      ping-poning between 2 states, and it should be possible to go for an
      in-between state that allows maximizing throughtput while still
      minimizing backoff feedback (backoff response or exception), aiming for a
      single backoff feedback per backoff window.

..
    TODO: Figure out the interaction APIs between components when we have:
    - The scheduler using the throttling manager to decide whether a request
      can be sent or not, and to sort requests.

..
    TODO: Review all related issues and PRs, including those about multiple
    slots, about per-request delays, and about politeness, and make sure every
    scenario is covered here.

..
    TODO: See if there is any info from the old autothrottle docs worth
    keeping:

    .. _topics-autothrottle:

    ======================
    AutoThrottle extension
    ======================

    This is an extension for automatically throttling crawling speed based on load
    of both the Scrapy server and the website you are crawling.

    Design goals
    ============

    1. be nicer to sites instead of using default download delay of zero
    2. automatically adjust Scrapy to the optimum crawling speed, so the user
    doesn't have to tune the download delays to find the optimum one.
    The user only needs to specify the maximum concurrent requests
    it allows, and the extension does the rest.

    .. _autothrottle-algorithm:

    How it works
    ============

    Scrapy allows defining the concurrency and delay of different download slots,
    e.g. through the :setting:`DOWNLOAD_SLOTS` setting. By default requests are
    assigned to slots based on their URL domain, although it is possible to
    customize the download slot of any request.

    The AutoThrottle extension adjusts the delay of each download slot dynamically,
    to make your spider send :setting:`AUTOTHROTTLE_TARGET_CONCURRENCY` concurrent
    requests on average to each remote website.

    It uses download latency to compute the delays. The main idea is the
    following: if a server needs ``latency`` seconds to respond, a client
    should send a request each ``latency/N`` seconds to have ``N`` requests
    processed in parallel.

    Instead of adjusting the delays one can just set a small fixed
    download delay and impose hard limits on concurrency using
    :setting:`CONCURRENT_REQUESTS_PER_DOMAIN` or
    :setting:`CONCURRENT_REQUESTS_PER_IP` options. It will provide a similar
    effect, but there are some important differences:

    * because the download delay is small there will be occasional bursts
    of requests;
    * often non-200 (error) responses can be returned faster than regular
    responses, so with a small download delay and a hard concurrency limit
    crawler will be sending requests to server faster when server starts to
    return errors. But this is an opposite of what crawler should do - in case
    of errors it makes more sense to slow down: these errors may be caused by
    the high request rate.

    AutoThrottle doesn't have these issues.

    Throttling algorithm
    ====================

    AutoThrottle algorithm adjusts download delays based on the following rules:

    1. spiders always start with a download delay of
    :setting:`AUTOTHROTTLE_START_DELAY`;
    2. when a response is received, the target download delay is calculated as
    ``latency / N`` where ``latency`` is a latency of the response,
    and ``N`` is :setting:`AUTOTHROTTLE_TARGET_CONCURRENCY`.
    3. download delay for next requests is set to the average of previous
    download delay and the target download delay;
    4. latencies of non-200 responses are not allowed to decrease the delay;
    5. download delay can't become less than :setting:`DOWNLOAD_DELAY` or greater
    than :setting:`AUTOTHROTTLE_MAX_DELAY`

    .. note:: The AutoThrottle extension honours the standard Scrapy settings for
    concurrency and delay. This means that it will respect
    :setting:`CONCURRENT_REQUESTS_PER_DOMAIN` and
    :setting:`CONCURRENT_REQUESTS_PER_IP` options and
    never set a download delay lower than :setting:`DOWNLOAD_DELAY`.

    .. _download-latency:

    In Scrapy, the download latency is measured as the time elapsed between
    establishing the TCP connection and receiving the HTTP headers.

    Note that these latencies are very hard to measure accurately in a cooperative
    multitasking environment because Scrapy may be busy processing a spider
    callback, for example, and unable to attend downloads. However, these latencies
    should still give a reasonable estimate of how busy Scrapy (and ultimately, the
    server) is, and this extension builds on that premise.

    .. reqmeta:: autothrottle_dont_adjust_delay

    Prevent specific requests from triggering slot delay adjustments
    ================================================================

    AutoThrottle adjusts the delay of download slots based on the latencies of
    responses that belong to that download slot. The only exceptions are non-200
    responses, which are only taken into account to increase that delay, but
    ignored if they would decrease that delay.

    You can also set the ``autothrottle_dont_adjust_delay`` request metadata key to
    ``True`` in any request to prevent its response latency from impacting the
    delay of its download slot:

    .. code-block:: python

        from scrapy import Request

        Request("https://example.com", meta={"autothrottle_dont_adjust_delay": True})

    Note, however, that AutoThrottle still determines the starting delay of every
    download slot by setting the ``download_delay`` attribute on the running
    spider. If you want AutoThrottle not to impact a download slot at all, in
    addition to setting this meta key in all requests that use that download slot,
    you might want to set a custom value for the ``delay`` attribute of that
    download slot, e.g. using :setting:`DOWNLOAD_SLOTS`.

    Settings
    ========

    The settings used to control the AutoThrottle extension are:

    * :setting:`AUTOTHROTTLE_ENABLED`
    * :setting:`AUTOTHROTTLE_START_DELAY`
    * :setting:`AUTOTHROTTLE_MAX_DELAY`
    * :setting:`AUTOTHROTTLE_TARGET_CONCURRENCY`
    * :setting:`AUTOTHROTTLE_DEBUG`
    * :setting:`CONCURRENT_REQUESTS_PER_DOMAIN`
    * :setting:`CONCURRENT_REQUESTS_PER_IP`
    * :setting:`DOWNLOAD_DELAY`

    For more information see :ref:`autothrottle-algorithm`.

    .. setting:: AUTOTHROTTLE_ENABLED

    AUTOTHROTTLE_ENABLED
    ~~~~~~~~~~~~~~~~~~~~

    Default: ``False``

    Enables the AutoThrottle extension.

    .. setting:: AUTOTHROTTLE_START_DELAY

    AUTOTHROTTLE_START_DELAY
    ~~~~~~~~~~~~~~~~~~~~~~~~

    Default: ``5.0``

    The initial download delay (in seconds).

    .. setting:: AUTOTHROTTLE_MAX_DELAY

    AUTOTHROTTLE_MAX_DELAY
    ~~~~~~~~~~~~~~~~~~~~~~

    Default: ``60.0``

    The maximum download delay (in seconds) to be set in case of high latencies.

    .. setting:: AUTOTHROTTLE_TARGET_CONCURRENCY

    AUTOTHROTTLE_TARGET_CONCURRENCY
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    Default: ``1.0``

    Average number of requests Scrapy should be sending in parallel to remote
    websites. It must be higher than ``0.0``.

    By default, AutoThrottle adjusts the delay to send a single
    concurrent request to each of the remote websites. Set this option to
    a higher value (e.g. ``2.0``) to increase the throughput and the load on remote
    servers. A lower ``AUTOTHROTTLE_TARGET_CONCURRENCY`` value
    (e.g. ``0.5``) makes the crawler more conservative and polite.

    Note that :setting:`CONCURRENT_REQUESTS_PER_DOMAIN`
    and :setting:`CONCURRENT_REQUESTS_PER_IP` options are still respected
    when AutoThrottle extension is enabled. This means that if
    ``AUTOTHROTTLE_TARGET_CONCURRENCY`` is set to a value higher than
    :setting:`CONCURRENT_REQUESTS_PER_DOMAIN` or
    :setting:`CONCURRENT_REQUESTS_PER_IP`, the crawler won't reach this number
    of concurrent requests.

    At every given time point Scrapy can be sending more or less concurrent
    requests than ``AUTOTHROTTLE_TARGET_CONCURRENCY``; it is a suggested
    value the crawler tries to approach, not a hard limit.

    .. setting:: AUTOTHROTTLE_DEBUG

    AUTOTHROTTLE_DEBUG
    ~~~~~~~~~~~~~~~~~~

    Default: ``False``

    Enable AutoThrottle debug mode which will display stats on every response
    received, so you can see how the throttling parameters are being adjusted in
    real time.

..
    TODO: Figure out how to properly deprecate AutoThrottle settings, API and
    keep its presence in the list of enabled extensions without that triggering
    a deprecation warning.

..
    TODO: Avoid so much code duplication in add_scope and update_scope_backoff.

..
    TODO: Describe in detail the backoff algorithm, with steps, etc., and also
    covering how it tries to maintain a sweet spot avoiding

..
    TODO: Define typed dicts for all dicts supported by settings, e.g. for
    THROTTLING_SCOPES.

..
    TODO: Provide an example implementation of a custom throttling scope
    manager based on the current implementation of scrapy-zyte-api retrying
    policy.

..
    TODO: If get_scopes reports expected quotas, treat those as actual
    consumptions at run time, and then handle the actual consumptions reported
    in get_response_backoff by reporting the difference.

    e.g. if a request is expected to consume 2.0 quota, lower the available
    quota in the current window by 2.0. If the response then reports that 2.5
    was actually consumed, then report 0.5 as the difference, to be also
    substracted from the current window.

..
    TODO: Implement some kind of system to free scope-related memory if a given
    scope is not used for a while?

..
    TODO: Think about tracking effective concurrency and delays, and reporting
    to users when their custom settings are not effective for a significant
    period of time.

..
    TODO: Provide a complete list of keys that THROTTLING_SCOPES supports.

..
    TODO: Update news.rst with all the changes, but only once everything else
    has been written. Make sure to include the new REDIRECT_MAX_DELAY setting.
