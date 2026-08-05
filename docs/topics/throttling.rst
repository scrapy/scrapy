.. _throttling:

==========
Throttling
==========

.. versionadded:: VERSION

Sending too many requests too quickly can `overwhelm websites`_.
:ref:`Concurrency and delay limits <basic-throttling>` aim to prevent that.

.. _overwhelm websites: https://en.wikipedia.org/wiki/Denial-of-service_attack

.. seealso::

    :ref:`topics-autothrottle`
        Adjust scope delays dynamically based on response latencies.

.. _basic-throttling:
.. _throttling-scopes:

Concurrency and delay
=====================

Requests are throttled on a **per-domain basis** by default [1]_: each domain is
a separate `throttling scope
<https://www.ietf.org/archive/id/draft-polli-ratelimit-headers-02.html#section-1.4-4.4>`__,
i.e. an aspect of a request that can be throttled independently. This allows
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

    Must be ``1`` or higher. Unlike :setting:`CONCURRENT_REQUESTS`, it cannot be
    set to ``0``: a throttling scope always enforces a concurrency limit.

-   .. setting:: DOWNLOAD_DELAY

    :setting:`DOWNLOAD_DELAY` (default: ``1``
    (:ref:`fallback <default-settings>`: ``0``))

    Minimum seconds between any two requests to the same domain.

    To target a specific number of requests per minute (RPM) *per domain*, set
    this to ``60 / RPM``. For example, ``DOWNLOAD_DELAY = 1.0`` for 60 RPM, or
    ``DOWNLOAD_DELAY = 2.0`` for 30 RPM.

When configuring these settings, note that:

-   :setting:`CONCURRENT_REQUESTS` caps
    :setting:`THROTTLING_SCOPE_CONCURRENCY`.

-   If :setting:`DOWNLOAD_DELAY` ≥ response time, concurrency is effectively
    ``1``, because the next request to the domain is not sent until the delay
    elapses, by which time the previous response has already arrived.

.. [1] You can :ref:`customize <custom-throttler>` how requests are grouped
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
    redirect-aware throttling assignment, see :ref:`custom-throttler`.

.. reqmeta:: delay

Delaying a single request
-------------------------

To hold a single request for a fixed number of seconds before it is sent,
regardless of its scopes, set the ``delay`` request metadata key:

.. code-block:: python

    Request("https://example.com/slow", meta={"delay": 5.0})

The delay is applied once, the first time the request is throttled.

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

Excluding a request from throttling
-----------------------------------

To exempt a request from the concurrency and delay limits of its scopes, set the
:reqmeta:`dont_throttle` request metadata key to ``True``:

.. code-block:: python

    Request("https://example.com/login", meta={"dont_throttle": True})

It does not count towards those limits either, so it does not delay other
requests of the same scopes.

.. setting:: THROTTLER

.. _custom-throttler:

Custom throttlers
=================

To change how scopes are assigned, or anything beyond per-scope settings, set
:setting:`THROTTLER` (default: :class:`~scrapy.throttler.Throttler`) to a
:ref:`component <topics-components>` that implements
:class:`~scrapy.throttler.ThrottlerProtocol` (or to its import path as a
string):

.. code-block:: python
    :caption: :file:`settings.py`

    THROTTLER = "myproject.throttling.MyThrottler"

The simplest way is to subclass :class:`~scrapy.throttler.Throttler` and
override :meth:`~scrapy.throttler.Throttler.get_scopes`, which decides the
scopes of a request that does not choose its own through the
:reqmeta:`throttling_scopes` metadata key:

.. code-block:: python
    :caption: :file:`myproject/throttling.py`

    from scrapy.throttler import Throttler
    from scrapy.utils.httpobj import urlparse_cached


    class MyThrottler(Throttler):
        def get_scopes(self, request):
            # One scope per host *and port*, rather than one per host name, so
            # that e.g. example.com:8080 is throttled separately from
            # example.com.
            return urlparse_cached(request).netloc

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
        from scrapy.throttler import Throttler
        from scrapy.utils.httpobj import urlparse_cached


        class MyThrottler(Throttler):
            def get_scopes(self, request):
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
        from scrapy.throttler import Throttler
        from scrapy.utils.httpobj import urlparse_cached


        class MyThrottler(Throttler):
            def get_scopes(self, request):
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

-   Implement a :ref:`throttler <custom-throttler>` that sets
    endpoint-specific throttling scopes for that domain:

    .. code-block:: python

        from scrapy.throttler import Throttler
        from scrapy.utils.httpobj import urlparse_cached


        class MyThrottler(Throttler):
            def get_scopes(self, request):
                parsed_url = urlparse_cached(request)
                if parsed_url.netloc != "api.example":
                    return super().get_scopes(request)
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

-   Implement a :ref:`throttler <custom-throttler>` that:

    -   Adds a throttling scope for the URL being scraped.

        For example, if you request
        ``https://api.example/?url=https://example.com``, by default it
        will get an ``api.example`` throttling scope, but it should also
        get the ``example.com`` throttling scope:

        .. code-block:: python

            from urllib.parse import urlparse

            from scrapy.throttler import Throttler
            from scrapy.utils.httpobj import urlparse_cached
            from w3lib.url import url_query_parameter


            class MyThrottler(Throttler):
                def get_scopes(self, request):
                    api_domain = urlparse_cached(request).netloc
                    if api_domain != "api.example":
                        return super().get_scopes(request)
                    target_url = url_query_parameter(request.url, "url")
                    if not target_url:
                        return api_domain
                    return [api_domain, urlparse(target_url).netloc]


.. _throttling-per-ip:

Per-IP concurrency limiting
---------------------------

A concurrency limit keyed by IP is just a throttling scope whose id is the
request's IP, with a ``concurrency`` limit. A request then carries two scopes,
its domain and its IP, and is only sent when **both** allow it.

-   Implement a :ref:`throttler <custom-throttler>` that adds
    the request's IP as a second scope:

    .. code-block:: python

        from scrapy.throttler import Throttler
        from scrapy.utils.httpobj import urlparse_cached

        ADDRESSES = {
            "books.toscrape.com": "203.0.113.1",
            "quotes.toscrape.com": "203.0.113.1",
        }


        class IPThrottler(Throttler):
            def get_scopes(self, request):
                host = urlparse_cached(request).hostname or ""
                address = ADDRESSES.get(host)
                return [host, address] if address else host

-   Use the :setting:`THROTTLING_SCOPES` setting to limit the concurrency of the
    address:

    .. code-block:: python
        :caption: :file:`settings.py`

        THROTTLING_SCOPES = {"203.0.113.1": {"concurrency": 2}}

    Both hosts above then share those two concurrency slots, on top of the
    limits of their own scopes.

.. _throttling-settings:

Additional settings
===================

-   .. setting:: RANDOMIZE_DOWNLOAD_DELAY

    :setting:`RANDOMIZE_DOWNLOAD_DELAY` (default: ``True``)

    Randomize delays by this factor, e.g. ``0.2`` randomizes delays between
    ``delay*0.8`` and ``delay*1.2``.

    ``True`` means ``0.5`` (i.e. ±50%), and ``False`` means no randomization.

-   .. setting:: THROTTLER_DEBUG

    :setting:`THROTTLER_DEBUG` (default: ``False``)

    Whether to log :ref:`throttling <throttling>` decisions (per-scope delays)
    for debugging.

-   .. setting:: THROTTLING_SCOPE_LIMIT

    :setting:`THROTTLING_SCOPE_LIMIT` (default: ``100_000``)

    Maximum number of :ref:`throttling scope <throttling-scopes>` states kept
    in memory at once, to bound memory usage on broad crawls that touch a large
    number of scopes (e.g. domains).

    When the limit is exceeded, the least-recently-used idle scopes are evicted
    (an evicted scope is recreated from its configuration the next time it is
    needed). Scopes with in-flight requests or with a pending delay are never
    evicted, so the limit may be temporarily exceeded if that many scopes are
    busy at once. Set to ``0`` to disable the limit.

.. _throttling-api:

API
===

.. autoclass:: scrapy.throttler.ThrottlerProtocol
    :members:

.. autoclass:: scrapy.throttler.Throttler
    :members: get_scopes

.. autoclass:: scrapy.throttler.ThrottlingScopeManager
    :members: get_base_delay, set_base_delay, get_concurrency, set_concurrency

.. autoclass:: scrapy.throttler.ThrottlingScopeConfig

.. autofunction:: scrapy.throttler.iter_scopes
