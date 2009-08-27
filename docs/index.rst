.. _topics-index:

====================
Scrapy documentation
====================

This documentation contains everything you need to know about Scrapy.

Getting help
============

Having trouble? We'd like to help!

* Try the :ref:`FAQ <faq>` -- it's got answers to some common questions.
* Looking for specific information? Try the :ref:`genindex` or :ref:`modindex`.
* Search for information in the `archives of the scrapy-users mailing list`_, or
  `post a question`_.
* Ask a question in the `#scrapy IRC channel`_.
* Report bugs with Scrapy in our `ticket tracker`_.

.. _archives of the scrapy-users mailing list: http://groups.google.com/group/scrapy-users/
.. _post a question: http://groups.google.com/group/scrapy-users/
.. _#scrapy IRC channel: irc://irc.freenode.net/scrapy
.. _ticket tracker: http://dev.scrapy.org/


First steps
===========

.. toctree::
   :hidden:

   intro/overview
   intro/install
   intro/tutorial

:ref:`intro-overview`
    Understand what Scrapy is and how it can help you.

:ref:`intro-install`
    Get Scrapy installed on your computer.

:ref:`intro-tutorial`
    Write your first Scrapy project.


Scraping basics
===============

.. toctree::
   :hidden:

   topics/items
   topics/spiders
   topics/link-extractors
   topics/selectors
   topics/loaders
   topics/shell
   topics/item-pipeline

:ref:`topics-items`
    Define the data you want to scrape.

:ref:`topics-spiders`
    Write the rules to crawl your websites.

:ref:`topics-selectors`
    Extract the data from web pages.

:ref:`topics-shell`
    Test your extraction code in an interactive environment.

:ref:`topics-loaders`
    Populate your items with the extracted data.

:ref:`topics-item-pipeline`
    Post-process and store your scraped data.


Built-in services
=================

.. toctree::
   :hidden:

   topics/logging
   topics/stats
   topics/email
   topics/telnetconsole
   topics/webconsole

:ref:`topics-logging`
    Understand the simple logging facility provided by Scrapy.
   
:ref:`topics-stats`
    Collect statistics about your scraping crawler.

:ref:`topics-email`
    Send email notifications when certain events occur.

:ref:`topics-telnetconsole`
    Inspect a running crawler using a built-in Python console.

:ref:`topics-webconsole`
    Monitor and control a crawler using a web interface.


Solving specific problems
=========================

.. toctree::
   :hidden:

   faq
   topics/firefox
   topics/firebug
   topics/leaks

:ref:`faq`
    Get answers to most frequently asked questions.

:ref:`topics-firefox`
    Learn how to scrape with Firefox and some useful add-ons.

:ref:`topics-firebug`
    Learn how to scrape efficiently using Firebug.

:ref:`topics-leaks`
    Learn how to find and get rid of memory leaks in your crawler.


Extending Scrapy
================

.. toctree::
   :hidden:

   topics/architecture
   topics/downloader-middleware
   topics/spider-middleware
   topics/scheduler-middleware
   topics/extensions

:ref:`topics-architecture`
    Understand the Scrapy architecture.

:ref:`topics-downloader-middleware`
    Customize how pages get requested and downloaded.

:ref:`topics-spider-middleware`
    Customize the input and output of your spiders.

:ref:`topics-scheduler-middleware`
    Customize how pages are scheduled.

:ref:`topics-extensions`
    Add any custom functionality using :ref:`signals <topics-signals>` and the
    Scrapy API


Reference
=========

.. toctree::
   :hidden:

   topics/request-response
   topics/settings
   topics/signals
   topics/exceptions

:ref:`topics-request-response`
    Understand the classes used to represent HTTP requests and responses.

:ref:`topics-settings`
    Learn how to configure Scrapy and see all :ref:`available settings <topics-settings-ref>`.

:ref:`topics-signals`
    See all available signals and how to work with them.

:ref:`topics-exceptions`
    See all available exceptions and their meaning.


All the rest
============

.. toctree::
   :hidden:

   api-stability
   experimental/index

:ref:`api-stability`
    Understand Scrapy versioning and API stability.

:ref:`experimental`
    Learn about bleeding-edge features.
