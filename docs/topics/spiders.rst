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

1. You start by generating the initial Requests to crawl the first URLs, and
   specify a callback function to be called with the response downloaded from
   those requests.

   The first requests to perform are obtained by calling the
   :meth:`~scrapy.spiders.Spider.start_requests` method which (by default)
   generates :class:`~scrapy.http.Request` for the URLs specified in the
   :attr:`~scrapy.spiders.Spider.start_urls` and the
   :attr:`~scrapy.spiders.Spider.parse` method as callback function for the
   Requests.

2. In the callback function, you parse the response (web page) and return either
   dicts with extracted data, :class:`~scrapy.item.Item` objects,
   :class:`~scrapy.http.Request` objects, or an iterable of these objects.
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

The simplest spider is :class:`~scrapy.http.Spider`, and the one from which
every other spider must inherit (including spiders that come bundled with
Scrapy, as well as spiders that you write yourself). It doesn't provide any
special functionality. It just provides a default :meth:`start_requests`
implementation which sends requests from the :attr:`start_urls` spider
attribute and calls the spider's method ``parse`` for each of the resulting
responses.

Let's see an example::

    import scrapy


    class MySpider(scrapy.Spider):
        name = 'example.com'
        allowed_domains = ['example.com']
        start_urls = [
            'http://www.example.com/1.html',
            'http://www.example.com/2.html',
            'http://www.example.com/3.html',
        ]

        def parse(self, response):
            self.logger.info('A response from %s just arrived!', response.url)

Return multiple Requests and items from a single callback::

    import scrapy

    class MySpider(scrapy.Spider):
        name = 'example.com'
        allowed_domains = ['example.com']
        start_urls = [
            'http://www.example.com/1.html',
            'http://www.example.com/2.html',
            'http://www.example.com/3.html',
        ]

        def parse(self, response):
            for h3 in response.xpath('//h3').getall():
                yield {"title": h3}

            for href in response.xpath('//a/@href').getall():
                yield scrapy.Request(response.urljoin(href), self.parse)

Instead of :attr:`~.start_urls` you can use :meth:`~.start_requests` directly;
to give data more structure you can use :ref:`topics-items`::

    import scrapy
    from myproject.items import MyItem

    class MySpider(scrapy.Spider):
        name = 'example.com'
        allowed_domains = ['example.com']

        def start_requests(self):
            yield scrapy.Request('http://www.example.com/1.html', self.parse)
            yield scrapy.Request('http://www.example.com/2.html', self.parse)
            yield scrapy.Request('http://www.example.com/3.html', self.parse)

        def parse(self, response):
            for h3 in response.xpath('//h3').getall():
                yield MyItem(title=h3)

            for href in response.xpath('//a/@href').getall():
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

Spiders can access arguments in their `__init__` methods::

    import scrapy

    class MySpider(scrapy.Spider):
        name = 'myspider'

        def __init__(self, category=None, *args, **kwargs):
            super(MySpider, self).__init__(*args, **kwargs)
            self.start_urls = ['http://www.example.com/categories/%s' % category]
            # ...

The default `__init__` method will take any spider arguments
and copy them to the spider as attributes.
The above example can also be written as follows::

    import scrapy

    class MySpider(scrapy.Spider):
        name = 'myspider'

        def start_requests(self):
            yield scrapy.Request('http://www.example.com/categories/%s' % self.category)

Keep in mind that spider arguments are only strings.
The spider will not do any parsing on its own.
If you were to set the `start_urls` attribute from the command line,
you would have to parse it on your own into a list
using something like
`ast.literal_eval <https://docs.python.org/library/ast.html#ast.literal_eval>`_
or `json.loads <https://docs.python.org/library/json.html#json.loads>`_
and then set it as an attribute.
Otherwise, you would cause iteration over a `start_urls` string
(a very common python pitfall)
resulting in each character being seen as a separate url.

A valid use case is to set the http auth credentials
used by :class:`~scrapy.downloadermiddlewares.httpauth.HttpAuthMiddleware`
or the user agent
used by :class:`~scrapy.downloadermiddlewares.useragent.UserAgentMiddleware`::

    scrapy crawl myspider -a http_user=myuser -a http_pass=mypassword -a user_agent=mybot

Spider arguments can also be passed through the Scrapyd ``schedule.json`` API.
See `Scrapyd documentation`_.

.. _builtin-spiders:

Generic Spiders
===============

Scrapy comes with some useful generic spiders that you can use to subclass
your spiders from. Their aim is to provide convenient functionality for a few
common scraping cases, like following all links on a site based on certain
rules, crawling from `Sitemaps`_, or parsing an XML/CSV feed.

For the examples used in the following spiders, we'll assume you have a project
with a ``TestItem`` declared in a ``myproject.items`` module::

    import scrapy

    class TestItem(scrapy.Item):
        id = scrapy.Field()
        name = scrapy.Field()
        description = scrapy.Field()


.. currentmodule:: scrapy.spiders

CrawlSpider
-----------

…

Crawling rules
~~~~~~~~~~~~~~

…

CrawlSpider example
~~~~~~~~~~~~~~~~~~~

Let's now take a look at an example CrawlSpider with rules::

    import scrapy
    from scrapy.spiders import CrawlSpider, Rule
    from scrapy.linkextractors import LinkExtractor

    class MySpider(CrawlSpider):
        name = 'example.com'
        allowed_domains = ['example.com']
        start_urls = ['http://www.example.com']

        rules = (
            # Extract links matching 'category.php' (but not matching 'subsection.php')
            # and follow links from them (since no callback means follow=True by default).
            Rule(LinkExtractor(allow=('category\.php', ), deny=('subsection\.php', ))),

            # Extract links matching 'item.php' and parse them with the spider's method parse_item
            Rule(LinkExtractor(allow=('item\.php', )), callback='parse_item'),
        )

        def parse_item(self, response):
            self.logger.info('Hi, this is an item page! %s', response.url)
            item = scrapy.Item()
            item['id'] = response.xpath('//td[@id="item_id"]/text()').re(r'ID: (\d+)')
            item['name'] = response.xpath('//td[@id="item_name"]/text()').get()
            item['description'] = response.xpath('//td[@id="item_description"]/text()').get()
            return item


This spider would start crawling example.com's home page, collecting category
links, and item links, parsing the latter with the ``parse_item`` method. For
each item response, some data will be extracted from the HTML using XPath, and
an :class:`~scrapy.item.Item` will be filled with it.

XMLFeedSpider
-------------

…


XMLFeedSpider example
~~~~~~~~~~~~~~~~~~~~~

These spiders are pretty easy to use, let's have a look at one example::

    from scrapy.spiders import XMLFeedSpider
    from myproject.items import TestItem

    class MySpider(XMLFeedSpider):
        name = 'example.com'
        allowed_domains = ['example.com']
        start_urls = ['http://www.example.com/feed.xml']
        iterator = 'iternodes'  # This is actually unnecessary, since it's the default value
        itertag = 'item'

        def parse_node(self, response, node):
            self.logger.info('Hi, this is a <%s> node!: %s', self.itertag, ''.join(node.getall()))

            item = TestItem()
            item['id'] = node.xpath('@id').get()
            item['name'] = node.xpath('name').get()
            item['description'] = node.xpath('description').get()
            return item

Basically what we did up there was to create a spider that downloads a feed from
the given ``start_urls``, and then iterates through each of its ``item`` tags,
prints them out, and stores some random data in an :class:`~scrapy.item.Item`.

CSVFeedSpider
-------------

…

CSVFeedSpider example
~~~~~~~~~~~~~~~~~~~~~

Let's see an example similar to the previous one, but using a
:class:`CSVFeedSpider`::

    from scrapy.spiders import CSVFeedSpider
    from myproject.items import TestItem

    class MySpider(CSVFeedSpider):
        name = 'example.com'
        allowed_domains = ['example.com']
        start_urls = ['http://www.example.com/feed.csv']
        delimiter = ';'
        quotechar = "'"
        headers = ['id', 'name', 'description']

        def parse_row(self, response, row):
            self.logger.info('Hi, this is a row!: %r', row)

            item = TestItem()
            item['id'] = row['id']
            item['name'] = row['name']
            item['description'] = row['description']
            return item


SitemapSpider
-------------

…

    .. method:: sitemap_filter(entries)

        This is a filter funtion that could be overridden to select sitemap entries
        based on their attributes.

        For example::

            <url>
                <loc>http://example.com/</loc>
                <lastmod>2005-01-01</lastmod>
            </url>

        We can define a ``sitemap_filter`` function to filter ``entries`` by date::

            from datetime import datetime
            from scrapy.spiders import SitemapSpider

            class FilteredSitemapSpider(SitemapSpider):
                name = 'filtered_sitemap_spider'
                allowed_domains = ['example.com']
                sitemap_urls = ['http://example.com/sitemap.xml']

                def sitemap_filter(self, entries):
                    for entry in entries:
                        date_time = datetime.strptime(entry['lastmod'], '%Y-%m-%d')
                        if date_time.year >= 2005:
                            yield entry

        This would retrieve only ``entries`` modified on 2005 and the following
        years.

        Entries are dict objects extracted from the sitemap document.
        Usually, the key is the tag name and the value is the text inside it.

        It's important to notice that:

        - as the loc attribute is required, entries without this tag are discarded
        - alternate links are stored in a list with the key ``alternate``
          (see ``sitemap_alternate_links``)
        - namespaces are removed, so lxml tags named as ``{namespace}tagname`` become only ``tagname``

        If you omit this method, all entries found in sitemaps will be
        processed, observing other attributes and their settings.


SitemapSpider examples
~~~~~~~~~~~~~~~~~~~~~~

Simplest example: process all urls discovered through sitemaps using the
``parse`` callback::

    from scrapy.spiders import SitemapSpider

    class MySpider(SitemapSpider):
        sitemap_urls = ['http://www.example.com/sitemap.xml']

        def parse(self, response):
            pass # ... scrape item here ...

Process some urls with certain callback and other urls with a different
callback::

    from scrapy.spiders import SitemapSpider

    class MySpider(SitemapSpider):
        sitemap_urls = ['http://www.example.com/sitemap.xml']
        sitemap_rules = [
            ('/product/', 'parse_product'),
            ('/category/', 'parse_category'),
        ]

        def parse_product(self, response):
            pass # ... scrape product ...

        def parse_category(self, response):
            pass # ... scrape category ...

Follow sitemaps defined in the `robots.txt`_ file and only follow sitemaps
whose url contains ``/sitemap_shop``::

    from scrapy.spiders import SitemapSpider

    class MySpider(SitemapSpider):
        sitemap_urls = ['http://www.example.com/robots.txt']
        sitemap_rules = [
            ('/shop/', 'parse_shop'),
        ]
        sitemap_follow = ['/sitemap_shops']

        def parse_shop(self, response):
            pass # ... scrape shop here ...

Combine SitemapSpider with other sources of urls::

    from scrapy.spiders import SitemapSpider

    class MySpider(SitemapSpider):
        sitemap_urls = ['http://www.example.com/robots.txt']
        sitemap_rules = [
            ('/shop/', 'parse_shop'),
        ]

        other_urls = ['http://www.example.com/about']

        def start_requests(self):
            requests = list(super(MySpider, self).start_requests())
            requests += [scrapy.Request(x, self.parse_other) for x in self.other_urls]
            return requests

        def parse_shop(self, response):
            pass # ... scrape shop here ...

        def parse_other(self, response):
            pass # ... scrape other here ...

.. _robots.txt: http://www.robotstxt.org/
.. _Scrapyd documentation: https://scrapyd.readthedocs.io/en/latest/
.. _Sitemaps: https://www.sitemaps.org/index.html
