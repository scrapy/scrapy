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
   iterable containing either ScrapedItem or Requests, or both. Those Requests
   will also contain a callback (maybe the same) and will then be followed by
   downloaded by Scrapy and then their response handled to the specified
   callback.

3. In callback functions you parse the page contants, typically using
   :ref:`topics-selectors` (but you can also use BeautifuSoup, lxml or whatever
   mechanism you prefer) and generate items with the parsed data.

4. Finally the items returned from the spider will be typically persisted in
   some Item pipeline.

Even though this cycles applies (more or less) to any kind of spider, there are
different kind of default spiders bundled into Scrapy for different purposes.
We will talk about those types here.

See :ref:`ref-spiders` for the list of default spiders available in Scrapy.

