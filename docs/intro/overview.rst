.. _intro-overview:

==================
Scrapy at a glance
==================

Scrapy a is an application framework for crawling web sites and extracting
structured data which can be used for a wide range of useful applications, like
data mining, information processing or historical archival.

Even though Scrapy was originally designed for `screen scraping`_ (more
precisely, `web scraping`_), it can also be used to extract data using APIs
(such as `Amazon Associates Web Services`_) or as a general purpose web
crawler.

.. _screen scraping: http://en.wikipedia.org/wiki/Screen_scraping
.. _web scraping: http://en.wikipedia.org/wiki/Web_scraping
.. _Amazon Associates Web Services: http://aws.amazon.com/associates/

The purpose of this document is to introduce you to the concepts behind Scrapy
so you can get an idea of how it works and decide if Scrapy is what you need. 

When you're ready to start a project, you can :ref:`start with the tutorial
<intro-tutorial>`.

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

    http://www.mininova.org/tor/2657665

.. _XPath: http://www.w3.org/TR/xpath
  
And look at the page HTML source to construct the XPath to select the data we
want to extract which is: torrent name, description and size.

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

.. _XPath reference: http://www.w3.org/TR/xpath

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


For brevity sake, we intentionally left out the import statements and the
Torrent class definition (which is included some paragraphs above).

Write a pipeline to store the items extracted
=============================================

Now let's write an :ref:`topics-item-pipeline` that serializes and stores the
extracted item into a file using `pickle`_::

    import pickle

    class StoreItemPipeline(object):
        def process_item(self, item, spider):
            torrent_id = item['url'].split('/')[-1]
            f = open("torrent-%s.pickle" % torrent_id, "w")
            pickle.dump(item, f)
            f.close()

.. _pickle: http://docs.python.org/library/pickle.html

What else?
==========

You've seen how to extract and store items from a website using Scrapy, but
this is just the surface. Scrapy provides a lot of powerful features for making
scraping easy and efficient, such as:

* Built-in support for :ref:`selecting and extracting <topics-selectors>` data
  from HTML and XML sources

* Built-in support for :ref:`exporting data <file-export-pipeline>` in multiple
  formats, including XML, CSV and JSON

* A media pipeline for :ref:`automatically downloading images <topics-images>`
  (or any other media) associated with the scraped items

* Support for :ref:`extending Scrapy <extending-scrapy>` by plugging
  your own functionality using middlewares, extensions, and pipelines

* Wide range of built-in middlewares and extensions for handling of
  compression, cache, cookies, authentication, user-agent spoofing, robots.txt
  handling, statistics, crawl depth restriction, etc

* An :ref:`Interactive scraping shell console <topics-shell>`, very useful for
  writing and debugging your spiders

* A builtin :ref:`Web service <topics-webservice>` for monitoring and
  controlling your bot

* A :ref:`Telnet console <topics-telnetconsole>` for full unrestricted access
  to a Python console inside your Scrapy process, to introspect and debug your
  crawler

* Built-in facilities for :ref:`logging <topics-logging>`, :ref:`collecting
  stats <topics-stats>`, and :ref:`sending email notifications <topics-email>`

What's next?
============

The next obvious steps are for you to `download Scrapy`_, read :ref:`the
tutorial <intro-tutorial>` and join `the community`_. Thanks for your
interest!

.. _download Scrapy: http://scrapy.org/download/
.. _the community: http://scrapy.org/community/
