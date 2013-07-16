.. _topics-spiders:

=======
Spiders
=======

Spiders are classes which define how a certain site (or group of sites) will be
scraped, including how to perform the crawl (ie. follow links) and how to
extract structured data from their pages (ie. scraping items). In other words,
Spiders are the place where you define the custom behaviour for crawling and
parsing pages for a particular site (or, in some cases, group of sites).

For spiders, the scraping cycle goes through something like this:

1. You start by generating the initial Requests to crawl the first URLs, and
   specify a callback function to be called with the response downloaded from
   those requests.

   The first requests to perform are obtained by calling the
   :meth:`~scrapy.spider.BaseSpider.start_requests` method which (by default)
   generates :class:`~scrapy.http.Request` for the URLs specified in the
   :attr:`~scrapy.spider.BaseSpider.start_urls` and the
   :attr:`~scrapy.spider.BaseSpider.parse` method as callback function for the
   Requests.

2. In the callback function, you parse the response (web page) and return either
   :class:`~scrapy.item.Item` objects, :class:`~scrapy.http.Request` objects,
   or an iterable of both. Those Requests will also contain a callback (maybe
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

Spiders receive arguments in their constructors::

    class MySpider(BaseSpider):
        name = 'myspider'

        def __init__(self, category=None, *args, **kwargs):
            super(MySpider, self).__init__(*args, **kwargs)
            self.start_urls = ['http://www.example.com/categories/%s' % category]
            # ...

Spider arguments can also be passed through the Scrapyd ``schedule.json`` API.
See `Scrapyd documentation`_.

.. _topics-spiders-ref:

Built-in spiders reference
==========================

Scrapy comes with some useful generic spiders that you can use, to subclass
your spiders from. Their aim is to provide convenient functionality for a few
common scraping cases, like following all links on a site based on certain
rules, crawling from `Sitemaps`_, or parsing a XML/CSV feed.

For the examples used in the following spiders, we'll assume you have a project
with a ``TestItem`` declared in a ``myproject.items`` module::

    from scrapy.item import Item

    class TestItem(Item):
        id = Field()
        name = Field()
        description = Field()


.. module:: scrapy.spider
   :synopsis: Spiders base class, spider manager and spider middleware

BaseSpider
----------

.. class:: BaseSpider()

   This is the simplest spider, and the one from which every other spider
   must inherit from (either the ones that come bundled with Scrapy, or the ones
   that you write yourself). It doesn't provide any special functionality. It just
   requests the given ``start_urls``/``start_requests``, and calls the spider's
   method ``parse`` for each of the resulting responses.

   .. attribute:: name
      
       A string which defines the name for this spider. The spider name is how
       the spider is located (and instantiated) by Scrapy, so it must be
       unique. However, nothing prevents you from instantiating more than one
       instance of the same spider. This is the most important spider attribute
       and it's required.

       If the spider scrapes a single domain, a common practice is to name the
       spider after the domain, or without the `TLD`_. So, for example, a
       spider that crawls ``mywebsite.com`` would often be called
       ``mywebsite``.

   .. attribute:: allowed_domains

       An optional list of strings containing domains that this spider is
       allowed to crawl. Requests for URLs not belonging to the domain names
       specified in this list won't be followed if
       :class:`~scrapy.contrib.spidermiddleware.offsite.OffsiteMiddleware` is enabled.

   .. attribute:: start_urls

       A list of URLs where the spider will begin to crawl from, when no
       particular URLs are specified. So, the first pages downloaded will be those
       listed here. The subsequent URLs will be generated successively from data
       contained in the start URLs.

   .. method:: start_requests()

       This method must return an iterable with the first Requests to crawl for
       this spider. 
       
       This is the method called by Scrapy when the spider is opened for
       scraping when no particular URLs are specified. If particular URLs are
       specified, the :meth:`make_requests_from_url` is used instead to create
       the Requests. This method is also called only once from Scrapy, so it's
       safe to implement it as a generator.

       The default implementation uses :meth:`make_requests_from_url` to
       generate Requests for each url in :attr:`start_urls`.

       If you want to change the Requests used to start scraping a domain, this is
       the method to override. For example, if you need to start by logging in using
       a POST request, you could do::

           def start_requests(self):
               return [FormRequest("http://www.example.com/login", 
                                   formdata={'user': 'john', 'pass': 'secret'},
                                   callback=self.logged_in)]

           def logged_in(self, response):
               # here you would extract links to follow and return Requests for
               # each of them, with another callback
               pass

   .. method:: make_requests_from_url(url)

       A method that receives a URL and returns a :class:`~scrapy.http.Request`
       object (or a list of :class:`~scrapy.http.Request` objects) to scrape. This
       method is used to construct the initial requests in the
       :meth:`start_requests` method, and is typically used to convert urls to
       requests.

       Unless overridden, this method returns Requests with the :meth:`parse`
       method as their callback function, and with dont_filter parameter enabled
       (see :class:`~scrapy.http.Request` class for more info).

   .. method:: parse(response)

       This is the default callback used by Scrapy to process downloaded
       responses, when their requests don't specify a callback.

       The ``parse`` method is in charge of processing the response and returning
       scraped data and/or more URLs to follow. Other Requests callbacks have
       the same requirements as the :class:`BaseSpider` class.

       This method, as well as any other Request callback, must return an
       iterable of :class:`~scrapy.http.Request` and/or
       :class:`~scrapy.item.Item` objects.

       :param response: the response to parse
       :type response: :class:~scrapy.http.Response`

   .. method:: log(message, [level, component])

       Log a message using the :func:`scrapy.log.msg` function, automatically
       populating the spider argument with the :attr:`name` of this
       spider. For more information see :ref:`topics-logging`.


BaseSpider example
~~~~~~~~~~~~~~~~~~

Let's see an example::

    from scrapy import log # This module is useful for printing out debug information
    from scrapy.spider import BaseSpider

    class MySpider(BaseSpider):
        name = 'example.com'
        allowed_domains = ['example.com']
        start_urls = [
            'http://www.example.com/1.html',
            'http://www.example.com/2.html',
            'http://www.example.com/3.html',
        ]

        def parse(self, response):
            self.log('A response from %s just arrived!' % response.url)

Another example returning multiples Requests and Items from a single callback::

    from scrapy.selector import HtmlXPathSelector
    from scrapy.spider import BaseSpider
    from scrapy.http import Request
    from myproject.items import MyItem

    class MySpider(BaseSpider):
        name = 'example.com'
        allowed_domains = ['example.com']
        start_urls = [
            'http://www.example.com/1.html',
            'http://www.example.com/2.html',
            'http://www.example.com/3.html',
        ]

        def parse(self, response):
            hxs = HtmlXPathSelector(response)
            for h3 in hxs.select('//h3').extract():
                yield MyItem(title=h3)

            for url in hxs.select('//a/@href').extract():
                yield Request(url, callback=self.parse)

.. module:: scrapy.contrib.spiders
   :synopsis: Collection of generic spiders

CrawlSpider
-----------

.. class:: CrawlSpider

   This is the most commonly used spider for crawling regular websites, as it
   provides a convenient mechanism for following links by defining a set of rules.
   It may not be the best suited for your particular web sites or project, but
   it's generic enough for several cases, so you can start from it and override it
   as needed for more custom functionality, or just implement your own spider.

   Apart from the attributes inherited from BaseSpider (that you must
   specify), this class supports a new attribute: 

   .. attribute:: rules

       Which is a list of one (or more) :class:`Rule` objects.  Each :class:`Rule`
       defines a certain behaviour for crawling the site. Rules objects are
       described below. If multiple rules match the same link, the first one
       will be used, according to the order they're defined in this attribute.

   This spider also exposes an overrideable method:

   .. method:: parse_start_url(response)

      This method is called for the start_urls responses. It allows to parse
      the initial responses and must return either a 
      :class:`~scrapy.item.Item` object, a :class:`~scrapy.http.Request` 
      object, or an iterable containing any of them.
       
Crawling rules
~~~~~~~~~~~~~~

.. class:: Rule(link_extractor, callback=None, cb_kwargs=None, follow=None, process_links=None, process_request=None)

   ``link_extractor`` is a :ref:`Link Extractor <topics-link-extractors>` object which
   defines how links will be extracted from each crawled page.
      
   ``callback`` is a callable or a string (in which case a method from the spider
   object with that name will be used) to be called for each link extracted with
   the specified link_extractor. This callback receives a response as its first
   argument and must return a list containing :class:`~scrapy.item.Item` and/or
   :class:`~scrapy.http.Request` objects (or any subclass of them).

   .. warning:: When writing crawl spider rules, avoid using ``parse`` as
       callback, since the :class:`CrawlSpider` uses the ``parse`` method
       itself to implement its logic. So if you override the ``parse`` method,
       the crawl spider will no longer work.

   ``cb_kwargs`` is a dict containing the keyword arguments to be passed to the
   callback function

   ``follow`` is a boolean which specifies if links should be followed from each
   response extracted with this rule. If ``callback`` is None ``follow`` defaults
   to ``True``, otherwise it default to ``False``.

   ``process_links`` is a callable, or a string (in which case a method from the
   spider object with that name will be used) which will be called for each list
   of links extracted from each response using the specified ``link_extractor``.
   This is mainly used for filtering purposes. 

   ``process_request`` is a callable, or a string (in which case a method from
   the spider object with that name will be used) which will be called with
   every request extracted by this rule, and must return a request or None (to
   filter out the request).

CrawlSpider example
~~~~~~~~~~~~~~~~~~~

Let's now take a look at an example CrawlSpider with rules::

    from scrapy.contrib.spiders import CrawlSpider, Rule
    from scrapy.contrib.linkextractors.sgml import SgmlLinkExtractor
    from scrapy.selector import HtmlXPathSelector
    from scrapy.item import Item

    class MySpider(CrawlSpider):
        name = 'example.com'
        allowed_domains = ['example.com']
        start_urls = ['http://www.example.com']
        
        rules = (
            # Extract links matching 'category.php' (but not matching 'subsection.php') 
            # and follow links from them (since no callback means follow=True by default).
            Rule(SgmlLinkExtractor(allow=('category\.php', ), deny=('subsection\.php', ))),

            # Extract links matching 'item.php' and parse them with the spider's method parse_item
            Rule(SgmlLinkExtractor(allow=('item\.php', )), callback='parse_item'),
        )

        def parse_item(self, response):
            self.log('Hi, this is an item page! %s' % response.url)

            hxs = HtmlXPathSelector(response)
            item = Item()
            item['id'] = hxs.select('//td[@id="item_id"]/text()').re(r'ID: (\d+)')
            item['name'] = hxs.select('//td[@id="item_name"]/text()').extract()
            item['description'] = hxs.select('//td[@id="item_description"]/text()').extract()
            return item


This spider would start crawling example.com's home page, collecting category
links, and item links, parsing the latter with the ``parse_item`` method. For
each item response, some data will be extracted from the HTML using XPath, and
a :class:`~scrapy.item.Item` will be filled with it.

XMLFeedSpider
-------------

.. class:: XMLFeedSpider

    XMLFeedSpider is designed for parsing XML feeds by iterating through them by a
    certain node name.  The iterator can be chosen from: ``iternodes``, ``xml``,
    and ``html``.  It's recommended to use the ``iternodes`` iterator for
    performance reasons, since the ``xml`` and ``html`` iterators generate the
    whole DOM at once in order to parse it.  However, using ``html`` as the
    iterator may be useful when parsing XML with bad markup.

    To set the iterator and the tag name, you must define the following class
    attributes:  

    .. attribute:: iterator

        A string which defines the iterator to use. It can be either:

           - ``'iternodes'`` - a fast iterator based on regular expressions 

           - ``'html'`` - an iterator which uses HtmlXPathSelector. Keep in mind
             this uses DOM parsing and must load all DOM in memory which could be a
             problem for big feeds

           - ``'xml'`` - an iterator which uses XmlXPathSelector. Keep in mind
             this uses DOM parsing and must load all DOM in memory which could be a
             problem for big feeds

        It defaults to: ``'iternodes'``.

    .. attribute:: itertag

        A string with the name of the node (or element) to iterate in. Example::

            itertag = 'product'

    .. attribute:: namespaces

        A list of ``(prefix, uri)`` tuples which define the namespaces
        available in that document that will be processed with this spider. The
        ``prefix`` and ``uri`` will be used to automatically register
        namespaces using the
        :meth:`~scrapy.selector.XPathSelector.register_namespace` method.

        You can then specify nodes with namespaces in the :attr:`itertag`
        attribute.

        Example::
            
            class YourSpider(XMLFeedSpider):

                namespaces = [('n', 'http://www.sitemaps.org/schemas/sitemap/0.9')]
                itertag = 'n:url'
                # ...

    Apart from these new attributes, this spider has the following overrideable
    methods too:

    .. method:: adapt_response(response)

        A method that receives the response as soon as it arrives from the spider
        middleware, before the spider starts parsing it. It can be used to modify
        the response body before parsing it. This method receives a response and
        also returns a response (it could be the same or another one).

    .. method:: parse_node(response, selector)
       
        This method is called for the nodes matching the provided tag name
        (``itertag``).  Receives the response and an XPathSelector for each node.
        Overriding this method is mandatory. Otherwise, you spider won't work.
        This method must return either a :class:`~scrapy.item.Item` object, a
        :class:`~scrapy.http.Request` object, or an iterable containing any of
        them.

    .. method:: process_results(response, results)
       
        This method is called for each result (item or request) returned by the
        spider, and it's intended to perform any last time processing required
        before returning the results to the framework core, for example setting the
        item IDs. It receives a list of results and the response which originated
        those results. It must return a list of results (Items or Requests).


XMLFeedSpider example
~~~~~~~~~~~~~~~~~~~~~

These spiders are pretty easy to use, let's have a look at one example::

    from scrapy import log
    from scrapy.contrib.spiders import XMLFeedSpider
    from myproject.items import TestItem

    class MySpider(XMLFeedSpider):
        name = 'example.com'
        allowed_domains = ['example.com']
        start_urls = ['http://www.example.com/feed.xml']
        iterator = 'iternodes' # This is actually unnecessary, since it's the default value
        itertag = 'item'

        def parse_node(self, response, node):
            log.msg('Hi, this is a <%s> node!: %s' % (self.itertag, ''.join(node.extract())))

            item = Item()
            item['id'] = node.select('@id').extract()
            item['name'] = node.select('name').extract()
            item['description'] = node.select('description').extract()
            return item

Basically what we did up there was to create a spider that downloads a feed from
the given ``start_urls``, and then iterates through each of its ``item`` tags,
prints them out, and stores some random data in an :class:`~scrapy.item.Item`.

CSVFeedSpider
-------------

.. class:: CSVFeedSpider

   This spider is very similar to the XMLFeedSpider, except that it iterates
   over rows, instead of nodes. The method that gets called in each iteration
   is :meth:`parse_row`.

   .. attribute:: delimiter

       A string with the separator character for each field in the CSV file
       Defaults to ``','`` (comma).

   .. attribute:: headers
      
       A list of the rows contained in the file CSV feed which will be used to
       extract fields from it.

   .. method:: parse_row(response, row)
      
       Receives a response and a dict (representing each row) with a key for each
       provided (or detected) header of the CSV file.  This spider also gives the
       opportunity to override ``adapt_response`` and ``process_results`` methods
       for pre- and post-processing purposes.

CSVFeedSpider example
~~~~~~~~~~~~~~~~~~~~~

Let's see an example similar to the previous one, but using a
:class:`CSVFeedSpider`::

    from scrapy import log
    from scrapy.contrib.spiders import CSVFeedSpider
    from myproject.items import TestItem

    class MySpider(CSVFeedSpider):
        name = 'example.com'
        allowed_domains = ['example.com']
        start_urls = ['http://www.example.com/feed.csv']
        delimiter = ';'
        headers = ['id', 'name', 'description']

        def parse_row(self, response, row):
            log.msg('Hi, this is a row!: %r' % row)

            item = TestItem()
            item['id'] = row['id']
            item['name'] = row['name']
            item['description'] = row['description']
            return item


SitemapSpider
-------------

.. class:: SitemapSpider

    SitemapSpider allows you to crawl a site by discovering the URLs using
    `Sitemaps`_.

    It supports nested sitemaps and discovering sitemap urls from
    `robots.txt`_.

    .. attribute:: sitemap_urls

        A list of urls pointing to the sitemaps whose urls you want to crawl.

        You can also point to a `robots.txt`_ and it will be parsed to extract
        sitemap urls from it.

    .. attribute:: sitemap_rules

        A list of tuples ``(regex, callback)`` where:

        * ``regex`` is a regular expression to match urls extracted from sitemaps.
          ``regex`` can be either a str or a compiled regex object.

        * callback is the callback to use for processing the urls that match
          the regular expression. ``callback`` can be a string (indicating the
          name of a spider method) or a callable.

        For example::

            sitemap_rules = [('/product/', 'parse_product')]

        Rules are applied in order, and only the first one that matches will be
        used.

        If you omit this attribute, all urls found in sitemaps will be
        processed with the ``parse`` callback.

    .. attribute:: sitemap_follow

        A list of regexes of sitemap that should be followed. This is is only
        for sites that use `Sitemap index files`_ that point to other sitemap
        files.

        By default, all sitemaps are followed.


SitemapSpider examples
~~~~~~~~~~~~~~~~~~~~~~

Simplest example: process all urls discovered through sitemaps using the
``parse`` callback::

    from scrapy.contrib.spiders import SitemapSpider

    class MySpider(SitemapSpider):
        sitemap_urls = ['http://www.example.com/sitemap.xml']

        def parse(self, response):
            pass # ... scrape item here ...

Process some urls with certain callback and other urls with a different
callback::

    from scrapy.contrib.spiders import SitemapSpider

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

    from scrapy.contrib.spiders import SitemapSpider

    class MySpider(SitemapSpider):
        sitemap_urls = ['http://www.example.com/robots.txt']
        sitemap_rules = [
            ('/shop/', 'parse_shop'),
        ]
        sitemap_follow = ['/sitemap_shops']

        def parse_shop(self, response):
            pass # ... scrape shop here ...

Combine SitemapSpider with other sources of urls::

    from scrapy.contrib.spiders import SitemapSpider

    class MySpider(SitemapSpider):
        sitemap_urls = ['http://www.example.com/robots.txt']
        sitemap_rules = [
            ('/shop/', 'parse_shop'),
        ]

        other_urls = ['http://www.example.com/about']

        def start_requests(self):
            requests = list(super(MySpider, self).start_requests())
            requests += [Request(x, callback=self.parse_other) for x in self.other_urls]
            return requests

        def parse_shop(self, response):
            pass # ... scrape shop here ...

        def parse_other(self, response):
            pass # ... scrape other here ...

.. _Sitemaps: http://www.sitemaps.org
.. _Sitemap index files: http://www.sitemaps.org/protocol.php#index
.. _robots.txt: http://www.robotstxt.org/
.. _TLD: http://en.wikipedia.org/wiki/Top-level_domain
.. _Scrapyd documentation: http://scrapyd.readthedocs.org/
