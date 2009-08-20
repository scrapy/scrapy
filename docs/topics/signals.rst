.. _topics-signals:

.. module:: scrapy.core.signals
   :synopsis: Signals definitions

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

Here's a list of signals used in Scrapy and their meaning, in alphabetical
order.

.. signal:: domain_closed
.. function:: domain_closed(domain, spider, reason)

    Sent right after a spider/domain has been closed.

    :param domain: a string which contains the domain of the spider which has
        been closed
    :type domain: str

    :param spider: the spider which has been closed
    :type spider: :class:`~scrapy.spider.BaseSpider` object

    :param reason: a string which describes the reason why the domain was closed. If
        it was closed because the domain has completed scraping, it the reason
        is ``'finished'``. Otherwise, if the domain was manually closed by
        calling the ``close_domain`` engine method, then the reason is the one
        passed in the ``reason`` argument of that method (which defaults to
        ``'cancelled'``). If the engine was shutdown (for example, by hitting
        Ctrl-C to stop it) the reason will be ``'shutdown'``.
    :type reason: str

.. signal:: domain_open
.. function:: domain_open(domain, spider)

    Sent right before a spider has been opened for crawling.

    :param domain: a string which contains the domain of the spider which is about
        to be opened
    :type domain: str

    :param spider: the spider which is about to be opened
    :type spider: :class:`~scrapy.spider.BaseSpider` object

.. signal:: domain_opened
.. function:: domain_opened(domain, spider)

    Sent right after a spider has been opened for crawling.

    :param domain: a string with the domain of the spider which has been opened
    :type domain: str

    :param spider: the spider which has been opened
    :type spider: :class:`~scrapy.spider.BaseSpider` object

.. signal:: domain_idle
.. function:: domain_idle(domain, spider)

    Sent when a domain has gone idle, which means the spider has no further:
        * requests waiting to be downloaded
        * requests scheduled
        * items being processed in the item pipeline

    :param domain: is a string with the domain of the spider which has gone idle
    :type domain: str

    :param spider: the spider which has gone idle
    :type spider: :class:`~scrapy.spider.BaseSpider` object

    If any handler of this signal handlers raises a
    :exception:`DontCloseDomain` the domain won't be closed this time and will
    wait until another idle signal is sent.  Otherwise (if no handler raises
    :exception:`DontCloseDomain`) the domain will be closed immediately after
    all handlers of ``domain_idle`` have finished, and a
    :signal:`domain_closed` will thus be sent.

.. signal:: engine_started
.. function:: engine_started()

    Sent when the Scrapy engine is started (for example, when a crawling
    process has started).

.. signal:: engine_stopped
.. function:: engine_stopped()

    Sent when the Scrapy engine is stopped (for example, when a crawling
    process has finished).

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

.. signal:: item_dropped
.. function:: item_dropped(item, spider, exception)

    Sent after an item has been dropped from the :ref:`topics-item-pipeline`
    when some stage raised a :exception:`DropItem` exception.

    :param item: the item dropped from the :ref:`topics-item-pipeline`
    :type item: :class:`~scrapy.item.Item` object

    :param spider: the spider which scraped the item 
    :type spider: :class:`~scrapy.spider.BaseSpider` object

    :param exception: the exception (which must be a :exception:`DropItem`
        subclass) which caused the item to be dropped 
    :type exception: :exception:`DropItem` exception

.. signal:: request_received
.. function:: request_received(request, spider, response)

    Sent when the engine receives a :class:`~scrapy.http.Request` from a spider.

    :param request: the request received
    :type request: :class:`~scrapy.http.Request` object

    :param spider: the spider which generated the request
    :type spider: :class:`~scrapy.spider.BaseSpider` object

    :param response: the :class:`~scrapy.http.Response` fed to the spider which
        generated the request later
    :type response: :class:`~scrapy.http.Response` object

.. signal:: request_uploaded
.. function:: request_uploaded(request, spider)

    Sent right after the download has sent a :class:`~scrapy.http.Request`.

    :param request: the request uploaded/sent
    :type request: :class:`~scrapy.http.Request` object

    :param spider: the spider which generated the request
    :type spider: :class:`~scrapy.spider.BaseSpider` object

.. signal:: response_received
.. function:: response_received(response, spider)

    :param response: the response received
    :type response: :class:`~scrapy.http.Response` object

    :param spider: the spider for which the response is intended
    :type spider: :class:`~scrapy.spider.BaseSpider` object

    Sent when the engine receives a new :class:`~scrapy.http.Response` from the
    downloader.

.. signal:: response_downloaded
.. function:: response_downloaded(response, spider)

    Sent by the downloader right after a ``HTTPResponse`` is downloaded.

    :param response: the response downloaded
    :type response: :class:`~scrapy.http.Response` object

    :param spider: the spider for which the response is intended
    :type spider: :class:`~scrapy.spider.BaseSpider` object

