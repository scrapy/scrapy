======================
AutoThrottle extension
======================

This is an extension for automatically throttling crawling speed based on load
of both the Scrapy server and the website you are crawling.

Design goals
============

1. be nicer to sites instead of using default download delay of zero
2. automatically adjust scrapy to the optimum crawling speed, so the user
   doesn't have to tune the download delays and concurrent requests to find the
   optimum one. the user only needs to specify the maximum concurrent requests
   it allows, and the extension does the rest.

How it works
============

In Scrapy, the download latency is measured as the time elapsed between
establishing the TCP connection and receiving the HTTP headers.

Note that these latencies are very hard to measure accurately in a cooperative
multitasking environment because Scrapy may be busy processing a spider
callback, for example, and unable to attend downloads. However, these latencies
should still give a reasonable estimate of how busy Scrapy (and ultimately, the
server) is, and this extension builds on that premise.

.. _autothrottle-algorithm:

Throttling algorithm
====================

This adjusts download delays and concurrency based on the following rules:

1. spiders always start with one concurrent request and a download delay of
   :setting:`AUTOTHROTTLE_START_DELAY`
2. when a response is received, the download delay is adjusted to the
   average of previous download delay and the latency of the response.

.. note:: The AutoThrottle extension honours the standard Scrapy settings for
   concurrency and delay. This means that it will never set a download delay
   lower than :setting:`DOWNLOAD_DELAY` or a concurrency higher than
   :setting:`CONCURRENT_REQUESTS_PER_DOMAIN`
   (or :setting:`CONCURRENT_REQUESTS_PER_IP`, depending on which one you use).

Settings
========

The settings used to control the AutoThrottle extension are:

* :setting:`AUTOTHROTTLE_ENABLED`
* :setting:`AUTOTHROTTLE_START_DELAY`
* :setting:`AUTOTHROTTLE_MAX_DELAY`
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

.. setting:: AUTOTHROTTLE_DEBUG

AUTOTHROTTLE_DEBUG
~~~~~~~~~~~~~~~~~~

Default: ``False``

Enable AutoThrottle debug mode which will display stats on every response
received, so you can see how the throttling parameters are being adjusted in
real time.
