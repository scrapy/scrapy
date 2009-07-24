.. _ref-spider-middleware:

====================================
Built-in spider middleware reference
====================================

This page describes all spider middleware components that come with Scrapy. For
information on how to use them and how to write your own spider middleware, see
the :ref:`spider middleware usage guide <topics-spider-middleware>`.

For a list of the components enabled by default (and their orders) see the
:setting:`SPIDER_MIDDLEWARES_BASE` setting.

Available spider middlewares
============================

DepthMiddleware
---------------

.. module:: scrapy.contrib.spidermiddleware.depth

.. class:: DepthMiddleware

   DepthMiddleware is a scrape middleware used for tracking the depth of each
   Request inside the site being scraped. It can be used to limit the maximum
   depth to scrape or things like that.

   The :class:`DepthMiddleware` can be configured through the following
   settings (see the settings documentation for more info):

      * :setting:`DEPTH_LIMIT` - The maximum depth that will be allowed to
        crawl for any site. If zero, no limit will be imposed.
      * :setting:`DEPTH_STATS` - Whether to collect depth stats.

HttpErrorMiddleware
-------------------

.. module:: scrapy.contrib.spidermiddleware.httperror

.. class:: HttpErrorMiddleware

    Filter out response outside of a range of valid status codes.

    This middleware filters out every response with status outside of the range
    200<=status<300. Spiders can add more exceptions using
    ``handle_httpstatus_list`` spider attribute.

OffsiteMiddleware
-----------------

.. module:: scrapy.contrib.spidermiddleware.offsite

.. class:: OffsiteMiddleware

   Filters out Requests for URLs outside the domains covered by the spider.

   This middleware filters out every request whose host names doesn't match
   :attr:`~scrapy.spider.BaseSpider.domain_name`, or the spider
   :attr:`~scrapy.spider.BaseSpider.domain_name` prefixed by "www.".  
   Spider can add more domains to exclude using 
   :attr:`~scrapy.spider.BaseSpider.extra_domain_names` attribute.

RequestLimitMiddleware
----------------------

.. module:: scrapy.contrib.spidermiddleware.requestlimit

.. class:: RequestLimitMiddleware

   Limits the maximum number of requests in the scheduler for each spider. When
   a spider tries to schedule more than the allowed amount of requests, the new
   requests (returned by the spider) will be dropped.

   The :class:`RequestLimitMiddleware` can be configured through the following
   settings (see the settings documentation for more info):

      * :setting:`REQUESTS_QUEUE_SIZE` - If non zero, it will be used as an
        upper limit for the amount of requests that can be scheduled per
        domain. Can be set per spider using ``requests_queue_size`` attribute.

RestrictMiddleware
------------------

.. module:: scrapy.contrib.spidermiddleware.restrict

.. class:: RestrictMiddleware 

   Restricts crawling to fixed set of particular URLs.

   The :class:`RestrictMiddleware` can be configured through the following
   settings (see the settings documentation for more info):

      * :setting:`RESTRICT_TO_URLS` - Set of URLs allowed to crawl.

UrlFilterMiddleware
-------------------

.. module:: scrapy.contrib.spidermiddleware.urlfilter

.. class:: UrlFilterMiddleware 

   Canonicalizes URLs to filter out duplicated ones

UrlLengthMiddleware
-------------------

.. module:: scrapy.contrib.spidermiddleware.urllength

.. class:: UrlLengthMiddleware 

   Filters out requests with URLs longer than URLLENGTH_LIMIT

   The :class:`UrlLengthMiddleware` can be configured through the following
   settings (see the settings documentation for more info):

      * :setting:`URLLENGTH_LIMIT` - The maximum URL length to allow for crawled URLs.

