.. _intro-tutorial:

===============
Scrapy Tutorial
===============

In this tutorial, we'll assume that Scrapy is already installed in your system.
If that's not the case see :ref:`intro-install`.

We are going to use `Open directory project (dmoz) <http://www.dmoz.org/>`_ as
our example domain to scrape.

This tutorial will walk you through through these tasks:

1. Creating a new Scrapy project
2. Defining the Items you will extract
3. Writing a :ref:`spider <topics-spiders>` to crawl a site and extract
   :ref:`Items <topics-items>`
4. Writing an :ref:`Item Pipeline <topics-item-pipeline>` to store the
   extracted Items

Creating a project
==================

Before start scraping, you will have set up a new Scrapy project. Enter a
directory where you'd like to store your code and then run::

   scrapy-admin.py startproject dmoz

This will create a ``dmoz`` directory with the following contents::

   dmoz/
       scrapy-ctl.py
       dmoz/
           __init__.py
           items.py
           pipelines.py
           settings.py
           spiders/
               __init__.py 
           templates/
               ... 

These are basically: 

* ``scrapy-ctl.py``: the project's control script.
* ``dmoz/``: the project's python module, you'll later import your code from
  here.
* ``dmoz/items.py``: the project's items file.
* ``dmoz/pipelines.py``: the project's pipelines file.
* ``dmoz/settings.py``: the project's settings file.
* ``dmoz/spiders/``: a directory where you'll later put your spiders.
* ``dmoz/templates/``: directory containing the spider's templates.

Defining our Item
=================

Items are placeholders for extracted data, they're represented by a simple
Python class: :class:`scrapy.item.ScrapedItem`, or any subclass of it.

In simple projects you won't need to worry about defining Items, because the
``startproject`` command has defined one for you in the ``items.py`` file, let's
see its contents::

    # Define here the models for your scraped items

    from scrapy.item import ScrapedItem

    class DmozItem(ScrapedItem):
        pass

Our first Spider
================

Spiders are user written classes to scrape information from a domain (or group
of domains). 

They define an initial list of URLs to download, how to follow links, and how
to parse the contents of those pages to extract :ref:`items <topics-items>`.

To create a Spider, you must subclass :class:`scrapy.spider.BaseSpider`, and
define the three main, mandatory, attributes:

* :attr:`~scrapy.spider.BaseSpider.domain_name`: identifies the Spider. It must
  be unique, that is, you can't set the same domain name for different Spiders.

* :attr:`~scrapy.spider.BaseSpider.start_urls`: is a list of URLs where the
  Spider will begin to crawl from.  So, the first pages downloaded will be those
  listed here. The subsequent URLs will be generated successively from data
  contained in the start URLs.

* :meth:`~scrapy.spider.BaseSpider.parse` is a method of the spider, which will
  be called with the downloaded :class:`~scrapy.http.Response` object of each
  start URL. The response is passed to the method as the first and only
  argument.
 
  This method is responsible for parsing the response data and extracting
  scraped data (as scraped items) and more URLs to follow.

  The :meth:`~scrapy.spider.BaseSpider.parse` method is in charge of processing
  the response and returning scraped data (as :class:`~scrapy.item.ScrapedItem`
  objects) and more URLs to follow (as :class:`~scrapy.http.Request` objects).

This is the code for our first Spider, save it in a file named
``dmoz_spider.py`` under the ``dmoz/spiders`` directory::

   from scrapy.spider import BaseSpider

   class DmozSpider(BaseSpider):
       domain_name = "dmoz.org"
       start_urls = [
           "http://www.dmoz.org/Computers/Programming/Languages/Python/Books/",
           "http://www.dmoz.org/Computers/Programming/Languages/Python/Resources/"
       ]
        
       def parse(self, response):
           filename = response.url.split("/")[-2]
           open(filename, 'wb').write(response.body)
           return []
            
   SPIDER = DmozSpider()

Crawling
--------

To put our spider to work, go to the project's top level directory and run::

   python scrapy-ctl.py crawl dmoz.org

The ``crawl dmoz.org`` subcommand runs the spider for the ``dmoz.org`` domain,
you'll get an output like this:: 

   [-] Log opened.
   [dmoz] INFO: Enabled extensions: ...
   [dmoz] INFO: Enabled scheduler middlewares: ...
   [dmoz] INFO: Enabled downloader middlewares: ...
   [dmoz] INFO: Enabled spider middlewares: ...
   [dmoz] INFO: Enabled item pipelines: ...
   [-] scrapy.management.web.WebConsole starting on 60738
   [-] scrapy.management.telnet.TelnetConsole starting on 51506
   [dmoz/dmoz.org] INFO: Domain opened
   [dmoz/dmoz.org] DEBUG: Crawled <http://www.dmoz.org/Computers/Programming/Languages/Python/Resources/> from <None>
   [dmoz/dmoz.org] DEBUG: Crawled <http://www.dmoz.org/Computers/Programming/Languages/Python/Books/> from <None>
   [dmoz/dmoz.org] INFO: Domain closed (finished)
   [scrapy.management.web.WebConsole] (Port 60738 Closed)
   [scrapy.management.telnet.TelnetConsole] (Port 51506 Closed)
   [-] Main loop terminated.

Pay attention to the lines labeled ``[dmoz/dmoz.org]``, which corresponds to
our spider identified by the domain "dmoz.org". You can see a log line for each
URL defined in ``start_urls``. Because these URLs are the starting ones, they
have no referrers, which is shown at the end of the log line, where it says
``from <None>``.

But more interesting, as our ``parse`` method instructs, two files have been
created: *Books* and *Resources*, with the content of both URLs.

What just happened under the hood?
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Scrapy creates :class:`scrapy.http.Request` objects for each URL in the
``start_urls`` attribute of the Spider, and assigns them the ``parse`` method of
the spider as their callback function.

These Requests are scheduled, then executed, and a :class:`scrapy.http.Response`
objects are returned and then fed to the spider, through the
:meth:`~scrapy.spider.BaseSpider.parse` method.

Extracting Items
----------------

Introduction to Selectors
^^^^^^^^^^^^^^^^^^^^^^^^^

There are several ways to extract data from web pages, Scrapy uses a mechanism
based on `XPath`_ expressions called :ref:`XPath selectors <topics-selectors>`.
For more information about selectors and other extraction mechanisms see the
:ref:`XPath selectors documentation <topics-selectors>`.

.. _XPath: http://www.w3.org/TR/xpath

Here are some examples of XPath expressions and their meanings:

* ``/html/head/title``: selects the ``<title>`` element, inside the ``<head>``
  element of a HTML document

* ``/html/head/title/text()``: selects the text inside the aforementioned
  ``<title>`` element.

* ``//td``: selects all the ``<td>`` elements

* ``//div[@class="mine"]``: selects all ``div`` elements which contain an
  attribute ``class="mine"``

These are just a couple of simple examples of what you can do with XPath, but
XPath expression are indeed much more powerful. To learn more about XPath we
recommend `this XPath tutorial <http://www.w3schools.com/XPath/default.asp>`_.

For working with XPaths, Scrapy provides a :class:`~scrapy.xpath.XPathSelector`
class, which comes in two flavours, :class:`~scrapy.xpath.HtmlXPatSelector`
(for HTML data) and :class:`~scrapy.xpath.XmlXPathSelector` (for XML data). In
order to use them you must instantiate the desired class with a
:class:`~scrapy.http.Response` object.

You can see selectors as objects that represents nodes in the document
structure. So, the first instantiated selectors are associated to the root
node, or the entire document.

Selectors have three methods (click on the method to see the complete API
documentation).

* :meth:`~scrapy.xpath.XPathSelector.x`: returns a list of selectors, each of
  them representing the nodes selected by the xpath expression given as
  argument. 

* :meth:`~scrapy.xpath.XPathSelector.extract`: returns a unicode string with
   the data selected by the XPath selector.

* :meth:`~scrapy.xpath.XPathSelector.re`: returns a list unicode strings
  extracted by applying the regular expression given as argument.


Trying Selectors in the Shell
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

To illustrate the use of Selectors we're going to use the built-in :ref:`Scrapy
shell <topics-shell>`, which also requires IPython (an extended Python console)
installed on your system.

To start a shell you must go to the project's top level directory and run::

   python scrapy-ctl.py shell http://www.dmoz.org/Computers/Programming/Languages/Python/Books/

This is what the shell looks like::

   [-] Log opened.
   Welcome to Scrapy shell!
   Fetching <http://www.dmoz.org/Computers/Programming/Languages/Python/Books/>...

   ------------------------------------------------------------------------------
   Available Scrapy variables:
      xxs: <class 'scrapy.xpath.selector.XmlXPathSelector'>
      url: http://www.dmoz.org/Computers/Programming/Languages/Python/Books/
      spider: <class 'dmoz.spiders.dmoz.OpenDirectorySpider'>
      hxs: <class 'scrapy.xpath.selector.HtmlXPathSelector'>
      item: <class 'scrapy.item.models.ScrapedItem'>
      response: <class 'scrapy.http.response.html.HtmlResponse'>
   Available commands:
      get [url]: Fetch a new URL or re-fetch current Request
      shelp: Prints this help.
   ------------------------------------------------------------------------------
   Python 2.6.1 (r261:67515, Dec  7 2008, 08:27:41) 
   Type "copyright", "credits" or "license" for more information.

   IPython 0.9.1 -- An enhanced Interactive Python.
   ?         -> Introduction and overview of IPython's features.
   %quickref -> Quick reference.
   help      -> Python's own help system.
   object?   -> Details about 'object'. ?object also works, ?? prints more.

   In [1]: 

After the shell loads, you will have the response fetched in a local
``response`` variable, so if you type ``response.body`` you will see the body
of the response, or you can ``response.headers`` to see its headers.

The shell also instantiates two selectors, one for HTML (in the ``hxs``
variable) and one for XML (in the ``xxs`` variable)with this response. So let's
try them::

   In [1]: hxs.x('/html/head/title')
   Out[1]: [<HtmlXPathSelector (title) xpath=/html/head/title>]

   In [2]: hxs.x('/html/head/title').extract()
   Out[2]: [u'<title>Open Directory - Computers: Programming: Languages: Python: Books</title>']

   In [3]: hxs.x('/html/head/title/text()')
   Out[3]: [<HtmlXPathSelector (text) xpath=/html/head/title/text()>]

   In [4]: hxs.x('/html/head/title/text()').extract()
   Out[4]: [u'Open Directory - Computers: Programming: Languages: Python: Books']

   In [5]: hxs.x('/html/head/title/text()').re('(\w+):')
   Out[5]: [u'Computers', u'Programming', u'Languages', u'Python']

Extracting the data
^^^^^^^^^^^^^^^^^^^

Now, let's try to extract some real information from those pages. 

You could type ``response.body`` in the console, and inspect the source code to
figure out the XPaths you need to use. However, inspecting the raw HTML code
there could become a very tedious task. To make this an easier task, you can
use some Firefox extensions like Firebug. For more information see
:ref:`topics-firebug` and :ref:`topics-firefox`.

After inspecting the page source you'll find that the web sites information
is inside a ``<ul>`` element, in fact the *second* ``<ul>`` element.

So we can select each ``<li>`` element belonging to the sites list with this
code::

   hxs.x('//ul[2]/li')

And from them, the sites descriptions::

   hxs.x('//ul[2]/li/text()').extract()

The sites titles::

   hxs.x('//ul[2]/li/a/text()').extract()

And the sites links::

   hxs.x('//ul[2]/li/a/@href').extract()

As we said before, each ``x()`` call returns a list of selectors, so we can
concatenate further ``x()`` calls to dig deeper into a node. We are going to use
that property here, so::

   sites = hxs.x('//ul[2]/li')
   for site in sites:
       title = site.x('a/text()').extract()
       link = site.x('a/@href').extract()
       desc = site.x('text()').extract()
       print title, link, desc

Let's add this code to our spider::

   from scrapy.spider import BaseSpider
   from scrapy.xpath.selector import HtmlXPathSelector

   class DmozSpider(BaseSpider):
      domain_name = "dmoz.org"
      start_urls = [
          "http://www.dmoz.org/Computers/Programming/Languages/Python/Books/",
          "http://www.dmoz.org/Computers/Programming/Languages/Python/Resources/"
      ]
       
      def parse(self, response):
          hxs = HtmlXPathSelector(response)
          sites = hxs.x('//ul[2]/li')
          for site in sites:
              title = site.x('a/text()').extract()
              link = site.x('a/@href').extract()
              desc = site.x('text()').extract()
              print title, link, desc
          return []
           
   SPIDER = DmozSpider()

Now try crawling the dmoz.org domain again and you'll see sites being printed
in your output, run::

   python scrapy-ctl.py crawl dmoz.org

Spiders are supposed to return their scraped data in the form of ScrapedItems,
so to actually return the data we've scraped so far, the code for our Spider
should be like this::

   from scrapy.spider import BaseSpider
   from scrapy.xpath.selector import HtmlXPathSelector

   from dmoz.items import DmozItem

   class DmozSpider(BaseSpider):
      domain_name = "dmoz.org"
      start_urls = [
          "http://www.dmoz.org/Computers/Programming/Languages/Python/Books/",
          "http://www.dmoz.org/Computers/Programming/Languages/Python/Resources/"
      ]
       
      def parse(self, response):
          hxs = HtmlXPathSelector(response)
          sites = hxs.x('//ul[2]/li')
          items = []
          for site in sites:
              item = DmozItem()
              item.title = site.x('a/text()').extract()
              item.link = site.x('a/@href').extract()
              item.desc = site.x('text()').extract()
              items.append(item)
          return items
           
   SPIDER = DmozSpider()

Now doing a crawl on the dmoz.org domain yields ``DmozItem``'s::

   [dmoz/dmoz.org] INFO: Scraped DmozItem({'title': [u'Text Processing in Python'], 'link': [u'http://gnosis.cx/TPiP/'], 'desc': [u' - By David Mertz; Addison Wesley. Book in progress, full text, ASCII format. Asks for feedback. [author website, Gnosis Software, Inc.]\n']}) in <http://www.dmoz.org/Computers/Programming/Languages/Python/Books/>
   [dmoz/dmoz.org] INFO: Scraped DmozItem({'title': [u'XML Processing with Python'], 'link': [u'http://www.informit.com/store/product.aspx?isbn=0130211192'], 'desc': [u' - By Sean McGrath; Prentice Hall PTR, 2000, ISBN 0130211192, has CD-ROM. Methods to build XML applications fast, Python tutorial, DOM and SAX, new Pyxie open source XML processing library. [Prentice Hall PTR]\n']}) in <http://www.dmoz.org/Computers/Programming/Languages/Python/Books/>


Storing the data (using an Item Pipeline)
=========================================

After an item has been scraped by a Spider, it is sent to the :ref:`Item
Pipeline <topics-item-pipeline>`.

The Item Pipeline is a group of user written Python classes that implement a
simple method. They receive an Item and perform an action over it (for example:
validation, checking for duplicates, or storing it in a database), and then
decide if the Item continues through the Pipeline or it's dropped and no longer
processed.

In small projects (like the one on this tutorial) we will use only one Item
Pipeline that just stores our Items.

As with Items, a Pipeline placeholder has been set up for you in the project
creation step, it's in ``dmoz/pipelines.py`` and looks like this::

   # Define your item pipelines here

   class DmozPipeline(object):
       def process_item(self, domain, item):
           return item

We have to override the ``process_item`` method in order to store our Items
somewhere. 

Here's a simple pipeline for storing the scraped items into a CSV (comma
separated values) file using the standard library `csv module`_::

   import csv

   class CsvWriterPipeline(object):

       def __init__(self):
           self.csvwriter = csv.writer(open('items.csv', 'wb'))
        
       def process_item(self, domain, item):
           self.csvwriter.writerow([item.title[0], item.link[0], item.desc[0]])
           return item

.. _csv module: http://docs.python.org/library/csv.html


Don't forget to enable the pipeline by adding it to the
:setting:`ITEM_PIPELINES` setting in your settings.py, like this::

    ITEM_PIPELINES = ['dmoz.pipelines.CsvWriterPipeline']

Finale
======
           
This tutorial covers only the basics of Scrapy, but there's a lot of other
features not mentioned here. We recommend you continue reading the section
:ref:`topics-index`.
