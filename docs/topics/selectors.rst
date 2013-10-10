.. _topics-selectors:

=========
Selectors
=========

When you're scraping web pages, the most common task you need to perform is
to extract data from the HTML source. There are several libraries available to
achieve this:

 * `BeautifulSoup`_ is a very popular screen scraping library among Python
   programmers which constructs a Python object based on the structure of the
   HTML code and also deals with bad markup reasonably well, but it has one
   drawback: it's slow.

 * `lxml`_ is a XML parsing library (which also parses HTML) with a pythonic
   API based on `ElementTree`_ (which is not part of the Python standard
   library).

Scrapy comes with its own mechanism for extracting data. They're called
selectors because they "select" certain parts of the HTML document specified
either by `XPath`_ or `CSS`_ expressions.

`XPath`_ is a language for selecting nodes in XML documents, which can also be
used with HTML. `CSS`_ is a language for applying styles to HTML documents. It
defines selectors to associate those styles with specific HTML elements.

Scrapy selectors are built over the `lxml`_ library, which means they're very
similar in speed and parsing accuracy.

This page explains how selectors work and describes their API which is very
small and simple, unlike the `lxml`_ API which is much bigger because the
`lxml`_ library can be used for many other tasks, besides selecting markup
documents.

For a complete reference of the selectors API see :ref:`XPath selector
reference <topics-xpath-selectors-ref>` and :ref:`CSS selector reference
<topics-css-selectors-ref>`.

.. _BeautifulSoup: http://www.crummy.com/software/BeautifulSoup/
.. _lxml: http://codespeak.net/lxml/
.. _ElementTree: http://docs.python.org/library/xml.etree.elementtree.html
.. _cssselect: https://pypi.python.org/pypi/cssselect/
.. _XPath: http://www.w3.org/TR/xpath
.. _CSS: http://www.w3.org/TR/selectors

Using selectors
===============

Constructing selectors
----------------------

There are four types of selectors bundled with Scrapy. Those are:

 * :class:`~scrapy.selector.HtmlXPathSelector` - for working with HTML
   documents using XPath.

 * :class:`~scrapy.selector.XmlXPathSelector` - for working with XML documents
   using XPath.

 * :class:`~scrapy.selector.HtmlCSSSelector` - for working with HTML documents
   using CSS selectors.

 * :class:`~scrapy.selector.XmlCSSSelector` - for working with XML documents
   using CSS selectors.

.. highlight:: python

All of them share the same selector API, and are constructed with a Response
object as their first parameter. This is the Response they're going to be
"selecting".

Example::

    hcs = HtmlCSSSelector(response)   # an HTML CSS selector
    xxs = XmlXPathSelector(response)  # an XML XPath selector

Using selectors
---------------

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

Then, after the shell loads, you'll have some selectors already instantiated
and ready to use.

Since we're dealing with HTML, we can use either the
:class:`~scrapy.selector.HtmlXPathSelector` object which is found, by default,
in the ``hxs`` shell variable, or the equivalent
:class:`~scrapy.selector.HtmlCSSSelector` found in the ``hcs`` shell variable.

.. highlight:: python

So, by looking at the :ref:`HTML code <topics-selectors-htmlcode>` of that
page, let's construct an XPath (using an HTML selector) for selecting the text
inside the title tag::

    >>> hxs.select('//title/text()')
    [<HtmlXPathSelector (text) xpath=//title/text()>]

As you can see, the ``select()`` method returns an
:class:`~scrapy.selector.SelectorList`, which is a list of new selectors. This
API can be used quickly for extracting nested data.

To actually extract the textual data, you must call the selector ``extract()``
method, as follows::

    >>> hxs.select('//title/text()').extract()
    [u'Example website']

Now notice that CSS selectors can select text or attribute nodes using CSS3
pseudo-elements::

    >>> hcs.select('title::text')
    [<HtmlCSSSelector xpath='text()' data=u'Example website'>]
    >>> hcs.select('title::text').extract()
    [u'Example website']

Now we're going to get the base URL and some image links::

    >>> hxs.select('//base/@href').extract()
    [u'http://example.com/']

    >>> hcs.select('base::attr(href)').extract()
    [u'http://example.com/']

    >>> hxs.select('//a[contains(@href, "image")]/@href').extract()
    [u'image1.html',
     u'image2.html',
     u'image3.html',
     u'image4.html',
     u'image5.html']

    >>> hcs.select('a[href*=image]::attr(href)').extract()
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

    >>> hcs.select('a[href*=image] img::attr(src)').extract()
    [u'image1_thumb.jpg',
     u'image2_thumb.jpg',
     u'image3_thumb.jpg',
     u'image4_thumb.jpg',
     u'image5_thumb.jpg']

.. _topics-selectors-nesting-selectors:

Nesting selectors
-----------------

The ``select()`` selector method returns a list of selectors of the same type
(XPath or CSS), so you can call the ``select()`` for those selectors too.
Here's an example::

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

Using selectors with regular expressions
----------------------------------------

Selectors (both CSS and XPath) also have a ``re()`` method for extracting data
using regular expressions. However, unlike using the ``select()`` method, the
``re()`` method does not return a list of
:class:`Selector` objects, so you can't construct nested
``.re()`` calls.

Here's an example used to extract images names from the :ref:`HTML code
<topics-selectors-htmlcode>` above::

    >>> hxs.select('//a[contains(@href, "image")]/text()').re(r'Name:\s*(.*)')
    [u'My image 1',
     u'My image 2',
     u'My image 3',
     u'My image 4',
     u'My image 5']

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

Built-in Selectors reference
============================

.. module:: scrapy.selector
   :synopsis: Selectors classes

There are four types of selectors bundled with Scrapy:
:class:`HtmlXPathSelector` and :class:`XmlXPathSelector`,
:class:`HtmlCSSSelector` and :class:`XmlCSSSelector`.

All of them implement the same :class:`XPathSelector` interface. The only
differences are the selector syntax and whether it is used to process HTML data
or XML data.

Selector interface
------------------

.. class:: Selector(response)

   An instance implementing :class:`Selector` interface is a wrapper over
   ``response`` to select certain parts of its content.

   ``response`` is a :class:`~scrapy.http.Response` object that will be used
   for selecting and extracting data.

    .. method:: select(query)

        Find nodes matching the selection query and return the result as a
        :class:`SelectorList` instance with all elements flattened. List
        elements must implement :class:`Selector` interface too.

    .. method:: extract()

       Serialize and return the matched nodes as a list of unicode strings

   .. method:: __nonzero__()

       Returns ``True`` if there is any real content selected or ``False``
       otherwise.  In other words, the boolean value of a :class:`Selector` is
       given by the contents it selects.


SelectorList objects
--------------------

.. class:: SelectorList

   The :class:`SelectorList` class is subclass of the builtin ``list``
   class, which provides a few additional methods.

   .. method:: select(query)

       Call the ``select()`` method for each element in this list and return
       their results flattened as another :class:`SelectorList`.

       ``query`` is the same argument as the one in :meth:`Selector.select`

   .. method:: extract()

       Call the ``extract()`` method for each element is this list and return
       their results flattened, as a list of unicode strings.

   .. method:: __nonzero__()

        returns True if the list is not empty, False otherwise.


.. _topics-xpath-selectors-ref:

XPathSelector objects
---------------------

.. class:: XPathSelector(response)

   :class:`Selector` interface implementation that uses `XPath`_ query language
   to select content on ``response``

   ``response`` is a :class:`~scrapy.http.Response` object that will be used
   for selecting and extracting data.

   In the background, XPath selectors are powered by `lxml`_ library

   .. method:: select(xpath)

       Apply the given XPath relative to this XPathSelector and return a list
       of :class:`XPathSelector` objects (ie. a :class:`SelectorList`)
       with the result.

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


HtmlXPathSelector objects
-------------------------

.. class:: HtmlXPathSelector(response)

   A subclass of :class:`XPathSelector` for working with HTML content. It uses
   the `lxml`_ HTML parser. See the :class:`XPathSelector` API for more
   info.

HtmlXPathSelector examples
~~~~~~~~~~~~~~~~~~~~~~~~~~

Here's a couple of :class:`HtmlXPathSelector` examples to illustrate several
concepts.  In all cases, we assume there is already an
:class:`HtmlXPathSelector` instantiated with a :class:`~scrapy.http.Response`
object like this::

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
      ...    print node.select("@class").extract()

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
   the `lxml`_ XML parser. See the :class:`XPathSelector` API for more info.

XmlXPathSelector examples
~~~~~~~~~~~~~~~~~~~~~~~~~

Here's a couple of :class:`XmlXPathSelector` examples to illustrate several
concepts. In both cases we assume there is already an :class:`XmlXPathSelector`
instantiated with a :class:`~scrapy.http.Response` object like this::

      x = XmlXPathSelector(xml_response)

1. Select all ``<product>`` elements from a XML response body, returning a list
   of :class:`XPathSelector` objects (ie. a :class:`XPathSelectorList`
   object)::

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

1. Removing namespaces requires to iterate and modify all nodes in the
   document, which is a reasonably expensive operation to performs for all
   documents crawled by Scrapy

2. There could be some cases where using namespaces is actually required, in
   case some element names clash between namespaces. These cases are very rare
   though.

.. _Google Base XML feed: http://base.google.com/support/bin/answer.py?hl=en&answer=59461

.. _topics-css-selectors-ref:

CSSSelector objects
-------------------

.. class:: CSSSelector(response)

   :class:`Selector` interface implementation that uses `CSS`_ query language
   to select content on ``response``

   ``response`` is a :class:`~scrapy.http.Response` object that will be used
   for selecting and extracting data.

   In the background, CSS selectors are translated into XPath selectors using
   `cssselect`_ library and run using :class:`XPathSelector`

   .. method:: select(css)

       Apply the given CSS selector relative to this CSSSelector and return a
       :class:`SelectorList` instance.

       ``css`` is a string containing the CSS selector to apply.

HtmlCSSSelector objects
-----------------------

.. class:: HtmlCSSSelector(response)

   A specialized class for working with HTML content using `CSS`_ selectors.

HtmlCSSSelector examples
~~~~~~~~~~~~~~~~~~~~~~~~

Here's a couple of :class:`HtmlCSSSelector` examples to illustrate several
concepts. In all cases, we assume there is already an :class:`HtmlCSSSelector`
instantiated with a :class:`~scrapy.http.HtmlResponse` object like this::

      x = HtmlCSSSelector(html_response)

1. Select all ``<h1>`` elements from a HTML response body, returning a list of
   :class:`HtmlCSSSelector` objects::

      x.select("h1")

2. Extract the text of all ``<h1>`` elements from a HTML response body,
   returning a list of unicode strings::

      x.select("h1").extract()         # Includes the h1 tag
      x.select("h1::text").extract()   # Only text inside the h1 tag

3. Iterate over all ``<p>`` tags and print their class attribute::

      for node in x.select("p"):
      ...    print node.select("::attr(class)").extract()

XmlCSSSelector objects
----------------------

.. class:: XmlCSSSelector(response)

   A specialized class for working with XML content using `CSS`_ selectors.

XmlCSSSelector examples
~~~~~~~~~~~~~~~~~~~~~~~

Here's a couple of :class:`XmlCSSSelector` examples to illustrate several
concepts. In both cases we assume there is already an :class:`XmlCSSSelector`
instantiated with a :class:`~scrapy.http.XmlResponse` object like this::

      x = XmlCSSSelector(xml_response)

1. Select all ``<product>`` elements from a XML response body, returning a list
   of :class:`XmlCSSSelector` objects::

      x.select("product")

Note that querying xml namespaces with CSS selectors doesn't work, if you are
interesting in this feature consider contributing to `cssselect`_ project.

.. _Google Base XML feed: http://base.google.com/support/bin/answer.py?hl=en&answer=59461
