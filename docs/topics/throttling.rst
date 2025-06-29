.. _throttling:

==========
Throttling
==========

Sending too many requests too quickly can `overload websites`_. To avoid that,
you must throttle_ your requests. Scrapy can :ref:`throttle requests
<basic-throttling>`, :ref:`handle backoff <backoff>`, and much more.

.. _overload websites: https://en.wikipedia.org/wiki/Denial-of-service_attack
.. _throttle: https://en.wikipedia.org/wiki/Bandwidth_throttling

.. _basic-throttling:

Concurrency and delay
=====================

Use the following :ref:`settings <topics-settings>` to configure the default
throttling for each :ref:`throttling scope <throttling-scopes>`:

-   .. setting:: THROTTLING_CONCURRENCY

    **THROTTLING_CONCURRENCY** (default: ``1``)

    The maximum number of concurrent requests.

-   .. setting:: THROTTLING_DELAY

    **THROTTLING_DELAY** (default: ``1.0``)

    The minimum seconds to wait between consecutive requests.

-   .. setting:: THROTTLING_JITTER

    **THROTTLING_JITTER** (default: ``0.5``, i.e. ±50%)

    Randomize delays by this factor, i.e. the final delay is a random value
    between ``delay*(1-jitter)`` and ``delay*(1+jitter)``.

    It can be set to a 2-item list with low and high factors, e.g.
    ``[-0.1, 0.3]`` to randomize delays between ``delay*0.9`` and
    ``delay*1.3``.

.. setting:: THROTTLING_SCOPES

Use **THROTTLING_SCOPES** (default: ``{}``) to override these values for
specific throttling scopes:

    .. code-block:: python

        THROTTLING_SCOPES = {
            "books.toscrape.com": {"concurrency": 16, "delay": 0.0},
            "example.com": {"jitter": 0.2},
        }

:setting:`THROTTLING_SCOPES` can also :ref:`override backoff settings
<scope-backoff>`.

When setting these values, note that:

-   :setting:`CONCURRENT_REQUESTS` effectively caps concurrency for any
    throttling scope.

-   When higher than response time, delay effectively limits concurrency to
    ``1``.


.. _crawl-delay:

Crawl-Delay directive
---------------------

`Crawl-Delay <https://en.wikipedia.org/wiki/Robots.txt#Crawl-delay_directive>`__
is a non-standard ``robots.txt`` directive that indicates a number of seconds to
wait between requests.

.. setting:: THROTTLING_ROBOTSTXT_OBEY
.. setting:: THROTTLING_ROBOTSTXT_MAX_DELAY

If :setting:`ROBOTSTXT_OBEY` and **THROTTLING_ROBOTSTXT_OBEY** are
``True`` (default), valid ``Crawl-Delay`` directives override
:setting:`THROTTLING_CONCURRENCY` and :setting:`THROTTLING_DELAY`. Concurrency
is set to ``1`` and delay is set to the value of ``Crawl-Delay``, capped at
**THROTTLING_ROBOTSTXT_MAX_DELAY** (default: ``60.0``).

If :setting:`THROTTLING_SCOPES` defines a different concurrency or delay, it
will be respected, but a warning will be logged about the discrepancy with
``Crawl-Delay``. Set ``ignore_robots_txt`` to ``True`` to silence this warning.


.. _backoff:

Backoff
=======

When a response or network error warrants backoff, `exponential backoff`_ is
used to reduce request rate.

.. _exponential backoff: https://en.wikipedia.org/wiki/Exponential_backoff

In such cases, every new request with the same throttling scope is sent with
its delay multiplied by some factor (up to some maximum) or set to some minimum
value (if it was lower), until a request gets a response that does not require
backoff. Once a response that does not require backoff is received, the delay
is gradually reduced back to its original value.

The following settings control backoff behavior:

-   .. setting:: BACKOFF_HTTP_CODES

    **BACKOFF_HTTP_CODES** (default: ``[429, 502, 503, 504, 520, 521, 522, 523, 524]``)

    HTTP response status codes that warrant backoff.

    Usually, all codes here should be in :setting:`RETRY_HTTP_CODES` as well,
    but not all codes in :setting:`RETRY_HTTP_CODES` need to be here: some bad
    responses may require a retry without backoff.

-   .. setting:: BACKOFF_EXCEPTIONS

    **BACKOFF_EXCEPTIONS**

    Default:

    .. code-block:: python

        [
            "twisted.internet.defer.TimeoutError",
            "twisted.internet.error.TimeoutError",
            "twisted.internet.error.TCPTimedOutError",
            "twisted.web.client.ResponseFailed",
        ]

    Exception classes that warrant backoff. Strings are interpreted as import
    paths.

    Usually, all exceptions here should be in :setting:`RETRY_EXCEPTIONS` as
    well, but not all exceptions in :setting:`RETRY_EXCEPTIONS` need to be
    here: some errors may require a retry without backoff.

-   .. setting:: BACKOFF_FACTOR

    **BACKOFF_FACTOR** (default: ``2.0``)

    The factor by which the delay is multiplied for each new request sent to a
    given throttling scope during backoff.

-   .. setting:: BACKOFF_MAX_DELAY

    **BACKOFF_MAX_DELAY** (default: ``300.0``)

    The maximum delay that can be applied during backoff. If the delay exceeds
    this value, it will be capped at this value.

-   .. setting:: BACKOFF_MIN_DELAY

    **BACKOFF_MIN_DELAY** (default: ``1.0``)

    The minimum delay that can be applied during backoff. If the delay is less
    than this value, it will be set to this value. Must be higher than ``0.0``.

-   .. setting:: BACKOFF_JITTER

    **BACKOFF_JITTER** (default: ``0.1``)

    Overrides :setting:`THROTTLING_JITTER` during backoff.

When a throttling scope is configured with a **concurrency higher than 1**,
backoff is handled separately per concurrency slot. If at some point all
concurrency slots reach the maximum backoff delay, a “concurrency backoff”
starts, controlled by the following setting:

-   .. setting:: BACKOFF_CONCURRENCY_DECREASE_FACTOR

    **BACKOFF_CONCURRENCY_DECREASE_FACTOR** (default: ``0.5``)

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
                "factor": 1.2,
                "max_delay": 180.0,
                "min_delay": 5.0,
                "jitter": [0.01, 0.33],
                "concurrency_decrease_factor": 0.8,
            }
        },
    }


.. _retry-after:

Rate limiting headers
---------------------

The `Retry-After
<https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Retry-After>`__
and the `RateLimit-Reset
<https://www.ietf.org/archive/id/draft-polli-ratelimit-headers-02.html#name-ratelimit-reset>`__
HTTP response headers indicate how long to wait before making a follow-up
request.

They are taken into account during :ref:`backoff <backoff>`: their value is
read (the highest if both headers are present), capped at
:setting:`BACKOFF_MAX_DELAY`, and used as a minimum delay, i.e. it is used if
higher than the current delay but ignored if lower.

.. seealso:: :setting:`REDIRECT_MAX_DELAY`


.. _throttling-scopes:

Scopes
======

Throttling scopes represent aspects of requests that can be throttled
independently.

..
    For future reference, the “throttling scope” name was taken from
    https://www.ietf.org/archive/id/draft-polli-ratelimit-headers-02.html#section-1.4-4.4

.. _default-throttling-scopes:

Default throttling scopes
--------------------------

By default, each request has a single throttling scope representing the domain
or subdomain of the target URL. That is, when you set the concurrency or delay
of a throttling scope, it applies to all requests made to that domain or
subdomain.

For example, https://books.toscrape.com and
https://books.toscrape.com/catalogue/page-2.html both get a
``books.toscrape.com`` throttling scope.

Note however that subdomains are treated as separate throttling scopes by
default. For example, https://toscrape.com gets a ``toscrape.com`` throttling
scope, and ``books.toscrape.com`` and ``toscrape.com`` are considered
unrelated throttling scopes. If you want to change this behavior, see
:ref:`alternative-domain-throttling`.


.. _custom-throttling-scopes:

Customizing throttling scopes
------------------------------

There are 2 ways to customize throttling scopes.

.. reqmeta:: throttling_scopes

For simple use cases, you can use the ``throttling_scopes`` request metadata
key:

.. code-block:: python

    Request("https://example.com/", meta={"throttling_scopes": "foo"})
    Request("https://example.com/", meta={"throttling_scopes": {"foo", "bar"}})
    Request("https://example.com/", meta={"throttling_scopes": {"foo": 1.0, "bar": 2.5}})

.. note:: Throttling scopes set through request metadata remain through the
    request lifetime, e.g. throught redirects, even if those change the request
    URL.

.. setting:: THROTTLING_MANAGER

For anything else, set **THROTTLING_MANAGER** (default:
:class:`~scrapy.throttling.ThrottlingManager`) to a :ref:`component
<topics-components>` that implements the
:class:`~scrapy.throttling.ThrottlingManagerProtocol` protocol (or its import
path as a string):

.. code-block:: python
    :caption: ``settings.py``

    THROTTLING_MANAGER = "myproject.throttling.MyThrottlingManager"


.. _throttling-quotas:

Quotas
======

When different requests can consume different amounts of a throttling scope,
you can express this using quotas.

In the :reqmeta:`throttling_scopes` request metadata key and in the
:meth:`~scrapy.throttling.ThrottlingManagerProtocol.get_scopes` method you use
a :class:`dict` structure where keys are throttling scopes and values are
:class:`float` that indicate the amount of a scope that the request is expected
to consume (it does not need to be exact).

By default, those values are ignored. However, if a call to
:meth:`~scrapy.throttling.ThrottlingManagerProtocol.get_response_throttling` or
:meth:`~scrapy.throttling.ThrottlingManagerProtocol.get_exception_throttling`
reports available quotas for one or more throttling scopes, request quotas will
start being tracked and determine which requests can be sent and which cannot.

In fact, everything else being equal,
:class:`~scrapy.pqueues.ScrapyPriorityQueue` prioritizes requests that consume
a higher portion of the available quota, to minimize the risk of those
requests getting stuck.


API
===

.. autoclass:: scrapy.throttling.ThrottlingManagerProtocol
    :members:
    :member-order: bysource

.. autoclass:: scrapy.throttling.ThrottlingManager


Examples
========

.. _alternative-domain-throttling:

Alternative domain throttling
-----------------------------

If you are not happy with the :ref:`default throttling scope behavior
<default-throttling-scopes>` with regards to domains and subdomains, you can
change it.

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











Requests can be assigned 1 or more throttling scopes, each with a value.



This setting is also affected by the :setting:`RANDOMIZE_DOWNLOAD_DELAY`
setting, which is enabled by default.

When :setting:`CONCURRENT_REQUESTS_PER_IP` is non-zero, delays are enforced
per IP address instead of per domain.

Note that :setting:`DOWNLOAD_DELAY` can lower the effective per-domain
concurrency below :setting:`CONCURRENT_REQUESTS_PER_DOMAIN`. If the response
time of a domain is lower than :setting:`DOWNLOAD_DELAY`, the effective
concurrency for that domain is 1. When testing throttling configurations, it
usually makes sense to lower :setting:`CONCURRENT_REQUESTS_PER_DOMAIN` first,
and only increase :setting:`DOWNLOAD_DELAY` once
:setting:`CONCURRENT_REQUESTS_PER_DOMAIN` is 1 but a higher throttling is
desired.

.. _spider-download_delay-attribute:

.. note::

    This delay can be set per spider using :attr:`download_delay` spider attribute.

It is also possible to change this setting per domain, although it requires
non-trivial code. See the implementation of the :ref:`AutoThrottle
<topics-autothrottle>` extension for an example.

..
    TODO: Add a section about the handling of subdomains. By default, Scrapy
    should treat subdomains as separate slots, but it should be easy to change
    that behavior for specific domains, maybe with some new setting.

Throttling scopes
==================

..
    TODO: Cover what they are, what their default values are, how to change
    them easily on a per-request base.


Settings
========


.. setting:: DOWNLOAD_SLOTS

DOWNLOAD_SLOTS
--------------

Default: ``{}``

Allows to define concurrency/delay parameters on per slot (domain) basis:

    .. code-block:: python

        DOWNLOAD_SLOTS = {
            "quotes.toscrape.com": {"concurrency": 1, "delay": 2, "randomize_delay": False},
            "books.toscrape.com": {"delay": 3, "randomize_delay": False},
        }

.. note::

    For other downloader slots default settings values will be used:

    -   :setting:`DOWNLOAD_DELAY`: ``delay``
    -   :setting:`CONCURRENT_REQUESTS_PER_DOMAIN`: ``concurrency``
    -   :setting:`RANDOMIZE_DOWNLOAD_DELAY`: ``randomize_delay``



Global Request Limits
======================

The simplest form of throttling is limiting the total number of concurrent requests across your entire spider.

CONCURRENT_REQUESTS
-------------------

The :setting:`CONCURRENT_REQUESTS` setting controls the maximum number of requests that can be processed simultaneously across all domains:

.. code-block:: python

    # settings.py
    CONCURRENT_REQUESTS = 16  # Default value

This is a global limit that affects all requests regardless of their target domain. Setting it to a lower value will make your spider more conservative and polite, but slower. Setting it higher will make requests faster but may overwhelm servers or your own network connection.

**When to use**: This is your first line of defense against sending too many requests at once. Good default values are typically between 8-32 depending on your needs and the target servers' capacity.

Per-Domain Request Limits
==========================

More sophisticated throttling involves limiting requests on a per-domain basis, which is usually more appropriate since different servers have different capacities.

CONCURRENT_REQUESTS_PER_DOMAIN
-------------------------------

The :setting:`CONCURRENT_REQUESTS_PER_DOMAIN` setting limits concurrent requests to each individual domain:

.. code-block:: python

    # settings.py
    CONCURRENT_REQUESTS_PER_DOMAIN = 8  # Default value

This means that even if you have :setting:`CONCURRENT_REQUESTS` set to 32, no single domain will receive more than 8 concurrent requests. This prevents one fast-responding domain from monopolizing all your concurrent request slots.

**Example**: If you're scraping both ``example.com`` and ``other-site.com``, each domain will be limited to 8 concurrent requests, allowing a total of up to 16 concurrent requests (but still subject to the global :setting:`CONCURRENT_REQUESTS` limit).

CONCURRENT_REQUESTS_PER_IP
---------------------------

Similar to per-domain limits, :setting:`CONCURRENT_REQUESTS_PER_IP` limits concurrent requests per IP address:

.. code-block:: python

    # settings.py
    CONCURRENT_REQUESTS_PER_IP = 1  # Default value

This is useful when multiple domains resolve to the same IP address (common with CDNs or shared hosting). The IP-based limit takes precedence over the domain-based limit when they conflict.

DOWNLOAD_DELAY
--------------

While concurrency limits control how many requests are sent simultaneously, :setting:`DOWNLOAD_DELAY` controls the time delay between requests to the same domain:

.. code-block:: python

    # settings.py
    DOWNLOAD_DELAY = 3  # Wait 3 seconds between requests to the same domain

This setting introduces a delay between consecutive requests to the same domain/slot. It's applied per-domain, so requests to different domains are not affected by each other's delays.

The delay can be randomized using :setting:`RANDOMIZE_DOWNLOAD_DELAY`:

.. code-block:: python

    # settings.py
    DOWNLOAD_DELAY = 3
    RANDOMIZE_DOWNLOAD_DELAY = True  # Default
    # This will use delays between 1.5 and 4.5 seconds (0.5 * DOWNLOAD_DELAY to 1.5 * DOWNLOAD_DELAY)

**When to use**: Download delays are particularly useful for websites that are sensitive to request frequency but can handle multiple concurrent connections. They're also helpful for mimicking human-like browsing patterns.

**Note**: A global download delay doesn't make sense because it would unnecessarily slow down requests to different domains. The per-domain approach allows you to be respectful to each server individually while maintaining overall efficiency.

Custom Download Slots
======================

For more advanced scenarios, you can customize how requests are grouped for throttling purposes using download slots.

Understanding Download Slots
-----------------------------

By default, Scrapy groups requests by their domain name for throttling purposes. Each domain gets its own "download slot" with its own concurrency limits and delays. However, you can customize this grouping:

.. code-block:: python

    # In your spider
    def start_requests(self):
        # Default: requests to example.com go to "example.com" slot
        yield scrapy.Request("https://example.com/page1")
        yield scrapy.Request("https://example.com/page2")

        # Custom: group these requests differently
        yield scrapy.Request(
            "https://api.example.com/fast", meta={"download_slot": "api_fast"}
        )
        yield scrapy.Request(
            "https://api.example.com/slow", meta={"download_slot": "api_slow"}
        )

Per-Slot Configuration
----------------------

You can configure different throttling settings for different slots using :setting:`DOWNLOAD_SLOTS`:

.. code-block:: python

    # settings.py
    DOWNLOAD_SLOTS = {
        "api_fast": {
            "concurrency": 1,
            "delay": 0.5,
        },
        "api_slow": {
            "concurrency": 1,
            "delay": 5.0,
        },
        "images": {
            "concurrency": 8,
            "delay": 0,
        },
    }

**Use cases**:
- Different API endpoints with different rate limits
- Separating expensive operations (like browser rendering) from cheap ones
- Treating different subdomains with different politeness levels
- Grouping requests by authentication context

Advanced Throttling System
===========================

For complex scraping scenarios that require fine-grained control over throttling, Scrapy provides an advanced throttling scope system that goes beyond simple per-domain limits.

Throttling Buckets
------------------

The new throttling system introduces the concept of "throttling scopes" - resources that requests consume and that can become temporarily unavailable when limits are exceeded. Unlike download slots, a single request can require multiple scopes, enabling multi-dimensional throttling.

Enabling Throttling Buckets
----------------------------

.. code-block:: python

    # settings.py
    THROTTLING_ENABLED = True
    THROTTLING_MANAGER = "scrapy.throttling.DefaultBucketManager"

Basic Bucket Usage
------------------

The simplest scope configuration replicates domain-based throttling:

.. code-block:: python

    # Custom scope manager
    class MyBucketManager:
        def get_request_scopes(self, request, spider):
            domain = urlparse(request.url).netloc
            return {domain: 1.0}  # Consume 1 unit of the domain scope

        def process_response(self, response, request, spider):
            if response.status == 429:  # Too Many Requests
                domain = urlparse(request.url).netloc
                # Throttle this domain for 60 seconds
                self.throttle_scope(domain, delay=60)

Multi-Dimensional Throttling
-----------------------------

The real power comes from using multiple scopes per request:

.. code-block:: python

    def get_request_scopes(self, request, spider):
        scopes = {}

        # Domain-based throttling
        domain = urlparse(request.url).netloc
        scopes[domain] = 1.0

        # API feature-based throttling
        if "browser=true" in request.url:
            scopes["browser_rendering"] = 1.0

        if "extract=true" in request.url:
            scopes["ai_extraction"] = 5.0  # More expensive

        # Geographic throttling
        if "region=eu" in request.url:
            scopes["eu_datacenter"] = 1.0

        return scopes

Cost-Based Throttling
---------------------

Some APIs charge different amounts for different operations. The scope system supports fractional consumption:

.. code-block:: python

    def get_request_scopes(self, request, spider):
        scopes = {"api_credits": 1.0}  # Default cost

        if "operation=expensive" in request.url:
            scopes["api_credits"] = 10.0  # Costs 10x more

        return scopes


    def process_response(self, response, request, spider):
        # Update actual consumption based on response
        if "X-Actual-Cost" in response.headers:
            actual_cost = float(response.headers["X-Actual-Cost"])
            # Could update scope consumption here for better accuracy

Responding to Server Signals
-----------------------------

The scope system can respond intelligently to server throttling signals:

.. code-block:: python

    def process_response(self, response, request, spider):
        if response.status == 429:
            # Check for Retry-After header
            retry_after = response.headers.get("Retry-After")
            if retry_after:
                delay = int(retry_after)
            else:
                delay = 60  # Default backoff

            # Determine which scope to throttle based on response
            if "rate limit exceeded for API key" in response.text:
                self.throttle_scope("api_key_global", delay=delay)
            elif "too many requests to this endpoint" in response.text:
                endpoint = self._extract_endpoint(request.url)
                self.throttle_scope(f"endpoint_{endpoint}", delay=delay)

        elif response.status == 503:
            # Service unavailable - throttle the entire domain
            domain = urlparse(request.url).netloc
            self.throttle_scope(domain, delay=300)  # 5 minutes

Configuration
-------------

The throttling system provides several configuration options:

.. code-block:: python

    # settings.py
    THROTTLING_ENABLED = True
    THROTTLING_MANAGER = "myproject.throttling.CustomBucketManager"

    # Maximum number of delayed requests to keep in memory
    THROTTLING_MAX_DELAYED_REQUESTS = 1000

    # Warn when delayed requests exceed this threshold
    THROTTLING_DELAYED_REQUESTS_WARN_THRESHOLD = 500

Integration with Direct Downloads
---------------------------------

The throttling system also works with direct downloads made via ``crawler.engine.download()``:

.. code-block:: python

    # In a pipeline or extension
    @inlineCallbacks
    def process_item(self, item, spider):
        # This request will respect throttling scopes
        request = scrapy.Request(item["image_url"])
        response = yield spider.crawler.engine.download(request)
        # Process response...

Best Practices
==============

Choosing the Right Approach
----------------------------

1. **Start Simple**: Begin with :setting:`CONCURRENT_REQUESTS` and :setting:`CONCURRENT_REQUESTS_PER_DOMAIN`
2. **Add Delays When Needed**: Use :setting:`DOWNLOAD_DELAY` for frequency-sensitive sites
3. **Use Custom Slots for Special Cases**: When different parts of a site need different treatment
4. **Advanced Buckets for Complex APIs**: When dealing with modern APIs with sophisticated rate limiting

Respectful Scraping
-------------------

- Always check ``robots.txt`` and respect ``Crawl-delay`` directives
- Monitor server response times and adjust settings if you're causing delays
- Watch for 429, 503, and other error responses that indicate you're going too fast
- Consider the server's perspective: your efficiency shouldn't come at their expense

Common Patterns
---------------

**E-commerce Site**:

.. code-block:: python

    CONCURRENT_REQUESTS_PER_DOMAIN = 2
    DOWNLOAD_DELAY = 1
    RANDOMIZE_DOWNLOAD_DELAY = True

**REST API**:

.. code-block:: python

    # Use throttling scopes to respect API rate limits
    THROTTLING_ENABLED = True
    CONCURRENT_REQUESTS_PER_DOMAIN = 5

**Mixed Content (API + Web)**:

.. code-block:: python

    DOWNLOAD_SLOTS = {
        "api": {"concurrency": 10, "delay": 0.1},
        "web": {"concurrency": 2, "delay": 2.0},
    }

Monitoring and Debugging
========================

Scrapy provides several ways to monitor your throttling:

.. code-block:: python

    # Enable autothrottle debugging (for legacy autothrottle extension only)
    AUTOTHROTTLE_DEBUG = True

    # Monitor stats
    # Check spider.crawler.stats for throttling-related statistics

.. warning::
    The AutoThrottle extension is deprecated and not recommended for new projects. It uses a simplistic latency-based approach that doesn't align with modern server throttling patterns. Use the throttling scope system instead.

Settings Reference
==================

Global Settings
---------------

RANDOMIZE_DOWNLOAD_DELAY

**Default**: ``True``

If enabled, Scrapy will wait a random amount of time (between 0.5 * and 1.5 * ``DOWNLOAD_DELAY``) while fetching requests from the same domain.

Slot Settings
-------------

DOWNLOAD_SLOTS

**Default**: ``{}``

A dictionary containing the download slots and their settings. Each slot can have the following settings:

* ``concurrency`` - Maximum concurrent requests for this slot
* ``delay`` - Download delay for this slot (in seconds)

Advanced Throttling Settings
----------------------------

.. setting:: THROTTLING_ENABLED

**Default**: ``False``

Enable the advanced throttling scope system.

.. setting:: THROTTLING_MAX_DELAYED_REQUESTS

**Default**: ``1000``

Maximum number of delayed requests to keep in memory.

.. setting:: THROTTLING_DELAYED_REQUESTS_WARN_THRESHOLD

**Default**: ``500``

Warn when the number of delayed requests exceeds this threshold.



..
    TODO: Provide real-life examples of throttling configurations, including
    exception and error response handling, throttling based on responses,
    delay adjustment geared towards rate limits optimization, querying of
    external resources for throttling decisions, etc.




-   .. setting:: CONCURRENT_REQUESTS

    ``CONCURRENT_REQUESTS`` (default: ``16``): The maximum number of total
    concurrent requests.

..
    TODO: Since this setting is more about limiting spider-side resources than
    throttling, maybe it does not need to be covered in this page.


..
    Implement a signal that can be emitted to change the throttling config of
    a specific throttling scope.


..
    TODO: Explain how things work, for every setting/parameter, when a request
    is assigned multiple scopes.

..
    TODO: Explain how scope units work, and give usage examples.

..
    TODO: Support backoff in THROTTLING_SCOPES having a cls key with a class
    or its import path as a string, and arbitraty kwargs to pass to its
    __init__ method, to implement a custom backoff strategy.


..
    TODO: Make sure that the API is flexible enough to support scrapy-zyte-api
    use cases.
