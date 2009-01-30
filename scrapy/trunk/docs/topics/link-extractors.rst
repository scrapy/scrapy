.. _topics-link-extractors:

===============
Link Extractors
===============

.. module:: scrapy.link

LinkExtractors are objects whose purpose is to extract links from web pages.
They're used in the :class:`~scrapy.contrib.spiders.CrawlSpider`, for defining
crawling rules, among other places.

There are two different LinkExtractors available in Scrapy by default, but you
create your own custom Link Extractor to suit your needs.

The only public method that every LinkExtractor has is ``extract_links``, which
always receives a response, independently of which LinkExtractor are you using.
This method should be called by you in case you want to extract links from a
response yourself. In the case of rules, however, you'll only have to define
your rules with the corresponding LinkExtractors, and the CrawlSpider will take
care of extracting them for each response arriving.

See :ref:`ref-link-extractors` for the list of available built-in Link
Extractors.

