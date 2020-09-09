.. _topics-link:

====
Link
====

Link objects represent an extracted link by the :class:`~scrapy.linkextractors.lxmlhtml.LxmlLinkExtractor`.

The ``__init__`` method of
:class:`scrapy.link.Link` takes values that describe structure of the anchor tag that makes
up the link. :class:`LxmlLinkExtractor.extract_links
<scrapy.linkextractors.lxmlhtml.LxmlLinkExtractor.extract_links>` returns a
list of matching :class:`scrapy.link.Link` objects from a
:class:`~scrapy.http.Response` object.


Link
----

.. module:: scrapy.link
   :synopsis: Link from link extractors

.. autoclass:: Link

.. _scrapy.link: https://github.com/scrapy/scrapy/blob/master/scrapy/link.py
