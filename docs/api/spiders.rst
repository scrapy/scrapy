===========
Spiders API
===========

.. _topics-spiders-ref:

Spiders
=======

.. class:: scrapy.spiders.Spider
.. autoclass:: scrapy.Spider
   :members:

.. autoclass:: scrapy.spiders.Rule
   :members:

.. autoclass:: scrapy.spiders.CrawlSpider
   :members:

.. autoclass:: scrapy.spiders.CSVFeedSpider
   :members:

.. autoclass:: scrapy.spiders.SitemapSpider
   :members:

.. autoclass:: scrapy.spiders.XMLFeedSpider
   :members:


Spider Contracts
================

.. autoclass:: scrapy.contracts.Contract

    ..
        These are method that may or may not be defined in subclasses. That is
        why they are documented where instead of in the sources.

    .. method:: pre_process(response)

        This allows hooking in various checks on the response received from the
        sample request, before it's being passed to the callback.

    .. method:: post_process(output)

        This allows processing the output of the callback. Iterators are
        converted listified before being passed to this hook.

.. automodule:: scrapy.contracts.default
   :members:


.. _robots.txt: http://www.robotstxt.org/
.. _Sitemap index files: https://www.sitemaps.org/protocol.html#index
.. _Sitemaps: https://www.sitemaps.org/index.html
.. _TLD: https://en.wikipedia.org/wiki/Top-level_domain
