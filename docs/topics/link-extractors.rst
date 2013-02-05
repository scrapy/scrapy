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
of links. Link Extractors are meant to be instantiated once and their
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
    providing additional filters that you can specify to extract links,
    including regular expressions patterns that the links must match to be
    extracted. All those filters are configured through these constructor
    parameters:

    :param allow: a single regular expression (or list of regular expressions)
        that the (absolute) urls must match in order to be extracted. If not
        given (or empty), it will match all links.
    :type allow: a regular expression (or list of)

    :param deny: a single regular expression (or list of regular expressions)
        that the (absolute) urls must match in order to be excluded (ie. not
        extracted). It has precedence over the ``allow`` parameter. If not
        given (or empty) it won't exclude any links.
    :type deny: a regular expression (or list of)

    :param allow_domains: a single value or a list of string containing
        domains which will be considered for extracting the links
    :type allow_domains: str or list

    :param deny_domains: a single value or a list of strings containing
        domains which won't be considered for extracting the links
    :type deny_domains: str or list

    :param deny_extensions: a list of extensions that should be ignored when
        extracting links. If not given, it will default to the
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

    :param attrs: list of attributes which should be considered when looking
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
