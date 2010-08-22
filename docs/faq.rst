.. _faq:

Frequently Asked Questions
==========================

How does Scrapy compare to BeautifulSoul or lxml?
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

.. _BeautifulSoup: http://www.crummy.com/software/BeautifulSoup/
.. _lxml: http://codespeak.net/lxml/
.. _jinja2: http://jinja.pocoo.org/2/
.. _Django: http://www.djangoproject.com

Does Scrapy work with Python 3.0?
---------------------------------

No, and there are no plans to port Scrapy to Python 3.0 yet. At the moment,
Scrapy works with Python 2.5, 2.6 and 2.7.

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

.. _Django: http://www.djangoproject.com

Does Scrapy work with HTTP proxies?
-----------------------------------

Yes. Support for HTTP proxies is provided (since Scrapy 0.8) through the HTTP
Proxy downloader middleware. See
:class:`~scrapy.contrib.downloadermiddleware.httpproxy.HttpProxyMiddleware`.

Scrapy crashes with: ImportError: No module named win32api
----------------------------------------------------------

You need to install `pywin32`_ because of `this Twisted bug`_.

.. _pywin32: http://sourceforge.net/projects/pywin32/
.. _this Twisted bug: http://twistedmatrix.com/trac/ticket/3707

How can I simulate a user login in my spider?
---------------------------------------------

See :ref:`topics-request-response-ref-request-userlogin`.

Can I crawl in depth-first order instead of breadth-first order?
----------------------------------------------------------------

Yes, there's a setting for that: :setting:`SCHEDULER_ORDER`.

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

Yes, see :class:`~scrapy.contrib.downloadermiddleware.httpauth.HttpAuthMiddleware`.

Why does Scrapy download pages in English instead of my native language?
------------------------------------------------------------------------

Try changing the default `Accept-Language`_ request header by overriding the
:setting:`DEFAULT_REQUEST_HEADERS` setting.

.. _Accept-Language: http://www.w3.org/Protocols/rfc2616/rfc2616-sec14.html#sec14.4

Where can I find some example code using Scrapy?
------------------------------------------------

Scrapy comes with a built-in, fully functional project to scrape the `Google
Directory`_. You can find it in the ``examples/googledir`` directory of the
Scrapy distribution.

Also, there's a site for sharing code snippets (spiders, middlewares,
extensions) called `Scrapy snippets`_.

Finally, you can find some example code for performing not-so-trivial tasks in
the `Scrapy Recipes`_ page.

.. _Google Directory: http://www.google.com/dirhp
.. _Community Spiders: http://dev.scrapy.org/wiki/CommunitySpiders
.. _Scrapy Recipes: http://dev.scrapy.org/wiki/ScrapyRecipes
.. _Scrapy snippets: http://snippets.scrapy.org/

Can I run a spider without creating a project?
----------------------------------------------

Yes. You can use the :command:`runspider` command. For example, if you have a
spider written in a ``my_spider.py`` file you can run it with::

    scrapy runspider my_spider.py

I get "Filtered offsite request" messages. How can I fix them?
--------------------------------------------------------------

Those messages (logged with ``DEBUG`` level) don't necessarily mean there is a
problem, so you may not need to fix them.

Those message are thrown by the Offsite Spider Middleware, which is a spider
middleware (enabled by default) whose purpose is to filter out requests to
domains outside the ones covered by the spider.

For more info see:
:class:`~scrapy.contrib.spidermiddleware.offsite.OffsiteMiddleware`.

What is the recommended way to deploy a Scrapy crawler in production?
---------------------------------------------------------------------

Scrapy comes with a built-in service based on `Twisted Application Framework`_
which can be launched through the `twistd`_ command. The ``scrapy.tac`` file
can be found in the ``extras/`` directory.

If you're running Ubuntu 9.10 or above, you can just use the `official APT
repos`_ for installing Scrapy in your servers. The Debian package automatically
deploys the service in the right place and leaves it ready to be started,
running as the ``scrapy`` user. It also provides an `upstart` script for
controlling the service.

For a practical example see this `guide on how to deploy a Scrapy crawler on
Amazon EC2 <http://dev.scrapy.org/wiki/AmazonEC2>`_.

.. _Twisted Application Framework: http://twistedmatrix.com/documents/current/core/howto/application.html
.. _twistd: http://twistedmatrix.com/documents/current/core/howto/basics.html#auto1
.. _official APT repos: http://dev.scrapy.org/wiki/AptRepos
.. _upstart: http://upstart.ubuntu.com/

Can I use JSON for large exports?
---------------------------------

It'll depend on how large your output is. See :ref:`this warning
<json-with-large-data>` in :class:`~scrapy.contrib.exporter.JsonItemExporter`
documentation.

Can I return (Twisted) deferreds from signal handlers?
------------------------------------------------------

Some signals support returning deferreds form their handlers, others don't. See
the :ref:`topics-signals-ref` to know which ones.

What does the response status code 999 means?
---------------------------------------------

999 is a custom reponse status code used by Yahoo sites to throttle requests.
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

Yes, but you can also use the Scrapy shell which allows you too quickly analyze
(and even modify) the response being processed by your spider, which is, quite
often, more useful than plain old ``pdb.set_trace()``.

For more info see :ref:`topics-shell-inspect-response`.

Simplest way to dump all my scraped items into a JSON/CSV/XML file?
-------------------------------------------------------------------

To dump into a JSON file::

    scrapy crawl myspider --set FEED_URI=items.json --set FEED_FORMAT=json

To dump into a CSV file::

    scrapy crawl myspider --set FEED_URI=items.csv --set FEED_FORMAT=csv

To dump into a XML file::

    scrapy crawl myspider --set FEED_URI=items.xml --set FEED_FORMAT=xml

For more information see :ref:`topics-feed-exports`
