.. _intro-tutorial:

===============
Scrapy Tutorial
===============

In this tutorial, we'll assume that Scrapy is already installed on your system.
If that's not the case, see :ref:`intro-install`.

We are going to use `quotes.toscrape.com <http://quotes.toscrape.com/>`_ as
our example domain to scrape.

This tutorial will walk you through these tasks:

1. Creating a new Scrapy project
2. Writing a :ref:`spider <topics-spiders>` to crawl a site and extract
   :ref:`Items <topics-items>`
3. Exporting the scraped data using command line

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


Our first Spider
================

Spiders are classes that you define and Scrapy uses to scrape information from a
domain (or group of domains).

They define an initial list of URLs to download, how to follow links, and how
to parse the contents of pages to extract :ref:`items <topics-items>`.

To create a Spider, you must subclass :class:`scrapy.Spider
<scrapy.spiders.Spider>` and define some attributes and methods:

* :attr:`~scrapy.spiders.Spider.name`: identifies the Spider. It must be
  unique within a project, that is, you can't set the same name for different
  Spiders.

* :meth:`~scrapy.spiders.Spider.start_requests`: must return a list
  of requests where the Spider will begin to crawl from.
  Subsequent requests will be generated successively from these initial requests.

  As alternative to defining this method, you can define a class
  attribute :attr:`~scrapy.spiders.Spider.start_urls`, which the default
  implementation of this method will use to create the proper requests.

* :meth:`~scrapy.spiders.Spider.parse`: a method of the spider, which will
  be called with the downloaded :class:`~scrapy.http.Response` object of each
  initial request. The response is passed to the method as the first and only
  argument.

  This method is responsible for parsing the response data and extracting
  scraped data (as scraped items) and more URLs to follow.

  The :meth:`~scrapy.spiders.Spider.parse` method is in charge of processing
  the response and returning scraped data (as :class:`~scrapy.item.Item`
  objects) and more URLs to follow (as :class:`~scrapy.http.Request` objects).

This is the code for our first Spider; save it in a file named
``quotes_spider.py`` under the ``tutorial/spiders`` directory::

    import scrapy


    class QuotesSpider(scrapy.Spider):
        name = "quotes"

        def start_requests(self):
            urls = [
                'http://quotes.toscrape.com/page/1/',
                'http://quotes.toscrape.com/page/2/',
            ]
            for url in urls:
                yield scrapy.Request(url=url, callback=self.parse)

        def parse(self, response):
            page = response.url.split("/")[-2]
            filename = 'quotes-%s.html' % page
            with open(filename, 'wb') as f:
                f.write(response.body)

Crawling
--------

To put our spider to work, go to the project's top level directory and run::

   scrapy crawl quotes

This command runs the spider with name ``quotes`` that we've just added, that
will send some requests for the ``quotes.toscrape.com`` domain. You will get an output
similar to this::


    2016-09-01 16:51:27 [scrapy] INFO: Scrapy started (bot: tutorial)
    2016-09-01 16:51:27 [scrapy] INFO: Overridden settings: {...}
    2016-09-01 16:51:27 [scrapy] INFO: Enabled extensions: ...
    2016-09-01 16:51:27 [scrapy] INFO: Enabled downloader middlewares: ...
    2016-09-01 16:51:27 [scrapy] INFO: Enabled spider middlewares: ...
    2016-09-01 16:51:27 [scrapy] INFO: Enabled item pipelines: ...
    2016-09-01 16:51:27 [scrapy] INFO: Spider opened
    2016-09-01 16:51:27 [scrapy] INFO: Crawled 0 pages (at 0 pages/min), scraped 0 items (at 0 items/min)
    2016-09-01 16:51:28 [scrapy] DEBUG: Crawled (404) <GET http://quotes.toscrape.com/robots.txt> (referer: None)
    2016-09-01 16:51:28 [scrapy] DEBUG: Crawled (200) <GET http://quotes.toscrape.com/page/1/> (referer: None)
    2016-09-01 16:51:29 [scrapy] DEBUG: Crawled (200) <GET http://quotes.toscrape.com/page/2/> (referer: None)
    2016-09-01 16:51:29 [scrapy] INFO: Closing spider (finished)

.. note::
    At the end you can see a log line for each URL defined in ``start_urls``.
    Because these URLs are the starting ones, they have no referrers, which is
    shown at the end of the log line, where it says ``(referer: None)``.

Now, check the files in the current directory. You should notice two new files
have been created: *quotes-1.html* and *quotes-2.html*, with the content for the respective
URLs, as our ``parse`` method instructs.

What just happened under the hood?
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Scrapy will schedule the :class:`scrapy.Request <scrapy.http.Request>` objects
returned by the ``start_requests`` method of the Spider, and when receiving
a response for each one it will instantiate :class:`scrapy.http.Response`
objects and call the ``parse`` callback method passing the response as argument.

.. TODO: add here an explanation about how this structure is so command that
   we can do a short version of the spider w/ start_urls and default callback

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
  element of an HTML document. Equivalent CSS selector: ``html > head > title``.

* ``/html/head/title/text()``: selects the text inside the aforementioned
  ``<title>`` element. Equivalent CSS selector: ``html > head > title ::text``.

* ``//td``: selects all the ``<td>`` elements from the whole document.
  Equivalent CSS selector: ``td``.

* ``//div[@class="mine"]``: selects all ``div`` elements which contain an
  attribute ``class="mine"``. Equivalent CSS selector: ``div.mine``.

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

For working with CSS and XPath expressions, Scrapy provides the
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

    scrapy shell "http://quotes.toscrape.com"

.. note::

   Remember to always enclose urls in quotes when running Scrapy shell from
   command-line, otherwise urls containing arguments (ie. ``&`` character)
   will not work.

This is what the shell looks like::

    [ ... Scrapy log here ... ]

    2016-09-01 18:14:39 [scrapy] DEBUG: Crawled (200) <GET http://quotes.toscrape.com> (referer: None)
    [s] Available Scrapy objects:
    [s]   crawler    <scrapy.crawler.Crawler object at 0x109001c90>
    [s]   item       {}
    [s]   request    <GET http://quotes.toscrape.com>
    [s]   response   <200 http://quotes.toscrape.com>
    [s]   settings   <scrapy.settings.Settings object at 0x109001610>
    [s]   spider     <DefaultSpider 'default' at 0x1092808d0>
    [s] Useful shortcuts:
    [s]   shelp()           Shell help (print this help)
    [s]   fetch(req_or_url) Fetch request (or URL) and update local objects
    [s]   view(response)    View response in a browser
    
    >>>

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
    Out[1]: [<Selector xpath='//title' data=u'<title>Quotes to Scrape</title>'>] 
    
    In [2]: response.xpath('//title').extract()
    Out[2]: [u'<title>Quotes to Scrape</title>']
    
    In [3]: response.xpath('//title/text()')
    Out[3]: [<Selector xpath='//title/text()' data=u'Quotes to Scrape'>]

    In [4]: response.xpath('//title/text()').extract()
    Out[4]: [u'Quotes to Scrape']
    
    In [11]: response.xpath('//title/text()').re('(\w+)')
    Out[11]: [u'Quotes', u'to', u'Scrape']

Extracting the data
^^^^^^^^^^^^^^^^^^^

Now, let's try to extract some real information from those pages.

You could type ``response.body`` in the console, and inspect the source code to
figure out the XPaths you need to use. However, inspecting the raw HTML code
there could become a very tedious task. To make it easier, you can
use Firefox Developer Tools or some Firefox extensions like Firebug. For more
information see :ref:`topics-firebug` and :ref:`topics-firefox`.

After inspecting the page source, you'll find that every quote in the website
is inside a separate ``<div class="quote">`` element, such as::

    <div class="quote">
        <span class="text">“We accept the love we think we deserve.”</span>
        <span>by <small class="author">Stephen Chbosky</small></span>
        <div class="tags">
            Tags:
            <meta class="keywords"> 
            <a class="tag" href="/tag/inspirational/page/1/">inspirational</a>
            <a class="tag" href="/tag/love/page/1/">love</a>
        </div>
    </div>


So we can select each ``<div class="quote">`` element belonging to the site's 
list with this code::

    response.xpath('//div[@class="quote"]')

From the quote elements, we can select the texts with::

    response.xpath('//div[@class="quote"]/span[@class="text"]/text()').extract()

The authors::

    response.xpath('//div[@class="quote"]/span/small/text()').extract()

As we've said before, each ``.xpath()`` call returns a list of selectors, so we can
concatenate further ``.xpath()`` calls to dig deeper into a node. We are going to use
that property here, so::

    for quote in response.xpath('//div[@class="quote"]'):
        text = quote.xpath('span[@class="text"]/text()').extract_first()
        author = quote.xpath('span/small/text()').extract_first()
        print({'text': text, 'author': author})

In the above snippet we've decided to use the method ``.extract_first()``
instead of ``.extract()``, to extract the content from the first element from a
selector list returned by ``.xpath()``.

.. note::

    For a more detailed description of using nested selectors, see
    :ref:`topics-selectors-nesting-selectors` and
    :ref:`topics-selectors-relative-xpaths` in the :ref:`topics-selectors`
    documentation

Knowing to use selectors, extracting data from a page is just a matter of
yield the Python dictionaries from the callback method instead of printing
them.

Let's add the necessary code to our spider::

    import scrapy


    class QuotesSpider(scrapy.Spider):
        name = "quotes"
        start_urls = [
            'http://quotes.toscrape.com/page/1/',
            'http://quotes.toscrape.com/page/2/',
        ]

        def parse(self, response):
            for quote in response.xpath('//div[@class="quote"]'):
                yield {
                    'text': quote.xpath('span[@class="text"]/text()').extract_first(),
                    'author': quote.xpath('span/small/text()').extract_first(),
                }

Run::

    scrapy crawl quotes

Now crawling quotes.toscrape.com will show dictionary objects::

    2016-09-02 16:35:20 [scrapy] DEBUG: Scraped from <200 http://quotes.toscrape.com/page/2/>
    {'author': 'Oscar Wilde',
     'text': '“We are all in the gutter, but some of us are looking at the stars.”'}
    2016-09-02 16:35:20 [scrapy] DEBUG: Scraped from <200 http://quotes.toscrape.com/page/2/>
    {'author': 'Mark Twain',
     'text': '“The man who does not read has no advantage over the man who cannot read.”'}


Following links
===============

Let's say, instead of just scraping the stuff from the first two pages
from quotes.toscrape.com, you want quotes from all the pages in the website.

Now that you know how to extract data from a page, why not extract the
pagination links in each page, follow them and then extract the data you
want for all of them?

Here is a modification to our spider that does just that::

    import scrapy


    class QuotesSpider(scrapy.Spider):
        name = "quotes"
        start_urls = [
            'http://quotes.toscrape.com/page/1/',
        ]

        def parse(self, response):
            for quote in response.xpath('//div[@class="quote"]'):
                yield {
                    'text': quote.xpath('span[@class="text"]/text()').extract_first(),
                    'author': quote.xpath('span/small/text()').extract_first(),
                }

            next_page = response.xpath('//li[@class="next"]/a/@href').extract_first()
            if next_page is not None:
                next_page = response.urljoin(next_page)
                yield scrapy.Request(next_page, callback=self.parse)

Now after extracting an item the `parse()` method looks for the link to the next page, 
builds a full absolute URL using the `response.urljoin` method (since the links can
be relative) and yields a new request to the next page, registering itself as callback to handle the data extraction for the next page and to keep the crawling going through all the pages.

What you see here is Scrapy's mechanism of following links: when you yield
a Request in a callback method, Scrapy will schedule that request to be sent
and register a callback method to be executed when that request finishes.

Using this, you can build complex crawlers that follow links according to rules
you define, and extract different kinds of data depending on the page it's
visiting.

In our example, it creates a sort of loop, following all the links to the next page
until it doesn't find one -- handy for crawling blogs, forums and other sites with
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

    scrapy crawl quotes -o items.json

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
