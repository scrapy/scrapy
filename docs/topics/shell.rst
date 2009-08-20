.. _topics-shell:

================
The Scrapy shell
================

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

 * ``%get [url]``- fetch a new response from the given URL and update all
   Scrapy objects accordingly. If the url is omitted, the last request is
   re-fetched. Since Requests are mutable objects, you can modify the Request
   "in place" and issue ``get`` to fetch it again with the modifications you've
   made.

These commands can be typed without the leading percent sign if you have
`automagic commands`_ enabled in IPython.

.. _automagic commands: http://ipython.scipy.org/doc/manual/html/interactive/reference.html#magic-command-system

Custom Shell Objects
--------------------

The console automatically creates some useful Scrapy objects for the downloaded
page, like the :class:`~scrapy.http.Response` object and the
:class:`~scrapy.selector.XPathSelector` objects (for both HTML and XML content).

Those objects are:

 * ``url`` - the URL being analyzed

 * ``spider`` - the Spider which is configured to process the URL to analyze,
   or a :class:`~scrapy.spider.BaseSpider` object if there is not spider
   configured to process that URL

 * ``request`` - a :class:`~scrapy.http.Request` object of the last fetched
   page. You can modify this Request "in place" and re-fetch it using the
   command ``get`` without no argument.

 * ``response`` - a :class:`~scrapy.http.Response` object of the last fetched
   page

 * ``hxs`` - a :class:`~scrapy.selector.HtmlXPathSelector` object for the Response
   of the downloaded page

 * ``xxs`` - a :class:`~scrapy.selector.XmlXPathSelector` object for the Response
   of the downloaded page

 * ``get <url>``- download a new response from the given URL and update all
   Scrapy objects accordingly


Example of shell session
========================

Here's an example of a typical shell session where we start by scraping the
http://scrapy.org page, and then proceed to scrape the http://slashdot.org
page. Finally, we modify the (slashdot) request method to POST and re-fetch it
getting a HTTP 405 (method not allowed) error. We end the session by typing
Ctrl-D (in the ``In [6]`` prompt).

Keep in mind that the data extracted here may not be the same when you try it,
as those pages are not static and could have changed by the time you test this.
The only purpose of this example is to get you familiarized with how the Scrapy
shell works.

::

    python scrapy-ctl.py shell http://scrapy.org

    2009-04-02 16:56:22-0300 [-] Log opened.
    Welcome to Scrapy shell!
    Fetching <http://scrapy.org>...

    ------------------------------------------------------------
    Available Scrapy variables:
       xxs: <XmlXPathSelector (http://scrapy.org)>
       url: http://scrapy.org
       request: <http://scrapy.org>
       spider: <class 'scrapy.spider.models.BaseSpider'>
       hxs: <HtmlXPathSelector (http://scrapy.org)>
       item: <class 'myproject.models.Item'>
       response: <http://scrapy.org>
    Available commands:
       get [url]: Fetch a new URL or re-fetch current Request
       shelp: Prints this help.
    ------------------------------------------------------------
    Python 2.5.2 (r252:60911, Oct  5 2008, 19:29:17) 
    Type "copyright", "credits" or "license" for more information.

    IPython 0.8.4 -- An enhanced Interactive Python.
    ?         -> Introduction and overview of IPython's features.
    %quickref -> Quick reference.
    help      -> Python's own help system.
    object?   -> Details about 'object'. ?object also works, ?? prints more.

    In [1]: hxs.select("//h2/text()").extract()[2]
    Out[1]: u'Welcome to Scrapy'

    In [2]: get http://slashdot.org
    Fetching <http://slashdot.org>...
    ------------------------------------------------------------
    Available Scrapy variables:
       xxs: <XmlXPathSelector (http://slashdot.org)>
       url: http://slashdot.org
       request: <http://slashdot.org>
       spider: <class 'scrapy.spider.models.BaseSpider'>
       hxs: <HtmlXPathSelector (http://slashdot.org)>
       item: <class 'myproject.models.Item'>
       response: <http://slashdot.org>
    Available commands:
       get <url>: Fetches an url and updates all variables.
       scrapehelp: Prints this help.
    ------------------------------------------------------------

    In [3]: hxs.select("//h2/text()").extract()
    Out[3]: [u'News for nerds, stuff that matters']

    In [3]: hxs.select("//h2/text()").extract()
    Out[3]: [u'News for nerds, stuff that matters']

    In [4]: request.method = "POST"

    In [5]: get
    Fetching <POST http://slashdot.org>...
    2009-04-03 00:57:39-0300 [decobot/None] ERROR: Downloading <http://slashdot.org> from <None>: 405 Method Not Allowed

    In [6]: 
    2009-04-03 01:07:12-0300 [-] Main loop terminated.


