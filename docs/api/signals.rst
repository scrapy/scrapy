.. _topics-api-signals:

.. currentmodule:: scrapy.signals

===========
Signals API
===========

.. _topics-signals-ref:

Signals
=======

.. autofunction:: engine_started()

.. autofunction:: engine_stopped()

.. autofunction:: item_scraped(item, response, spider)

.. autofunction:: item_dropped(item, response, exception, spider)

.. autofunction:: item_error(item, response, spider, failure)

.. autofunction:: spider_closed(spider, reason)

.. autofunction:: spider_opened(spider)

.. autofunction:: spider_idle(spider)

.. autofunction:: spider_error(failure, response, spider)

.. autofunction:: request_scheduled(request, spider)

.. autofunction:: request_dropped(request, spider)

.. autofunction:: request_reached_downloader(request, spider)

.. autofunction:: response_received(response, request, spider)

.. autofunction:: response_downloaded(response, request, spider)


Signal Manager
==============

.. automodule:: scrapy.signalmanager
   :synopsis: The signal manager
   :members:
   :undoc-members:
