.. _topics-selectors:

=========
Selectors
=========

When you're scraping web pages, the most common task you need to perform is
to extract data from the HTML source. There are several libraries available to
achieve this: 

 * `BeautifulSoup`_ is a very popular screen scraping library among Python
   programmers which constructs a Python object based on the
   structure of the HTML code and also deals with bad markup reasonably well,
   but it has one drawback: it's slow.

 * `lxml`_ is a XML parsing library (which also parses HTML) with a pythonic
   API based on `ElementTree`_ (which is not part of the Python standard
   library).

Scrapy comes with its own mechanism for extracting data. They're called XPath
selectors (or just "selectors", for short) because they "select" certain parts
of the HTML document specified by `XPath`_ expressions.

`XPath`_ is a language for selecting nodes in XML documents, which can also be used with HTML.

Both `lxml`_ and Scrapy Selectors are built over the `libxml2`_ library, which
means they're very similar in speed and parsing accuracy.

This page explains how selectors work and describes their API which is very
small and simple, unlike the `lxml`_ API which is much bigger because the
`lxml`_ library can be used for many other tasks, besides selecting markup
documents.

For a complete reference of the selectors API see the :ref:`XPath selector
reference <topics-selectors-ref>`.

.. _BeautifulSoup: http://www.crummy.com/software/BeautifulSoup/
.. _lxml: http://codespeak.net/lxml/
.. _ElementTree: http://docs.python.org/library/xml.etree.elementtree.html
.. _libxml2: http://xmlsoft.org/
.. _XPath: http://www.w3.org/TR/xpath

Using selectors
===============

Constructing selectors
----------------------

There are two types of selectors bundled with Scrapy. Those are:

 * :class:`~scrapy.selector.HtmlXPathSelector` - for working with HTML documents

 * :class:`~scrapy.selector.XmlXPathSelector` - for working with XML documents

.. highlight:: python

Both share the same selector API, and are constructed with a Response object as
their first parameter. This is the Response they're going to be "selecting".

Example::

    hxs = HtmlXPathSelector(response) # a HTML selector
    xxs = XmlXPathSelector(response) # a XML selector

Using selectors with XPaths
---------------------------

To explain how to use the selectors we'll use the `Scrapy shell` (which
provides interactive testing) and an example page located in the Scrapy
documentation server:

    http://doc.scrapy.org/en/latest/_static/selectors-sample1.html

.. _topics-selectors-htmlcode:

Here's its HTML code:

.. literalinclude:: ../_static/selectors-sample1.html
   :language: html

.. highlight:: sh

First, let's open the shell::

    scrapy shell http://doc.scrapy.org/en/latest/_static/selectors-sample1.html

Then, after the shell loads, you'll have some selectors already instantiated and
ready to use.

Since we're dealing with HTML, we'll be using the
:class:`~scrapy.selector.HtmlXPathSelector` object which is found, by default, in
the ``hxs`` shell variable.

.. highlight:: python

So, by looking at the :ref:`HTML code <topics-selectors-htmlcode>` of that page,
let's construct an XPath (using an HTML selector) for selecting the text inside
the title tag::

    >>> hxs.select('//title/text()')
    [<HtmlXPathSelector (text) xpath=//title/text()>]

As you can see, the select() method returns an XPathSelectorList, which is a list of
new selectors. This API can be used quickly for extracting nested data. 

To actually extract the textual data, you must call the selector ``extract()``
method, as follows::

    >>> hxs.select('//title/text()').extract()
    [u'Example website']

Now we're going to get the base URL and some image links::

    >>> hxs.select('//base/@href').extract()
    [u'http://example.com/']

    >>> hxs.select('//a[contains(@href, "image")]/@href').extract()
    [u'image1.html',
     u'image2.html',
     u'image3.html',
     u'image4.html',
     u'image5.html']

    >>> hxs.select('//a[contains(@href, "image")]/img/@src').extract()
    [u'image1_thumb.jpg',
     u'image2_thumb.jpg',
     u'image3_thumb.jpg',
     u'image4_thumb.jpg',
     u'image5_thumb.jpg']


Using selectors with regular expressions
----------------------------------------

Selectors also have a ``re()`` method for extracting data using regular
expressions. However, unlike using the ``select()`` method, the ``re()`` method
does not return a list of :class:`~scrapy.selector.XPathSelector` objects, so you
can't construct nested ``.re()`` calls. 

Here's an example used to extract images names from the :ref:`HTML code
<topics-selectors-htmlcode>` above::

    >>> hxs.select('//a[contains(@href, "image")]/text()').re(r'Name:\s*(.*)')
    [u'My image 1',
     u'My image 2',
     u'My image 3',
     u'My image 4',
     u'My image 5']

.. _topics-selectors-nesting-selectors:

Nesting selectors
-----------------

The ``select()`` selector method returns a list of selectors, so you can call the
``select()`` for those selectors too. Here's an example::

    >>> links = hxs.select('//a[contains(@href, "image")]')
    >>> links.extract()
    [u'<a href="image1.html">Name: My image 1 <br><img src="image1_thumb.jpg"></a>',
     u'<a href="image2.html">Name: My image 2 <br><img src="image2_thumb.jpg"></a>',
     u'<a href="image3.html">Name: My image 3 <br><img src="image3_thumb.jpg"></a>',
     u'<a href="image4.html">Name: My image 4 <br><img src="image4_thumb.jpg"></a>',
     u'<a href="image5.html">Name: My image 5 <br><img src="image5_thumb.jpg"></a>']

    >>> for index, link in enumerate(links):
            args = (index, link.select('@href').extract(), link.select('img/@src').extract())
            print 'Link number %d points to url %s and image %s' % args

    Link number 0 points to url [u'image1.html'] and image [u'image1_thumb.jpg']
    Link number 1 points to url [u'image2.html'] and image [u'image2_thumb.jpg']
    Link number 2 points to url [u'image3.html'] and image [u'image3_thumb.jpg']
    Link number 3 points to url [u'image4.html'] and image [u'image4_thumb.jpg']
    Link number 4 points to url [u'image5.html'] and image [u'image5_thumb.jpg']

.. _topics-selectors-relative-xpaths:

Working with relative XPaths
----------------------------

Keep in mind that if you are nesting XPathSelectors and use an XPath that
starts with ``/``, that XPath will be absolute to the document and not relative
to the ``XPathSelector`` you're calling it from.

For example, suppose you want to extract all ``<p>`` elements inside ``<div>``
elements. First, you would get all ``<div>`` elements::

    >>> divs = hxs.select('//div')

At first, you may be tempted to use the following approach, which is wrong, as
it actually extracts all ``<p>`` elements from the document, not only those
inside ``<div>`` elements::

    >>> for p in divs.select('//p') # this is wrong - gets all <p> from the whole document
    >>>     print p.extract()

This is the proper way to do it (note the dot prefixing the ``.//p`` XPath)::

    >>> for p in divs.select('.//p') # extracts all <p> inside
    >>>     print p.extract()

Another common case would be to extract all direct ``<p>`` children::

    >>> for p in divs.select('p')
    >>>     print p.extract()

For more details about relative XPaths see the `Location Paths`_ section in the
XPath specification.

.. _Location Paths: http://www.w3.org/TR/xpath#location-paths


.. _topics-selectors-ref:

Built-in XPath Selectors reference
==================================

.. module:: scrapy.selector
   :synopsis: XPath selectors classes

There are two types of selectors bundled with Scrapy:
:class:`HtmlXPathSelector` and :class:`XmlXPathSelector`. Both of them
implement the same :class:`XPathSelector` interface. The only different is that
one is used to process HTML data and the other XML data.

XPathSelector objects
---------------------

.. class:: XPathSelector(response)

   A :class:`XPathSelector` object is a wrapper over response to select
   certain parts of its content.

   ``response`` is a :class:`~scrapy.http.Response` object that will be used
   for selecting and extracting data 

   .. method:: select(xpath)

       Apply the given XPath relative to this XPathSelector and return a list
       of :class:`XPathSelector` objects (ie. a :class:`XPathSelectorList`) with
       the result.

       ``xpath`` is a string containing the XPath to apply

   .. method:: re(regex)

       Apply the given regex and return a list of unicode strings with the
       matches.

       ``regex`` can be either a compiled regular expression or a string which
       will be compiled to a regular expression using ``re.compile(regex)``

   .. method:: extract()

       Return a unicode string with the content of this :class:`XPathSelector`
       object.

   .. method:: register_namespace(prefix, uri)

       Register the given namespace to be used in this :class:`XPathSelector`.
       Without registering namespaces you can't select or extract data from
       non-standard namespaces. See examples below.

   .. method:: remove_namespaces()

       Remove all namespaces, allowing to traverse the document using
       namespace-less xpaths. See example below.

   .. method:: __nonzero__()

       Returns ``True`` if there is any real content selected by this
       :class:`XPathSelector` or ``False`` otherwise.  In other words, the boolean
       value of an XPathSelector is given by the contents it selects. 

XPathSelectorList objects
-------------------------

.. class:: XPathSelectorList

   The :class:`XPathSelectorList` class is subclass of the builtin ``list``
   class, which provides a few additional methods.

   .. method:: select(xpath)

       Call the :meth:`XPathSelector.select` method for all :class:`XPathSelector`
       objects in this list and return their results flattened, as a new
       :class:`XPathSelectorList`.

       ``xpath`` is the same argument as the one in :meth:`XPathSelector.select`

   .. method:: re(regex)

       Call the :meth:`XPathSelector.re` method for all :class:`XPathSelector`
       objects in this list and return their results flattened, as a list of
       unicode strings.

       ``regex`` is the same argument as the one in :meth:`XPathSelector.re`

   .. method:: extract()

       Call the :meth:`XPathSelector.extract` method for all :class:`XPathSelector`
       objects in this list and return their results flattened, as a list of
       unicode strings.

   .. method:: extract_unquoted()

       Call the :meth:`XPathSelector.extract_unoquoted` method for all
       :class:`XPathSelector` objects in this list and return their results
       flattened, as a list of unicode strings. This method should not be applied
       to all kinds of XPathSelectors. For more info see
       :meth:`XPathSelector.extract_unoquoted`.

HtmlXPathSelector objects
-------------------------

.. class:: HtmlXPathSelector(response)

   A subclass of :class:`XPathSelector` for working with HTML content. It uses
   the `libxml2`_ HTML parser. See the :class:`XPathSelector` API for more info.

.. _libxml2: http://xmlsoft.org/

HtmlXPathSelector examples
~~~~~~~~~~~~~~~~~~~~~~~~~~

Here's a couple of :class:`HtmlXPathSelector` examples to illustrate several
concepts.  In all cases, we assume there is already an :class:`HtmlPathSelector`
instantiated with a :class:`~scrapy.http.Response` object like this::

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
------------------------

.. class:: XmlXPathSelector(response)

   A subclass of :class:`XPathSelector` for working with XML content. It uses
   the `libxml2`_ XML parser. See the :class:`XPathSelector` API for more info.

XmlXPathSelector examples
~~~~~~~~~~~~~~~~~~~~~~~~~

Here's a couple of :class:`XmlXPathSelector` examples to illustrate several
concepts.  In both cases we assume there is already an :class:`XmlXPathSelector`
instantiated with a :class:`~scrapy.http.Response` object like this::

      x = XmlXPathSelector(xml_response)

1. Select all ``<product>`` elements from a XML response body, returning a list of
   :class:`XPathSelector` objects (ie. a :class:`XPathSelectorList` object)::

      x.select("//product")

2. Extract all prices from a `Google Base XML feed`_ which requires registering
   a namespace::

      x.register_namespace("g", "http://base.google.com/ns/1.0")
      x.select("//g:price").extract()

.. _removing-namespaces:

Removing namespaces
~~~~~~~~~~~~~~~~~~~

When dealing with scraping projects, it is often quite convenient to get rid of
namespaces altogether and just work with element names, to write more
simple/convenient XPaths. You can use the
:meth:`XPathSelector.remove_namespaces` method for that.

Let's show an example that illustrates this with Github blog atom feed.

First, we open the shell with the url we want to scrape::

    $ scrapy shell https://github.com/blog.atom

Once in the shell we can try selecting all ``<link>`` objects and see that it
doesn't work (because the Atom XML namespace is obfuscating those nodes)::

    >>> xxs.select("//link")
    []

But once we call the :meth:`XPathSelector.remove_namespaces` method, all
nodes can be accessed directly by their names::

    >>> xxs.remove_namespaces()
    >>> xxs.select("//link")
    [<XmlXPathSelector xpath='//link' data=u'<link xmlns="http://www.w3.org/2005/Atom'>,
     <XmlXPathSelector xpath='//link' data=u'<link xmlns="http://www.w3.org/2005/Atom'>,
     ...

If you wonder why the namespace removal procedure is not always called, instead
of having to call it manually. This is because of two reasons which, in order
of relevance, are:

1. removing namespaces requires to iterate and modify all nodes in the
   document, which is a reasonably expensive operation to performs for all
   documents crawled by Scrapy

2. there could be some cases where using namespaces is actually required, in
   case some element names clash between namespaces. These cases are very rare
   though.

.. _Google Base XML feed: http://base.google.com/support/bin/answer.py?hl=en&answer=59461
