.. _topics-index:

==============================
Scrapy |version| documentation
==============================

Scrapy is a fast high-level `web crawling`_ and `web scraping`_ framework, used
to crawl websites and extract structured data from their pages. It can be used
for a wide range of purposes, from data mining to monitoring and automated
testing.

.. _web crawling: https://en.wikipedia.org/wiki/Web_crawler
.. _web scraping: https://en.wikipedia.org/wiki/Web_scraping

Getting help
============

Having trouble? We'd like to help!

* Try the :doc:`FAQ <faq>` -- it's got answers to some common questions.
* Looking for specific information? Try the :ref:`genindex` or :ref:`modindex`.
* Ask or search questions in `StackOverflow using the scrapy tag`_.
* Ask or search questions in the `Scrapy subreddit`_.
* Search for questions on the archives of the `scrapy-users mailing list`_.
* Ask a question in the `#scrapy IRC channel`_,
* Report bugs with Scrapy in our `issue tracker`_.

.. _scrapy-users mailing list: https://groups.google.com/forum/#!forum/scrapy-users
.. _Scrapy subreddit: https://www.reddit.com/r/scrapy/
.. _StackOverflow using the scrapy tag: https://stackoverflow.com/tags/scrapy
.. _#scrapy IRC channel: irc://irc.freenode.net/scrapy
.. _issue tracker: https://github.com/scrapy/scrapy/issues


First steps
===========

.. toctree::
   :caption: First steps
   :hidden:

   intro/overview
   intro/install
   intro/tutorial
   intro/examples

:doc:`intro/overview`
    Understand what Scrapy is and how it can help you.

:doc:`intro/install`
    Get Scrapy installed on your computer.

:doc:`intro/tutorial`
    Write your first Scrapy project.

:doc:`intro/examples`
    Learn more by playing with a pre-made Scrapy project.

.. _section-basics:

Basic concepts
==============

.. toctree::
   :caption: Basic concepts
   :hidden:

   topics/commands
   topics/spiders
   topics/selectors
   topics/items
   topics/loaders
   topics/shell
   topics/item-pipeline
   topics/feed-exports
   topics/request-response
   topics/link-extractors
   topics/settings
   topics/exceptions


:doc:`topics/commands`
    Learn about the command-line tool used to manage your Scrapy project.

:doc:`topics/spiders`
    Write the rules to crawl your websites.

:doc:`topics/selectors`
    Extract the data from web pages using XPath.

:doc:`topics/shell`
    Test your extraction code in an interactive environment.

:doc:`topics/items`
    Define the data you want to scrape.

:doc:`topics/loaders`
    Populate your items with the extracted data.

:doc:`topics/item-pipeline`
    Post-process and store your scraped data.

:doc:`topics/feed-exports`
    Output your scraped data using different formats and storages.

:doc:`topics/request-response`
    Understand the classes used to represent HTTP requests and responses.

:doc:`topics/link-extractors`
    Convenient classes to extract links to follow from pages.

:doc:`topics/settings`
    Learn how to configure Scrapy and see all :ref:`available settings <topics-settings-ref>`.

:doc:`topics/exceptions`
    See all available exceptions and their meaning.


Built-in services
=================

.. toctree::
   :caption: Built-in services
   :hidden:

   topics/logging
   topics/stats
   topics/email
   topics/telnetconsole
   topics/webservice

:doc:`topics/logging`
    Learn how to use Python's builtin logging on Scrapy.

:doc:`topics/stats`
    Collect statistics about your scraping crawler.

:doc:`topics/email`
    Send email notifications when certain events occur.

:doc:`topics/telnetconsole`
    Inspect a running crawler using a built-in Python console.

:doc:`topics/webservice`
    Monitor and control a crawler using a web service.


Solving specific problems
=========================

.. toctree::
   :caption: Solving specific problems
   :hidden:

   faq
   topics/debug
   topics/contracts
   topics/practices
   topics/broad-crawls
   topics/developer-tools
   topics/dynamic-content
   topics/leaks
   topics/media-pipeline
   topics/deploy
   topics/autothrottle
   topics/benchmarking
   topics/jobs
   topics/coroutines
   topics/asyncio

:doc:`faq`
    Get answers to most frequently asked questions.

:doc:`topics/debug`
    Learn how to debug common problems of your Scrapy spider.

:doc:`topics/contracts`
    Learn how to use contracts for testing your spiders.

:doc:`topics/practices`
    Get familiar with some Scrapy common practices.

:doc:`topics/broad-crawls`
    Tune Scrapy for crawling a lot domains in parallel.

:doc:`topics/developer-tools`
    Learn how to scrape with your browser's developer tools.

:doc:`topics/dynamic-content`
    Read webpage data that is loaded dynamically.

:doc:`topics/leaks`
    Learn how to find and get rid of memory leaks in your crawler.

:doc:`topics/media-pipeline`
    Download files and/or images associated with your scraped items.

:doc:`topics/deploy`
    Deploying your Scrapy spiders and run them in a remote server.

:doc:`topics/autothrottle`
    Adjust crawl rate dynamically based on load.

:doc:`topics/benchmarking`
    Check how Scrapy performs on your hardware.

:doc:`topics/jobs`
    Learn how to pause and resume crawls for large spiders.

:doc:`topics/coroutines`
    Use the :ref:`coroutine syntax <async>`.

:doc:`topics/asyncio`
    Use :mod:`asyncio` and :mod:`asyncio`-powered libraries.

.. _extending-scrapy:

Extending Scrapy
================

.. toctree::
   :caption: Extending Scrapy
   :hidden:

   topics/architecture
   topics/downloader-middleware
   topics/spider-middleware
   topics/extensions
   topics/api
   topics/signals
   topics/exporters


:doc:`topics/architecture`
    Understand the Scrapy architecture.

:doc:`topics/downloader-middleware`
    Customize how pages get requested and downloaded.

:doc:`topics/spider-middleware`
    Customize the input and output of your spiders.

:doc:`topics/extensions`
    Extend Scrapy with your custom functionality

:doc:`topics/api`
    Use it on extensions and middlewares to extend Scrapy functionality

:doc:`topics/signals`
    See all available signals and how to work with them.

:doc:`topics/exporters`
    Quickly export your scraped items to a file (XML, CSV, etc).


All the rest
============

.. toctree::
   :caption: All the rest
   :hidden:

   news
   contributing
   versioning

:doc:`news`
    See what has changed in recent Scrapy versions.

:doc:`contributing`
    Learn how to contribute to the Scrapy project.

:doc:`versioning`
    Understand Scrapy versioning and API stability.
