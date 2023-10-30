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

AutoThrottle extension adjusts download delays dynamically to make spider send
:setting:`AUTOTHROTTLE_TARGET_CONCURRENCY` concurrent requests on average
to each remote website.

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
websites.

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
