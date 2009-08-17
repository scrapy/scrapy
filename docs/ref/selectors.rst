.. _ref-selectors:

===================
XPath Selectors API
===================

.. module:: scrapy.xpath
   :synopsis: XPath selectors classes

There are two types of selectors bundled with Scrapy:
:class:`HtmlXPathSelector` and :class:`XmlXPathSelector`. Both of them
implement the same :class:`XPathSelector` interface. The only different is that
one is used to process HTML data and the other XML data.

XPathSelector objects
=====================

.. class:: XPathSelector(response)

    A :class:`XPathSelector` object is a wrapper over response to select
    certain parts of its content.

    A :class:`Request` object represents an HTTP request, which is usually
    generated in the Spider and executed by the Downloader, and thus generating
    a :class:`Response`.
    
    ``url`` is a :class:`~scrapy.http.Response` object that will be used for
       selecting and extracting data 
   

XPathSelector Methods
---------------------

.. method:: XPathSelector.select(xpath)

    Apply the given XPath relative to this XPathSelector and return a list
    of :class:`XPathSelector` objects (ie. a :class:`XPathSelectorList`) with
    the result.

    ``xpath`` is a string containing the XPath to apply

.. method:: XPathSelector.re(regex)

    Apply the given regex and return a list of unicode strings with the
    matches.

    ``regex`` can be either a compiled regular expression or a string which
    will be compiled to a regular expression using ``re.compile(regex)``

.. method:: XPathSelector.extract()

    Return a unicode string with the content of this :class:`XPathSelector`
    object.

.. method:: XPathSelector.extract_unquoted()

    Return a unicode string with the content of this :class:`XPathSelector`
    without entities or CDATA. This method is intended to be use for text-only
    selectors, like ``//h1/text()`` (but not ``//h1``). If it's used for
    :class:`XPathSelector` objects which don't select a textual content (ie. if
    they contain tags), the output of this method is undefined.

.. method:: XPathSelector.register_namespace(prefix, uri)

    Register the given namespace to be used in this :class:`XPathSelector`.
    Without registering namespaces you can't select or extract data from
    non-standard namespaces. See examples below.

.. method:: XPathSelector.__nonzero__()

    Returns ``True`` if there is any real content selected by this
    :class:`XPathSelector` or ``False`` otherwise.  In other words, the boolean
    value of an XPathSelector is given by the contents it selects. 

XPathSelectorList objects
=========================

.. class:: XPathSelectorList

    The :class:`XPathSelectorList` class is subclass of the builtin ``list``
    class, which provides a few additional methods.


XPathSelectorList Methods
-------------------------

.. method:: XPathSelectorList.select(xpath)

    Call the :meth:`XPathSelector.re` method for all :class:`XPathSelector`
    objects in this list and return their results flattened, as new
    :class:`XPathSelectorList`.

    ``xpath`` is the same argument as the one in :meth:`XPathSelector.x`

.. method:: XPathSelector.re(regex)

    Call the :meth:`XPathSelector.re` method for all :class:`XPathSelector`
    objects in this list and return their results flattened, as a list of
    unicode strings.

    ``regex`` is the same argument as the one in :meth:`XPathSelector.re`

.. method:: XPathSelector.extract()

    Call the :meth:`XPathSelector.re` method for all :class:`XPathSelector`
    objects in this list and return their results flattened, as a list of
    unicode strings.

.. method:: XPathSelector.extract_unquoted()

    Call the :meth:`XPathSelector.extract_unoquoted` method for all
    :class:`XPathSelector` objects in this list and return their results
    flattened, as a list of unicode strings. This method should not be applied
    to all kinds of XPathSelectors. For more info see
    :meth:`XPathSelector.extract_unoquoted`.

HtmlXPathSelector objects
=========================

.. class:: HtmlXPathSelector(response)

   A subclass of :class:`XPathSelector` for working with HTML content. It uses
   the `libxml2`_ HTML parser. See the :class:`XPathSelector` API for more info.

.. _libxml2: http://xmlsoft.org/

HtmlXPathSelector examples
--------------------------

Here's a couple of :class:`HtmlXPathSelector` examples to illustrate several
concepts.  In all cases we assume there is already a :class:`HtmlPathSelector`
instanced with a :class:`~scrapy.http.Response` object like this::

      x = HtmlXPathSelector(html_response)

1. Select all ``<h1>`` elements from a HTML response body, returning a list of
   :class:`XPathSelector` objects (ie. a :class:`XPathSelectorList` object)::

      x.select("//h1")

2. Extract the text of all ``<h1>`` elements from a HTML response body,
   returning a list of unicode strings::

      x.select("//h1").extract()         # this includes the h1 tag
      x.select("//h1/text()").extract()  # this excludes the h1 tag

3. Iterate over all ``<p>`` tags and print their class attribute::

      for node in x.select("//p"):
      ...    print node.select("@href")

4. Extract textual data from all ``<p>`` tags without entities, as a list of
   unicode strings::

      x.select("//p/text()").extract_unquoted()

      # the following line is wrong. extract_unquoted() should only be used
      # with textual XPathSelectors
      x.select("//p").extract_unquoted()  # it may work but output is unpredictable

XmlXPathSelector objects
========================

.. class:: XmlXPathSelector(response)

   A subclass of :class:`XPathSelector` for working with XML content. It uses
   the `libxml2`_ XML parser. See the :class:`XPathSelector` API for more info.

XmlXPathSelector examples
-------------------------

Here's a couple of :class:`XmlXPathSelector` examples to illustrate several
concepts.  In all cases we assume there is already a :class:`XmlPathSelector`
instanced with a :class:`~scrapy.http.Response` object like this::

      x = HtmlXPathSelector(xml_response)

1. Select all ``<product>`` elements from a XML response body, returning a list of
   :class:`XPathSelector` objects (ie. a :class:`XPathSelectorList` object)::

      x.select("//h1")

2. Extract all prices from a `Google Base XML feed`_ which requires registering
   a namespace::

      x.register_namespace("g", "http://base.google.com/ns/1.0")
      x.select("//g:price").extract()

.. _Google Base XML feed: http://base.google.com/support/bin/answer.py?hl=en&answer=59461
