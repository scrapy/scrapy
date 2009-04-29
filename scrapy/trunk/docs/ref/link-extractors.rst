.. _ref-link-extractors:

=========================
Available Link Extractors
=========================

.. module:: scrapy.link
   :synopsis: Link extractors classes

LinkExtractor
=============

.. class:: LinkExtractor(tag="a", href="href", unique=False)

    This is the most basic Link Extractor which extracts links from a response with
    by looking at the given attributes inside the given tags.

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

RegexLinkExtractor
==================

.. class:: RegexLinkExtractor(allow=(), deny=(), allow_domains=(), deny_domains=(), restrict_xpaths(), tags=('a', 'area'), attrs=('href'), canonicalize=True, unique=True)

    The RegexLinkExtractor extends the base :class:`LinkExtractor` by providing
    additional filters that you can specify to extract links, including regular
    expressions patterns that the links must match to be extracted. All those
    filters are configured through these constructor paramters:

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

