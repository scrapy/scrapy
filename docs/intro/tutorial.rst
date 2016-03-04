.. _intro-tutorial:

===============
Scrapy Tutorial
===============

In this tutorial, we'll assume that Scrapy is already installed on your system.
If that's not the case, see :ref:`intro-install`.

We are going to use `Open directory project (dmoz) <https://www.dmoz.org/>`_ as
our example domain to scrape.

This tutorial will walk you through these tasks:

1. Creating a new Scrapy project
2. Defining the Items you will extract
3. Writing a :ref:`spider <topics-spiders>` to crawl a site and extract
   :ref:`Items <topics-items>`
4. Writing an :ref:`Item Pipeline <topics-item-pipeline>` to store the
   extracted Items

Scrapy is written in Python_. If you're new to the language you might want to
start by getting an idea of what the language is like, to get the most out of
Scrapy.  If you're already familiar with other languages, and want to learn
Python quickly, we recommend `Learn Python The Hard Way`_.  If you're new to programming
and want to start with Python, take a look at `this list of Python resources
for non-programmers`_.

.. _Python: https://www.python.org/
.. _this list of Python resources for non-programmers: https://wiki.python.org/moin/BeginnersGuide/NonProgrammers
.. _Learn Python The Hard Way: http://learnpythonthehardway.org/book/

Creating a project
==================

Before you start scraping, you will have to set up a new Scrapy project. Enter a
directory where you'd like to store your code and run::

    scrapy startproject tutorial

This will create a ``tutorial`` directory with the following contents::

    tutorial/
        scrapy.cfg            # deploy configuration file

        tutorial/             # project's Python module, you'll import your code from here
            __init__.py

            items.py          # project items file

            pipelines.py      # project pipelines file

            settings.py       # project settings file

            spiders/          # a directory where you'll later put your spiders
                __init__.py
                ...


Defining our Item
=================

`Items` are containers that will be loaded with the scraped data; they work
like simple Python dicts. While you can use plain Python dicts with Scrapy,
`Items` provide additional protection against populating undeclared fields,
preventing typos. They can also be used with :ref:`Item Loaders
<topics-loaders>`, a mechanism with helpers to conveniently populate `Items`.

They are declared by creating a :class:`scrapy.Item <scrapy.item.Item>` class and defining
its attributes as :class:`scrapy.Field <scrapy.item.Field>` objects, much like in an ORM
(don't worry if you're not familiar with ORMs, you will see that this is an
easy task).

We begin by modeling the item that we will use to hold the site's data obtained
from dmoz.org. As we want to capture the name, url and description of the
sites, we define fields for each of these three attributes. To do that, we edit
``items.py``, found in the ``tutorial`` directory. Our Item class looks like this::

    import scrapy

    class DmozItem(scrapy.Item):
        title = scrapy.Field()
        link = scrapy.Field()
        desc = scrapy.Field()

This may seem complicated at first, but defining an item class allows you to use other handy
components and helpers within Scrapy.

Our first Spider
================

Spiders are classes that you define and Scrapy uses to scrape information from a
domain (or group of domains).

They define an initial list of URLs to download, how to follow links, and how
to parse the contents of pages to extract :ref:`items <topics-items>`.

To create a Spider, you must subclass :class:`scrapy.Spider
<scrapy.spiders.Spider>` and define some attributes:

* :attr:`~scrapy.spiders.Spider.name`: identifies the Spider. It must be
  unique, that is, you can't set the same name for different Spiders.

* :attr:`~scrapy.spiders.Spider.start_urls`: a list of URLs where the
  Spider will begin to crawl from.  The first pages downloaded will be those
  listed here. The subsequent URLs will be generated successively from data
  contained in the start URLs.

* :meth:`~scrapy.spiders.Spider.parse`: a method of the spider, which will
  be called with the downloaded :class:`~scrapy.http.Response` object of each
  start URL. The response is passed to the method as the first and only
  argument.

  This method is responsible for parsing the response data and extracting
  scraped data (as scraped items) and more URLs to follow.

  The :meth:`~scrapy.spiders.Spider.parse` method is in charge of processing
  the response and returning scraped data (as :class:`~scrapy.item.Item`
  objects) and more URLs to follow (as :class:`~scrapy.http.Request` objects).

This is the code for our first Spider; save it in a file named
``dmoz_spider.py`` under the ``tutorial/spiders`` directory::

    import scrapy

    class DmozSpider(scrapy.Spider):
        name = "dmoz"
        allowed_domains = ["dmoz.org"]
        start_urls = [
            "http://www.dmoz.org/Computers/Programming/Languages/Python/Books/",
            "http://www.dmoz.org/Computers/Programming/Languages/Python/Resources/"
        ]

        def parse(self, response):
            filename = response.url.split("/")[-2] + '.html'
            with open(filename, 'wb') as f:
                f.write(response.body)

Crawling
--------

To put our spider to work, go to the project's top level directory and run::

   scrapy crawl dmoz

This command runs the spider with name ``dmoz`` that we've just added, that
will send some requests for the ``dmoz.org`` domain. You will get an output
similar to this::

    2014-01-23 18:13:07-0400 [scrapy] INFO: Scrapy started (bot: tutorial)
    2014-01-23 18:13:07-0400 [scrapy] INFO: Optional features available: ...
    2014-01-23 18:13:07-0400 [scrapy] INFO: Overridden settings: {}
    2014-01-23 18:13:07-0400 [scrapy] INFO: Enabled extensions: ...
    2014-01-23 18:13:07-0400 [scrapy] INFO: Enabled downloader middlewares: ...
    2014-01-23 18:13:07-0400 [scrapy] INFO: Enabled spider middlewares: ...
    2014-01-23 18:13:07-0400 [scrapy] INFO: Enabled item pipelines: ...
    2014-01-23 18:13:07-0400 [scrapy] INFO: Spider opened
    2014-01-23 18:13:08-0400 [scrapy] DEBUG: Crawled (200) <GET http://www.dmoz.org/Computers/Programming/Languages/Python/Resources/> (referer: None)
    2014-01-23 18:13:09-0400 [scrapy] DEBUG: Crawled (200) <GET http://www.dmoz.org/Computers/Programming/Languages/Python/Books/> (referer: None)
    2014-01-23 18:13:09-0400 [scrapy] INFO: Closing spider (finished)


.. note::
    At the end you can see a log line for each URL defined in ``start_urls``.
    Because these URLs are the starting ones, they have no referrers, which is
    shown at the end of the log line, where it says ``(referer: None)``.

Now, check the files in the current directory. You should notice two new files
have been created: *Books.html* and *Resources.html*, with the content for the respective
URLs, as our ``parse`` method instructs.

What just happened under the hood?
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Scrapy creates :class:`scrapy.Request <scrapy.http.Request>` objects
for each URL in the ``start_urls`` attribute of the Spider, and assigns
them the ``parse`` method of the spider as their callback function.

These Requests are scheduled, then executed, and :class:`scrapy.http.Response`
objects are returned and then fed back to the spider, through the
:meth:`~scrapy.spiders.Spider.parse` method.

Extracting Items
----------------

Introduction to Selectors
^^^^^^^^^^^^^^^^^^^^^^^^^

There are several ways to extract data from web pages. Scrapy uses a mechanism
based on `XPath`_ or `CSS`_ expressions called :ref:`Scrapy Selectors
<topics-selectors>`.  For more information about selectors and other extraction
mechanisms see the :ref:`Selectors documentation <topics-selectors>`.

.. _XPath: https://www.w3.org/TR/xpath
.. _CSS: https://www.w3.org/TR/selectors

Here are some examples of XPath expressions and their meanings:

* ``/html/head/title``: selects the ``<title>`` element, inside the ``<head>``
  element of an HTML document

* ``/html/head/title/text()``: selects the text inside the aforementioned
  ``<title>`` element.

* ``//td``: selects all the ``<td>`` elements

* ``//div[@class="mine"]``: selects all ``div`` elements which contain an
  attribute ``class="mine"``

These are just a couple of simple examples of what you can do with XPath, but
XPath expressions are indeed much more powerful. To learn more about XPath, we
recommend `this tutorial to learn XPath through examples
<http://zvon.org/comp/r/tut-XPath_1.html>`_, and `this tutorial to learn "how
to think in XPath" <http://plasmasturm.org/log/xpath101/>`_.

.. note:: **CSS vs XPath:** you can go a long way extracting data from web pages
  using only CSS selectors. However, XPath offers more power because besides
  navigating the structure, it can also look at the content: you're
  able to select things like: *the link that contains the text 'Next Page'*.
  Because of this, we encourage you to learn about XPath even if you
  already know how to construct CSS selectors.

For working with CSS and XPath expressions, Scrapy provides
:class:`~scrapy.selector.Selector` class and convenient shortcuts to avoid
instantiating selectors yourself every time you need to select something from a
response.

You can see selectors as objects that represent nodes in the document
structure. So, the first instantiated selectors are associated with the root
node, or the entire document.

Selectors have four basic methods (click on the method to see the complete API
documentation):

* :meth:`~scrapy.selector.Selector.xpath`: returns a list of selectors, each of
  which represents the nodes selected by the xpath expression given as
  argument.

* :meth:`~scrapy.selector.Selector.css`: returns a list of selectors, each of
  which represents the nodes selected by the CSS expression given as argument.

* :meth:`~scrapy.selector.Selector.extract`: returns a unicode string with the
  selected data.

* :meth:`~scrapy.selector.Selector.re`: returns a list of unicode strings
  extracted by applying the regular expression given as argument.


Trying Selectors in the Shell
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

To illustrate the use of Selectors we're going to use the built-in :ref:`Scrapy
shell <topics-shell>`, which also requires `IPython <http://ipython.org/>`_ (an extended Python console)
installed on your system.

To start a shell, you must go to the project's top level directory and run::

    scrapy shell "http://www.dmoz.org/Computers/Programming/Languages/Python/Books/"

.. note::

   Remember to always enclose urls in quotes when running Scrapy shell from
   command-line, otherwise urls containing arguments (ie. ``&`` character)
   will not work.

This is what the shell looks like::

    [ ... Scrapy log here ... ]

    2014-01-23 17:11:42-0400 [scrapy] DEBUG: Crawled (200) <GET http://www.dmoz.org/Computers/Programming/Languages/Python/Books/> (referer: None)
    [s] Available Scrapy objects:
    [s]   crawler    <scrapy.crawler.Crawler object at 0x3636b50>
    [s]   item       {}
    [s]   request    <GET http://www.dmoz.org/Computers/Programming/Languages/Python/Books/>
    [s]   response   <200 http://www.dmoz.org/Computers/Programming/Languages/Python/Books/>
    [s]   settings   <scrapy.settings.Settings object at 0x3fadc50>
    [s]   spider     <Spider 'default' at 0x3cebf50>
    [s] Useful shortcuts:
    [s]   shelp()           Shell help (print this help)
    [s]   fetch(req_or_url) Fetch request (or URL) and update local objects
    [s]   view(response)    View response in a browser

    In [1]:

After the shell loads, you will have the response fetched in a local
``response`` variable, so if you type ``response.body`` you will see the body
of the response, or you can type ``response.headers`` to see its headers.

More importantly ``response`` has a ``selector`` attribute which is an instance of
:class:`~scrapy.selector.Selector` class, instantiated with this particular ``response``.
You can run queries on ``response`` by calling ``response.selector.xpath()`` or
``response.selector.css()``. There are also some convenience shortcuts like ``response.xpath()``
or ``response.css()`` which map directly to ``response.selector.xpath()`` and
``response.selector.css()``.


So let's try it::

    In [1]: response.xpath('//title')
    Out[1]: [<Selector xpath='//title' data=u'<title>Open Directory - Computers: Progr'>]
 
    In [2]: response.xpath('//title').extract()
    Out[2]: [u'<title>Open Directory - Computers: Programming: Languages: Python: Books</title>']
 
    In [3]: response.xpath('//title/text()')
    Out[3]: [<Selector xpath='//title/text()' data=u'Open Directory - Computers: Programming:'>]
 
    In [4]: response.xpath('//title/text()').extract()
    Out[4]: [u'Open Directory - Computers: Programming: Languages: Python: Books']
 
    In [5]: response.xpath('//title/text()').re('(\w+):')
    Out[5]: [u'Computers', u'Programming', u'Languages', u'Python']

Extracting the data
^^^^^^^^^^^^^^^^^^^

Now, let's try to extract some real information from those pages.

You could type ``response.body`` in the console, and inspect the source code to
figure out the XPaths you need to use. However, inspecting the raw HTML code
there could become a very tedious task. To make it easier, you can
use Firefox Developer Tools or some Firefox extensions like Firebug. For more
information see :ref:`topics-firebug` and :ref:`topics-firefox`.

After inspecting the page source, you'll find that the web site's information
is inside a ``<ul>`` element, in fact the *second* ``<ul>`` element.

So we can select each ``<li>`` element belonging to the site's list with this
code::

    response.xpath('//ul/li')

And from them, the site's descriptions::

    response.xpath('//ul/li/text()').extract()

The site's titles::

    response.xpath('//ul/li/a/text()').extract()

And the site's links::

    response.xpath('//ul/li/a/@href').extract()

As we've said before, each ``.xpath()`` call returns a list of selectors, so we can
concatenate further ``.xpath()`` calls to dig deeper into a node. We are going to use
that property here, so::

    for sel in response.xpath('//ul/li'):
        title = sel.xpath('a/text()').extract()
        link = sel.xpath('a/@href').extract()
        desc = sel.xpath('text()').extract()
        print title, link, desc

.. note::

    For a more detailed description of using nested selectors, see
    :ref:`topics-selectors-nesting-selectors` and
    :ref:`topics-selectors-relative-xpaths` in the :ref:`topics-selectors`
    documentation

Let's add this code to our spider::

    import scrapy
     
    class DmozSpider(scrapy.Spider):
        name = "dmoz"
        allowed_domains = ["dmoz.org"]
        start_urls = [
            "http://www.dmoz.org/Computers/Programming/Languages/Python/Books/",
            "http://www.dmoz.org/Computers/Programming/Languages/Python/Resources/"
        ]
     
        def parse(self, response):
            for sel in response.xpath('//ul/li'):
                title = sel.xpath('a/text()').extract()
                link = sel.xpath('a/@href').extract()
                desc = sel.xpath('text()').extract()
                print title, link, desc

Now try crawling dmoz.org again and you'll see sites being printed
in your output. Run::

    scrapy crawl dmoz

Using our item
--------------

:class:`~scrapy.item.Item` objects are custom Python dicts; you can access the
values of their fields (attributes of the class we defined earlier) using the
standard dict syntax like::

    >>> item = DmozItem()
    >>> item['title'] = 'Example title'
    >>> item['title']
    'Example title'

So, in order to return the data we've scraped so far, the final code for our
Spider would be like this::

    import scrapy

    from tutorial.items import DmozItem

    class DmozSpider(scrapy.Spider):
        name = "dmoz"
        allowed_domains = ["dmoz.org"]
        start_urls = [
            "http://www.dmoz.org/Computers/Programming/Languages/Python/Books/",
            "http://www.dmoz.org/Computers/Programming/Languages/Python/Resources/"
        ]

        def parse(self, response):
            for sel in response.xpath('//ul/li'):
                item = DmozItem()
                item['title'] = sel.xpath('a/text()').extract()
                item['link'] = sel.xpath('a/@href').extract()
                item['desc'] = sel.xpath('text()').extract()
                yield item

.. note:: You can find a fully-functional variant of this spider in the dirbot_
   project available at https://github.com/scrapy/dirbot

Now crawling dmoz.org yields ``DmozItem`` objects::

   [scrapy] DEBUG: Scraped from <200 http://www.dmoz.org/Computers/Programming/Languages/Python/Books/>
        {'desc': [u' - By David Mertz; Addison Wesley. Book in progress, full text, ASCII format. Asks for feedback. [author website, Gnosis Software, Inc.\n],
         'link': [u'http://gnosis.cx/TPiP/'],
         'title': [u'Text Processing in Python']}
   [scrapy] DEBUG: Scraped from <200 http://www.dmoz.org/Computers/Programming/Languages/Python/Books/>
        {'desc': [u' - By Sean McGrath; Prentice Hall PTR, 2000, ISBN 0130211192, has CD-ROM. Methods to build XML applications fast, Python tutorial, DOM and SAX, new Pyxie open source XML processing library. [Prentice Hall PTR]\n'],
         'link': [u'http://www.informit.com/store/product.aspx?isbn=0130211192'],
         'title': [u'XML Processing with Python']}


Following links
===============

Let's say, instead of just scraping the stuff in *Books* and *Resources* pages,
you want everything that is under the `Python directory
<http://www.dmoz.org/Computers/Programming/Languages/Python/>`_.

Now that you know how to extract data from a page, why not extract the links
for the pages you are interested, follow them and then extract the data you
want for all of them?

Here is a modification to our spider that does just that::

    import scrapy

    from tutorial.items import DmozItem

    class DmozSpider(scrapy.Spider):
        name = "dmoz"
        allowed_domains = ["dmoz.org"]
        start_urls = [
            "http://www.dmoz.org/Computers/Programming/Languages/Python/",
        ]

        def parse(self, response):
            for href in response.css("ul.directory.dir-col > li > a::attr('href')"):
                url = response.urljoin(href.extract())
                yield scrapy.Request(url, callback=self.parse_dir_contents)

        def parse_dir_contents(self, response):
            for sel in response.xpath('//ul/li'):
                item = DmozItem()
                item['title'] = sel.xpath('a/text()').extract()
                item['link'] = sel.xpath('a/@href').extract()
                item['desc'] = sel.xpath('text()').extract()
                yield item

Now the `parse()` method only extract the interesting links from the page,
builds a full absolute URL using the `response.urljoin` method (since the links can
be relative) and yields new requests to be sent later, registering as callback
the method `parse_dir_contents()` that will ultimately scrape the data we want.

What you see here is the Scrapy's mechanism of following links: when you yield
a Request in a callback method, Scrapy will schedule that request to be sent
and register a callback method to be executed when that request finishes.

Using this, you can build complex crawlers that follow links according to rules
you define, and extract different kinds of data depending on the page it's
visiting.

A common pattern is a callback method that extract some items, looks for a link
to follow to the next page and then yields a `Request` with the same callback
for it::

    def parse_articles_follow_next_page(self, response):
        for article in response.xpath("//article"):
            item = ArticleItem()

            ... extract article data here

            yield item

        next_page = response.css("ul.navigation > li.next-page > a::attr('href')")
        if next_page:
            url = response.urljoin(next_page[0].extract())
            yield scrapy.Request(url, self.parse_articles_follow_next_page)

This creates a sort of loop, following all the links to the next page until it
doesn't find one -- handy for crawling blogs, forums and other sites with
pagination.

Another common pattern is to build an item with data from more than one page,
using a :ref:`trick to pass additional data to the callbacks
<topics-request-response-ref-request-callback-arguments>`.


.. note::
    As an example spider that leverages this mechanism, check out the
    :class:`~scrapy.spiders.CrawlSpider` class for a generic spider
    that implements a small rules engine that you can use to write your
    crawlers on top of it.

Storing the scraped data
========================

The simplest way to store the scraped data is by using :ref:`Feed exports
<topics-feed-exports>`, with the following command::

    scrapy crawl dmoz -o items.json

That will generate an ``items.json`` file containing all scraped items,
serialized in `JSON`_.

In small projects (like the one in this tutorial), that should be enough.
However, if you want to perform more complex things with the scraped items, you
can write an :ref:`Item Pipeline <topics-item-pipeline>`. As with Items, a
placeholder file for Item Pipelines has been set up for you when the project is
created, in ``tutorial/pipelines.py``. Though you don't need to implement any item
pipelines if you just want to store the scraped items.

Next steps
==========

This tutorial covered only the basics of Scrapy, but there's a lot of other
features not mentioned here. Check the :ref:`topics-whatelse` section in
:ref:`intro-overview` chapter for a quick overview of the most important ones.

Then, we recommend you continue by playing with an example project (see
:ref:`intro-examples`), and then continue with the section
:ref:`section-basics`.

.. _JSON: https://en.wikipedia.org/wiki/JSON
.. _dirbot: https://github.com/scrapy/dirbot
