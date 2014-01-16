.. _topics-broad-crawls:

============
Broad Crawls
============

Scrapy defaults are optimized for crawling specific sites. These sites are
often handled by a single Scrapy spider, although this is not necessary or
required (for example, there are generic spiders that handle any given site
thrown at them).

In addition to this "focused crawl", there is another common type of crawling
which covers a large (potentially unlimited) number of domains, and is only
limited by time or other arbitrary constraint, rather than stopping when the
domain was crawled to completion or when there are no more requests to perform.
These are called "broad crawls" and is the typical crawlers employed by search
engines.

These are some common properties often found in broad crawls:

* they crawl many domains (often, unbounded) instead of a specific set of sites

* they don't necessarily crawl domains to completion, because it would
  impractical (or impossible) to do so, and instead limit the crawl by time or
  number of pages crawled

* they are simpler in logic (as opposed to very complex spiders with many
  extraction rules) because data is often post-processed in a separate stage

* they crawl many domains concurrently, which allows them to achieve faster
  crawl speeds by not being limited by any particular site constraint (each site
  is crawled slowly to respect politeness, but many sites are crawled in
  parallel)

As said above, Scrapy default settings are optimized for focused crawls, not
broad crawls. However, due to its asynchronous architecture, Scrapy is very
well suited for performing fast broad crawls. This page summarize some things
you need to keep in mind when using Scrapy for doing broad crawls, along with
concrete suggestions of Scrapy settings to tune in order to achieve an
efficient broad crawl.

Increase concurrency
====================

Concurrency is the number of requests that are processed in parallel. There is
a global limit and a per-domain limit.

The default global concurrency limit in Scrapy is not suitable for crawling
many different  domains in parallel, so you will want to increase it. How much
to increase it will depend on how much CPU you crawler will have available. A
good starting point is ``100``, but the best way to find out is by doing some
trials and identifying at what concurrency your Scrapy process gets CPU
bounded. For optimum performance, You should pick a concurrency where CPU usage
is at 80-90%.

To increase the global concurrency use::

    CONCURRENT_REQUESTS = 100

Reduce log level
================

When doing broad crawls you are often only interested in the crawl rates you
get and any errors found. These stats are reported by Scrapy when using the
``INFO`` log level. In order to save CPU (and log storage requirements) you
should not use ``DEBUG`` log level when preforming large broad crawls in
production. Using ``DEBUG`` level when developing your (broad) crawler may fine
though.

To set the log level use::

    LOG_LEVEL = 'INFO'

Disable cookies
===============

Disable cookies unless you *really* need. Cookies are often not needed when
doing broad crawls (search engine crawlers ignore them), and they improve
performance by saving some CPU cycles and reducing the memory footprint of your
Scrapy crawler.

To disable cookies use::

    COOKIES_ENABLED = False

Disable retries
===============

Retrying failed HTTP requests can slow down the crawls substantially, specially
when sites causes are very slow (or fail) to respond, thus causing a timeout
error which gets retried many times, unnecessarily, preventing crawler capacity
to be reused for other domains.

To disable retries use::

    RETRY_ENABLED = False

Reduce download timeout
=======================

Unless you are crawling from a very slow connection (which shouldn't be the
case for broad crawls) reduce the download timeout so that stuck requests are
discarded quickly and free up capacity to process the next ones.

To reduce the download timeout use::

    DOWNLOAD_TIMEOUT = 15

Disable redirects
=================

Consider disabling redirects, unless you are interested in following them. When
doing broad crawls it's common to save redirects and resolve them when
revisiting the site at a later crawl. This also help to keep the number of
request constant per crawl batch, otherwise redirect loops may cause the
crawler to dedicate too many resources on any specific domain.

To disable redirects use::

    REDIRECT_ENABLED = False

Enable crawling of "Ajax Crawlable Pages"
=========================================

Some pages (up to 1%, based on empirical data from year 2013) declare
themselves as `ajax crawlable`_. This means they provide plain HTML
version of content that is usually available only via AJAX.
Pages can indicate it in two ways:

1) by using ``#!`` in URL - this is the default way;
2) by using a special meta tag - this way is used on
   "main", "index" website pages.

Scrapy handles (1) automatically; to handle (2) enable
:ref:`AjaxCrawlMiddleware <ajaxcrawl-middleware>`::

    AJAXCRAWL_ENABLED = True

When doing broad crawls it's common to crawl a lot of "index" web pages;
AjaxCrawlMiddleware helps to crawl them correctly.
It is turned OFF by default because it has some performance overhead,
and enabling it for focused crawls doesn't make much sense.

.. _ajax crawlable: https://developers.google.com/webmasters/ajax-crawling/docs/getting-started
