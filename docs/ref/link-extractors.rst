.. _ref-link-extractors:

=========================
Available Link Extractors
=========================

.. module:: scrapy.contrib.linkextractors
   :synopsis: Link extractors classes

All available link extractors classes bundled with Scrapy are provided in the
:mod:`scrapy.contrib.linkextractors` module.

.. module:: scrapy.contrib.linkextractors.sgml
   :synopsis: SGMLParser-based link extractors

SgmlLinkExtractor
=================

.. class:: SgmlLinkExtractor(allow=(), deny=(), allow_domains=(), deny_domains=(), restrict_xpaths(), tags=('a', 'area'), attrs=('href'), canonicalize=True, unique=True, process_value=None)

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
    :type allow: a regular expression (or list of)

    :param allow_domains: is single value or a list of string containing
        domains which will be considered for extracting the links
    :type allow: str or list

    :param deny_domains: is single value or a list of strings containing
        domains which which won't be considered for extracting the links
    :type allow: str or list

    :param restrict_xpaths: is a XPath (or list of XPath's) which defines
        regions inside the response where links should be extracted from. 
        If given, only the text selected by those XPath will be scanned for
        links. See examples below.
    :type restrict_xpaths: str or list

    :param tags: a tag or a list of tags to consider when extracting links.
        Defaults to ``('a', 'area')``.
    :type tags: str or list

    :param attrs: list of attrbitues which should be considered when looking
        for links to extract (only for those tags specified in the ``tags``
        parameter). Defaults to ``('href',)``
    :type attrs: boolean

    :param canonicalize: canonicalize each extracted url (using
        scrapy.utils.url.canonicalize_url). Defaults to ``True``.
    :type canonicalize: boolean

    :param unique: whether duplicate filtering should be applied to extracted
        links.
    :type unique: boolean

    :param process_value: see ``process_value`` argument of
        :class:`LinkExtractor` class constructor
    :type process_value: boolean

BaseSgmlLinkExtractor
=====================

.. class:: BaseSgmlLinkExtractor(tag="a", href="href", unique=False, process_value=None)

    The purpose of this Link Extractor is only to serve as a base class for the
    :class:`SgmlLinkExtractor`. You should use that one instead.
    
    The constructor arguments are:

    :param tag: either a string (with the name of a tag) or a function that
        receives a tag name and returns ``True`` if links should be extracted
        from those tag, or ``False`` if they shouldn't. Defaults to ``'a'``.
        request (once its downloaded) as its first parameter. For more
        information see :ref:`ref-request-callback-arguments` below.
    :type tag: str or callable

    :param attr:  either string (with the name of a tag attribute), or a
        function that receives a an attribute name and returns ``True`` if
        links should be extracted from it, or ``False`` if the shouldn't.
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

