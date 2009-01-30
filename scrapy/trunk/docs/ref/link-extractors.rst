.. _ref-link-extractors:

=========================
Available Link Extractors
=========================

LinkExtractor
=============

.. class:: LinkExtractor(tag="a", href="href", unique=False)

This is the most basic Link Extractor which extracts links from a response with
by looking at the given attributes inside the given tags.

``tag`` is either a string (with the name of a tag) or a function that receives
a tag name and returns True if links should be extracted from it, or False if
they shouldn't. Defaults to 'a'.

``attr`` is either a string (with the name of an tag attribute), or a function
that receives a an attribute name and returns True if links should be extracted from it, or False if the shouldn't. 

``unique`` is a boolean that specifies if a duplicate filtering should be
applied to links extracted.

RegexLinkExtractor
==================

.. class:: RegexLinkExtractor(allow=(), deny=(), allow_domains=(), deny_domains=(), restrict_xpaths(), tags=('a', 'area'), attrs=('href'), canonicalize=True, unique=True)

This Link Extractor extracts links from a response by applying several filters
that you can specify, including regular expressions that match (or don't match)
the extracted links.  These parameters are configured when instantiating the
RegexLinkExtractor object.

``allow`` is a list of regular expressions that the (absolute) urls must match
in order to be extracted.  deny: A list of regular expressions that makes any
url matching them be ignored.  allow_domains: A list of domains from which to
extract urls.  deny_domains: A list of domains to not extract urls from.
restrict_xpaths: Only extract links from the areas inside the provided xpaths
(in a list).  tags: List of tags to extract links from. Defaults to ('a',
'area').  attrs: List of attributes to extract links from. Defaults to ('href',
) canonicalize: Canonicalize each extracted url (using
scrapy.utils.url.canonicalize_url). Defaults to True.

``allow_domains`` is a list of string containing domains which will be
considered for extracting the links

``deny_domains`` is a list of strings containing domains which which won't be
considered for extracting the links

``restrict_xpaths`` is a list of string with XPath's. If specified, links will
only be looked inside the sections of the pages specified by those XPaths.

``tags`` is an iterable with the name of the tags where links should be extracted from

``attrs`` is an interable with the name of the attributes where links should be extracted from

``unique`` is a boolean that specifies if a duplicate filtering should be
applied to links extracted.

