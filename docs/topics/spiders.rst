.. _topics-spiders:

=======
Spiders
=======

Spiders are classes which define how a certain site (or domain) will be
scraped, including how to crawl the site and how to extract scraped items from
their pages. In other words, Spiders are the place where you define the custom
behaviour for crawling and parsing pages for a particular site.

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

2. In the callback function you parse the response (web page) and return an
   iterable containing either :class:`~scrapy.item.Item` objects,
   :class:`~scrapy.http.Request` objects, or both. Those Requests will also
   contain a callback (maybe the same) and will then be followed by downloaded
   by Scrapy and then their response handled to the specified callback.

3. In callback functions you parse the page contants, typically using
   :ref:`topics-selectors` (but you can also use BeautifuSoup, lxml or whatever
   mechanism you prefer) and generate items with the parsed data.

4. Finally the items returned from the spider will be typically persisted in
   some Item pipeline.

Even though this cycles applies (more or less) to any kind of spider, there are
different kind of default spiders bundled into Scrapy for different purposes.
We will talk about those types here.


.. _topics-spiders-ref:

Built-in spiders reference
==========================

For the examples used in the following spiders reference we'll assume we have a
``TestItem`` declared in a ``myproject.items`` module, in your project::

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

   .. attribute:: domain_name
      
       A string which defines the domain name for this spider, which will also be
       the unique identifier for this spider (which means you can't have two
       spider with the same ``domain_name``). This is the most important spider
       attribute and it's required, and it's the name by which Scrapy will known
       the spider. 

   .. attribute:: extra_domain_names

       An optional list of strings containing additional domains that this spider
       is allowed to crawl. Requests for URLs not belonging to the domain name
       specified in :attr:`Spider.domain_name` or this list won't be followed.

   .. attribute:: start_urls

       Is a list of URLs where the spider will begin to crawl from, when no
       particular URLs are specified. So, the first pages downloaded will be those
       listed here. The subsequent URLs will be generated successively from data
       contained in the start URLs.

   .. method:: start_requests()

       This method must return an iterable with the first Requests to crawl for
       this spider. 
       
       This is the method called by Scrapy when the spider is opened for scraping
       when no particular URLs are specified. If particular URLs are specified,
       the :meth:`BaseSpider.make_requests_from_url` is used instead to create the
       Requests. This method is also called only once from Scrapy, so it's safe to
       implement it as a generator.

       The default implementation uses :meth:`BaseSpider.make_requests_from_url`
       to generate Requests for each url in :attr:`start_urls`.

       If you want to change the Requests used to start scraping a domain, this is
       the method to override. For example, if you need to start by login in using
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

       This is the default callback used by the :meth:`start_requests` method, and
       will be used to parse the first pages crawled by the spider.

       The ``parse`` method is in charge of processing the response and returning
       scraped data and/or more URLs to follow, because of this, the method must
       always return a list or at least an empty one. Other Requests callbacks
       have the same requirements as the BaseSpider class.

BaseSpider example
~~~~~~~~~~~~~~~~~~

Let's see an example::

    from scrapy import log # This module is useful for printing out debug information
    from scrapy.spider import BaseSpider

    class MySpider(BaseSpider):
        domain_name = 'http://www.example.com'
        start_urls = [
            'http://www.example.com/1.html',
            'http://www.example.com/2.html',
            'http://www.example.com/3.html',
        ]

        def parse(self, response):
            self.log('A response from %s just arrived!' % response.url)
            return []

    SPIDER = MySpider()

.. module:: scrapy.contrib.spiders
   :synopsis: Collection of generic spiders

CrawlSpider
-----------

.. class:: CrawlSpider

   This is the most commonly used spider for crawling regular websites, as it
   provides a convenient mechanism for following links by defining a set of rules.
   It may not be the best suited for your particular web sites or project, but
   it's generic enough for several cases, so you can start from it and override it
   as need more custom functionality, or just implement your own spider.

   Apart from the attributes inherited from BaseSpider (that you must
   specify), this class supports a new attribute: 

   .. attribute:: rules

       Which is a list of one (or more) :class:`Rule` objects.  Each :class:`Rule`
       defines a certain behaviour for crawling the site. Rules objects are
       described below .
       
Crawling rules
~~~~~~~~~~~~~~
.. class:: Rule(link_extractor, callback=None, cb_kwargs=None, follow=None, process_links=None)

   ``link_extractor`` is a :ref:`Link Extractor <topics-link-extractors>` object which
   defines how links will be extracted from each crawled page.
      
   ``callback`` is a callable or a string (in which case a method from the spider
   object with that name will be used) to be called for each link extracted with
   the specified link_extractor. This callback receives a response as its first
   argument and must return a list containing :class:`~scrapy.item.Item` and/or
   :class:`~scrapy.http.Request` objects (or any subclass of them).

   ``cb_kwargs`` is a dict containing the keyword arguments to be passed to the
   callback function

   ``follow`` is a boolean which specified if links should be followed from each
   response extracted with this rule. If ``callback`` is None ``follow`` defaults
   to ``True``, otherwise it default to ``False``.

   ``process_links`` is a callable, or a string (in which case a method from the
   spider object with that name will be used) which will be called for each list
   of links extracted from each response using the specified ``link_extractor``.
   This is mainly used for filtering purposes. 


CrawlSpider example
-------------------

Let's now take a look at an example CrawlSpider with rules::

    from scrapy.contrib.spiders import CrawlSpider, Rule
    from scrapy.contrib.linkextractors.sgml import SgmlLinkExtractor
    from scrapy.xpath.selector import HtmlXPathSelector
    from scrapy.item import Item

    class MySpider(CrawlSpider):
        domain_name = 'example.com'
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
            return [item]

    SPIDER = MySpider()


This spider would start crawling example.com's home page, collecting category
links, and item links, parsing the latter with the
:meth:`XMLFeedSpider.parse_item` method. For each item response, some data will
be extracted from the HTML using XPath, and a :class:`~scrapy.item.Item` will
be filled with it.

XMLFeedSpider
-------------

.. class:: XMLFeedSpider

    XMLFeedSpider is designed for parsing XML feeds by iterating through them by a
    certain node name.  The iterator can be chosen from: ``iternodes``, ``xml``,
    and ``html``.  It's recommended to use the ``iternodes`` iterator for
    performance reasons, since the ``xml`` and ``html`` iterators generate the
    whole DOM at once in order to parse it.  However, using ``html`` as the
    iterator may be useful when parsing XML with bad markup.

    For setting the iterator and the tag name, you must define the following class
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
        :meth:`~scrapy.xpath.XPathSelector.register_namespace` method.

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
        middleware and before start parsing it. It can be used used for modifying
        the response body before parsing it. This method receives a response and
        returns response (it could be the same or another one).

    .. method:: parse_item(response, selector)
       
        This method is called for the nodes matching the provided tag name
        (``itertag``).  Receives the response and an XPathSelector for each node.
        Overriding this method is mandatory. Otherwise, you spider won't work.
        This method must return either a :class:`~scrapy.item.Item` object, a
        :class:`~scrapy.http.Request` object, or an iterable containing any of
        them.

        .. warning:: This method will soon change its name to ``parse_node``

    .. method:: process_results(response, results)
       
        This method is called for each result (item or request) returned by the
        spider, and it's intended to perform any last time processing required
        before returning the results to the framework core, for example setting the
        item IDs. It receives a list of results and the response which originated
        that results. It must return a list of results (Items or Requests)."""


XMLFeedSpider example
~~~~~~~~~~~~~~~~~~~~~

These spiders are pretty easy to use, let's have at one example::

    from scrapy import log
    from scrapy.contrib.spiders import XMLFeedSpider
    from myproject.items import TestItem

    class MySpider(XMLFeedSpider):
        domain_name = 'example.com'
        start_urls = ['http://www.example.com/feed.xml']
        iterator = 'iternodes' # This is actually unnecesary, since it's the default value
        itertag = 'item'

        def parse_item(self, response, node):
            log.msg('Hi, this is a <%s> node!: %s' % (self.itertag, ''.join(node.extract())))

            item = Item()
            item['id'] = node.select('@id').extract()
            item['name'] = node.select('name').extract()
            item['description'] = node.select('description').extract()
            return item

    SPIDER = MySpider()

Basically what we did up there was creating a spider that downloads a feed from
the given ``start_urls``, and then iterates through each of its ``item`` tags,
prints them out, and stores some random data in an :class:`~scrapy.item.Item`.

CSVFeedSpider
-------------

.. class:: CSVFeedSpider

   .. warning:: The API of the CSVFeedSpider is not yet stable. Use with caution.

   This spider is very similar to the XMLFeedSpider, although it iterates through
   rows, instead of nodes.  It also has other two different attributes:

   .. attribute:: CSVFeedSpider.delimiter

       A string with the separator character for each field in the CSV file
       Defaults to ``','`` (comma).

   .. attribute:: CSVFeedSpider.headers
      
       A list of the rows contained in the file CSV feed which will be used for
       extracting fields from it.

   In this spider, the method that gets called in each row iteration ``parse_row``
   instead of ``parse_item`` (like in :class:`XMLFeedSpider`).

   .. method:: CSVFeedSpider.parse_row(response, row)
      
       Receives a response and a dict (representing each row) with a key for each
       provided (or detected) header of the CSV file.  This spider also gives the
       opportunity to override ``adapt_response`` and ``process_results`` methods
       for pre and post-processing purposes.

CSVFeedSpider example
~~~~~~~~~~~~~~~~~~~~~

Let's see an example similar to the previous one, but using a
:class:`CSVFeedSpider`::

    from scrapy import log
    from scrapy.contrib.spiders import CSVFeedSpider
    from myproject.items import TestItem

    class MySpider(CSVFeedSpider):
        domain_name = 'example.com'
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

    SPIDER = MySpider()

