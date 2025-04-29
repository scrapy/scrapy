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
