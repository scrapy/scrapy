.. _spiders:

Spiders
=======

Spiders are user written classes which define how a certain site (or domain)
will be scraped; including how to crawl the site and how to scrape :ref:`Items
<items>` from their pages. 

All Spiders must be descendant of :class:`~scrapy.spider.BaseSpider` or any
subclass of it, below you can see a list of available Spiders in Scrapy.

.. _spiders-ref:

Available Spiders
=================

.. module:: scrapy.spider

BaseSpider
----------

.. autoclass:: BaseSpider(object)
   :members:

   .. attribute:: domain_name

      A string which defines the domain name for this spider, which will also
      be the unique identifier for this spider (which means you can't have two
      spider with the same :attr:`domain_name`). This is the most important
      spider attribute and it's required, and it's the name by which Scrapy
      will known the spider. 

   .. attribute:: extra_domain_names

      An optional list of strings containing additional domains that this
      spider is allowed to crawl. Requests for URLs not belonging to the domain
      name specified in :attr:`domain_name` or this list won't be followed.

   .. attribute:: start_urls

      Is a list of URLs where the spider will begin to crawl from, when no
      particular URLs are specified. So, the first pages downloaded will be
      those listed here. The subsequent URLs will be generated successively
      from data contained in the start URLs.

BaseSpider example
^^^^^^^^^^^^^^^^^^

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
-----------

.. autoclass:: CrawlSpider(BaseSpider)
   :members:

   .. attribute:: CrawlSpider.rules

      Which is a list of one (or more) :class:`Rule` objects.  Each
      :class:`Rule` defines a certain behaviour for crawling the site. Rules
      objects are described below.
    
Crawling rules
^^^^^^^^^^^^^^

.. autoclass:: Rule(link_extractor, callback=None, cb_kwargs=None, follow=None, process_links=None)

CrawlSpider example
^^^^^^^^^^^^^^^^^^^

Let's now take a look at an example CrawlSpider with Rules::

    from scrapy import log
    from scrapy.contrib.spiders import CrawlSpider, Rule
    from scrapy.link.extractors import RegexLinkExtractor
    from scrapy.xpath.selector import HtmlXPathSelector
    from scrapy.item import ScrapedItem

    class MySpider(CrawlSpider):
        domain_name = 'example.com'
        start_urls = ['http://www.example.com']
        
        rules = (
            # Extract links matching 'category.php' (but not matching 'subsection.php')
            # and follow links from them (since no callback means follow=True by default).
            Rule(RegexLinkExtractor(allow=('category\.php', ), deny=('subsection\,php', ))),

            # Extract links matching 'item.php' and parse them with the spider's method parse_item
            Rule(RegexLinkExtractor(allow=('item\.php', )), callback='parse_item'),
        )

        def parse_item(self, response):
            log.msg('Hi, this is an item page! %s' % response.url)

            hxs = HtmlXPathSelector(response)
            item = ScrapedItem()
            item.attribute('id', hxs.x('//td[@id="item_id"]/text()').re(r'ID: (\d+)'))
            item.attribute('name', hxs.x('//td[@id="item_name"]/text()'))
            item.attributE('description', hxs.x('//td[@id="item_description"]/text()'))
            return [item]

    SPIDER = MySpider()

This spider would start crawling example.com's home page, collecting category
links, and item links, parsing the latter with the *parse_item* method. For
each item response, some data will be extracted from the HTML using XPath, and
a ScrapedItem will be filled with it.

XMLFeedSpider
-------------

.. autoclass:: XMLFeedSpider(BaseSpider)
   :members:

   .. attribute:: iterator

      A string which defines the iterator to use. It can be either:

      * 'iternodes':  a fast iterator based on regular expressions 

      * 'html': an iterator which uses HtmlXPathSelector. Keep in mind this
        uses DOM parsing and must load all DOM in memory which could be a
        problem for big feeds

      * 'xml': an iterator which uses XmlXPathSelector. Keep in mind this uses
        DOM parsing and must load all DOM in memory which could be a problem
        for big feeds

      It defaults to: 'iternodes'.

   .. attribute:: itertag

      A string with the name of the node (or element) to iterate in.


XMLFeedSpider example
^^^^^^^^^^^^^^^^^^^^^

These spiders are pretty easy to use, let's have at one example::

    from scrapy import log
    from scrapy.contrib.spiders import XMLFeedSpider
    from scrapy.item import ScrapedItem

    class MySpider(XMLFeedSpider):
        domain_name = 'example.com'
        start_urls = ['http://www.example.com/feed.xml']
        iterator = 'iternodes' # This is actually unnecesary, since it's the default value
        itertag = 'item'

        def parse_nodes(self, response, node):
            log.msg('Hi, this is a <%s> node!: %s' % (self.itertag, ''.join(node.extract())))

            item = ScrapedItem()
            item.attribute('id', node.x('@id'))
            item.attribute('name', node.x('name'))
            item.attribute('description', node.x('description'))
            return item

    SPIDER = MySpider()

Basically what we did up there was creating a spider that downloads a feed from
the given ``start_urls``, and then iterates through each of its ``item`` tags,
prints them out, and stores some random data in ScrapedItems.

CSVFeedSpider
-------------

.. warning:: The API of the CSVFeedSpider is not yet stable. Use with caution.

.. autoclass:: CSVFeedSpider(BaseSpider)
   :members:

   .. attribute:: CSVFeedSpider.delimiter

      A string with the separator character for each field in the CSV file
      Defaults to ``','`` (comma).

   .. attribute:: CSVFeedSpider.headers
   
      A list of the rows contained in the file CSV feed which will be used for
      extracting fields from it.

CSVFeedSpider example
^^^^^^^^^^^^^^^^^^^^^

Let's see an example similar to the previous one, but using CSVFeedSpider::

    from scrapy import log
    from scrapy.contrib.spiders import CSVFeedSpider
    from scrapy.item import ScrapedItem

    class MySpider(CSVFeedSpider):
        domain_name = 'example.com'
        start_urls = ['http://www.example.com/feed.csv']
        delimiter = ';'
        headers = ['id', 'name', 'description']

        def parse_rows(self, response, row):
            log.msg('Hi, this is a row!: %r' % row)

            item = ScrapedItem()
            item.attribute('id', row['id'])
            item.attribute('name', row['name'])
            item.attribute('description', row['description'])
            return item

    SPIDER = MySpider()

