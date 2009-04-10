.. _ref-spiders:

=================
Available Spiders
=================

.. module:: scrapy.spider

BaseSpider
==========

.. class:: BaseSpider()

This is the simplest spider, and the one from which every other spider
must inherit from (either the ones that come bundled with Scrapy, or the ones
that you write yourself). It doesn't provide any special functionality. It just
requests the given ``start_urls``/``start_requests``, and calls the spider's
method ``parse`` for each of the resulting responses.

.. attribute:: BaseSpider.domain_name
   
    A string which defines the domain name for this spider, which will also be
    the unique identifier for this spider (which means you can't have two
    spider with the same ``domain_name``). This is the most important spider
    attribute and it's required, and it's the name by which Scrapy will known
    the spider. 

.. attribute:: BaseSpider.extra_domain_names

    An optional list of strings containing additional domains that this spider
    is allowed to crawl. Requests for URLs not belonging to the domain name
    specified in :attr:`Spider.domain_name` or this list won't be followed.

.. attribute:: BaseSpider.start_urls

    Is a list of URLs where the spider will begin to crawl from, when no
    particular URLs are specified. So, the first pages downloaded will be those
    listed here. The subsequent URLs will be generated successively from data
    contained in the start URLs.

.. method:: BaseSpider.start_requests(urls=None)

    A method that receives a list of URLs to scrape (for that spider) and
    returns a list of Requests for those urls.

    If urls is `None` it will use the :attr:`BaseSpider.start_urls` attribute.

    Unless overriden, the Requests returned by this method will use the
    :meth:`BaseSpider.parse` method as their callback function.

    This is also the first method called by Scrapy when it opens a spider for
    scraping, so you if you want to change the Requests used to start scraping
    a domain, this is the method to override. For example, if you need to start
    by login in using a POST request, you could do::

        def start_requests(self):
            return [FormRequest("http://www.example.com/login", 
                                formdata={'user': 'john', 'pass': 'secret'},
                                callback=self.logged_in)]

        def logged_in(self, response):
            # here you would extract links to follow and return Requests for
            # each of them, perhaps with another callback
            pass

.. method:: BaseSpider.parse(response)

    This is the default callback used by the :meth:`start_requests` method, and
    will be used to parse the first pages crawled by the spider.

    The ``parse`` method is in charge of processing the response and returning
    scraped data and/or more URLs to follow, because of this, the method must
    always return a list or at least an empty one. Other Requests callbacks
    have the same requirements as the BaseSpider class.

BaseSpider example
------------------

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
            log.msg('Hey! A response from %s has just arrived!' % response.url)
            return []

    SPIDER = MySpider()

.. module:: scrapy.contrib.spiders

CrawlSpider
===========

.. class:: CrawlSpider

This is the most commonly used spider, and it's the one preferred for crawling
standard web sites (ie. HTML pages), extracts links from there (given certain
extraction rules), and scrapes items from those pages.

This spider is a bit more complicated than the previous one, because it
introduces a few new concepts, but you'll probably find it useful.

Apart from the attributes inherited from BaseSpider (that you must
specify), this class supports a new attribute: 

.. attribute:: CrawlSpider.rules

    Which is a list of one (or more) :class:`Rule` objects.  Each :class:`Rule`
    defines a certain behaviour for crawling the site. Rules objects are
    described below .
    
Crawling rules
--------------

.. class:: Rule(link_extractor, callback=None, cb_kwargs=None, follow=None, process_links=None)

``link_extractor`` is a :ref:`Link Extractor <topics-link-extractors>` object which
defines how links will be extracted from each crawled page.
   
``callback`` is a callable or a string (in which case a method from the spider
object with that name will be used) to be called for each link extracted with
the specified link_extractor. This callback receives a response as its first
argument and must return a list containing either ScrapedItems and Requests (or
any subclass of them).

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

    from scrapy import log
    from scrapy.contrib.spiders import CrawlSpider, Rule
    from scrapy.link.extractors import RegexLinkExtractor
    from scrapy.xpath.selector import HtmlXPathSelector
    from scrapy.item import ScrapedItem

    class MySpider(CrawlSpider):
        domain_name = 'example.com'
        start_urls = ['http://www.example.com']
        
        rules = (
            # Extract links matching 'category.php' (but not matching 'subsection.php') and follow links from them (since no callback means follow=True by default).
            Rule(RegexLinkExtractor(allow=('category\.php', ), deny=('subsection\,php', ))),

            # Extract links matching 'item.php' and parse them with the spider's method parse_item
            Rule(RegexLinkExtractor(allow=('item\.php', )), callback='parse_item'),
        )

        def parse_item(self, response):
            log.msg('Hi, this is an item page! %s' % response.url)

            hxs = HtmlXPathSelector(response)
            item = ScrapedItem()
            item.id = hxs.x('//td[@id="item_id"]/text()').re(r'ID: (\d+)')
            item.name = hxs.x('//td[@id="item_name"]/text()').extract()
            item.description = hxs.x('//td[@id="item_description"]/text()').extract()
            return [item]

    SPIDER = MySpider()


This spider would start crawling example.com's home page, collecting category
links, and item links, parsing the latter with the *parse_item* method. For
each item response, some data will be extracted from the HTML using XPath, and
a ScrapedItem will be filled with it.

XMLFeedSpider
=============

.. class:: XMLFeedSpider

XMLFeedSpider is designed for parsing XML feeds by iterating through them by a
certain node name.  The iterator can be chosen from: ``iternodes``, ``xml``,
and ``html``.  It's recommended to use the ``iternodes`` iterator for
performance reasons, since the ``xml`` and ``html`` iterators generate the
whole DOM at once in order to parse it.  However, using ``html`` as the
iterator may be useful when parsing XML with bad markup.

For setting the iterator and the tag name, you must define the following class
attributes:  

.. attribute:: XMLFeedSpider.iterator

    A string which defines the iterator to use. It can be either:

       - ``'iternodes'`` - a fast iterator based on regular expressions 

       - ``'html'`` - an iterator which uses HtmlXPathSelector. Keep in mind
         this uses DOM parsing and must load all DOM in memory which could be a
         problem for big feeds

       - ``'xml'`` - an iterator which uses XmlXPathSelector. Keep in mind
         this uses DOM parsing and must load all DOM in memory which could be a
         problem for big feeds

    It defaults to: ``'iternodes'``.

.. attribute:: XMLFeedSpider.itertag

    A stirng with the name of the node (or element) to iterate in.

Apart from these new attributes, this spider has the following overrideable
methods too:

.. method:: XMLFeedSpider.adapt_response(response)

    A method that receives the response as soon as it arrives from the spider
    middleware and before start parsing it. It can be used used for modifying
    the response body before parsing it. This method receives a response and
    returns response (it could be the same or another one).

.. method:: XMLFeedSpider.parse_item(response, selector)
   
    This method is called for the nodes matching the provided tag name
    (``itertag``).  Receives the response and an XPathSelector for each node.
    Overriding this method is mandatory. Otherwise, you spider won't work.
    This method must return either a ScrapedItem, a Request, or a list
    containing any of them.

    .. warning:: This method will soon change its name to ``parse_node``

.. method:: XMLFeedSpider.process_results(response, results)
   
    This method is called for each result (item or request) returned by the
    spider, and it's intended to perform any last time processing required
    before returning the results to the framework core, for example setting the
    item IDs. It receives a list of results and the response which originated
    that results. It must return a list of results (Items or Requests)."""


XMLFeedSpider example
---------------------

These spiders are pretty easy to use, let's have at one example::

    from scrapy import log
    from scrapy.contrib.spiders import XMLFeedSpider
    from scrapy.item import ScrapedItem

    class MySpider(XMLFeedSpider):
        domain_name = 'example.com'
        start_urls = ['http://www.example.com/feed.xml']
        iterator = 'iternodes' # This is actually unnecesary, since it's the default value
        itertag = 'item'

        def parse_item(self, response, node):
            log.msg('Hi, this is a <%s> node!: %s' % (self.itertag, ''.join(node.extract())))

            item = ScrapedItem()
            item.id = node.x('@id').extract()
            item.name = node.x('name').extract()
            item.description = node.x('description').extract()
            return item

    SPIDER = MySpider()

Basically what we did up there was creating a spider that downloads a feed from
the given ``start_urls``, and then iterates through each of its ``item`` tags,
prints them out, and stores some random data in ScrapedItems.

CSVFeedSpider
=============

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
---------------------

Let's see an example similar to the previous one, but using CSVFeedSpider::

    from scrapy import log
    from scrapy.contrib.spiders import CSVFeedSpider
    from scrapy.item import ScrapedItem

    class MySpider(CSVFeedSpider):
        domain_name = 'example.com'
        start_urls = ['http://www.example.com/feed.csv']
        delimiter = ';'
        headers = ['id', 'name', 'description']

        def parse_row(self, response, row):
            log.msg('Hi, this is a row!: %r' % row)

            item = ScrapedItem()
            item.id = row['id']
            item.name = row['name']
            item.description = row['description']
            return item

    SPIDER = MySpider()


