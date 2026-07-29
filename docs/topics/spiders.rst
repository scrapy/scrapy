.. _topics-spiders:

=======
Spiders
=======

Spiders are classes which define how a certain site (or a group of sites) will be
scraped, including how to perform the crawl (i.e. follow links) and how to
extract structured data from their pages (i.e. scraping items). In other words,
Spiders are the place where you define the custom behaviour for crawling and
parsing pages for a particular site (or, in some cases, a group of sites).

For spiders, the scraping cycle goes through something like this:

1. You start by generating the initial requests to crawl the first URLs, and
   specify a callback function to be called with the response downloaded from
   those requests.

   The first requests to perform are obtained by iterating the
   :meth:`~scrapy.Spider.start` method, which by default yields a
   :class:`~scrapy.Request` object for each URL in the
   :attr:`~scrapy.Spider.start_urls` spider attribute, with the
   :attr:`~scrapy.Spider.parse` method set as :attr:`~scrapy.Request.callback`
   function to handle each :class:`~scrapy.http.Response`.

2. In the callback function, you parse the response (web page) and return
   :ref:`item objects <topics-items>`,
   :class:`~scrapy.Request` objects, or an iterable of these objects.
   Those Requests will also contain a callback (maybe
   the same) and will then be downloaded by Scrapy and then their
   response handled by the specified callback.

3. In callback functions, you parse the page contents, typically using
   :ref:`topics-selectors` (but you can also use BeautifulSoup, lxml or whatever
   mechanism you prefer) and generate items with the parsed data.

4. Finally, the items returned from the spider will be typically persisted to a
   database (in some :ref:`Item Pipeline <topics-item-pipeline>`) or written to
   a file using :ref:`topics-feed-exports`.

Even though this cycle applies (more or less) to any kind of spider, there are
different kinds of default spiders bundled into Scrapy for different purposes.
We will talk about those types here.

.. _topics-spiders-ref:

scrapy.Spider
=============

.. class:: scrapy.spiders.Spider
.. autoclass:: scrapy.Spider

    .. autoattribute:: name

    .. attribute:: allowed_domains
        :type: list[str]

        The domains that this spider is allowed to crawl, if any. Requests for
        URLs not belonging to the domain names specified in this list (or their
        subdomains) won't be followed if
        :class:`~scrapy.downloadermiddlewares.offsite.OffsiteMiddleware` is
        enabled.

        Let's say your target url is ``https://www.example.com/1.html``,
        then add ``'example.com'`` to the list.

    .. autoattribute:: start_urls

    .. autoattribute:: custom_settings

    .. autoattribute:: crawler

    .. autoattribute:: settings

    .. autoattribute:: logger

    .. attribute:: state
        :type: dict[str, Any]

        Spider state to persist between batches.
        See :ref:`topics-keeping-persistent-state-between-batches` for details.

    .. automethod:: update_settings

    .. automethod:: from_crawler

    .. automethod:: start

    .. automethod:: parse

    .. method:: closed(reason)

        Called when the spider closes. This method provides a shortcut to
        signals.connect() for the :signal:`spider_closed` signal.

Let's see an example:

.. code-block:: python

    import scrapy


    class MySpider(scrapy.Spider):
        name = "example.com"
        allowed_domains = ["example.com"]
        start_urls = [
            "http://www.example.com/1.html",
            "http://www.example.com/2.html",
            "http://www.example.com/3.html",
        ]

        def parse(self, response):
            self.logger.info("A response from %s just arrived!", response.url)

Return multiple Requests and items from a single callback:

.. code-block:: python

    import scrapy


    class MySpider(scrapy.Spider):
        name = "example.com"
        allowed_domains = ["example.com"]
        start_urls = [
            "http://www.example.com/1.html",
            "http://www.example.com/2.html",
            "http://www.example.com/3.html",
        ]

        def parse(self, response):
            for h3 in response.xpath("//h3").getall():
                yield {"title": h3}

            for href in response.xpath("//a/@href").getall():
                yield scrapy.Request(response.urljoin(href), self.parse)

Instead of :attr:`~.start_urls` you can use :meth:`~scrapy.Spider.start`
directly; to give data more structure you can use :class:`~scrapy.Item`
objects:

.. skip: next
.. code-block:: python

    import scrapy
    from myproject.items import MyItem


    class MySpider(scrapy.Spider):
        name = "example.com"
        allowed_domains = ["example.com"]

        async def start(self):
            yield scrapy.Request("http://www.example.com/1.html", self.parse)
            yield scrapy.Request("http://www.example.com/2.html", self.parse)
            yield scrapy.Request("http://www.example.com/3.html", self.parse)

        def parse(self, response):
            for h3 in response.xpath("//h3").getall():
                yield MyItem(title=h3)

            for href in response.xpath("//a/@href").getall():
                yield scrapy.Request(response.urljoin(href), self.parse)

.. _spiderargs:

Spider arguments
================

Spiders can receive arguments that modify their behaviour. Some common uses for
spider arguments are to define the start URLs or to restrict the crawl to
certain sections of the site, but they can be used to configure any
functionality of the spider.

Spider arguments are passed through the :command:`crawl` command using the
``-a`` option. For example::

    scrapy crawl myspider -a category=electronics

Spiders can access arguments in their `__init__` methods:

.. code-block:: python

    import scrapy


    class MySpider(scrapy.Spider):
        name = "myspider"

        def __init__(self, category=None, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.start_urls = [f"http://www.example.com/categories/{category}"]
            # ...

The default `__init__` method will take any spider arguments
and copy them to the spider as attributes.
The above example can also be written as follows:

.. code-block:: python

    import scrapy


    class MySpider(scrapy.Spider):
        name = "myspider"

        async def start(self):
            yield scrapy.Request(f"http://www.example.com/categories/{self.category}")

If you are :ref:`running Scrapy from a script <run-from-script>`, you can
specify spider arguments when calling
:meth:`CrawlerProcess.crawl <scrapy.crawler.CrawlerProcess.crawl>` or
:meth:`CrawlerRunner.crawl <scrapy.crawler.CrawlerRunner.crawl>`:

.. skip: next
.. code-block:: python

    process = CrawlerProcess()
    process.crawl(MySpider, category="electronics")

Keep in mind that spider arguments are only strings.
The spider will not do any parsing on its own.
If you were to set the ``start_urls`` attribute from the command line,
you would have to parse it on your own into a list
using something like :func:`ast.literal_eval` or :func:`json.loads`
and then set it as an attribute.
Otherwise, you would cause iteration over a ``start_urls`` string
(a very common python pitfall)
resulting in each character being seen as a separate url.

Spider arguments can also be passed through the Scrapyd ``schedule.json`` API.
See `Scrapyd documentation`_.

.. _spiderargs-scrapy-spider-metadata:

scrapy-spider-metadata parameters
---------------------------------

Another alternative to pass spider arguments is the library `scrapy-spider-metadata`_.

This allows for Scrapy spiders to define, validate, document and pre-process
their arguments as Pydantic models.

The example shows how to define typed parameters where a string argument
is automatically converted to an integer:

.. code-block:: python

    import scrapy
    from pydantic import BaseModel
    from scrapy_spider_metadata import Args


    class MyParams(BaseModel):
        pages: int


    class BookSpider(Args[MyParams], scrapy.Spider):
        name = "bookspider"
        start_urls = ["http://books.toscrape.com/catalogue"]

        async def start(self):
            for start_url in self.start_urls:
                for index in range(1, self.args.pages + 1):
                    yield scrapy.Request(f"{start_url}/page-{index}.html")

        def parse(self, response):
            book_links = response.css("article.product_pod h3 a::attr(href)").getall()
            for book_link in book_links:
                yield response.follow(book_link, self.parse_book)

        def parse_book(self, response):
            yield {
                "title": response.css("h1::text").get(),
                "price": response.css("p.price_color::text").get(),
            }

This spider can be called from the command line::

    scrapy crawl bookspider -a pages=2

.. _start-requests:

Start requests
==============

**Start requests** are :class:`~scrapy.Request` objects yielded from the
:meth:`~scrapy.Spider.start` method of a spider or from the
:meth:`~scrapy.spidermiddlewares.SpiderMiddleware.process_start` method of a
:ref:`spider middleware <topics-spider-middleware>`.

.. seealso:: :ref:`start-request-order`

.. _start-requests-lazy:

Delaying start request iteration
--------------------------------

You can override the :meth:`~scrapy.Spider.start` method as follows to pause
its iteration whenever there are scheduled requests:

.. code-block:: python

    async def start(self):
        async for item_or_request in super().start():
            if self.crawler.engine.needs_backout():
                await self.crawler.signals.wait_for(signals.scheduler_empty)
            yield item_or_request

This can help minimize the number of requests in the scheduler at any given
time, to minimize resource usage (memory or disk, depending on
:setting:`JOBDIR`).

.. _builtin-spiders:

Generic Spiders
===============

Scrapy comes with some useful generic spiders that you can use to subclass
your spiders from. Their aim is to provide convenient functionality for a few
common scraping cases, like following all links on a site based on certain
rules, crawling from `Sitemaps`_, or parsing an XML/CSV feed.

For the examples used in the following spiders, we'll assume you have a project
with a ``TestItem`` declared in a ``myproject.items`` module:

.. code-block:: python

    from dataclasses import dataclass


    @dataclass
    class TestItem:
        id: str | None = None
        name: str | None = None
        description: str | None = None


.. currentmodule:: scrapy.spiders

CrawlSpider
-----------

.. autoclass:: CrawlSpider

    .. autoattribute:: rules

    .. automethod:: parse_start_url

Crawling rules
~~~~~~~~~~~~~~

.. autoclass:: Rule

CrawlSpider example
~~~~~~~~~~~~~~~~~~~

Let's now take a look at an example CrawlSpider with rules:

.. code-block:: python

    from scrapy.spiders import CrawlSpider, Rule
    from scrapy.linkextractors import LinkExtractor


    class MySpider(CrawlSpider):
        name = "example.com"
        allowed_domains = ["example.com"]
        start_urls = ["http://www.example.com"]

        rules = (
            # Extract links matching 'category.php' (but not matching 'subsection.php')
            # and follow links from them (since no callback means follow=True by default).
            Rule(LinkExtractor(allow=(r"category\.php",), deny=(r"subsection\.php",))),
            # Extract links matching 'item.php' and parse them with the spider's method parse_item
            Rule(LinkExtractor(allow=(r"item\.php",)), callback="parse_item"),
        )

        def parse_item(self, response):
            self.logger.info("Hi, this is an item page! %s", response.url)
            item = {}
            item["id"] = response.xpath('//td[@id="item_id"]/text()').re(r"ID: (\d+)")
            item["name"] = response.xpath('//td[@id="item_name"]/text()').get()
            item["description"] = response.xpath(
                '//td[@id="item_description"]/text()'
            ).get()
            item["link_text"] = response.meta["link_text"]
            url = response.xpath('//td[@id="additional_data"]/@href').get()
            return response.follow(
                url, self.parse_additional_page, cb_kwargs=dict(item=item)
            )

        def parse_additional_page(self, response, item):
            item["additional_data"] = response.xpath(
                '//p[@id="additional_data"]/text()'
            ).get()
            return item


This spider would start crawling example.com's home page, collecting category
links, and item links, parsing the latter with the ``parse_item`` method. For
each item response, some data will be extracted from the HTML using XPath, and
a dictionary will be filled with it.

XMLFeedSpider
-------------

.. autoclass:: XMLFeedSpider

    .. autoattribute:: iterator

    .. autoattribute:: itertag

    .. autoattribute:: namespaces

    .. automethod:: adapt_response

    .. automethod:: parse_node

    .. automethod:: process_results


XMLFeedSpider example
~~~~~~~~~~~~~~~~~~~~~

These spiders are pretty easy to use, let's have a look at one example:

.. skip: next
.. code-block:: python

    from scrapy.spiders import XMLFeedSpider
    from myproject.items import TestItem


    class MySpider(XMLFeedSpider):
        name = "example.com"
        allowed_domains = ["example.com"]
        start_urls = ["http://www.example.com/feed.xml"]
        iterator = "iternodes"  # This is actually unnecessary, since it's the default value
        itertag = "item"

        def parse_node(self, response, node):
            self.logger.info(
                "Hi, this is a <%s> node!: %s", self.itertag, "".join(node.getall())
            )

            item = TestItem()
            item.id = node.xpath("@id").get()
            item.name = node.xpath("name").get()
            item.description = node.xpath("description").get()
            return item

Basically what we did up there was to create a spider that downloads a feed from
the given ``start_urls``, and then iterates through each of its ``item`` tags,
prints them out, and stores some random data in an :class:`~scrapy.Item`.

CSVFeedSpider
-------------

.. autoclass:: CSVFeedSpider

    .. autoattribute:: delimiter

    .. autoattribute:: quotechar

    .. autoattribute:: headers

    .. automethod:: adapt_response

    .. automethod:: parse_row

    .. automethod:: process_results

CSVFeedSpider example
~~~~~~~~~~~~~~~~~~~~~

Let's see an example similar to the previous one, but using a
:class:`CSVFeedSpider`:

.. skip: next
.. code-block:: python

    from scrapy.spiders import CSVFeedSpider
    from myproject.items import TestItem


    class MySpider(CSVFeedSpider):
        name = "example.com"
        allowed_domains = ["example.com"]
        start_urls = ["http://www.example.com/feed.csv"]
        delimiter = ";"
        quotechar = "'"
        headers = ["id", "name", "description"]

        def parse_row(self, response, row):
            self.logger.info("Hi, this is a row!: %r", row)

            item = TestItem()
            item.id = row["id"]
            item.name = row["name"]
            item.description = row["description"]
            return item


SitemapSpider
-------------

.. autoclass:: SitemapSpider

    .. autoattribute:: sitemap_urls

    .. autoattribute:: sitemap_rules

    .. autoattribute:: sitemap_follow

    .. autoattribute:: sitemap_alternate_links

    .. automethod:: sitemap_filter


SitemapSpider examples
~~~~~~~~~~~~~~~~~~~~~~

Simplest example: process all urls discovered through sitemaps using the
``parse`` callback:

.. code-block:: python

    from scrapy.spiders import SitemapSpider


    class MySpider(SitemapSpider):
        sitemap_urls = ["http://www.example.com/sitemap.xml"]

        def parse(self, response):
            pass  # ... scrape item here ...

Process some urls with certain callback and other urls with a different
callback:

.. code-block:: python

    from scrapy.spiders import SitemapSpider


    class MySpider(SitemapSpider):
        sitemap_urls = ["http://www.example.com/sitemap.xml"]
        sitemap_rules = [
            ("/product/", "parse_product"),
            ("/category/", "parse_category"),
        ]

        def parse_product(self, response):
            pass  # ... scrape product ...

        def parse_category(self, response):
            pass  # ... scrape category ...

Follow sitemaps defined in the `robots.txt`_ file and only follow sitemaps
whose url contains ``/sitemap_shop``:

.. code-block:: python

    from scrapy.spiders import SitemapSpider


    class MySpider(SitemapSpider):
        sitemap_urls = ["http://www.example.com/robots.txt"]
        sitemap_rules = [
            ("/shop/", "parse_shop"),
        ]
        sitemap_follow = ["/sitemap_shops"]

        def parse_shop(self, response):
            pass  # ... scrape shop here ...

Combine SitemapSpider with other sources of urls:

.. code-block:: python

    from scrapy import Request
    from scrapy.spiders import SitemapSpider


    class MySpider(SitemapSpider):
        sitemap_urls = ["http://www.example.com/robots.txt"]
        sitemap_rules = [
            ("/shop/", "parse_shop"),
        ]

        other_urls = ["http://www.example.com/about"]

        async def start(self):
            async for item_or_request in super().start():
                yield item_or_request
            for url in self.other_urls:
                yield Request(url, self.parse_other)

        def parse_shop(self, response):
            pass  # ... scrape shop here ...

        def parse_other(self, response):
            pass  # ... scrape other here ...

.. _scrapy-spider-metadata: https://scrapy-spider-metadata.readthedocs.io/en/latest/params.html
.. _Sitemaps: https://www.sitemaps.org/index.html
.. _robots.txt: https://www.robotstxt.org/
.. _Scrapyd documentation: https://scrapyd.readthedocs.io/en/latest/
