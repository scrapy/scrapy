.. _topics-link-extractors:

===============
Link Extractors
===============

LinkExtractors are objects whose only purpose is to extract links from web
pages (:class:`scrapy.http.Response` objects) which will be eventually
followed.

There are two Link Extractors available in Scrapy by default, but you create
your own custom Link Extractors to suit your needs by implanting a simple
interface.

The only public method that every LinkExtractor have is ``extract_links``,
which receives a :class:`~scrapy.http.Response` object and returns a list
of links. Link Extractors are meant to be instantiated once and their
``extract_links`` method called several times with different responses, to
extract links to follow. 

Link extractors are used in the :class:`~scrapy.contrib.spiders.CrawlSpider`
class (available in Scrapy), through a set of rules, but you can also use it in
your spiders even if you don't subclass from
:class:`~scrapy.contrib.spiders.CrawlSpider`, as its purpose is very simple: to
extract links.

See :ref:`ref-link-extractors` for the list of available built-in Link
Extractors, including some examples.

