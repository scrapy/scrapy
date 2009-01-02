.. _overview:

Overview
========

Scrapy is a framework designed for retrieving information from websites.
The basic idea of scrapy is to be a robot that goes through websites, crawling pages, and extracting information from them.

The framework is formed by components that take care of different activities.
These components are basically:

* :ref:`spiders`
* :ref:`selectors`
* Items
* Adaptors


Features
--------

Scrapy includes many interesting features that make the scraping process much more easier and faster. These include:

* Asynchronous crawling/parsing on top of the Twisted framework.
* Easily configurable crawling through sets of rules.
* Ability for parsing HTML, XML, and CSV files.
* Media pipeline useful for scraping items with images or any other media files.
* *Very* extensible thanks to pipelines, middlewares, downloader-middlewares, and extensions.
* Automatic handling of compression, cache, cookies, authentication and more through already-included middlewares.
* Interactive scraping shell console, very useful for developing.

