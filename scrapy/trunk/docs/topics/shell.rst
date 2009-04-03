.. _topics-shell:

=====
Shell
=====

The Scrapy shell is an interactive shell where you can try and debug your
scraping code very quickly, without having to run the spider. It's meant to be
used for testing data extraction code, but you can actually use it for testing
any kind of code as it is also a regular Python shell.

The shell is used for testing XPath expressions and see how they work and what
data they extract from the web pages you're trying to scrape. It allows you to
interactively test your XPaths while you're writing your spider, without having
to run the spider to test every change.

Once you get familiarized with the Scrapy shell you'll see that it's an
invaluable tool for developing and debugging your spiders.

Requirements
============

The Scrapy shell is powered by `IPython`_, so you need to install it before you
can use it, but we highly recommend to do it. See the `IPython installation
guide`_ for more info.

.. _IPython: http://ipython.scipy.org/
.. _IPython installation guide: http://ipython.scipy.org/doc/rel-0.9.1/html/install/index.html

Launch the shell
================

To launch the shell type::

    scrapy-ctl.py shell <url>

Where the ``<url>`` is the URL you want to screen scrape.

Using the shell
===============

The Scrapy shell is just a regular `IPython`_ shell (see `IPython
documentation`_) with a few extensions:

.. _IPython documentation: http://ipython.scipy.org/moin/Documentation

Custom Shell Commands 
---------------------

 * ``%shelp`` - show the status of your Scrapy objects and get a list of
   all (Scrapy related) available objects. 

 * ``%get <url>``- download a new response from the given URL and update all
   Scrapy objects accordingly

These commands can be typed without the leading percent sign if you have
`automagic commands`_ enabled in IPython.

.. _automagic commands: http://ipython.scipy.org/doc/manual/html/interactive/reference.html#magic-command-system

Custom Shell Objects
--------------------

The console automatically makes some useful Scrapy objects available for the
downloaded page, like the Response object and the XPath selectors (for both
HTML and XML content).

Those objects are:

 * ``url`` - the URL being analyzed

 * ``spider`` - the Spider which is configured to process the URL to analyze,
   or a :class:`~scrapy.spider.BaseSpider` object if there is not spider
   configured to process that URL

 * ``response`` - a Response object of the downloaded page

 * ``hxs`` - a HtmlXPathSelector object for the Response of the downloaded page

 * ``xxs`` - a XmlXPathSelector object for the Response of the downloaded page

 * ``get <url>``- download a new response from the given URL and update all
   Scrapy objects accordingly


Example of shell session
========================

Here's an example of a typical shell session where we start by scraping the
http://scrapy.org page, and then the http://slashdot.org page. Note, however,
that the data extracted may not be the same when you try this as those pages
are not static and could have changed by the time you test this. The purpose of
this example is only to get you familiarized with how the Scrapy shell works.

::

    scrapy-ctl.py shell http://scrapy.org

    2009-04-02 16:56:22-0300 [-] Log opened.
    Starting Scrapy 0.7.0 shell...
    Downloading URL...            Done.

    ------------------------------------------------------------
    Available Scrapy variables:
       xxs: <class 'scrapy.xpath.selector.XmlXPathSelector'>
       url: http://scrapy.org
       spider: <class 'scrapy.spider.models.BaseSpider'>
       hxs: <class 'scrapy.xpath.selector.HtmlXPathSelector'>
       item: <class 'myproject.models.Item'>
       response: <class 'scrapy.http.response.html.HtmlResponse'>
    Available commands:
       get <url>: Fetches an url and updates all variables.
       scrapehelp: Prints this help.
    ------------------------------------------------------------
    Python 2.5.2 (r252:60911, Oct  5 2008, 19:29:17) 
    Type "copyright", "credits" or "license" for more information.

    IPython 0.8.4 -- An enhanced Interactive Python.
    ?         -> Introduction and overview of IPython's features.
    %quickref -> Quick reference.
    help      -> Python's own help system.
    object?   -> Details about 'object'. ?object also works, ?? prints more.

    In [1]: hxs.x("//h2/text()").extract()[2]
    Out[1]: u'Welcome to Scrapy'

    In [2]: get http://slashdot.org
    Downloading URL...            Done.
    ------------------------------------------------------------
    Available Scrapy variables:
       xxs: <class 'scrapy.xpath.selector.XmlXPathSelector'>
       url: http://slashdot.org
       spider: <class 'scrapy.spider.models.BaseSpider'>
       hxs: <class 'scrapy.xpath.selector.HtmlXPathSelector'>
       item: <class 'myproject.models.Item'>
       r: <class 'scrapy.http.response.html.HtmlResponse'>
       response: <class 'scrapy.http.response.html.HtmlResponse'>
    Available commands:
       get <url>: Fetches an url and updates all variables.
       scrapehelp: Prints this help.
    ------------------------------------------------------------

    In [3]: hxs.x("//h2/text()").extract()
    Out[3]: [u'News for nerds, stuff that matters']

