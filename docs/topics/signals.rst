.. _topics-signals:

=======
Signals
=======

Scrapy uses signals extensively to notify when certain events occur. You can
catch some of those signals in your Scrapy project (using an :ref:`extension
<topics-extensions>`, for example) to perform additional tasks or extend Scrapy
to add functionality not provided out of the box.

Even though signals provide several arguments, the handlers that catch them
don't need to accept all of them - the signal dispatching mechanism will only
deliver the arguments that the handler receives.

You can connect to signals (or send your own) through the
:ref:`topics-api-signals`.

Here is a simple example showing how you can catch signals and perform some action::

    from scrapy import signals
    from scrapy import Spider


    class DmozSpider(Spider):
        name = "dmoz"
        allowed_domains = ["dmoz.org"]
        start_urls = [
            "http://www.dmoz.org/Computers/Programming/Languages/Python/Books/",
            "http://www.dmoz.org/Computers/Programming/Languages/Python/Resources/",
        ]


        @classmethod
        def from_crawler(cls, crawler, *args, **kwargs):
            spider = super(DmozSpider, cls).from_crawler(crawler, *args, **kwargs)
            crawler.signals.connect(spider.spider_closed, signal=signals.spider_closed)
            return spider


        def spider_closed(self, spider):
            spider.logger.info('Spider closed: %s', spider.name)


        def parse(self, response):
            pass

.. _signal-deferred:

Deferred signal handlers
========================

Some signals support returning :class:`~twisted.internet.defer.Deferred`
objects from their handlers, allowing you to run asynchronous code that
does not block Scrapy. If a signal handler returns a
:class:`~twisted.internet.defer.Deferred`, Scrapy waits for that
:class:`~twisted.internet.defer.Deferred` to fire.

Let's take an example::

    class SignalSpider(scrapy.Spider):
        name = 'signals'
        start_urls = ['http://quotes.toscrape.com/page/1/']

        @classmethod
        def from_crawler(cls, crawler, *args, **kwargs):
            spider = super(SignalSpider, cls).from_crawler(crawler, *args, **kwargs)
            crawler.signals.connect(spider.item_scraped, signal=signals.item_scraped)
            return spider

        def item_scraped(self, item):
            # Send the scraped item to the server
            d = treq.post(
                'http://example.com/post',
                json.dumps(item).encode('ascii'),
                headers={b'Content-Type': [b'application/json']}
            )

            # The next item will be scraped only after
            # deferred (d) is fired
            return d

        def parse(self, response):
            for quote in response.css('div.quote'):
                yield {
                    'text': quote.css('span.text::text').get(),
                    'author': quote.css('small.author::text').get(),
                    'tags': quote.css('div.tags a.tag::text').getall(),
                }

See the :ref:`topics-signals-ref` below to know which signals support
:class:`~twisted.internet.defer.Deferred`.

.. _topics-signals-ref:

Built-in signals reference
==========================

.. module:: scrapy.signals
   :synopsis: Signals definitions

Here's the list of Scrapy built-in signals and their meaning.

Engine signals
--------------

engine_started
~~~~~~~~~~~~~~

.. signal:: engine_started
.. function:: engine_started()

    Sent when the Scrapy engine has started crawling.

    This signal supports returning deferreds from their handlers.

.. note:: This signal may be fired *after* the :signal:`spider_opened` signal,
    depending on how the spider was started. So **don't** rely on this signal
    getting fired before :signal:`spider_opened`.

engine_stopped
~~~~~~~~~~~~~~

.. signal:: engine_stopped
.. function:: engine_stopped()

    Sent when the Scrapy engine is stopped (for example, when a crawling
    process has finished).

    This signal supports returning deferreds from their handlers.

Item signals
------------

.. note::
    As at max :setting:`CONCURRENT_ITEMS` items are processed in
    parallel, many deferreds are fired together using
    :class:`~twisted.internet.defer.DeferredList`. Hence the next
    batch waits for the :class:`~twisted.internet.defer.DeferredList`
    to fire and then runs the respective item signal handler for
    the next batch of scraped items.

item_scraped
~~~~~~~~~~~~

.. signal:: item_scraped
.. function:: item_scraped(item, response, spider)

    Sent when an item has been scraped, after it has passed all the
    :ref:`topics-item-pipeline` stages (without being dropped).

    This signal supports returning deferreds from their handlers.

    :param item: the item scraped
    :type item: dict or :class:`~scrapy.item.Item` object

    :param spider: the spider which scraped the item
    :type spider: :class:`~scrapy.spiders.Spider` object

    :param response: the response from where the item was scraped
    :type response: :class:`~scrapy.http.Response` object

item_dropped
~~~~~~~~~~~~

.. signal:: item_dropped
.. function:: item_dropped(item, response, exception, spider)

    Sent after an item has been dropped from the :ref:`topics-item-pipeline`
    when some stage raised a :exc:`~scrapy.exceptions.DropItem` exception.

    This signal supports returning deferreds from their handlers.

    :param item: the item dropped from the :ref:`topics-item-pipeline`
    :type item: dict or :class:`~scrapy.item.Item` object

    :param spider: the spider which scraped the item
    :type spider: :class:`~scrapy.spiders.Spider` object

    :param response: the response from where the item was dropped
    :type response: :class:`~scrapy.http.Response` object

    :param exception: the exception (which must be a
        :exc:`~scrapy.exceptions.DropItem` subclass) which caused the item
        to be dropped
    :type exception: :exc:`~scrapy.exceptions.DropItem` exception

item_error
~~~~~~~~~~

.. signal:: item_error
.. function:: item_error(item, response, spider, failure)

    Sent when a :ref:`topics-item-pipeline` generates an error (i.e. raises
    an exception), except :exc:`~scrapy.exceptions.DropItem` exception.

    This signal supports returning deferreds from their handlers.

    :param item: the item dropped from the :ref:`topics-item-pipeline`
    :type item: dict or :class:`~scrapy.item.Item` object

    :param response: the response being processed when the exception was raised
    :type response: :class:`~scrapy.http.Response` object

    :param spider: the spider which raised the exception
    :type spider: :class:`~scrapy.spiders.Spider` object

    :param failure: the exception raised
    :type failure: twisted.python.failure.Failure

Spider signals
--------------

spider_closed
~~~~~~~~~~~~~

.. signal:: spider_closed
.. function:: spider_closed(spider, reason)

    Sent after a spider has been closed. This can be used to release per-spider
    resources reserved on :signal:`spider_opened`.

    This signal supports returning deferreds from their handlers.

    :param spider: the spider which has been closed
    :type spider: :class:`~scrapy.spiders.Spider` object

    :param reason: a string which describes the reason why the spider was closed. If
        it was closed because the spider has completed scraping, the reason
        is ``'finished'``. Otherwise, if the spider was manually closed by
        calling the ``close_spider`` engine method, then the reason is the one
        passed in the ``reason`` argument of that method (which defaults to
        ``'cancelled'``). If the engine was shutdown (for example, by hitting
        Ctrl-C to stop it) the reason will be ``'shutdown'``.
    :type reason: str

spider_opened
~~~~~~~~~~~~~

.. signal:: spider_opened
.. function:: spider_opened(spider)

    Sent after a spider has been opened for crawling. This is typically used to
    reserve per-spider resources, but can be used for any task that needs to be
    performed when a spider is opened.

    This signal supports returning deferreds from their handlers.

    :param spider: the spider which has been opened
    :type spider: :class:`~scrapy.spiders.Spider` object

spider_idle
~~~~~~~~~~~

.. signal:: spider_idle
.. function:: spider_idle(spider)

    Sent when a spider has gone idle, which means the spider has no further:

        * requests waiting to be downloaded
        * requests scheduled
        * items being processed in the item pipeline

    If the idle state persists after all handlers of this signal have finished,
    the engine starts closing the spider. After the spider has finished
    closing, the :signal:`spider_closed` signal is sent.

    You may raise a :exc:`~scrapy.exceptions.DontCloseSpider` exception to
    prevent the spider from being closed.

    This signal does not support returning deferreds from their handlers.

    :param spider: the spider which has gone idle
    :type spider: :class:`~scrapy.spiders.Spider` object

.. note:: Scheduling some requests in your :signal:`spider_idle` handler does
    **not** guarantee that it can prevent the spider from being closed,
    although it sometimes can. That's because the spider may still remain idle
    if all the scheduled requests are rejected by the scheduler (e.g. filtered
    due to duplication).

spider_error
~~~~~~~~~~~~

.. signal:: spider_error
.. function:: spider_error(failure, response, spider)

    Sent when a spider callback generates an error (i.e. raises an exception).

    This signal does not support returning deferreds from their handlers.

    :param failure: the exception raised
    :type failure: twisted.python.failure.Failure

    :param response: the response being processed when the exception was raised
    :type response: :class:`~scrapy.http.Response` object

    :param spider: the spider which raised the exception
    :type spider: :class:`~scrapy.spiders.Spider` object

Request signals
---------------

request_scheduled
~~~~~~~~~~~~~~~~~

.. signal:: request_scheduled
.. function:: request_scheduled(request, spider)

    Sent when the engine schedules a :class:`~scrapy.http.Request`, to be
    downloaded later.

    The signal does not support returning deferreds from their handlers.

    :param request: the request that reached the scheduler
    :type request: :class:`~scrapy.http.Request` object

    :param spider: the spider that yielded the request
    :type spider: :class:`~scrapy.spiders.Spider` object

request_dropped
~~~~~~~~~~~~~~~

.. signal:: request_dropped
.. function:: request_dropped(request, spider)

    Sent when a :class:`~scrapy.http.Request`, scheduled by the engine to be
    downloaded later, is rejected by the scheduler.

    The signal does not support returning deferreds from their handlers.

    :param request: the request that reached the scheduler
    :type request: :class:`~scrapy.http.Request` object

    :param spider: the spider that yielded the request
    :type spider: :class:`~scrapy.spiders.Spider` object

request_reached_downloader
~~~~~~~~~~~~~~~~~~~~~~~~~~

.. signal:: request_reached_downloader
.. function:: request_reached_downloader(request, spider)

    Sent when a :class:`~scrapy.http.Request` reached downloader.

    The signal does not support returning deferreds from their handlers.

    :param request: the request that reached downloader
    :type request: :class:`~scrapy.http.Request` object

    :param spider: the spider that yielded the request
    :type spider: :class:`~scrapy.spiders.Spider` object

request_left_downloader
~~~~~~~~~~~~~~~~~~~~~~~

.. signal:: request_left_downloader
.. function:: request_left_downloader(request, spider)

    .. versionadded:: 2.0

    Sent when a :class:`~scrapy.http.Request` leaves the downloader, even in case of
    failure.

    This signal does not support returning deferreds from its handlers.

    :param request: the request that reached the downloader
    :type request: :class:`~scrapy.http.Request` object

    :param spider: the spider that yielded the request
    :type spider: :class:`~scrapy.spiders.Spider` object

Response signals
----------------

response_received
~~~~~~~~~~~~~~~~~

.. signal:: response_received
.. function:: response_received(response, request, spider)

    Sent when the engine receives a new :class:`~scrapy.http.Response` from the
    downloader.

    This signal does not support returning deferreds from their handlers.

    :param response: the response received
    :type response: :class:`~scrapy.http.Response` object

    :param request: the request that generated the response
    :type request: :class:`~scrapy.http.Request` object

    :param spider: the spider for which the response is intended
    :type spider: :class:`~scrapy.spiders.Spider` object

response_downloaded
~~~~~~~~~~~~~~~~~~~

.. signal:: response_downloaded
.. function:: response_downloaded(response, request, spider)

    Sent by the downloader right after a ``HTTPResponse`` is downloaded.

    This signal does not support returning deferreds from their handlers.

    :param response: the response downloaded
    :type response: :class:`~scrapy.http.Response` object

    :param request: the request that generated the response
    :type request: :class:`~scrapy.http.Request` object

    :param spider: the spider for which the response is intended
    :type spider: :class:`~scrapy.spiders.Spider` object
