.. _topics-scheduler-middleware:

====================
Scheduler middleware
====================

The scheduler middleware is a framework of hooks in the Scrapy's scheduling
mechanism where you can plug custom functionality to process request being
enqueued.

Activating a scheduler middleware
=================================

To activate a scheduler middleware component, add it to the
:setting:`SCHEDULER_MIDDLEWARES` setting, which is a dict whose keys are the
middleware class path and their values are the middleware orders.

Here's an example::

    SCHEDULER_MIDDLEWARES = {
        'myproject.middlewares.CustomSchedulerMiddleware': 543,
    }

The :setting:`SCHEDULER_MIDDLEWARES` setting is merged with the
:setting:`SCHEDULER_MIDDLEWARES_BASE` setting defined in Scrapy (and not meant
to be overridden) and then sorted by order to get the final sorted list of
enabled middlewares: the first middleware is the one closer to the engine and
the last is the one closer to the spider.

To decide which order to assign to your middleware see the
:setting:`SCHEDULER_MIDDLEWARES_BASE` setting and pick a value according to
where you want to insert the middleware. The order does matter because each
middleware performs a different action and your middleware could depend on some
previous (or subsequent) middleware being applied.

If you want to disable a builtin middleware (the ones defined in
:setting:`SCHEDULER_MIDDLEWARES_BASE`, and enabled by default) you must define it
in your project :setting:`SCHEDULER_MIDDLEWARES` setting and assign `None` as its
value.  For example, if you want to disable the duplicates filter middleware::

    SPIDER_MIDDLEWARES = {
        'myproject.middlewares.CustomSchedulerMiddleware': 543,
        'scrapy.contrib.spidermiddleware.duplicatesfilter.DuplicatesFilterMiddleware: None,
    }

Finally, keep in mind that some middlewares may need to be enabled through a
particular setting. See each middleware documentation for more info.

Writing your own scheduler middleware
=====================================

Writing your own scheduler middleware is easy. Each middleware component is a
single Python class that defines one or more of the following methods:

.. module:: scrapy.contrib.schedulermiddleware

.. class:: SchedulerMiddleware

   .. method:: enqueue_request(domain, request)

      :meth:`enqueue_request` should return either ``None``, a
      :class:`~scrapy.http.Response` object or a ``Deferred``.

      :param domain: the domain originating the request
      :type domain: string

      :param requests: the request to be enqueued
      :type request: :class:`~scrapy.http.Request` object

   .. method:: open_domain(domain)

      :param domain: the domain being opened
      :type domain: string

   .. method:: close_domain(domain)

      :param domain: the domain being closed
      :type domain: string

.. _topics-scheduler-middleware-ref:

Built-in scheduler middleware reference
========================================

This page describes all scheduler middleware components that come with
Scrapy. 

For a list of the components enabled by default (and their orders) see the
:setting:`SCHEDULER_MIDDLEWARES_BASE` setting.

DuplicatesFilterMiddleware
--------------------------

.. module:: scrapy.contrib.schedulermiddleware.duplicatesfilter
   :synopsis: Duplicates Filter Scheduler Middleware

.. class:: DuplicatesFilterMiddleware

   Filter out already visited urls.

   The :class:`DuplicatesFilterMiddleware` can be configured through the following
   settings (see the settings documentation for more info):

      * :setting:`DUPEFILTER_CLASS` - The class used to detect and filter
        duplicate requests.

