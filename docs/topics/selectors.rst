.. _topics-selectors:

===============
XPath Selectors
===============

Introduction
------------

When you're scraping web pages, the most common task you need to perform is
to extract data from the HTML source. There are several libraries available to
achieve this: 

 * `BeautifulSoup`_ is a very popular screen scraping library among Python
   programmers which constructs a Python object based on the
   structure of the HTML code and also deals with bad markup reasonable well,
   but it has one drawback: it's slow.

 * `lxml`_ is a XML parsing library (which also parses HTML) with a pythonic
   API based on `ElementTree`_ (which is not part of the Python standard
   library).

Scrapy comes with its own mechanism for extracting data. They're called XPath
selectors (or just "selectors", for short) because they "select" certain parts
of the HTML document specified by `XPath`_ expressions.

`XPath`_ is a language for selecting nodes in XML documents, which can be used
to with HTML.

Both `lxml`_ and Scrapy Selectors are built over the `libxml2`_ library, which
means they're very similar in speed and parsing accuracy.

This page explains how selectors work and describes their API which is very
small and simple, unlike the `lxml`_ API which is much bigger because the
`lxml`_ library can be use for many other tasks, besides selecting markup
documents.

For a complete reference of the selectors API see the :ref:`XPath selector
reference <ref-selectors>`.

.. _BeautifulSoup: http://www.crummy.com/software/BeautifulSoup/
.. _lxml: http://codespeak.net/lxml/
.. _ElementTree: http://docs.python.org/library/xml.etree.elementtree.html
.. _libxml2: http://xmlsoft.org/
.. _XPath: http://www.w3.org/TR/xpath

Constructing selectors
----------------------

There are two types of selectors bundled with Scrapy. Those are:

 * :class:`~scrapy.xpath.HtmlXPathSelector` - for working with HTML documents

 * :class:`~scrapy.xpath.XmlXPathSelector` - for working with XML documents

.. highlight:: python

Both share the same selector API, and are constructed with a Response object as
its first parameter. This is the Response they're gonna be "selecting".

Example::

    hxs = HtmlXPathSelector(response) # a HTML selector
    xxs = XmlXPathSelector(response) # a XML selector

Using selectors with XPaths
---------------------------

To explain how to use the selectors we'll use the `Scrapy shell` (which
provides interactive testing) and an example page located in Scrapy
documentation server:

    http://doc.scrapy.org/_static/selectors-sample1.html

.. _topics-selectors-htmlcode:

Here's its HTML code:

.. literalinclude:: ../_static/selectors-sample1.html
   :language: html

.. highlight:: sh

First, let's open the shell::

    scrapy-ctl.py shell http://doc.scrapy.org/_static/selectors-sample1.html

Then, after the shell loads, you'll have some selectors already instanced and
ready to use.

Since we're dealing with HTML we'll be using the
:class:`~scrapy.xpath.HtmlXPathSelector` object which is found, by default, in
the ``hxs`` shell variable.

.. highlight:: python

So, by looking at the :ref:`HTML code <topics-selectors-htmlcode>` of that page
let's construct an XPath (using an HTML selector) for selecting the text inside
the title tag::

    >>> hxs.x('//title/text()')
    [<HtmlXPathSelector (text) xpath=//title/text()>]

As you can see, the x() method returns a XPathSelectorList, which is a list of
new selectors. This API can be used quickly for extracting nested data. 

To actually extract the textual data you must call the selector ``extract()``
method, as follows::

    >>> hxs.x('//title/text()').extract()
    [u'Example website']

Now we're going to get the base URL and some image links::

    >>> hxs.x('//base/@href').extract()
    [u'http://example.com/']

    >>> hxs.x('//a[contains(@href, "image")]/@href').extract()
    [u'image1.html',
     u'image2.html',
     u'image3.html',
     u'image4.html',
     u'image5.html']

    >>> hxs.x('//a[contains(@href, "image")]/img/@src').extract()
    [u'image1_thumb.jpg',
     u'image2_thumb.jpg',
     u'image3_thumb.jpg',
     u'image4_thumb.jpg',
     u'image5_thumb.jpg']


Using selectors with regular expressions
----------------------------------------

Selectors also have a ``re()`` method for extracting data using regular
expressions. However, unlike using the ``x()`` method, the ``re()`` method does
not return a list of :class:`~scrapy.xpath.XPathSelector` objects, so you can't
construct nested ``.re()`` calls. 

Here's an example used to extract images names from the :ref:`HTML code
<topics-selectors-htmlcode>` above::

    >>> hxs.x('//a[contains(@href, "image")]/text()').re(r'Name:\s*(.*)')
    [u'My image 1',
     u'My image 2',
     u'My image 3',
     u'My image 4',
     u'My image 5']


Nesting selectors
-----------------

The ``x()`` selector method returns a list of selectors, so you can call the
``x()`` for those selectors too. Here's an example::

    >>> links = hxs.x('//a[contains(@href, "image")]')
    >>> links.extract()
    [u'<a href="image1.html">Name: My image 1 <br><img src="image1_thumb.jpg"></a>',
     u'<a href="image2.html">Name: My image 2 <br><img src="image2_thumb.jpg"></a>',
     u'<a href="image3.html">Name: My image 3 <br><img src="image3_thumb.jpg"></a>',
     u'<a href="image4.html">Name: My image 4 <br><img src="image4_thumb.jpg"></a>',
     u'<a href="image5.html">Name: My image 5 <br><img src="image5_thumb.jpg"></a>']

    >>> for index, link in enumerate(links):
            args = (index, link.x('@href').extract(), link.x('img/@src').extract())
            print 'Link number %d points to url %s and image %s' % args

    Link number 0 points to url [u'image1.html'] and image [u'image1_thumb.jpg']
    Link number 1 points to url [u'image2.html'] and image [u'image2_thumb.jpg']
    Link number 2 points to url [u'image3.html'] and image [u'image3_thumb.jpg']
    Link number 3 points to url [u'image4.html'] and image [u'image4_thumb.jpg']
    Link number 4 points to url [u'image5.html'] and image [u'image5_thumb.jpg']

Working with relative XPaths
----------------------------

Keep in mind that if you are nesting XPathSelectors and use an XPath that
starts with ``/``, that XPath will be absolute to the document and not relative
to the ``XPathSelector`` you're calling it from.

For example, suppose you want to extract all ``<p>`` elements inside ``<div>``
elements. First you get would get all ``<div>`` elements::

    >>> divs = hxs.x('//div')

At first, you may be tempted to use the following approach, which is wrong, as
it actually extracts all ``<p>`` elements from the document, not only those
inside ``<div>`` elements::

    >>> for p in divs.x('//p') # this is wrong - gets all <p> from the whole document
    >>>     print p.extract()

This is the proper way to do it (note the dot prefixing the ``.//p`` XPath)::

    >>> for p in divs.x('//p') # extracts all <p> inside
    >>>     print p.extract()

Another common case would be to extract all direct ``<p>`` children::

    >>> for p in divs.x('p')
    >>>     print p.extract()

For more details about relative XPaths see the `Location Paths`_ section in the
XPath specification.

.. _Location Paths: http://www.w3.org/TR/xpath#location-paths
