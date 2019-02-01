.. _topics-link-extractors:

===============
Link Extractors
===============

Link extractors are objects whose only purpose is to extract links from web
pages (:class:`scrapy.http.Response` objects) which will be eventually
followed.

There is ``scrapy.linkextractors.LinkExtractor`` available
in Scrapy, but you can create your own custom Link Extractors to suit your
needs by implementing a simple interface.

The only public method that every link extractor has is ``extract_links``,
which receives a :class:`~scrapy.http.Response` object and returns a list
of :class:`scrapy.link.Link` objects. Link extractors are meant to be
instantiated once and their ``extract_links`` method called several times
with different responses to extract links to follow.

Link extractors are used in the :class:`~scrapy.spiders.CrawlSpider`
class (available in Scrapy), through a set of rules, but you can also use it in
your spiders, even if you don't subclass from
:class:`~scrapy.spiders.CrawlSpider`, as its purpose is very simple: to
extract links.


.. _topics-link-extractors-ref:

Built-in link extractors reference
==================================

.. module:: scrapy.linkextractors
   :synopsis: Link extractors classes

Link extractors classes bundled with Scrapy are provided in the
:mod:`scrapy.linkextractors` module.

The default link extractor is ``LinkExtractor``, which is the same as
:class:`~.LxmlLinkExtractor`::

    from scrapy.linkextractors import LinkExtractor

There used to be other link extractor classes in previous Scrapy versions,
but they are deprecated now.

LxmlLinkExtractor
-----------------

.. module:: scrapy.linkextractors.lxmlhtml
   :synopsis: lxml's HTMLParser-based link extractors

.. autoclass:: LxmlLinkExtractor
