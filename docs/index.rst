.. _topics-index:

==============================
Scrapy |version| documentation
==============================

This documentation contains everything you need to know about Scrapy.

Getting help
============

Having trouble? We'd like to help!

* Try the :doc:`FAQ <faq>` -- it's got answers to some common questions.
* Looking for specific information? Try the :ref:`genindex` or :ref:`modindex`.
* Search for information in the `archives of the scrapy-users mailing list`_, or
  `post a question`_.
* Ask a question in the `#scrapy IRC channel`_.
* Report bugs with Scrapy in our `issue tracker`_.

.. _archives of the scrapy-users mailing list: http://groups.google.com/group/scrapy-users/
.. _post a question: http://groups.google.com/group/scrapy-users/
.. _#scrapy IRC channel: irc://irc.freenode.net/scrapy
.. _issue tracker: https://github.com/scrapy/scrapy/issues


First steps
===========

.. toctree::
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
   :hidden:

   topics/commands
   topics/items
   topics/spiders
   topics/selectors
   topics/loaders
   topics/shell
   topics/item-pipeline
   topics/feed-exports
   topics/link-extractors

:doc:`topics/commands`
    Learn about the command-line tool used to manage your Scrapy project.

:doc:`topics/items`
    Define the data you want to scrape.

:doc:`topics/spiders`
    Write the rules to crawl your websites.

:doc:`topics/selectors`
    Extract the data from web pages using XPath.

:doc:`topics/shell`
    Test your extraction code in an interactive environment.

:doc:`topics/loaders`
    Populate your items with the extracted data.

:doc:`topics/item-pipeline`
    Post-process and store your scraped data.

:doc:`topics/feed-exports`
    Output your scraped data using different formats and storages.

:doc:`topics/link-extractors`
    Convenient classes to extract links to follow from pages.

Built-in services
=================

.. toctree::
   :hidden:

   topics/logging
   topics/stats
   topics/email
   topics/telnetconsole
   topics/webservice

:doc:`topics/logging`
    Understand the simple logging facility provided by Scrapy.
   
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
   :hidden:

   faq
   topics/debug
   topics/contracts
   topics/practices
   topics/broad-crawls
   topics/firefox
   topics/firebug
   topics/leaks
   topics/images
   topics/ubuntu
   topics/scrapyd
   topics/autothrottle
   topics/benchmarking
   topics/jobs
   topics/djangoitem

:doc:`faq`
    Get answers to most frequently asked questions.

:doc:`topics/debug`
    Learn how to debug common problems of your scrapy spider.

:doc:`topics/contracts`
    Learn how to use contracts for testing your spiders.

:doc:`topics/practices`
    Get familiar with some Scrapy common practices.

:doc:`topics/broad-crawls`
    Tune Scrapy for crawling a lot domains in parallel.

:doc:`topics/firefox`
    Learn how to scrape with Firefox and some useful add-ons.

:doc:`topics/firebug`
    Learn how to scrape efficiently using Firebug.

:doc:`topics/leaks`
    Learn how to find and get rid of memory leaks in your crawler.

:doc:`topics/images`
    Download static images associated with your scraped items.

:doc:`topics/ubuntu`
    Install latest Scrapy packages easily on Ubuntu

:doc:`topics/scrapyd`
    Deploying your Scrapy project in production.

:doc:`topics/autothrottle`
    Adjust crawl rate dynamically based on load.

:doc:`topics/benchmarking`
    Check how Scrapy performs on your hardware.

:doc:`topics/jobs`
    Learn how to pause and resume crawls for large spiders.

:doc:`topics/djangoitem`
    Write scraped items using Django models.

.. _extending-scrapy:

Extending Scrapy
================

.. toctree::
   :hidden:

   topics/architecture
   topics/downloader-middleware
   topics/spider-middleware
   topics/extensions
   topics/api

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

Reference
=========

.. toctree::
   :hidden:

   topics/request-response
   topics/settings
   topics/signals
   topics/exceptions
   topics/exporters

:doc:`topics/commands`
    Learn about the command-line tool and see all :ref:`available commands <topics-commands-ref>`.

:doc:`topics/request-response`
    Understand the classes used to represent HTTP requests and responses.

:doc:`topics/settings`
    Learn how to configure Scrapy and see all :ref:`available settings <topics-settings-ref>`.

:doc:`topics/signals`
    See all available signals and how to work with them.

:doc:`topics/exceptions`
    See all available exceptions and their meaning.

:doc:`topics/exporters`
    Quickly export your scraped items to a file (XML, CSV, etc).


All the rest
============

.. toctree::
   :hidden:

   news
   contributing
   versioning
   experimental/index

:doc:`news`
    See what has changed in recent Scrapy versions.

:doc:`contributing`
    Learn how to contribute to the Scrapy project.

:doc:`versioning`
    Understand Scrapy versioning and API stability.

:doc:`experimental/index`
    Learn about bleeding-edge features.
