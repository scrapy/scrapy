============
Introduction
============

.. architecture:

Overview
========

.. image:: _images/scrapy_architecture.png
   :width: 700
   :height: 468
   :alt: Scrapy architecture

.. _items:

Items
-----

In Scrapy, Items are the placeholder to use for the scraped data. They are
represented by a :class:`~scrapy.item.ScrapedItem` object, or any subclass
instance, and store the information in instance attributes.

.. _request-response:

Requests and Responses
----------------------

Scrapy uses :class:`~scrapy.http.Request` and :class:`~scrapy.http.Response`
objects for crawling web sites. 

Generally, :class:`~scrapy.http.Request` objects are generated in the
:ref:`Spiders <spiders>` (although they can be generated in any component of
the framework), then they pass across the system until they reach the
Downloader, which actually executes the request and returns a
:class:`~scrapy.http.Response` object to the :class:`Request's callback
function <scrapy.http.Request>`.

.. _overview-spiders:

Spiders
-------

Spiders are user written classes which define how a certain site (or domain)
will be scraped; including how to crawl the site and how to scrape :ref:`Items
<items>` from their pages. 

All Spiders must be descendant of :class:`~scrapy.spider.BaseSpider` or any
subclass of it, in :ref:`ref-spiders` you can see a list of available Spiders
in Scrapy.
.. _selectors:

Selectors
---------

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
-------------

After an :ref:`Item <items>` has been scraped by a :ref:`Spider <spiders>`, it
is sent to the Item Pipeline which allows us to perform some actions over the
:ref:`scrapped Items <items>`.

The Item Pipeline is a list of user written Python classes that implement a
specific method , which is called sequentially for every element of the
Pipeline.

Each element receives the Scraped Item, do an action upon it (like validating,
checking for duplicates, store the item), and then decide if the Item
continues trough the Pipeline or the item is dropped.
