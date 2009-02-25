.. _tutorial:

===============
Scrapy Tutorial
===============

In this tutorial, we'll assume that Scrapy is already installed in your system,
if not see :ref:`intro-install`.

We are going to use `Open directory project (dmoz) <http://www.dmoz.org/>`_ as
our example domain to scrape.

This tutorial will introduce you to this tasks:

* Creating a project
* Defining the Items you will extract
* Writing a spider to crawl a site and extract Items
* Write an Item Pipeline to store the extracted Items

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

They define an initial set of URLs to download, and how to parse the downloaded contents in the search for data (Items) or more URLs to follow.

To create a Spider, you must subclass :class:`scrapy.spider.BaseSpider`, and
then define the three main, mandatory, attributes:

* :attr:`~scrapy.spider.BaseSpider.domain_name`: identifies the Spider. It must
  be unique, that is, you can't set the same domain name for different Spiders.

* :attr:`~scrapy.spider.BaseSpider.start_urls`: is a list of URLs where the
  Spider will begin to crawl from.  So, the first pages downloaded will be those
  listed here. The subsequent URLs will be generated successively from data
  contained in the start URLs.

* :meth:`~scrapy.spider.BaseSpider.parse` is the callback method of the spider.
  This means that each time a URL is retrieved, the downloaded data (Response)
  will be passed to this method.
 
  The :meth:`~scrapy.spider.BaseSpider.parse` method is in charge of processing
  the response and returning scraped data and or more URLs to follow, because of
  this, the method must always return a list or at least an empty one.

This is the code for our first Spider, save it in a file named
``dmoz_spider.py`` inside ``dmoz/spiders`` directory::

   from scrapy.spider import BaseSpider

   class DmozSpider(BaseSpider):
       domain_name = "dmoz.org"
       start_urls = [
           "http://www.dmoz.org/Computers/Programming/Languages/Python/Books/",
           "http://www.dmoz.org/Computers/Programming/Languages/Python/Resources/"
       ]
        
       def parse(self, response):
           filename = response.url.split("/")[-2]
           open(filename, 'w').write(response.body)
           return []
            
   SPIDER = DmozSpider()

.. warning::

   When creating spiders, be sure not to name them equal to the project's name
   or you won't be able to import modules from your project in your spider!

Crawling
--------

To put our spider to work, go to the project's top level directory and run::

   ./scrapy-ctl.py crawl dmoz.org

The ``crawl dmoz.org`` subcommand runs the spider for the ``dmoz.org`` domain, you'll get an output like this:: 

   [-] Log opened.
   [dmoz] INFO: Enabled extensions: TelnetConsole, WebConsole
   [dmoz] INFO: Enabled downloader middlewares: ErrorPagesMiddleware, CookiesMiddleware, HttpAuthMiddleware, UserAgentMiddleware, RetryMiddleware, CommonMiddleware, RedirectMiddleware, HttpCompressionMiddleware
   [dmoz] INFO: Enabled spider middlewares: OffsiteMiddleware, RefererMiddleware, UrlLengthMiddleware, DepthMiddleware, UrlFilterMiddleware
   [dmoz] INFO: Enabled item pipelines: 
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
have no referrers, and this condition is indicated at the end of the log line,
where it says ``from <None>``.

But more interesting, as our ``parse`` method instructs, two files have been
created: *Books* and *Resources*, with the content of both URLs.

What just happened under the hood?
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Scrapy creates :class:`scrapy.http.Request` objects for each URL in the
``start_urls`` attribute of the Spider, and assigns them the ``parse`` method of
the spider as their callback function.

These Requests are scheduled, then executed, and :class:`scrapy.http.Response`
objects are returned to the generator of the Requests.

Extracting Items
----------------

Introduction to Selectors
^^^^^^^^^^^^^^^^^^^^^^^^^

In order to extract information from web pages Scrapy adopted `XPath
<http://www.w3.org/TR/xpath>`_, a language for finding information in a XML
document navigating trough its elements and attributes.

Here are some examples of XPath queries and their corresponding results:

* ``/html/head/title``: Will give you the ``title`` node of the document.
* ``/html/head/title/text()``: Will give you the text inside the ``title`` node of the document.
* ``//td``: Will select all the ``td`` elements. 
* ``//div[@class="queryMe"]``: Will select all the ``div`` elements with ``class
  = queryMe``.

This are really simple examples of what you can do with XPath, we strongly
suggest you to follow this `XPath tutorial
<http://www.w3schools.com/XPath/default.asp>`_ before continuing.

Scrapy defines a class :class:`~scrapy.xpath.XPathSelector`, that comes in two
flavours, :class:`~scrapy.xpath.HtmlXPatSelector` (for HTML) and
:class:`~scrapy.xpath.XmlXPathSelector` (for XML). In order to use them you
must instantiate the desired class with a :ref:`Response <request-response>`
object.

You can see selectors as objects that represents nodes in the document
structure. So, the first instantiated selectors are associated to the root
node, or the entire document.

Selectors have three methods: ``x``, ``extract`` and ``re``.

* ``x``: returns a list of selectors, each of them representing the nodes
  gotten in the xpath expression given as parameter.
* ``extract``: actually extracts the data contained in the node. Does not
  receive parameters.
* ``re``: returns a list of results of a regular expression given as parameter.

Trying Selectors in the Shell
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

To illustrate the use of Selectors we're going to use the built-in shell of
Scrapy, notice that in order to use this feature you must have IPython (an
extended Python console) installed on your system.

To start a shell you must go to the project's top level directory and run::

   ./scrapy-ctl.py shell http://www.dmoz.org/Computers/Programming/Languages/Python/Books/

This is what the shell looks like::

   [-] Log opened.
   Scrapy 0.7.0 - Interactive scraping console

   [-] scrapy.management.web.WebConsole starting on 33227
   [-] scrapy.management.telnet.TelnetConsole starting on 42311
   Downloading URL...            Done.
   ------------------------------------------------------------------------------
   Available local variables:
      xxs: <class 'scrapy.xpath.selector.XmlXPathSelector'>
      url: http://www.dmoz.org/Computers/Programming/Languages/Python/Books/
      spider: <class 'dmoz.spiders.dmoz.OpenDirectorySpider'>
      hxs: <class 'scrapy.xpath.selector.HtmlXPathSelector'>
      item: <class 'scrapy.item.models.ScrapedItem'>
      response: <class 'scrapy.http.response.html.HtmlResponse'>
   Available commands:
      get <url>: Fetches an url and updates all variables.
      scrapehelp: Prints this help.
   ------------------------------------------------------------------------------
   Python 2.6.1 (r261:67515, Dec  7 2008, 08:27:41) 
   Type "copyright", "credits" or "license" for more information.

   IPython 0.9.1 -- An enhanced Interactive Python.
   ?         -> Introduction and overview of IPython's features.
   %quickref -> Quick reference.
   help      -> Python's own help system.
   object?   -> Details about 'object'. ?object also works, ?? prints more.

   In [1]: 

After the shell loads, it will put the result of the request action for the
given URL in a ``response`` variable, so if you enter ``response.body`` the
downloaded data will be printed on the screen.

The shell has also instantiated for two selectors with this respose as an
initialization parameter, so let's try them::

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

Actually extracting Items
^^^^^^^^^^^^^^^^^^^^^^^^^

Now, let's try to extract the sites information from the directory page.

If you do a ``response.body`` in the console, look at the source code of the
page or better yet use Firebug to inspect the page, you'll find that the sites
part of the code is an ``ul`` tag, in fact the *second* ``ul`` tag.

So we can select each ``li`` item belonging to the sites list with this code::

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

   ./scrapy-ctl.py crawl dmoz.org

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

Now doing a crawl on the dmoz.org domain yields DmozItems::

   [dmoz/dmoz.org] DEBUG: Scraped DmozItem({'title': [u'Text Processing in Python'], 'link': [u'http://gnosis.cx/TPiP/'], 'desc': [u' - By David Mertz; Addison Wesley. Book in progress, full text, ASCII format. Asks for feedback. [author website, Gnosis Software, Inc.]\n']}) in <http://www.dmoz.org/Computers/Programming/Languages/Python/Books/>
   [dmoz/dmoz.org] DEBUG: Scraped DmozItem({'title': [u'XML Processing with Python'], 'link': [u'http://www.informit.com/store/product.aspx?isbn=0130211192'], 'desc': [u' - By Sean McGrath; Prentice Hall PTR, 2000, ISBN 0130211192, has CD-ROM. Methods to build XML applications fast, Python tutorial, DOM and SAX, new Pyxie open source XML processing library. [Prentice Hall PTR]\n']}) in <http://www.dmoz.org/Computers/Programming/Languages/Python/Books/>


Item Pipeline
=============

After an item has been scraped by a Spider, it is sent to the Item Pipeline.

The Item Pipeline is a set of user written Python classes that implement a
simple method. They receive the Item, do an action upon it (like validating,
checking for duplicates, store the item), and then decide if the Item continues
trough the Pipeline or it's dropped.

In small projects like this we will use only one Item Pipeline that stores our
Items.

Like with the Item, a Pipeline placeholder has been set up for you in the
project creation step, it's in ``dmoz/pipelines.py`` and looks like this::

   # Define yours item pipelines here

   class DmozPipeline(object):
       def process_item(self, domain, item):
           return item

We have to override the ``process_item`` method in order to store our Items for
example in a csv file::

   import csv

   class DmozPipeline(object):
       def process_item(self, domain, item):
           item_writer = csv.writer(open('items.csv', 'a'))
           item_writer.writerow([item.title[0], item.link[0], item.desc[0]])
           return item

Finale
======
           
This covers the basics of Scrapy, but they're a lot of features that haven't
been mentioned. They'll be in further tutorials.
