.. _throttling:

==========
Throttling
==========

Scrapy provides several mechanisms to control the rate at which requests are
sent, to prevent website overloading and handle rate limiting responses.

Basic throttling
================

The main :ref:`settings <topics-settings>` to control throttling are:

-   :setting:`CONCURRENT_REQUESTS`: The maximum number of total concurrent
    requests.

-   :setting:`THROTTLING_BUCKET_CONCURRENCY`: The maximum number of concurrent
    requests per :ref:`throttling bucket <throttling-buckets>`.

-   :setting:`THROTTLING_BUCKET_DELAY`: The minimum seconds to wait between
    consecutive requests to the same :ref:`throttling bucket
    <throttling-buckets>`.

..
    TODO: Add a section about the handling of subdomains. By default, Scrapy
    should treat subdomains as separate slots, but it should be easy to change
    that behavior for specific domains, maybe with some new setting.

.. _throttling-buckets:

Throttling buckets
==================

..
    TODO: Cover what they are, what their default values are, how to change
    them easily on a per-request base.


Settings
========

.. setting:: CONCURRENT_REQUESTS

CONCURRENT_REQUESTS
-------------------

Default: ``16``

The maximum number of concurrent (i.e. simultaneous) requests that will be
performed by the Scrapy downloader.

.. setting:: CONCURRENT_REQUESTS_PER_DOMAIN

CONCURRENT_REQUESTS_PER_DOMAIN
------------------------------

Default: ``8``

The maximum number of concurrent (i.e. simultaneous) requests that will be
performed to any single domain.

See also: :ref:`topics-autothrottle` and its
:setting:`AUTOTHROTTLE_TARGET_CONCURRENCY` option.



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

For complex scraping scenarios that require fine-grained control over throttling, Scrapy provides an advanced throttling bucket system that goes beyond simple per-domain limits.

Throttling Buckets
------------------

The new throttling system introduces the concept of "throttling buckets" - resources that requests consume and that can become temporarily unavailable when limits are exceeded. Unlike download slots, a single request can require multiple buckets, enabling multi-dimensional throttling.

Enabling Throttling Buckets
----------------------------

.. code-block:: python

    # settings.py
    THROTTLING_ENABLED = True
    THROTTLING_BUCKET_MANAGER = "scrapy.throttling.DefaultBucketManager"

Basic Bucket Usage
------------------

The simplest bucket configuration replicates domain-based throttling:

.. code-block:: python

    # Custom bucket manager
    class MyBucketManager:
        def get_request_buckets(self, request, spider):
            domain = urlparse(request.url).netloc
            return {domain: 1.0}  # Consume 1 unit of the domain bucket

        def process_response(self, response, request, spider):
            if response.status == 429:  # Too Many Requests
                domain = urlparse(request.url).netloc
                # Throttle this domain for 60 seconds
                self.throttle_bucket(domain, delay=60)

Multi-Dimensional Throttling
-----------------------------

The real power comes from using multiple buckets per request:

.. code-block:: python

    def get_request_buckets(self, request, spider):
        buckets = {}

        # Domain-based throttling
        domain = urlparse(request.url).netloc
        buckets[domain] = 1.0

        # API feature-based throttling
        if "browser=true" in request.url:
            buckets["browser_rendering"] = 1.0

        if "extract=true" in request.url:
            buckets["ai_extraction"] = 5.0  # More expensive

        # Geographic throttling
        if "region=eu" in request.url:
            buckets["eu_datacenter"] = 1.0

        return buckets

Cost-Based Throttling
---------------------

Some APIs charge different amounts for different operations. The bucket system supports fractional consumption:

.. code-block:: python

    def get_request_buckets(self, request, spider):
        buckets = {"api_credits": 1.0}  # Default cost

        if "operation=expensive" in request.url:
            buckets["api_credits"] = 10.0  # Costs 10x more

        return buckets


    def process_response(self, response, request, spider):
        # Update actual consumption based on response
        if "X-Actual-Cost" in response.headers:
            actual_cost = float(response.headers["X-Actual-Cost"])
            # Could update bucket consumption here for better accuracy

Responding to Server Signals
-----------------------------

The bucket system can respond intelligently to server throttling signals:

.. code-block:: python

    def process_response(self, response, request, spider):
        if response.status == 429:
            # Check for Retry-After header
            retry_after = response.headers.get("Retry-After")
            if retry_after:
                delay = int(retry_after)
            else:
                delay = 60  # Default backoff

            # Determine which bucket to throttle based on response
            if "rate limit exceeded for API key" in response.text:
                self.throttle_bucket("api_key_global", delay=delay)
            elif "too many requests to this endpoint" in response.text:
                endpoint = self._extract_endpoint(request.url)
                self.throttle_bucket(f"endpoint_{endpoint}", delay=delay)

        elif response.status == 503:
            # Service unavailable - throttle the entire domain
            domain = urlparse(request.url).netloc
            self.throttle_bucket(domain, delay=300)  # 5 minutes

Configuration
-------------

The throttling system provides several configuration options:

.. code-block:: python

    # settings.py
    THROTTLING_ENABLED = True
    THROTTLING_BUCKET_MANAGER = "myproject.throttling.CustomBucketManager"

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
        # This request will respect throttling buckets
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

    # Use throttling buckets to respect API rate limits
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
    The AutoThrottle extension is deprecated and not recommended for new projects. It uses a simplistic latency-based approach that doesn't align with modern server throttling patterns. Use the throttling bucket system instead.

Settings Reference
==================

Global Settings
---------------

.. setting:: CONCURRENT_REQUESTS

**Default**: ``16``

The maximum number of concurrent requests performed by Scrapy.

.. setting:: CONCURRENT_REQUESTS_PER_DOMAIN

**Default**: ``8``

The maximum number of concurrent requests performed to any single domain.

.. setting:: CONCURRENT_REQUESTS_PER_IP

**Default**: ``1``

The maximum number of concurrent requests performed to any single IP address.

.. setting:: DOWNLOAD_DELAY

**Default**: ``0``

The amount of time (in seconds) that the downloader should wait before downloading consecutive pages from the same domain.

.. setting:: RANDOMIZE_DOWNLOAD_DELAY

**Default**: ``True``

If enabled, Scrapy will wait a random amount of time (between 0.5 * and 1.5 * ``DOWNLOAD_DELAY``) while fetching requests from the same domain.

Slot Settings
-------------

.. setting:: DOWNLOAD_SLOTS

**Default**: ``{}``

A dictionary containing the download slots and their settings. Each slot can have the following settings:

* ``concurrency`` - Maximum concurrent requests for this slot
* ``delay`` - Download delay for this slot (in seconds)

Advanced Throttling Settings
----------------------------

.. setting:: THROTTLING_ENABLED

**Default**: ``False``

Enable the advanced throttling bucket system.

.. setting:: THROTTLING_BUCKET_MANAGER

**Default**: ``'scrapy.throttling.DefaultBucketManager'``

A string specifying the throttling bucket manager to use.

.. setting:: THROTTLING_MAX_DELAYED_REQUESTS

**Default**: ``1000``

Maximum number of delayed requests to keep in memory.

.. setting:: THROTTLING_DELAYED_REQUESTS_WARN_THRESHOLD

**Default**: ``500``

Warn when the number of delayed requests exceeds this threshold.
