.. _topics-spiders:

=======
Spiders
=======

.. module:: scrapy.spider

| Spiders are modules whose purpose is to scrape information from a certain domain.
| It's there where you'll define the behaviour regarding the crawling and parsing processes, and where most of the action takes part, actually.

In spiders, the scraping cycle goes through something like:

1. Request for information.
2. Find what you were looking for in the response you got.
3. Adapt it (or not).
4. Create items containing your scraped data.
5. Store them (or print them, or whatever you want to do with them).

| Now, this cycle starts by an entry point which you specify in the spider itself, and it's the first piece of information that you ask for.
  The ``start_urls`` and ``start_requests`` class attributes.
| These attributes are expressed as lists containing either URLs as strings (for the ``start_urls``), or Request instances (for ``start_requests``).
| It's not mandatory that you assign both attributes, but you should specify at least one of them.

Another attribute that you must assign is ``domain_name``, which is nothing but a string containing the domain name of the site you're scraping.
You have to you specify these attributes, because it's the way Scrapy knows which site is it crawling an where to start scraping from.

Now, although the previous applies for any kind of spider, there are different types of spiders, with different behaviours, let's check them out:

BaseSpider
----------

.. class:: BaseSpider

| This is the simplest available spider, and from which inherit any other spiders (either the ones that come built-in with Scrapy, or the ones users could make).
| It doesn't provide any special functionality. It just requests the given ``start_urls``/``start_requests``, and calls the spider's method ``parse`` for each of the resulting responses.

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

.. class:: CrawlSpider

| This is the most commonly used spider, and it's the one who crawls over HTML pages, extracts links from there (given certain rules of extraction), and scrapes items from
  there.
| This spider is a bit more complicated than the previous one, because it introduces a few new concepts, but you'll probably find it useful.
| 
| Apart from the attributes inherited from BaseSpider (that you **must** specify), this class provides you with a new attribute: ``rules``.
| This one is a tuple containing one or more ``Rule`` objects.
| Each ``Rule`` defines a certain behaviour for crawling the site, by the following parameters (the ones between [ ] are optional):

* link_extractor: A ``LinkExtractor`` instance, the one that will take care of extracting urls from each response (i'll explain this further).
* [callback]: A callable, or a string (in which case a method from the spider class with that name will be used) to be called for each link extracted
  with the link_extractor. This callback must always return a list, which can contain both ScrapedItems (or any descendant), and Requests.
* [cb_kwargs]: A dictionary containing the keyword arguments to be passed to the callback function.
* [follow]: A boolean defining whether links should be followed from each response extracted with this rule or not. If callback was specified, defaults
  to False, else defaults to True.
* [process_links]: A callable, or a string (applying the same as in the callback) to be called with each set of links extracted from each response with
  the link_extractor (mainly for filtering purposes).

LinkExtractors
^^^^^^^^^^^^^^

| LinkExtractors are objects designed -obviously- for extracting links from web pages.
| There are currently only two different LinkExtractors available in Scrapy: ``LinkExtractor`` and ``RegexLinkExtractor``.
| The first one extracts links from a response with the given tag names and attributes. It doesn't do any other filtering.
| RegexLinkExtractors, however, extract links from a response by applying several filters that you can specify, mostly regular expressions that match (or not)
  the extracted links.
| These are the parameters that LinkExtractors may receive when instanciating them:

.. class:: scrapy.link.LinkExtractor

    * tag: Can be either a tag name in a string, or a function that receives a tag name and returns True if links should be extracted from it, or False if they
      shouldn't. Defaults to 'a'.
    * attr: The same as in ``tag``, for attribute names.
    * unique: A boolean that decides whether links with the same url should be extracted only once or not.

.. class:: scrapy.link.extractors.RegexLinkExtractor

    * tag: The same purpose as in LinkExtractor.
    * attr: The same purpose as in LinkExtractor.
    * unique: The same purpose as in LinkExtractor.
    * allow: A list of regular expressions that the (absolute) urls must match in order to be extracted.
    * deny: A list of regular expressions that makes any url matching them be ignored.
    * allow_domains: A list of domains from which to extract urls.
    * deny_domains: A list of domains to not extract urls from.
    * restrict_xpaths: Only extract links from the areas inside the provided xpaths (in a list).
    * tags: List of tags to extract links from. Defaults to ('a', 'area').
    * attrs: List of attributes to extract links from. Defaults to ('href', )
    * canonicalize: Canonicalize each extracted url (using scrapy.utils.url.canonicalize_url). Defaults to True.

| The only public method that every LinkExtractor has is ``extract_links``, which always receives a response, independently of which LinkExtractor are you using.
  This method should be called by you in case you want to extract links from a response yourself.
| In the case of rules, however, you'll only have to define your rules with the corresponding LinkExtractors,
  and the CrawlSpider will take care of extracting them for each response arriving.

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
            item.attribute('id', hxs.x('//td[@id="item_id"]/text()').re(r'ID: (\d+)'))
            item.attribute('name', hxs.x('//td[@id="item_name"]/text()'))
            item.attributE('description', hxs.x('//td[@id="item_description"]/text()'))
            return [item]

    SPIDER = MySpider()


This spider would start crawling example.com's home page, collecting category links, and item links, parsing the latter with the *parse_item* method.
For each item response, some data will be extracted from the HTML using XPath, and a ScrapedItem will be filled with it.

Feed Spiders
-------------

XMLFeedSpider
^^^^^^^^^^^^^

.. class:: XMLFeedSpider

XMLFeedSpider is designed for parsing XML feeds by iterating through them by a certain node name.
The iterator can be chosen from: ``iternodes``, ``xml``, and ``html``.
It's recommended to use the ``iternodes`` iterator for performance reasons, since the ``xml``
and ``html`` iterators generate the whole DOM at once in order to parse it.
However, using ``html`` as the iterator may be useful when parsing XML with bad markup.

For setting the iterator and the tag name, you must define the class attributes
``iterator`` and ``itertag``.
The default values are ``iternodes`` for ``iterator``, and ``item`` for ``itertag``.

Apart from these new attributes, this spider has some new overrideable methods too:

* adapt_response: used for modifying the response and/or its body before parsing it.
  Receives a response and returns another one.
* parse_item: the method to be called for the nodes matching the provided tag name (``itertag``).
  Receives the response and an XPathSelector for each node.
  Overriding this method is mandatory. If not, the spider won't work.
  This method must return either a ScrapedItem, a Request, or a list containing any of them.
* process_results: this method will be called after each call of parse_node, with a response
  and the parsing list of results.

These spiders are pretty easy to use, let's have a look::

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
            item.attribute('id', node.x('@id'))
            item.attribute('name', node.x('name'))
            item.attribute('description', node.x('description'))
            return item

    SPIDER = MySpider()

Basically what we did up there was creating a spider that downloads a feed from the given ``start_urls``,
iterates through each of its 'item' tags, prints them out, and stores some random data in ScrapedItems.

CSVFeedSpider
^^^^^^^^^^^^^

.. class:: CSVFeedSpider

This spider is very similar to the XMLFeedSpider, although it iterates through rows, instead of nodes.
It also has other two different attributes: ``delimiter``, and ``headers``.
The ``delimiter`` is a string representing the limit between each field in the CSV file,
while the ``headers`` are an ordered list of field names (in strings) that the file contains.

The default ``delimiter`` is the same as in Python's csv module, a `,` (comma), while the ``headers`` parameter,
if not specified, is tried to be found out.

In this case, the method that gets called in each row iteration is called ``parse_row`` instead of ``parse_item`` (as it was in XMLFeedSpider),
and receives a response and a dictionary (representing each row) with a key for each provided (or detected) header of the CSV file.
This spider also gives the opportunity to override ``adapt_response`` and ``process_results`` methods for pre/post-processing purposes.

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
            item.attribute('id', row['id'])
            item.attribute('name', row['name'])
            item.attribute('description', row['description'])
            return item

    SPIDER = MySpider()


