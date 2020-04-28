.. _faq:

Frequently Asked Questions
==========================

.. _faq-scrapy-bs-cmp:

How does Scrapy compare to BeautifulSoup or lxml?
-------------------------------------------------

`BeautifulSoup`_ and `lxml`_ are libraries for parsing HTML and XML. Scrapy is
an application framework for writing web spiders that crawl web sites and
extract data from them.

Scrapy provides a built-in mechanism for extracting data (called
:ref:`selectors <topics-selectors>`) but you can easily use `BeautifulSoup`_
(or `lxml`_) instead, if you feel more comfortable working with them. After
all, they're just parsing libraries which can be imported and used from any
Python code.

In other words, comparing `BeautifulSoup`_ (or `lxml`_) to Scrapy is like
comparing `jinja2`_ to `Django`_.

.. _BeautifulSoup: https://www.crummy.com/software/BeautifulSoup/
.. _lxml: https://lxml.de/
.. _jinja2: https://palletsprojects.com/p/jinja/
.. _Django: https://www.djangoproject.com/

Can I use Scrapy with BeautifulSoup?
------------------------------------

Yes, you can.
As mentioned :ref:`above <faq-scrapy-bs-cmp>`, `BeautifulSoup`_ can be used
for parsing HTML responses in Scrapy callbacks.
You just have to feed the response's body into a ``BeautifulSoup`` object
and extract whatever data you need from it.

Here's an example spider using BeautifulSoup API, with ``lxml`` as the HTML parser::


    from bs4 import BeautifulSoup
    import scrapy


    class ExampleSpider(scrapy.Spider):
        name = "example"
        allowed_domains = ["example.com"]
        start_urls = (
            'http://www.example.com/',
        )

        def parse(self, response):
            # use lxml to get decent HTML parsing speed
            soup = BeautifulSoup(response.text, 'lxml')
            yield {
                "url": response.url,
                "title": soup.h1.string
            }

.. note::

    ``BeautifulSoup`` supports several HTML/XML parsers.
    See `BeautifulSoup's official documentation`_ on which ones are available.

.. _BeautifulSoup's official documentation: https://www.crummy.com/software/BeautifulSoup/bs4/doc/#specifying-the-parser-to-use

.. _faq-python-versions:

What Python versions does Scrapy support?
-----------------------------------------

Scrapy is supported under Python 3.5+
under CPython (default Python implementation) and PyPy (starting with PyPy 5.9).
Python 3 support was added in Scrapy 1.1.
PyPy support was added in Scrapy 1.4, PyPy3 support was added in Scrapy 1.5.
Python 2 support was dropped in Scrapy 2.0.

.. note::
    For Python 3 support on Windows, it is recommended to use
    Anaconda/Miniconda as :ref:`outlined in the installation guide <intro-install-windows>`.

Did Scrapy "steal" X from Django?
---------------------------------

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

Does Scrapy work with HTTP proxies?
-----------------------------------

Yes. Support for HTTP proxies is provided (since Scrapy 0.8) through the HTTP
Proxy downloader middleware. See
:class:`~scrapy.downloadermiddlewares.httpproxy.HttpProxyMiddleware`.

How can I scrape an item with attributes in different pages?
------------------------------------------------------------

See :ref:`topics-request-response-ref-request-callback-arguments`.


Scrapy crashes with: ImportError: No module named win32api
----------------------------------------------------------

You need to install `pywin32`_ because of `this Twisted bug`_.

.. _pywin32: https://sourceforge.net/projects/pywin32/
.. _this Twisted bug: https://twistedmatrix.com/trac/ticket/3707

How can I simulate a user login in my spider?
---------------------------------------------

See :ref:`topics-request-response-ref-request-userlogin`.

.. _faq-bfo-dfo:

Does Scrapy crawl in breadth-first or depth-first order?
--------------------------------------------------------

By default, Scrapy uses a `LIFO`_ queue for storing pending requests, which
basically means that it crawls in `DFO order`_. This order is more convenient
in most cases.

If you do want to crawl in true `BFO order`_, you can do it by
setting the following settings::

    DEPTH_PRIORITY = 1
    SCHEDULER_DISK_QUEUE = 'scrapy.squeues.PickleFifoDiskQueue'
    SCHEDULER_MEMORY_QUEUE = 'scrapy.squeues.FifoMemoryQueue'

While pending requests are below the configured values of
:setting:`CONCURRENT_REQUESTS`, :setting:`CONCURRENT_REQUESTS_PER_DOMAIN` or
:setting:`CONCURRENT_REQUESTS_PER_IP`, those requests are sent
concurrently. As a result, the first few requests of a crawl rarely follow the
desired order. Lowering those settings to ``1`` enforces the desired order, but
it significantly slows down the crawl as a whole.


My Scrapy crawler has memory leaks. What can I do?
--------------------------------------------------

See :ref:`topics-leaks`.

Also, Python has a builtin memory leak issue which is described in
:ref:`topics-leaks-without-leaks`.

How can I make Scrapy consume less memory?
------------------------------------------

See previous question.

Can I use Basic HTTP Authentication in my spiders?
--------------------------------------------------

Yes, see :class:`~scrapy.downloadermiddlewares.httpauth.HttpAuthMiddleware`.

Why does Scrapy download pages in English instead of my native language?
------------------------------------------------------------------------

Try changing the default `Accept-Language`_ request header by overriding the
:setting:`DEFAULT_REQUEST_HEADERS` setting.

.. _Accept-Language: https://www.w3.org/Protocols/rfc2616/rfc2616-sec14.html#sec14.4

Where can I find some example Scrapy projects?
----------------------------------------------

See :ref:`intro-examples`.

Can I run a spider without creating a project?
----------------------------------------------

Yes. You can use the :command:`runspider` command. For example, if you have a
spider written in a ``my_spider.py`` file you can run it with::

    scrapy runspider my_spider.py

See :command:`runspider` command for more info.

I get "Filtered offsite request" messages. How can I fix them?
--------------------------------------------------------------

Those messages (logged with ``DEBUG`` level) don't necessarily mean there is a
problem, so you may not need to fix them.

Those messages are thrown by the Offsite Spider Middleware, which is a spider
middleware (enabled by default) whose purpose is to filter out requests to
domains outside the ones covered by the spider.

For more info see:
:class:`~scrapy.spidermiddlewares.offsite.OffsiteMiddleware`.

What is the recommended way to deploy a Scrapy crawler in production?
---------------------------------------------------------------------

See :ref:`topics-deploy`.

Can I use JSON for large exports?
---------------------------------

It'll depend on how large your output is. See :ref:`this warning
<json-with-large-data>` in :class:`~scrapy.exporters.JsonItemExporter`
documentation.

Can I return (Twisted) deferreds from signal handlers?
------------------------------------------------------

Some signals support returning deferreds from their handlers, others don't. See
the :ref:`topics-signals-ref` to know which ones.

What does the response status code 999 means?
---------------------------------------------

999 is a custom response status code used by Yahoo sites to throttle requests.
Try slowing down the crawling speed by using a download delay of ``2`` (or
higher) in your spider::

    class MySpider(CrawlSpider):

        name = 'myspider'

        download_delay = 2

        # [ ... rest of the spider code ... ]

Or by setting a global download delay in your project with the
:setting:`DOWNLOAD_DELAY` setting.

Can I call ``pdb.set_trace()`` from my spiders to debug them?
-------------------------------------------------------------

Yes, but you can also use the Scrapy shell which allows you to quickly analyze
(and even modify) the response being processed by your spider, which is, quite
often, more useful than plain old ``pdb.set_trace()``.

For more info see :ref:`topics-shell-inspect-response`.

Simplest way to dump all my scraped items into a JSON/CSV/XML file?
-------------------------------------------------------------------

To dump into a JSON file::

    scrapy crawl myspider -o items.json

To dump into a CSV file::

    scrapy crawl myspider -o items.csv

To dump into a XML file::

    scrapy crawl myspider -o items.xml

For more information see :ref:`topics-feed-exports`

What's this huge cryptic ``__VIEWSTATE`` parameter used in some forms?
----------------------------------------------------------------------

The ``__VIEWSTATE`` parameter is used in sites built with ASP.NET/VB.NET. For
more info on how it works see `this page`_. Also, here's an `example spider`_
which scrapes one of these sites.

.. _this page: https://metacpan.org/pod/release/ECARROLL/HTML-TreeBuilderX-ASP_NET-0.09/lib/HTML/TreeBuilderX/ASP_NET.pm
.. _example spider: https://github.com/AmbientLighter/rpn-fas/blob/master/fas/spiders/rnp.py

What's the best way to parse big XML/CSV data feeds?
----------------------------------------------------

Parsing big feeds with XPath selectors can be problematic since they need to
build the DOM of the entire feed in memory, and this can be quite slow and
consume a lot of memory.

In order to avoid parsing all the entire feed at once in memory, you can use
the functions ``xmliter`` and ``csviter`` from ``scrapy.utils.iterators``
module. In fact, this is what the feed spiders (see :ref:`topics-spiders`) use
under the cover.

Does Scrapy manage cookies automatically?
-----------------------------------------

Yes, Scrapy receives and keeps track of cookies sent by servers, and sends them
back on subsequent requests, like any regular web browser does.

For more info see :ref:`topics-request-response` and :ref:`cookies-mw`.

How can I see the cookies being sent and received from Scrapy?
--------------------------------------------------------------

Enable the :setting:`COOKIES_DEBUG` setting.

How can I instruct a spider to stop itself?
-------------------------------------------

Raise the :exc:`~scrapy.exceptions.CloseSpider` exception from a callback. For
more info see: :exc:`~scrapy.exceptions.CloseSpider`.

How can I prevent my Scrapy bot from getting banned?
----------------------------------------------------

See :ref:`bans`.

Should I use spider arguments or settings to configure my spider?
-----------------------------------------------------------------

Both :ref:`spider arguments <spiderargs>` and :ref:`settings <topics-settings>`
can be used to configure your spider. There is no strict rule that mandates to
use one or the other, but settings are more suited for parameters that, once
set, don't change much, while spider arguments are meant to change more often,
even on each spider run and sometimes are required for the spider to run at all
(for example, to set the start url of a spider).

To illustrate with an example, assuming you have a spider that needs to log
into a site to scrape data, and you only want to scrape data from a certain
section of the site (which varies each time). In that case, the credentials to
log in would be settings, while the url of the section to scrape would be a
spider argument.

I'm scraping a XML document and my XPath selector doesn't return any items
--------------------------------------------------------------------------

You may need to remove namespaces. See :ref:`removing-namespaces`.

.. _faq-split-item:

How to split an item into multiple items in an item pipeline?
-------------------------------------------------------------

:ref:`Item pipelines <topics-item-pipeline>` cannot yield multiple items per
input item. :ref:`Create a spider middleware <custom-spider-middleware>`
instead, and use its
:meth:`~scrapy.spidermiddlewares.SpiderMiddleware.process_spider_output`
method for this purpose. For example::

    from copy import deepcopy

    from scrapy.item import BaseItem


    class MultiplyItemsMiddleware:

        def process_spider_output(self, response, result, spider):
            for item in result:
                if isinstance(item, (BaseItem, dict)):
                    for _ in range(item['multiply_by']):
                        yield deepcopy(item)

Does Scrapy support IPv6 addresses?
-----------------------------------

Yes, by setting :setting:`DNS_RESOLVER` to ``scrapy.resolver.CachingHostnameResolver``.
Note that by doing so, you lose the ability to set a specific timeout for DNS requests
(the value of the :setting:`DNS_TIMEOUT` setting is ignored).


.. _faq-specific-reactor:

How to deal with ``<class 'ValueError'>: filedescriptor out of range in select()`` exceptions?
----------------------------------------------------------------------------------------------

This issue `has been reported`_ to appear when running broad crawls in macOS, where the default
Twisted reactor is :class:`twisted.internet.selectreactor.SelectReactor`. Switching to a
different reactor is possible by using the :setting:`TWISTED_REACTOR` setting.


.. _has been reported: https://github.com/scrapy/scrapy/issues/2905
.. _user agents: https://en.wikipedia.org/wiki/User_agent
.. _LIFO: https://en.wikipedia.org/wiki/Stack_(abstract_data_type)
.. _DFO order: https://en.wikipedia.org/wiki/Depth-first_search
.. _BFO order: https://en.wikipedia.org/wiki/Breadth-first_search
