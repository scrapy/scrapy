.. _faq:

Frequently Asked Questions
==========================

How does Scrapy compare to BeautifulSoul or lxml?
-------------------------------------------------

`BeautifulSoup`_ and `lxml`_ are libraries for parsing HTML and XML. Scrapy is
an application framework for writing web spiders that crawl web sites and
extract data from it. Scrapy provides some mechanisms for extracting data
(called selectors) but you can easily use `BeautifulSoup`_ or `lxml`_ if you
feel more comfortable with them. After all, they're just parsing libraries
which can be imported and used from any Python code.

In other words, comparing `BeautifulSoup`_ or `lxml`_ to Scrapy is like
comparing `urllib`_ or `urlparse`_ to `Django`_ (a popular Python web
framework).

.. _BeautifulSoup: http://www.crummy.com/software/BeautifulSoup/
.. _lxml: http://codespeak.net/lxml/
.. _urllib: http://docs.python.org/library/urllib.html
.. _urlparse: http://docs.python.org/library/urlparse.html
.. _Django: http://www.djangoproject.com

Does Scrapy work with Python 3.0?
---------------------------------

No, and there are no plans to port Scrapy to Python 3.0 yet. At the moment
Scrapy works with Python 2.5 or 2.6.

Does Scrapy "stole" X from Django?
----------------------------------

Probably, but we don't like that word. We think Django_ is a great open source
project and an example to follow, so we've used it as an inspiration for
Scrapy. 

We believe that, if something is already done well, there's no need to reinvent
it. This concept, besides being one of the foundations for open source and free
software, not only applies to software but also to documentation, procedures,
policies, etc. So, instead of going through each problem ourselves, we choose
to copy ideas from those projects that have already solved them properly, and
focus on the real problems we need to solve.

We'd be proud if Scrapy serves as an inspiration for other projects. Feel free
to steal from us!

.. _Django: http://www.djangoproject.com

Does Scrapy work with HTTP proxies?
-----------------------------------

No. support for HTTP proxies is not currently implemented in Scrapy, but it
will be in the future. For more information about this, follow `this ticket
<http://dev.scrapy.org/ticket/71>`_. Setting the ``http_proxy`` environment
variable won't work because Twisted (the library used by Scrapy to download
pages) doesn't support it. See `this Twisted ticket
<http://twistedmatrix.com/trac/ticket/2714>`_ for more info.

Scrapy crashes with: ImportError: No module named win32api
----------------------------------------------------------

You need to install `pywin32`_ because of `this Twisted bug`_.

.. _pywin32: http://sourceforge.net/projects/pywin32/
.. _this Twisted bug: http://twistedmatrix.com/trac/ticket/3707

How can I simulate a user login in my spider?
---------------------------------------------

See :ref:`ref-request-userlogin`.
