.. _intro-overview:

==================
Scrapy at a glance
==================

Scrapy a is an application framework for crawling web sites and extracting
structured data which can be used for a wide range of useful applications, like
data mining, information processing or historical archival.

Even though Scrapy was originally designed for `screen scraping`_, it can also
be used to extract data using APIs (such as `Amazon Associates Web Services`_)
or as a general purpose web crawler.

.. _screen scraping: http://en.wikipedia.org/wiki/Screen_scraping
.. _Amazon Associates Web Services: http://aws.amazon.com/associates/

The purpose of this document is to introduce you to the concepts behind Scrapy
so you can get an idea of how it works and decide if Scrapy is what you need. 

When you're ready to start a project, you can :ref:`start with the tutorial
<intro-tutorial1>`. For more detailed information you can take a look at the
:ref:`documentation contents <index>`.

Pick a website
==============

So you need to extract some information from a website, but the website doesn't
provide any API or mechanism to access that info from a computer program.
Scrapy can help you extract that information. Let's say we want to extract
information about all torrent files added today in the `mininova`_ torrent
site.

.. _mininova: http://www.mininova.org

The list of all torrents added today can be found in this page:

    http://www.mininova.org/today
    
Define the Item
===============

First of all we need to define a class for the items we're going to extract, so
let's define a Torrent class, which must inherit from ScrapedItem::

    from scrapy.item import ScrapedItem

    class Torrent(ScrapedItem):
        pass

Write a Spider to extract the Items
===================================

Now we'll write a Spider which defines the start URL
(http://www.mininova.org/today), the rules for following links and the rules
for extracting the data from pages.

If we take a look at that page content we'll see that all torrent URLs are like
http://www.mininova.org/tor/NUMBER where ``NUMBER`` is an integer. We'll use
that to construct the regular expression for the links to follow: ``/tor/\d+``.

For extracting data we'll use `XPath`_ to select the part of the document where
the data is to be extracted. Let's take one of those torrent pages:

    http://www.mininova.org/tor/2004522

.. _XPath: http://www.w3.org/TR/xpath
  
And look at the page HTML source to construct the XPath to select the data we
want to extract which is: torrent name, description and size.

.. highlight:: html

By looking at the page HTML source we can see that the file name is contained
inside a ``<h1>`` tag::

    <h1>The Dark Knight[2008]DvDrip-aXXo</h1>

.. highlight:: none

An XPath expression to extract the name could be::

    //h1/text()

.. highlight:: html

And the description is contained inside a ``<div>`` tag with ``id="description"``::

    <h2>Description:</h2>

    <div id="description">
    &gt;  F i L E   i N F O <br />
    &gt;<br />
    &gt;  TiTLE......[ The Dark Knight<br />
    &gt;  AKA........[ Batman Begins 2<br />

    ...

.. highlight:: none

An XPath expression to select the description could be::

    //div[@id='description']

.. highlight:: html

Finally, the file size is contained in the second ``<p>`` tag inside the ``<div>``
tag with ``id=info-left``::

   <div id="info-left">

   <p>
   <strong>Category:</strong>
   <a href="/cat/4">Movies</a> &gt; <a href="/sub/1">Action</a>
   </p>

   <p>
   <strong>Total size:</strong>
   801.44&nbsp;megabyte</p>

.. highlight:: none

An XPath expression to select the description could be::

   //div[@id='info-left']/p[2]/text()[2]

.. highlight:: python

For more information about XPath see the `XPath reference`_.

.. _XPath reference: http://www.w3.org/TR/xpath

Finally, here's the spider code::

    class MininovaSpider(CrawlSpider):

        domain_name = 'mininova.org'
        start_urls = ['http://www.mininova.org/today']
        rules = [Rule(RegexLinkExtractor(allow=['/tor/\d+']), 'parse_torrent')]
        
        def parse_torrent(self, response):
            x = HtmlXPathSelector(response)
            torrent = Torrent()
        
            torrent.url = response.url
            torrent.name = x.x("//h1/text()").extract()
            torrent.description = x.x("//div[@id='description']").extract()
            torrent.size = x.x("//div[@id='info-left']/p[2]/text()[2]").extract()
            return [torrent]


For brevity sake, we intentionally left out the import statements and the
Torrent class definition (which is included some paragraphs above).

Write a pipeline to store the items extracted
=============================================

Now let's write an :ref:`topics-item-pipeline` that serializes and stores the
extracted item into a file using `pickle`_::

    import pickle

    class StoreItemPipeline(object):
        def process_item(self, domain, response, item):
            torrent_id = item.url.split('/')[-1]
            f = open("/tmp/torrent-%s" % torrent_id, "w")
            pickle.dump(item, f)
            f.close()

.. _pickle: http://docs.python.org/library/pickle.html

What else?
==========

You've seen how to extract and store items from a website using Scrapy, but
this is just the surface. Scrapy provides a lot of powerful features for making
scraping easy and efficient, such as:

* Built-in support for parsing HTML, XML, CSV, and Javascript 

* A media pipeline for scraping items with images (or any other media) and
  download the image files as well

* Support for extending Scrapy by plugging your own functionality using
  middlewares, extensions, and pipelines

* Wide range of built-in middlewares and extensions for handling of
  compression, cache, cookies, authentication, user-agent spoofing, robots.txt
  handling, statistics, crawl depth restriction, etc

* Interactive scraping shell console, very useful for developing and debugging

* Web management console for monitoring and controlling your bot

* Telnet console for low-level access to the Scrapy process

What's next?
============

The next obvious steps are for you to `download Scrapy`_, read :ref:`the
tutorial <intro-tutorial1>` and join `the community`_. Thanks for your
interest!

.. _download Scrapy: http://scrapy.org/download/
.. _the community: http://scrapy.org/community/
