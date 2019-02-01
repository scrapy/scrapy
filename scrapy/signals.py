"""
Scrapy signals

These signals are documented in docs/topics/signals.rst. Please don't add new
signals here without documenting them there.
"""

#: .. signal:: engine_started
#:
#: Sent when the Scrapy engine has started crawling.
#:
#: This signal supports returning deferreds from their handlers.
#:
#: .. note:: This signal may be fired *after* the :signal:`spider_opened` signal,
#:           depending on how the spider was started. So **don't** rely on this signal
#:           getting fired before :signal:`spider_opened`.
engine_started = object()

#: .. signal:: engine_stopped
#:
#: Sent when the Scrapy engine is stopped (for example, when a crawling
#: process has finished).
#:
#: This signal supports returning deferreds from their handlers.
engine_stopped = object()

#: .. signal:: spider_opened
#:
#: Sent after a spider has been opened for crawling. This is typically used to
#: reserve per-spider resources, but can be used for any task that needs to be
#: performed when a spider is opened.
#:
#: This signal supports returning deferreds from their handlers.
#:
#: :param spider: the spider which has been opened
#: :type spider: :class:`~scrapy.spiders.Spider` object
spider_opened = object()

#: .. signal:: spider_idle
#:
#: Sent when a spider has gone idle, which means the spider has no further:
#:
#:     * requests waiting to be downloaded
#:     * requests scheduled
#:     * items being processed in the item pipeline
#:
#: If the idle state persists after all handlers of this signal have finished,
#: the engine starts closing the spider. After the spider has finished
#: closing, the :signal:`spider_closed` signal is sent.
#:
#: You may raise a :exc:`~scrapy.exceptions.DontCloseSpider` exception to
#: prevent the spider from being closed.
#:
#: This signal does not support returning deferreds from their handlers.
#:
#: :param spider: the spider which has gone idle
#: :type spider: :class:`~scrapy.spiders.Spider` object
#:
#: .. note:: Scheduling some requests in your :signal:`spider_idle` handler does
#:     **not** guarantee that it can prevent the spider from being closed,
#:     although it sometimes can. That's because the spider may still remain idle
#:     if all the scheduled requests are rejected by the scheduler (e.g. filtered
#:     due to duplication).
spider_idle = object()

#: .. signal:: spider_closed
#:
#: Sent after a spider has been closed. This can be used to release per-spider
#: resources reserved on :signal:`spider_opened`.
#:
#: This signal supports returning deferreds from their handlers.
#:
#: :param spider: the spider which has been closed
#: :type spider: :class:`~scrapy.spiders.Spider` object
#:
#: :param reason: a string which describes the reason why the spider was closed. If
#:     it was closed because the spider has completed scraping, the reason
#:     is ``'finished'``. Otherwise, if the spider was manually closed by
#:     calling the ``close_spider`` engine method, then the reason is the one
#:     passed in the ``reason`` argument of that method (which defaults to
#:     ``'cancelled'``). If the engine was shutdown (for example, by hitting
#:     Ctrl-C to stop it) the reason will be ``'shutdown'``.
#: :type reason: str
spider_closed = object()

#: .. signal:: spider_error
#:
#: Sent when a spider callback generates an error (ie. raises an exception).
#:
#: This signal does not support returning deferreds from their handlers.
#:
#: :param failure: the exception raised as a Twisted `Failure`_ object
#: :type failure: `Failure`_ object
#:
#: :param response: the response being processed when the exception was raised
#: :type response: :class:`Response <scrapy.Response>` object
#:
#: :param spider: the spider which raised the exception
#: :type spider: :class:`~scrapy.spiders.Spider` object
spider_error = object()

#: .. signal:: request_scheduled
#:
#: Sent when the engine schedules a :class:`Request <scrapy.Request>`, to be
#: downloaded later.
#:
#: The signal does not support returning deferreds from their handlers.
#:
#: :param request: the request that reached the scheduler
#: :type request: :class:`Request <scrapy.Request>` object
#:
#: :param spider: the spider that yielded the request
#: :type spider: :class:`~scrapy.spiders.Spider` object
request_scheduled = object()

#: .. signal:: request_dropped
#:
#: Sent when a :class:`Request <scrapy.Request>`, scheduled by the engine to be
#: downloaded later, is rejected by the scheduler.
#:
#: The signal does not support returning deferreds from their handlers.
#:
#: :param request: the request that reached the scheduler
#: :type request: :class:`Request <scrapy.Request>` object
#:
#: :param spider: the spider that yielded the request
#: :type spider: :class:`~scrapy.spiders.Spider` object
request_dropped = object()

#: .. signal:: request_reached_downloader
#:
#: Sent when a :class:`Request <scrapy.Request>` reached downloader.
#:
#: The signal does not support returning deferreds from their handlers.
#:
#: :param request: the request that reached downloader
#: :type request: :class:`Request <scrapy.Request>` object
#:
#: :param spider: the spider that yielded the request
#: :type spider: :class:`~scrapy.spiders.Spider` object
request_reached_downloader = object()

#: .. signal:: response_received
#:
#: Sent when the engine receives a new :class:`Response <scrapy.Response>` from the
#: downloader.
#:
#: This signal does not support returning deferreds from their handlers.
#:
#: :param response: the response received
#: :type response: :class:`Response <scrapy.Response>` object
#:
#: :param request: the request that generated the response
#: :type request: :class:`Request <scrapy.Request>` object
#:
#: :param spider: the spider for which the response is intended
#: :type spider: :class:`~scrapy.spiders.Spider` object
response_received = object()

#: .. signal:: response_downloaded
#:
#: Sent by the downloader right after a ``HTTPResponse`` is downloaded.
#:
#: This signal does not support returning deferreds from their handlers.
#:
#: :param response: the response downloaded
#: :type response: :class:`Response <scrapy.Response>` object
#:
#: :param request: the request that generated the response
#: :type request: :class:`Request <scrapy.Request>` object
#:
#: :param spider: the spider for which the response is intended
#: :type spider: :class:`~scrapy.spiders.Spider` object
response_downloaded = object()

#: .. signal:: item_scraped
#:
#: Sent when an item has been scraped, after it has passed all the
#: :ref:`topics-item-pipeline` stages (without being dropped).
#:
#: This signal supports returning deferreds from their handlers.
#:
#: :param item: the item scraped
#: :type item: dict or :class:`~scrapy.item.Item` object
#:
#: :param spider: the spider which scraped the item
#: :type spider: :class:`~scrapy.spiders.Spider` object
#:
#: :param response: the response from where the item was scraped
#: :type response: :class:`Response <scrapy.Response>` object
item_scraped = object()

#: .. signal:: item_dropped
#:
#: Sent after an item has been dropped from the :ref:`topics-item-pipeline`
#: when some stage raised a :exc:`~scrapy.exceptions.DropItem` exception.
#:
#: This signal supports returning deferreds from their handlers.
#:
#: :param item: the item dropped from the :ref:`topics-item-pipeline`
#: :type item: dict or :class:`~scrapy.item.Item` object
#:
#: :param spider: the spider which scraped the item
#: :type spider: :class:`~scrapy.spiders.Spider` object
#:
#: :param response: the response from where the item was dropped
#: :type response: :class:`Response <scrapy.Response>` object
#:
#: :param exception: the exception (which must be a
#:     :exc:`~scrapy.exceptions.DropItem` subclass) which caused the item
#:     to be dropped
#: :type exception: :exc:`~scrapy.exceptions.DropItem` exception
item_dropped = object()

#: .. signal:: item_error
#:
#: Sent when a :ref:`topics-item-pipeline` generates an error (ie. raises
#: an exception), except :exc:`~scrapy.exceptions.DropItem` exception.
#:
#: This signal supports returning deferreds from their handlers.
#:
#: :param item: the item dropped from the :ref:`topics-item-pipeline`
#: :type item: dict or :class:`~scrapy.item.Item` object
#:
#: :param response: the response being processed when the exception was raised
#: :type response: :class:`Response <scrapy.Response>` object
#:
#: :param spider: the spider which raised the exception
#: :type spider: :class:`~scrapy.spiders.Spider` object
#:
#: :param failure: the exception raised as a Twisted `Failure`_ object
#: :type failure: `Failure`_ object
item_error = object()

# for backwards compatibility
stats_spider_opened = spider_opened
stats_spider_closing = spider_closed
stats_spider_closed = spider_closed

item_passed = item_scraped

request_received = request_scheduled
