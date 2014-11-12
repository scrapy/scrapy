.. _topics-shell:

============
Scrapy shell
============

The Scrapy shell is an interactive shell where you can try and debug your
scraping code very quickly, without having to run the spider. It's meant to be
used for testing data extraction code, but you can actually use it for testing
any kind of code as it is also a regular Python shell.

The shell is used for testing XPath or CSS expressions and see how they work
and what data they extract from the web pages you're trying to scrape. It
allows you to interactively test your expressions while you're writing your
spider, without having to run the spider to test every change.

Once you get familiarized with the Scrapy shell, you'll see that it's an
invaluable tool for developing and debugging your spiders.

If you have `IPython`_ installed, the Scrapy shell will use it (instead of the
standard Python console). The `IPython`_ console is much more powerful and
provides smart auto-completion and colorized output, among other things.

We highly recommend you install `IPython`_, specially if you're working on
Unix systems (where `IPython`_ excels). See the `IPython installation guide`_
for more info.

.. _IPython: http://ipython.org/
.. _IPython installation guide: http://ipython.org/install.html

Launch the shell
================

To launch the Scrapy shell you can use the :command:`shell` command like
this::

    scrapy shell <url>

Where the ``<url>`` is the URL you want to scrape.

Using the shell
===============

The Scrapy shell is just a regular Python console (or `IPython`_ console if you
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

.. _<base> tag: https://developer.mozilla.org/en-US/docs/Web/HTML/Element/base

Available Scrapy objects
------------------------

The Scrapy shell automatically creates some convenient objects from the
downloaded page, like the :class:`~scrapy.http.Response` object and the
:class:`~scrapy.selector.Selector` objects (for both HTML and XML
content).

Those objects are:

 * ``crawler`` - the current :class:`~scrapy.crawler.Crawler` object.

 * ``spider`` - the Spider which is known to handle the URL, or a
   :class:`~scrapy.spider.Spider` object if there is no spider found for
   the current URL

 * ``request`` - a :class:`~scrapy.http.Request` object of the last fetched
   page. You can modify this request using :meth:`~scrapy.http.Request.replace`
   or fetch a new request (without leaving the shell) using the ``fetch``
   shortcut.

 * ``response`` - a :class:`~scrapy.http.Response` object containing the last
   fetched page

 * ``sel`` - a :class:`~scrapy.selector.Selector` object constructed
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

    scrapy shell 'http://scrapy.org' --nolog

Then, the shell fetches the URL (using the Scrapy downloader) and prints the
list of available objects and useful shortcuts (you'll notice that these lines
all start with the ``[s]`` prefix)::

    [s] Available Scrapy objects:
    [s]   crawler    <scrapy.crawler.Crawler object at 0x1e16b50>
    [s]   item       {}
    [s]   request    <GET http://scrapy.org>
    [s]   response   <200 http://scrapy.org>
    [s]   sel        <Selector xpath=None data=u'<html>\n  <head>\n    <meta charset="utf-8'>
    [s]   settings   <scrapy.settings.Settings object at 0x2bfd650>
    [s]   spider     <Spider 'default' at 0x20c6f50>
    [s] Useful shortcuts:
    [s]   shelp()           Shell help (print this help)
    [s]   fetch(req_or_url) Fetch request (or URL) and update local objects
    [s]   view(response)    View response in a browser

    >>>

After that, we can start playing with the objects::

    >>> sel.xpath("//h2/text()").extract()[0]
    u'Welcome to Scrapy'

    >>> fetch("http://slashdot.org")
    [s] Available Scrapy objects:
    [s]   crawler    <scrapy.crawler.Crawler object at 0x1a13b50>
    [s]   item       {}
    [s]   request    <GET http://slashdot.org>
    [s]   response   <200 http://slashdot.org>
    [s]   sel        <Selector xpath=None data=u'<html lang="en">\n<head>\n\n\n\n\n<script id="'>
    [s]   settings   <scrapy.settings.Settings object at 0x2bfd650>
    [s]   spider     <Spider 'default' at 0x20c6f50>
    [s] Useful shortcuts:
    [s]   shelp()           Shell help (print this help)
    [s]   fetch(req_or_url) Fetch request (or URL) and update local objects
    [s]   view(response)    View response in a browser

    >>> sel.xpath('//title/text()').extract()
    [u'Slashdot: News for nerds, stuff that matters']

    >>> request = request.replace(method="POST")

    >>> fetch(request)
    [s] Available Scrapy objects:
    [s]   crawler    <scrapy.crawler.Crawler object at 0x1e16b50>
    ...

    >>>

.. _topics-shell-inspect-response:

Invoking the shell from spiders to inspect responses
====================================================

Sometimes you want to inspect the responses that are being processed in a
certain point of your spider, if only to check that response you expect is
getting there.

This can be achieved by using the ``scrapy.shell.inspect_response`` function.

Here's an example of how you would call it from your spider::

    import scrapy


    class MySpider(scrapy.Spider):
        name = "myspider"
        start_urls = [
            "http://example.com",
            "http://example.org",
            "http://example.net",
        ]

        def parse(self, response):
            # We want to inspect one specific response.
            if ".org" in response.url:
                from scrapy.shell import inspect_response
                inspect_response(response, self)

            # Rest of parsing code.

When you run the spider, you will get something similar to this::

    2014-01-23 17:48:31-0400 [myspider] DEBUG: Crawled (200) <GET http://example.com> (referer: None)
    2014-01-23 17:48:31-0400 [myspider] DEBUG: Crawled (200) <GET http://example.org> (referer: None)
    [s] Available Scrapy objects:
    [s]   crawler    <scrapy.crawler.Crawler object at 0x1e16b50>
    ...

    >>> response.url
    'http://example.org'

Then, you can check if the extraction code is working::

    >>> sel.xpath('//h1[@class="fn"]')
    []

Nope, it doesn't. So you can open the response in your web browser and see if
it's the response you were expecting::

    >>> view(response)
    True

Finally you hit Ctrl-D (or Ctrl-Z in Windows) to exit the shell and resume the
crawling::

    >>> ^D
    2014-01-23 17:50:03-0400 [myspider] DEBUG: Crawled (200) <GET http://example.net> (referer: None)
    ...

Note that you can't use the ``fetch`` shortcut here since the Scrapy engine is
blocked by the shell. However, after you leave the shell, the spider will
continue crawling where it stopped, as shown above.
