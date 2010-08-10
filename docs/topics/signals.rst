.. _topics-signals:

=======
Signals
=======

Scrapy uses signals extensively to notify when certain actions occur. You can
catch some of those signals in your Scrapy project or extension to perform
additional tasks or extend Scrapy to add functionality not provided out of the
box.

Even though signals provide several arguments, the handlers which catch them
don't have to receive all of them.

For more information about working when see the documentation of
`pydispatcher`_ (library used to implement signals).

.. _pydispatcher: http://pydispatcher.sourceforge.net/


.. _topics-signals-ref:

Built-in signals reference
==========================

.. module:: scrapy.signals
   :synopsis: Signals definitions

Here's a list of signals used in Scrapy and their meaning, in alphabetical
order.

engine_started
--------------

.. signal:: engine_started
.. function:: engine_started()

    Sent when the Scrapy engine is started (for example, when a crawling
    process has started).

engine_stopped
--------------

.. signal:: engine_stopped
.. function:: engine_stopped()

    Sent when the Scrapy engine is stopped (for example, when a crawling
    process has finished).

item_scraped
------------

.. signal:: item_scraped
.. function:: item_scraped(item, spider, response)

    Sent when the engine receives a new scraped item from the spider, and right
    before the item is sent to the :ref:`topics-item-pipeline`.

    :param item: is the item scraped
    :type item: :class:`~scrapy.item.Item` object

    :param spider: the spider which scraped the item
    :type spider: :class:`~scrapy.spider.BaseSpider` object

    :param response: the response from which the item was scraped
    :type response: :class:`~scrapy.http.Response` object

item_passed
-----------

.. signal:: item_passed
.. function:: item_passed(item, spider, output)

    Sent after an item has passed all the :ref:`topics-item-pipeline` stages without
    being dropped.

    :param item: the item which passed the pipeline
    :type item: :class:`~scrapy.item.Item` object

    :param spider: the spider which scraped the item
    :type spider: :class:`~scrapy.spider.BaseSpider` object

    :param output: the output of the item pipeline. This is typically the
        same :class:`~scrapy.item.Item` object received in the ``item``
        parameter, unless some pipeline stage created a new item.

item_dropped
------------

.. signal:: item_dropped
.. function:: item_dropped(item, spider, exception)

    Sent after an item has been dropped from the :ref:`topics-item-pipeline`
    when some stage raised a :exc:`~scrapy.exceptions.DropItem` exception.

    :param item: the item dropped from the :ref:`topics-item-pipeline`
    :type item: :class:`~scrapy.item.Item` object

    :param spider: the spider which scraped the item
    :type spider: :class:`~scrapy.spider.BaseSpider` object

    :param exception: the exception (which must be a
        :exc:`~scrapy.exceptions.DropItem` subclass) which caused the item
        to be dropped
    :type exception: :exc:`~scrapy.exceptions.DropItem` exception

spider_closed
-------------

.. signal:: spider_closed
.. function:: spider_closed(spider, reason)

    Sent after a spider has been closed. This can be used to release per-spider
    resources reserved on :signal:`spider_opened`.

    :param spider: the spider which has been closed
    :type spider: :class:`~scrapy.spider.BaseSpider` object

    :param reason: a string which describes the reason why the spider was closed. If
        it was closed because the spider has completed scraping, it the reason
        is ``'finished'``. Otherwise, if the spider was manually closed by
        calling the ``close_spider`` engine method, then the reason is the one
        passed in the ``reason`` argument of that method (which defaults to
        ``'cancelled'``). If the engine was shutdown (for example, by hitting
        Ctrl-C to stop it) the reason will be ``'shutdown'``.
    :type reason: str

spider_opened
-------------

.. signal:: spider_opened
.. function:: spider_opened(spider)

    Sent after a spider has been opened for crawling. This is typically used to
    reserve per-spider resources, but can be used for any task that needs to be
    performed when a spider is opened.

    :param spider: the spider which has been opened
    :type spider: :class:`~scrapy.spider.BaseSpider` object

spider_idle
-----------

.. signal:: spider_idle
.. function:: spider_idle(spider)

    Sent when a spider has gone idle, which means the spider has no further:

        * requests waiting to be downloaded
        * requests scheduled
        * items being processed in the item pipeline

    If the idle state persists after all handlers of this signal have finished,
    the engine starts closing the spider. After the spider has finished
    closing, the :signal:`spider_closed` signal is sent.

    You can, for example, schedule some requests in your :signal:`spider_idle`
    handler to prevent the spider from being closed.

    :param spider: the spider which has gone idle
    :type spider: :class:`~scrapy.spider.BaseSpider` object

request_received
----------------

.. signal:: request_received
.. function:: request_received(request, spider)

    Sent when the engine receives a :class:`~scrapy.http.Request` from a spider.

    :param request: the request received
    :type request: :class:`~scrapy.http.Request` object

    :param spider: the spider which generated the request
    :type spider: :class:`~scrapy.spider.BaseSpider` object

request_uploaded
----------------

.. signal:: request_uploaded
.. function:: request_uploaded(request, spider)

    Sent right after the download has sent a :class:`~scrapy.http.Request`.

    :param request: the request uploaded/sent
    :type request: :class:`~scrapy.http.Request` object

    :param spider: the spider which generated the request
    :type spider: :class:`~scrapy.spider.BaseSpider` object

response_received
-----------------

.. signal:: response_received
.. function:: response_received(response, spider)

    :param response: the response received
    :type response: :class:`~scrapy.http.Response` object

    :param spider: the spider for which the response is intended
    :type spider: :class:`~scrapy.spider.BaseSpider` object

    Sent when the engine receives a new :class:`~scrapy.http.Response` from the
    downloader.

response_downloaded
-------------------

.. signal:: response_downloaded
.. function:: response_downloaded(response, spider)

    Sent by the downloader right after a ``HTTPResponse`` is downloaded.

    :param response: the response downloaded
    :type response: :class:`~scrapy.http.Response` object

    :param spider: the spider for which the response is intended
    :type spider: :class:`~scrapy.spider.BaseSpider` object

