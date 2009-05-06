.. _ref-downloader-middleware:

========================================
Built-in downloader middleware reference
========================================

This document explains all downloader middleware components that come with
Scrapy. For information on how to use them and how to write your own downloader
middleware, see the :ref:`downloader middleware usage guide
<topics-downloader-middleware>`.

Available downloader middlewares
================================

.. _ref-downloader-middleware-common:

"Common" downloader middleware
------------------------------

.. module:: scrapy.contrib.downloadermiddleware.common
   :synopsis: Downloader middleware for performing basic required tasks

.. class:: scrapy.contrib.downloadermiddleware.common.CommonMiddleware

This middleware performs some commonly required tasks over all requests, and
thus it's recommended to leave it always enabled. Those tasks are:

    * If the ``Accept`` request header is not already set, then set it to
      :setting:`REQUEST_HEADER_ACCEPT`
    
    * If the ``Accept-Language`` request header is not already set, then set it
      to :setting:`REQUEST_HEADER_ACCEPT_LANGUAGE` 

    * If the request method is ``POST`` and the ``Content-Type`` header is not
      set, then set it to ``'application/x-www-form-urlencoded'``, the `default
      Form content type`_.

    * If the request contains a body and the ``Content-Length`` headers it not
      set, then set it to the ``len(body)``.
    
.. _default Form content type: http://www.w3.org/TR/html401/interact/forms.html#h-17.13.4.1

