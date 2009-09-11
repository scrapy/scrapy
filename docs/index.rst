.. _topics-index:

====================
Scrapy documentation
====================

This documentation contains everything you need to know about Scrapy.

Getting help
============

Having trouble? We'd like to help!

* Try the :doc:`FAQ <faq>` -- it's got answers to some common questions.
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

:doc:`intro/overview`
    Understand what Scrapy is and how it can help you.

:doc:`intro/install`
    Get Scrapy installed on your computer.

:doc:`intro/tutorial`
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

:doc:`topics/items`
    Define the data you want to scrape.

:doc:`topics/spiders`
    Write the rules to crawl your websites.

:doc:`topics/selectors`
    Extract the data from web pages.

:doc:`topics/shell`
    Test your extraction code in an interactive environment.

:doc:`topics/loaders`
    Populate your items with the extracted data.

:doc:`topics/item-pipeline`
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

:doc:`topics/logging`
    Understand the simple logging facility provided by Scrapy.
   
:doc:`topics/stats`
    Collect statistics about your scraping crawler.

:doc:`topics/email`
    Send email notifications when certain events occur.

:doc:`topics/telnetconsole`
    Inspect a running crawler using a built-in Python console.

:doc:`topics/webconsole`
    Monitor and control a crawler using a web interface.


Solving specific problems
=========================

.. toctree::
   :hidden:

   faq
   topics/firefox
   topics/firebug
   topics/leaks

:doc:`faq`
    Get answers to most frequently asked questions.

:doc:`topics/firefox`
    Learn how to scrape with Firefox and some useful add-ons.

:doc:`topics/firebug`
    Learn how to scrape efficiently using Firebug.

:doc:`topics/leaks`
    Learn how to find and get rid of memory leaks in your crawler.


Extending Scrapy
================

.. toctree::
   :hidden:

   topics/architecture
   topics/downloader-middleware
   topics/spider-middleware
   topics/extensions

:doc:`topics/architecture`
    Understand the Scrapy architecture.

:doc:`topics/downloader-middleware`
    Customize how pages get requested and downloaded.

:doc:`topics/spider-middleware`
    Customize the input and output of your spiders.

:doc:`experimental/scheduler-middleware`
    Customize how pages are scheduled (warning: experimental doc).

:doc:`topics/extensions`
    Add any custom functionality using :doc:`signals <topics/signals>` and the
    Scrapy API


Reference
=========

.. toctree::
   :hidden:

   topics/scrapy-ctl
   topics/request-response
   topics/settings
   topics/signals
   topics/exceptions
   topics/exporters

:doc:`topics/scrapy-ctl`
    Understand the command used to control your Scrapy project.

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

   api-stability
   experimental/index

:doc:`api-stability`
    Understand Scrapy versioning and API stability.

:doc:`experimental/index`
    Learn about bleeding-edge features.
