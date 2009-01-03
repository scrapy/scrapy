.. _signals:

Available Signals
=================

Scrapy uses signals extensively to notify when certain actions occur. You can
catch some of those signals in your Scrapy project or extension to perform
additional tasks or extend Scrapy to add functionality not provided out of the
box.

Here's a list of signals used in Scrapy and their meaning, in alphabetical
order.

.. signal:: domain_closed

domain_closed
-------------

Arguments: 
 * ``domain`` - the domain (of the spider) which has been closed
 * ``spider`` - the spider which has been closed

Sent right after a spider/domain has been closed.

.. signal:: domain_open

domain_open
-----------

Arguments: 
 * ``domain`` - the domain (of the spider) which is about to be opened
 * ``spider`` - the spider which is about to be opened

Sent right before a spider has been opened for crawling.

.. signal:: domain_opened

domain_opened
-------------

Arguments: 
 * ``domain`` - the domain (of the spider) which has been opened
 * ``spider`` - the spider which has been opened

Sent right after a spider has been opened for crawling.

.. signal:: domain_idle

domain_idle
-----------

Arguments: 
 * ``domain`` - the domain (of the spider) which has gone idle
 * ``spider`` - the spider which has gone idle

Sent when a domain has no further:
 * requests waiting to be downloaded
 * requests scheduled
 * items being processed in the item pipeline

If any handler of this signals raises a :exception:`DontCloseDomain` the domain
won't be closed at this time and will wait until another idle signal is sent.
Otherwise (if no handler raises :exception:`DontCloseDomain`) the domain will
be closed immediately after all handlers of ``domain_idle`` have finished, and
a :signal:`domain_closed` will thus be sent.

.. signal:: engine_started

engine_started
--------------

Arguments: ``None``

Sent when the Scrapy engine is started (for example, when a crawling
process has started).

.. signal:: engine_stopped

engine_stopped
--------------

Arguments: ``None``

Sent when the Scrapy engine is stopped (for example, when a crawling
process has started).

.. signal:: request_received

request_received
----------------

Arguments: 
 * ``request`` - the ``HTTPRequest`` received
 * ``spider`` - the spider which generated the request
 * ``response`` - the ``HTTPResponse`` fed to the spider which generated the
    request

Sent when the engine receives a ``HTTPRequest`` from a spider.

.. signal:: request_uploaded

request_uploaded
----------------

Arguments: 
 * ``request`` - the ``HTTPRequest`` uploaded/sent
 * ``spider`` - the spider which generated the request

Sent right after the download has sent a ``HTTPRequest``.

.. signal:: response_received

response_received
-----------------

Arguments: 
 * ``response`` - the ``HTTPResponse`` received
 * ``spider`` - the spider for which the response is intended

Sent when the engine receives a new ``HTTPResponse`` from the downloader.

.. signal:: response_downloaded

response_downloaded
-------------------

Arguments: 
 * ``response`` - the ``HTTPResponse`` downloaded
 * ``spider`` - the spider for which the response is intended

Sent by the downloader right after a ``HTTPResponse`` is downloaded.

.. signal:: item_scraped

item_scraped
------------

Arguments:
 * ``item`` - the item scraped
 * ``spider`` - the spider which scraped the item 
 * ``response`` - the response from which the item was scraped

Sent when the engine receives a new scraped item from the spider, and right
before the item is sent to the :topic:`item-pipeline`.

.. signal:: item_passed

item_passed
-----------

Arguments:
 * ``item`` - the item passed
 * ``spider`` - the spider which scraped the item 
 * ``response`` - the response from which the item was scraped
 * ``pipe_output`` - the output of the item pipeline. Typically, this points to
    the same ``item`` object, unless some pipeline stage created a new item.

Sent after an item has passed al the :topic:`item-pipeline` stages without
being dropped.

.. signal:: item_dropped

item_dropped
------------

Arguments:
 * ``item`` - the item dropped
 * ``spider`` - the spider which scraped the item 
 * ``response`` - the response from which the item was scraped
 * ``exception`` - the exception that caused the item to be dropped (which must inherit from :exception:`DropItem`) 

Sent after an item has dropped from the :topic:`item-pipeline` when some stage
raised a :exception:`DropItem` exception.


