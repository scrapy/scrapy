.. _topics-scheduler-middleware:

====================
Scheduler middleware
====================


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

