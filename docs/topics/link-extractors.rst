.. _topics-link-extractors:

===============
Link Extractors
===============

LinkExtractors are objects whose only purpose is to extract links from web
pages (:class:`scrapy.http.Response` objects) which will be eventually
followed.

There are two Link Extractors available in Scrapy by default, but you create
your own custom Link Extractors to suit your needs by implementing a simple
interface.

The only public method that every LinkExtractor has is ``extract_links``,
which receives a :class:`~scrapy.http.Response` object and returns a list
of :class:`scrapy.link.Link` objects. Link Extractors are meant to be instantiated once and their
``extract_links`` method called several times with different responses, to
extract links to follow. 

Link extractors are used in the :class:`~scrapy.contrib.spiders.CrawlSpider`
class (available in Scrapy), through a set of rules, but you can also use it in
your spiders, even if you don't subclass from
:class:`~scrapy.contrib.spiders.CrawlSpider`, as its purpose is very simple: to
extract links.


.. _topics-link-extractors-ref:

Built-in link extractors reference
==================================

.. module:: scrapy.contrib.linkextractors
   :synopsis: Link extractors classes

All available link extractors classes bundled with Scrapy are provided in the
:mod:`scrapy.contrib.linkextractors` module.

.. module:: scrapy.contrib.linkextractors.sgml
   :synopsis: SGMLParser-based link extractors

SgmlLinkExtractor
-----------------

.. class:: SgmlLinkExtractor(allow=(), deny=(), allow_domains=(), deny_domains=(), deny_extensions=None, restrict_xpaths=(), tags=('a', 'area'), attrs=('href'), canonicalize=True, unique=True, process_value=None)

    The SgmlLinkExtractor extends the base :class:`BaseSgmlLinkExtractor` by
    providing additional filters which exclude links from extraction.
    All those filters are configured through these constructor
    parameters:

    :param allow: If not empty, absolute urls must match at least one of
        the regular expressions to be extracted.
    :type allow: a regular expression (or a list of regular expressions)

    :param deny: If not empty, absolute urls must not match any of the
        regular expressions to be extracted.
    :type deny: a regular expression (or a list of regular expressions)

    :param allow_domains: If not empty, urls must be from at least one
        of the domains to be extracted.
    :type allow_domains: string (or a list of string)

    :param deny_domains: If not empty, urls must not be from any of the
        domains to be extracted.
    :type deny_domains: string (or a list of strings)

    :param deny_extensions: a single value or list of strings containing
        extensions that should be ignored when extracting links. 
        If not given, it will default to the
        ``IGNORED_EXTENSIONS`` list defined in the `scrapy.linkextractor`_
        module.
    :type deny_extensions: list

    :param restrict_xpaths: is a XPath (or list of XPath's) which defines
        regions inside the response where links should be extracted from. 
        If given, only the text selected by those XPath will be scanned for
        links. See examples below.
    :type restrict_xpaths: str or list

    :param tags: a tag or a list of tags to consider when extracting links.
        Defaults to ``('a', 'area')``.
    :type tags: str or list

    :param attrs: an attribute or list of attributes which should be considered when looking
        for links to extract (only for those tags specified in the ``tags``
        parameter). Defaults to ``('href',)``
    :type attrs: list

    :param canonicalize: canonicalize each extracted url (using
        scrapy.utils.url.canonicalize_url). Defaults to ``True``.
    :type canonicalize: boolean

    :param unique: whether duplicate filtering should be applied to extracted
        links.
    :type unique: boolean

    :param process_value: see ``process_value`` argument of
        :class:`BaseSgmlLinkExtractor` class constructor
    :type process_value: callable

BaseSgmlLinkExtractor
---------------------

.. class:: BaseSgmlLinkExtractor(tag="a", attr="href", unique=False, process_value=None)

    The purpose of this Link Extractor is only to serve as a base class for the
    :class:`SgmlLinkExtractor`. You should use that one instead.
    
    The constructor arguments are:

    :param tag: either a string (with the name of a tag) or a function that
       receives a tag name and returns ``True`` if links should be extracted from
       that tag, or ``False`` if they shouldn't. Defaults to ``'a'``.  request
       (once it's downloaded) as its first parameter. For more information, see
       :ref:`topics-request-response-ref-request-callback-arguments`.
    :type tag: str or callable

    :param attr:  either string (with the name of a tag attribute), or a
        function that receives an attribute name and returns ``True`` if
        links should be extracted from it, or ``False`` if they shouldn't.
        Defaults to ``href``.
    :type attr: str or callable

    :param unique: is a boolean that specifies if a duplicate filtering should
        be applied to links extracted.
    :type unique: boolean

    :param process_value: a function which receives each value extracted from
        the tag and attributes scanned and can modify the value and return a
        new one, or return ``None`` to ignore the link altogether. If not
        given, ``process_value`` defaults to ``lambda x: x``.

        .. highlight:: html

        For example, to extract links from this code::

            <a href="javascript:goToPage('../other/page.html'); return false">Link text</a>
        
        .. highlight:: python

        You can use the following function in ``process_value``::
        
            def process_value(value):
                m = re.search("javascript:goToPage\('(.*?)'", value)
                if m:
                    return m.group(1) 

    :type process_value: callable

.. _scrapy.linkextractor: https://github.com/scrapy/scrapy/blob/master/scrapy/linkextractor.py
