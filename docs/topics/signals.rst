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

Signals underwent a major refactoring with an eye towards speed. Although still
backwards compatible, receivers now need to have a ``**kwargs`` argument i.e. all
receivers should now accept a variable keyword args param. We request that you
make sure all your receivers follow this contract.

You can connect to signals (or send your own) through the
:ref:`topics-api-signals`.

Connecting receivers to Signals
================================

Using connect method of the signalmanager
-----------------------------------------

Here is a simple example showing how you can catch signals and perform some action:
::

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


        def spider_closed(self, spider, **named):
            spider.logger.info('Spider closed: %s', spider.name)


        def parse(self, response):
            pass

Using the receiver decorator
----------------------------

An alternate way to connect to a signal is exposed by the  :func:`scrapy.dispatch.receiver`
decorator.

::

    from scrapy import signals
    from scrapy import Spider
    from scrapy.dispatch import receiver


    class DmozSpider(Spider):
        name = "dmoz"
        allowed_domains = ["dmoz.org"]
        start_urls = [
            "http://www.dmoz.org/Computers/Programming/Languages/Python/Books/",
            "http://www.dmoz.org/Computers/Programming/Languages/Python/Resources/",
        ]

        def parse(self, response):
            pass


    @receiver(signals.spider_closed)
    def spider_closed(spider, **kwargs):
        spider.logger.info('Spider closed: %s', spider.name)


Defining custom signals
=======================

Signals in scrapy are instances of the :class:`scrapy.dispatch.Signal` class.
Even though the actual signaling logic is in methods of 
:class:`scrapy.dispatch.Signal`, it is strongly recommended that you perform
all signal opreations by routing your signals through
:class:`scrapy.signalmanager.SignalManager` as any change in the signal backend
will not break the :ref:`topics-api-signals` (signalmanager API).The
:ref:`topics-api-dispatch` is still however documented for reference. Here is a
simple example of how to create a custom signal and connect receivers to it.

The ``providing_args`` is a list of the names of arguments the signal will
provide to listeners. This is purely documentational, however, as there is
nothing that checks thatthe signal actually provides these arguments to its
listeners.

::
    
    from scrapy import Spider
    from scrapy import signals
    from scrapy.dispatch import Signal

    # Defining a signal that will inform all connected receivers that parsing
    # has been completed
    parse_completed = Signal(providing_args=['url'])


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
            crawler.signals.connect(spider.parse_successful, signal=parse_completed)
            return spider

        def spider_closed(self, spider, **named):
            spider.logger.info('Spider closed: %s', spider.name)

        def parse(self, response):
            # Parse the html
            self.crawler.signals.send_catch_log(parse_completed, url=response.url)

        def parse_successful(self, sender=None, **kwargs):
            self.logger.info('Successfully parsed: %s', kwargs['url'])


Deferred signal handlers
========================

Some signals support returning `Twisted deferreds`_ from their handlers, see
the :ref:`topics-signals-ref` below to know which ones.

.. _Twisted deferreds: https://twistedmatrix.com/documents/current/core/howto/defer.html

.. _topics-signals-ref:

Built-in signals reference
==========================

.. module:: scrapy.signals
   :synopsis: Signals definitions

Here's the list of Scrapy built-in signals and their meaning.

engine_started
--------------

.. signal:: engine_started
.. function:: engine_started()

    Sent when the Scrapy engine has started crawling.

    This signal supports returning deferreds from their handlers.

.. note:: This signal may be fired *after* the :signal:`spider_opened` signal,
    depending on how the spider was started. So **don't** rely on this signal
    getting fired before :signal:`spider_opened`.

engine_stopped
--------------

.. signal:: engine_stopped
.. function:: engine_stopped()

    Sent when the Scrapy engine is stopped (for example, when a crawling
    process has finished).

    This signal supports returning deferreds from their handlers.

item_scraped
------------

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
------------

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

spider_closed
-------------

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
-------------

.. signal:: spider_opened
.. function:: spider_opened(spider)

    Sent after a spider has been opened for crawling. This is typically used to
    reserve per-spider resources, but can be used for any task that needs to be
    performed when a spider is opened.

    This signal supports returning deferreds from their handlers.

    :param spider: the spider which has been opened
    :type spider: :class:`~scrapy.spiders.Spider` object

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

    This signal does not support returning deferreds from their handlers.

    :param spider: the spider which has gone idle
    :type spider: :class:`~scrapy.spiders.Spider` object

spider_error
------------

.. signal:: spider_error
.. function:: spider_error(failure, response, spider)

    Sent when a spider callback generates an error (ie. raises an exception).

    This signal does not support returning deferreds from their handlers.

    :param failure: the exception raised as a Twisted `Failure`_ object
    :type failure: `Failure`_ object

    :param response: the response being processed when the exception was raised
    :type response: :class:`~scrapy.http.Response` object

    :param spider: the spider which raised the exception
    :type spider: :class:`~scrapy.spiders.Spider` object

request_scheduled
-----------------

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
---------------

.. signal:: request_dropped
.. function:: request_dropped(request, spider)

    Sent when a :class:`~scrapy.http.Request`, scheduled by the engine to be
    downloaded later, is rejected by the scheduler.

    The signal does not support returning deferreds from their handlers.

    :param request: the request that reached the scheduler
    :type request: :class:`~scrapy.http.Request` object

    :param spider: the spider that yielded the request
    :type spider: :class:`~scrapy.spiders.Spider` object

response_received
-----------------

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
-------------------

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

.. _Failure: https://twistedmatrix.com/documents/current/api/twisted.python.failure.Failure.html
