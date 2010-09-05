.. _topics-shell:

============
Scrapy shell
============

The Scrapy shell is an interactive shell where you can try and debug your
scraping code very quickly, without having to run the spider. It's meant to be
used for testing data extraction code, but you can actually use it for testing
any kind of code as it is also a regular Python shell.

The shell is used for testing XPath expressions and see how they work and what
data they extract from the web pages you're trying to scrape. It allows you to
interactively test your XPaths while you're writing your spider, without having
to run the spider to test every change.

Once you get familiarized with the Scrapy shell, you'll see that it's an
invaluable tool for developing and debugging your spiders.

If you have `IPython`_ installed, the Scrapy shell will use it (instead of the
standard Python console). The `IPython`_ console is much more powerful and
provides smart auto-completion and colorized output, among other things.

We highly recommend you install `IPython`_, specially if you're working on
Unix systems (where `IPython`_ excels). See the `IPython installation guide`_
for more info.

.. _IPython: http://ipython.scipy.org/
.. _IPython installation guide: http://ipython.scipy.org/doc/rel-0.9.1/html/install/index.html

Launch the shell
================

To launch the Scrapy shell you can use the :command:`shell` command like
this::

    scrapy shell <url>

Where the ``<url>`` is the URL you want to scrape.

Using the shell
===============

The Scrapy shell is just a regular Python console (or `IPython` console if you
have it available) which provides some additional shortcut functions for
convenience.

Available Shortcuts
-------------------

 * ``shelp()`` - print a help with the list of available objects and shortcuts

 * ``fetch(request_or_url)`` - fetch a new response from the given request or
   URL and update all related objects accordingly.

 * ``view(response)`` - open the given response in your local web browser, for
   inspection. This will add a `\<base\> tag`_ to the response body in order
   for external links (such as images and style sheets) to display properly.
   Note, however,that this will create a temporary file in your computer,
   which won't be removed automatically.

.. _<base> tag: http://www.w3schools.com/TAGS/tag_base.asp

Available Scrapy objects
-------------------------

The Scrapy shell automatically creates some convenient objects from the
downloaded page, like the :class:`~scrapy.http.Response` object and the
:class:`~scrapy.selector.XPathSelector` objects (for both HTML and XML
content).

Those objects are:

 * ``spider`` - the Spider which is known to handle the URL, or a
   :class:`~scrapy.spider.BaseSpider` object if there is no spider found for
   the current URL

 * ``request`` - a :class:`~scrapy.http.Request` object of the last fetched
   page. You can modify this request using :meth:`~scrapy.http.Request.replace` or
   fetch a new request (without leaving the shell) using the ``fetch``
   shortcut.

 * ``response`` - a :class:`~scrapy.http.Response` object containing the last
   fetched page

 * ``hxs`` - a :class:`~scrapy.selector.HtmlXPathSelector` object constructed
   with the last response fetched

 * ``xxs`` - a :class:`~scrapy.selector.XmlXPathSelector` object constructed
   with the last response fetched

 * ``settings`` - the current :ref:`Scrapy settings <topics-settings>`

Example of shell session
========================

Here's an example of a typical shell session where we start by scraping the
http://scrapy.org page, and then proceed to scrape the http://slashdot.org
page. Finally, we modify the (Slashdot) request method to POST and re-fetch it
getting a HTTP 405 (method not allowed) error. We end the session by typing
Ctrl-D (in Unix systems) or Ctrl-Z in Windows.

Keep in mind that the data extracted here may not be the same when you try it,
as those pages are not static and could have changed by the time you test this.
The only purpose of this example is to get you familiarized with how the Scrapy
shell works.

First, we launch the shell::

    scrapy shell http://scrapy.org --nolog

Then, the shell fetches the URL (using the Scrapy downloader) and prints the
list of available objects and useful shortcuts (you'll notice that these lines
all start with the ``[s]`` prefix)::

    [s] Available objects
    [s]   hxs       <HtmlXPathSelector (http://scrapy.org) xpath=None>
    [s]   item      Item()
    [s]   request   <http://scrapy.org>
    [s]   response  <http://scrapy.org>
    [s]   settings  <Settings 'mybot.settings'>
    [s]   spider    <scrapy.spider.models.BaseSpider object at 0x2bed9d0>
    [s]   xxs       <XmlXPathSelector (http://scrapy.org) xpath=None>
    [s] Useful shortcuts:
    [s]   shelp()           Prints this help.
    [s]   fetch(req_or_url) Fetch a new request or URL and update objects
    [s]   view(response)    View response in a browser

    >>>

After that, we can star playing with the objects::

    >>> hxs.select("//h2/text()").extract()[0]
    u'Welcome to Scrapy'

    >>> fetch("http://slashdot.org")
    [s] Available Scrapy objects:
    [s]   hxs        <HtmlXPathSelector (http://slashdot.org) xpath=None>
    [s]   item       JobItem()
    [s]   request    <GET http://slashdot.org>
    [s]   response   <200 http://slashdot.org>
    [s]   settings   <Settings 'jobsbot.settings'>
    [s]   spider     <BaseSpider 'default' at 0x3c44a10>
    [s]   xxs        <XmlXPathSelector (http://slashdot.org) xpath=None>
    [s] Useful shortcuts:
    [s]   shelp()           Shell help (print this help)
    [s]   fetch(req_or_url) Fetch request (or URL) and update local objects
    [s]   view(response)    View response in a browser

    >>> hxs.select("//h2/text()").extract()
    [u'News for nerds, stuff that matters']

    >>> request = request.replace(method="POST")

    >>> fetch(request)
    2009-04-03 00:57:39-0300 [default] ERROR: Downloading <http://slashdot.org> from <None>: 405 Method Not Allowed

    >>> 

.. _topics-shell-inspect-response:

Invoking the shell from spiders to inspect responses
====================================================

Sometimes you want to inspect the responses that are being processed in a
certain point of your spider, if only to check that response you expect is
getting there.

This can be achieved by using the ``scrapy.shell.inspect_response`` function.

Here's an example of how you would call it from your spider::

    class MySpider(BaseSpider):
        ...

        def parse(self, response):
            if response.url == 'http://www.example.com/products.php':
                from scrapy.shell import inspect_response
                inspect_response(response)

            # ... your parsing code ..

When you run the spider, you will get something similar to this::

    2009-08-27 19:15:25-0300 [example.com] DEBUG: Crawled <http://www.example.com/> (referer: <None>)
    2009-08-27 19:15:26-0300 [example.com] DEBUG: Crawled <http://www.example.com/products.php> (referer: <http://www.example.com/>)
    [s] Available objects
    [s]   hxs       <HtmlXPathSelector (http://www.example.com/products.php) xpath=None>
    ...

    >>> response.url
    'http://www.example.com/products.php'

Then, you can check if the extraction code is working::

    >>> hxs.select('//h1')
    []

Nope, it doesn't. So you can open the response in your web browser and see if
it's the response you were expecting::

    >>> view(response)
    >>>

Finally you hit Ctrl-D (or Ctrl-Z in Windows) to exit the shell and resume the
crawling::

    >>> ^D
    2009-08-27 19:15:25-0300 [example.com] DEBUG: Crawled <http://www.example.com/product.php?id=1> (referer: <None>)
    2009-08-27 19:15:25-0300 [example.com] DEBUG: Crawled <http://www.example.com/product.php?id=2> (referer: <None>)
    # ...

Note that you can't use the ``fetch`` shortcut here since the Scrapy engine is
blocked by the shell. However, after you leave the shell, the spider will
continue crawling where it stopped, as shown above.

