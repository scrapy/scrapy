============
Introduction
============

.. architecture:

Architecture
============

.. image:: _images/scrapy_architecture.png
   :width: 700
   :height: 468
   :alt: Scrapy architecture

.. _items:

Items
=====

In Scrapy, Items are the placeholder to use for the scraped data. They are
represented by a :class:`~scrapy.item.ScrapedItem` object, or any subclass
instance, and store the information in instance attributes.

.. _request-response:

Requests and Responses
======================

Scrapy uses :class:`~scrapy.http.Request` and :class:`~scrapy.http.Response`
objects for crawling web sites. 

Generally, :class:`~scrapy.http.Request` objects are generated in the
:ref:`Spiders <spiders>` (although they can be generated in any component of
the framework), then they pass across the system until they reach the
Downloader, which actually executes the request and returns a
:class:`~scrapy.http.Response` object to the :class:`Request's callback
function <scrapy.http.Request>`.

.. _spiders:

Spiders
=======

Spiders are user written classes which define how a certain site (or domain)
will be scraped; including how to crawl the site and how to scrape :ref:`Items
<items>` from their pages. 

All Spiders must be descendant of :class:`~scrapy.spider.BaseSpider` or any
subclass of it, in :ref:`ref-spiders` you can see a list of available Spiders
in Scrapy.

Scraping cycle
--------------

1. *Generating Requests*:
   
   The first step is to generate the initial :ref:`Requests
   <request-response>` to crawl the first URLs, and specify a callback
   function to be called with the :ref:`Response <request-response>`
   downloaded from those :ref:`Requests <request-response>`.

   The first :ref:`Requests <request-response>`. to perform are obtained by
   calling the :meth:`~scrapy.spider.BaseSpider.start_requests` method which
   (by default) generates :class:`~scrapy.http.Request` for the URLs specified
   in the :attr:`BaseSpider.start_urls` and the
   :meth:`~scrapy.spider.BaseSpider.parse` method as callback function for the
   :ref:`Requests <request-response>`..

2. *Parsing Responses*:
   
   In callback functions you parse the :ref:`Response <request-response>`
   contents and return an    iterable object containing :ref:`Items <items>`,
   :ref:`Requests <request-response>`, or both. 

   Typically you do the parsing by using :ref:`selectors`, but you could also
   use BeautifuSoup, lxml or the mechanism of your choice.

3. *The final step*:
  
   Returned :ref:`Requests <request-response>` (if any) will be downloaded by
   Scrapy and their :ref:`Responses <request-response>` handled to the
   specified callback, wich could be the same than the one specified in the
   first step.

   Returned :ref:`Items <items>`. (if any) will be directed to the :ref:`Item
   Pipeline <item-pipeline>`.

.. _selectors:

Selectors
=========

Selectors are the recommended tool to extract information from documents. They
retrieve information from the :ref:`Response <request-response>` body using
`XPath <http://www.w3.org/TR/xpath>`_, a language for finding information in a
XML document navigating trough its elements and attributes.

Scrapy defines a class :class:`~scrapy.xpath.XPathSelector`, that comes in two
flavours, :class:`~scrapy.xpath.HtmlXPatSelector` (for HTML) and
:class:`~scrapy.xpath.XmlXPathSelector` (for XML). In order to use them you
must instantiate the desired class with a :ref:`Response <request-response>`
object.

You can see selectors as objects that represents nodes in the document
structure. So, the first instantiated selectors are associated to the root
node, or the entire document.

.. _item-pipeline:

Item Pipeline
=============

After an :ref:`Item <items>` has been scraped by a :ref:`Spider <spiders>`, it
is sent to the Item Pipeline which allows us to perform some actions over the
:ref:`scrapped Items <items>`.

The Item Pipeline is a list of user written Python classes that define the
:meth:`process_item` method, which is called sequentially for every element.

The :meth:`process_item` must return the Item object on a successful action,
or raise a :exception:`DropItem` exception (ex: failing a validation test).
Dropped :ref:`Items <items>` are no longer processed by further pipeline
components.

Typical uses of the Item Pipeline include:

* Clean the HTML in Item attributes 
* Validate the Item
* Store the Item
