.. _signals:

.. module:: scrapy.core.signals
   :synopsis: Signals definitions

Available Signals
=================

Scrapy uses signals extensively to notify when certain actions occur. You can
catch some of those signals in your Scrapy project or extension to perform
additional tasks or extend Scrapy to add functionality not provided out of the
box.

Even though signals provide several arguments, the handlers which catch them
don't have to receive all of them.

For more information about working when see the documentation of
`pydispatcher`_ (library used to implement signals).

.. _pydispatcher: http://pydispatcher.sourceforge.net/

Here's a list of signals used in Scrapy and their meaning, in alphabetical
order.

.. signal:: domain_closed
.. function:: domain_closed(domain, spider, status)

Sent right after a spider/domain has been closed.

``domain`` is a string which contains the domain of the spider which has been closed
``spider`` is the spider which has been closed
``status`` is a string which can have two values: ``'finished'`` if the domain
has finished successfully, or ``'cancelled'`` if the domain was cancelled (for
example, by hitting Ctrl-C, by calling the engine ``stop()`` method or by
explicitly closing the domain).

.. signal:: domain_open
.. function:: domain_open(domain, spider)

Sent right before a spider has been opened for crawling.

``domain`` is a string which contains the domain of the spider which is about
to be opened
``spider`` is the spider which is about to be opened

.. signal:: domain_opened
.. function:: domain_opened(domain, spider)

Sent right after a spider has been opened for crawling.

``domain`` is a string with the domain of the spider which has been opened
``spider`` is the spider which has been opened

.. signal:: domain_idle
.. function:: domain_idle(domain, spider)

Sent when a domain has no further:
 * requests waiting to be downloaded
 * requests scheduled
 * items being processed in the item pipeline

``domain`` is a string with the domain of the spider which has gone idle
``spider`` is the spider which has gone idle

If any handler of this signals raises a :exception:`DontCloseDomain` the domain
won't be closed at this time and will wait until another idle signal is sent.
Otherwise (if no handler raises :exception:`DontCloseDomain`) the domain will
be closed immediately after all handlers of ``domain_idle`` have finished, and
a :signal:`domain_closed` will thus be sent.

.. signal:: engine_started
.. function:: engine_started()

Sent when the Scrapy engine is started (for example, when a crawling
process has started).

.. signal:: engine_stopped
.. function:: engine_stopped()

Sent when the Scrapy engine is stopped (for example, when a crawling
process has started).

.. signal:: request_received
.. function:: request_received(request, spider, response)

Sent when the engine receives a :class:`~scrapy.http.Request` from a spider.

``request`` is the :class:`~scrapy.http.Request` received
``spider`` is the spider which generated the request
``response`` is the :class:`~scrapy.http.Response` fed to the spider which
generated the request

.. signal:: request_uploaded
.. function:: request_uploaded(request, spider)

Sent right after the download has sent a :class:`~scrapy.http.Request`.

``request`` is the :class:`~scrapy.http.Request` uploaded/sent
``spider`` is the spider which generated the request

.. signal:: response_received
.. function:: response_received(response, spider)

``response`` is the :class:`~scrapy.http.Response` received
``spider`` is  the spider for which the response is intended

Sent when the engine receives a new :class:`~scrapy.http.Response` from the
downloader.

.. signal:: response_downloaded
.. function:: response_downloaded(response, spider)

Sent by the downloader right after a ``HTTPResponse`` is downloaded.

``response`` is the ``HTTPResponse`` downloaded
``spider`` is the spider for which the response is intended

.. signal:: item_scraped
.. function:: item_scraped(item, spider, response)

Sent when the engine receives a new scraped item from the spider, and right
before the item is sent to the :ref:`topics-item-pipeline`.

``item`` is the item scraped
``spider`` is the spider which scraped the item 
``response`` is the :class:`~scrapy.http.Response` from which the item was
scraped

.. signal:: item_passed
.. function:: item_passed(item, spider, response, pipe_output)

Sent after an item has passed al the :ref:`topics-item-pipeline` stages without
being dropped.

``item`` is the item which passed the pipeline
``spider`` is the spider which scraped the item 
``response`` is the :class:`~scrapy.http.Response` from which the item was scraped
``pipe_output`` is  the output of the item pipeline. Typically, this points to
the same ``item`` object, unless some pipeline stage created a new item.

.. signal:: item_dropped
.. function:: item_dropped(item, spider, response, exception)

Sent after an item has dropped from the :ref:`topics-item-pipeline` when some stage
raised a :exception:`DropItem` exception.

``item`` is the item dropped from the :ref:`topics-item-pipeline`
``spider`` is the spider which scraped the item 
``response`` is the :class:`~scrapy.http.Response` from which the item was scraped
``exception`` is the (:exception:`DropItem` child) exception that caused the
item to be dropped 


