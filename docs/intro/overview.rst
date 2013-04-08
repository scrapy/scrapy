.. _intro-overview:

==================
Scrapy at a glance
==================

Scrapy is an application framework for crawling web sites and extracting
structured data which can be used for a wide range of useful applications, like
data mining, information processing or historical archival.

Even though Scrapy was originally designed for `screen scraping`_ (more
precisely, `web scraping`_), it can also be used to extract data using APIs
(such as `Amazon Associates Web Services`_) or as a general purpose web
crawler.

The purpose of this document is to introduce you to the concepts behind Scrapy
so you can get an idea of how it works and decide if Scrapy is what you need. 

When you're ready to start a project, you can :ref:`start with the tutorial
<intro-tutorial>`.

Pick a website
==============

So you need to extract some information from a website, but the website doesn't
provide any API or mechanism to access that info programmatically.  Scrapy can
help you extract that information.

Let's say we want to extract the URL, name, description and size of all torrent
files added today in the `Mininova`_ site.

The list of all torrents added today can be found on this page:

    http://www.mininova.org/today
    
.. _intro-overview-item:

Define the data you want to scrape
==================================

The first thing is to define the data we want to scrape. In Scrapy, this is
done through :ref:`Scrapy Items <topics-items>` (Torrent files, in this case).

This would be our Item::

    from scrapy.item import Item, Field

    class TorrentItem(Item):
        url = Field()
        name = Field()
        description = Field()
        size = Field()

Write a Spider to extract the data
==================================

The next thing is to write a Spider which defines the start URL
(http://www.mininova.org/today), the rules for following links and the rules
for extracting the data from pages.

If we take a look at that page content we'll see that all torrent URLs are like
http://www.mininova.org/tor/NUMBER where ``NUMBER`` is an integer. We'll use
that to construct the regular expression for the links to follow: ``/tor/\d+``.

We'll use `XPath`_ for selecting the data to extract from the web page HTML
source. Let's take one of those torrent pages:

    http://www.mininova.org/tor/2657665

And look at the page HTML source to construct the XPath to select the data we
want which is: torrent name, description and size.

.. highlight:: html

By looking at the page HTML source we can see that the file name is contained
inside a ``<h1>`` tag::

   <h1>Home[2009][Eng]XviD-ovd</h1>

.. highlight:: none

An XPath expression to extract the name could be::

    //h1/text()

.. highlight:: html

And the description is contained inside a ``<div>`` tag with ``id="description"``::

   <h2>Description:</h2>

   <div id="description">
   "HOME" - a documentary film by Yann Arthus-Bertrand
   <br/>
   <br/>
   ***
   <br/>
   <br/>
   "We are living in exceptional times. Scientists tell us that we have 10 years to change the way we live, avert the depletion of natural resources and the catastrophic evolution of the Earth's climate.

   ...

.. highlight:: none

An XPath expression to select the description could be::

    //div[@id='description']

.. highlight:: html

Finally, the file size is contained in the second ``<p>`` tag inside the ``<div>``
tag with ``id=specifications``::

   <div id="specifications">

   <p>
   <strong>Category:</strong>
   <a href="/cat/4">Movies</a> &gt; <a href="/sub/35">Documentary</a>
   </p>

   <p>
   <strong>Total size:</strong>
   699.79&nbsp;megabyte</p>


.. highlight:: none

An XPath expression to select the description could be::

   //div[@id='specifications']/p[2]/text()[2]

.. highlight:: python

For more information about XPath see the `XPath reference`_.

Finally, here's the spider code::

    class MininovaSpider(CrawlSpider):

        name = 'mininova.org'
        allowed_domains = ['mininova.org']
        start_urls = ['http://www.mininova.org/today']
        rules = [Rule(SgmlLinkExtractor(allow=['/tor/\d+']), 'parse_torrent')]
        
        def parse_torrent(self, response):
            x = HtmlXPathSelector(response)

            torrent = TorrentItem()
            torrent['url'] = response.url
            torrent['name'] = x.select("//h1/text()").extract()
            torrent['description'] = x.select("//div[@id='description']").extract()
            torrent['size'] = x.select("//div[@id='info-left']/p[2]/text()[2]").extract()
            return torrent

For brevity's sake, we intentionally left out the import statements. The
Torrent item is :ref:`defined above <intro-overview-item>`.

Run the spider to extract the data
==================================

Finally, we'll run the spider to crawl the site an output file
``scraped_data.json`` with the scraped data in JSON format::

    scrapy crawl mininova.org -o scraped_data.json -t json

This uses :ref:`feed exports <topics-feed-exports>` to generate the JSON file.
You can easily change the export format (XML or CSV, for example) or the
storage backend (FTP or `Amazon S3`_, for example).

You can also write an :ref:`item pipeline <topics-item-pipeline>` to store the
items in a database very easily.

Review scraped data
===================

If you check the ``scraped_data.json`` file after the process finishes, you'll
see the scraped items there::

    [{"url": "http://www.mininova.org/tor/2657665", "name": ["Home[2009][Eng]XviD-ovd"], "description": ["HOME - a documentary film by ..."], "size": ["699.69 megabyte"]},
    # ... other items ...
    ]

You'll notice that all field values (except for the ``url`` which was assigned
directly) are actually lists. This is because the :ref:`selectors
<topics-selectors>` return lists. You may want to store single values, or
perform some additional parsing/cleansing to the values. That's what
:ref:`Item Loaders <topics-loaders>` are for.

.. _topics-whatelse:

What else?
==========

You've seen how to extract and store items from a website using Scrapy, but
this is just the surface. Scrapy provides a lot of powerful features for making
scraping easy and efficient, such as:

* Built-in support for :ref:`selecting and extracting <topics-selectors>` data
  from HTML and XML sources

* Built-in support for cleaning and sanitizing the scraped data using a
  collection of reusable filters (called :ref:`Item Loaders <topics-loaders>`)
  shared between all the spiders.

* Built-in support for :ref:`generating feed exports <topics-feed-exports>` in
  multiple formats (JSON, CSV, XML) and storing them in multiple backends (FTP,
  S3, local filesystem)

* A media pipeline for :ref:`automatically downloading images <topics-images>`
  (or any other media) associated with the scraped items

* Support for :ref:`extending Scrapy <extending-scrapy>` by plugging
  your own functionality using :ref:`signals <topics-signals>` and a
  well-defined API (middlewares, :ref:`extensions <topics-extensions>`, and
  :ref:`pipelines <topics-item-pipeline>`).

* Wide range of built-in middlewares and extensions for:

  * cookies and session handling
  * HTTP compression
  * HTTP authentication
  * HTTP cache
  * user-agent spoofing
  * robots.txt
  * crawl depth restriction
  * and more

* Robust encoding support and auto-detection, for dealing with foreign,
  non-standard and broken encoding declarations.

* Support for creating spiders based on pre-defined templates, to speed up
  spider creation and make their code more consistent on large projects. See
  :command:`genspider` command for more details.

* Extensible :ref:`stats collection <topics-stats>` for multiple spider
  metrics, useful for monitoring the performance of your spiders and detecting
  when they get broken

* An :ref:`Interactive shell console <topics-shell>` for trying XPaths, very
  useful for writing and debugging your spiders

* A :ref:`System service <topics-scrapyd>` designed to ease the deployment and
  run of your spiders in production.

* A built-in :ref:`Web service <topics-webservice>` for monitoring and
  controlling your bot

* A :ref:`Telnet console <topics-telnetconsole>` for hooking into a Python
  console running inside your Scrapy process, to introspect and debug your
  crawler

* :ref:`Logging <topics-logging>` facility that you can hook on to for catching
  errors during the scraping process.

* Support for crawling based on URLs discovered through `Sitemaps`_

* A caching DNS resolver

What's next?
============

The next obvious steps are for you to `download Scrapy`_, read :ref:`the
tutorial <intro-tutorial>` and join `the community`_. Thanks for your
interest!

.. _download Scrapy: http://scrapy.org/download/
.. _the community: http://scrapy.org/community/
.. _screen scraping: http://en.wikipedia.org/wiki/Screen_scraping
.. _web scraping: http://en.wikipedia.org/wiki/Web_scraping
.. _Amazon Associates Web Services: http://aws.amazon.com/associates/
.. _Mininova: http://www.mininova.org
.. _XPath: http://www.w3.org/TR/xpath
.. _XPath reference: http://www.w3.org/TR/xpath
.. _Amazon S3: http://aws.amazon.com/s3/
.. _Sitemaps: http://www.sitemaps.org
