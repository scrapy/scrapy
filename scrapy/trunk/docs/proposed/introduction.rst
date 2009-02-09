============
Introduction
============

.. architecture:

Overview
========

.. image:: _images/scrapy_architecture.png
   :width: 700
   :height: 468
   :alt: Scrapy architecture

Requests and Responses
----------------------

Scrapy uses *Requests* and *Responses* for crawling web sites. 

Generally, *Requests* are generated in the Spiders and pass across the system
until they reach the *Downloader*, which executes the *Request* and returns a
*Response* which goes back to the Spider that generated the *Request*.

Spiders
-------

Spiders are user written classes to scrape information from a domain (or group
of domains).

They define an initial set of URLs (or Requests) to download, how to crawl the
domain and how to scrape *Items* from their pages.

Items
-----

Items are the placeholder to use for the scraped data. They are represented by a
simple Python class.

After an Item has been scraped by a Spider, it is sent to the Item Pipeline for further proccesing.

Item Pipeline
-------------

The Item Pipeline is a list of user written Python classes that implement a
specific method, which is called sequentially for every element of the Pipeline.

Each element receives the Scraped Item, do an action upon it (like validating,
checking for duplicates, store the item), and then decide if the Item continues
trough the Pipeline or the item is dropped.
