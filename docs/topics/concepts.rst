.. _concepts:

========================
Scrapy's building blocks
========================

Scrapy splits the work of crawling and scraping across a handful of pieces,
each responsible for one part of the problem. Placing a given piece of custom
logic where it belongs keeps that logic reusable across spiders and the
project easy to follow — this separation is what lets Scrapy scale from a
single spider to large, maintainable projects, rather than one script per
site.

This page is a quick map of those pieces, what problem each one solves, and
when to reach for it.

Spiders
=======

A :ref:`spider <topics-spiders>` defines which requests to send and how to
parse their responses. It is where a scraping project usually starts: one
spider per site (or group of similar sites), yielding :ref:`items <topics-items>`
and further requests as it parses each response.

Items
=====

An :ref:`item <topics-items>` is the data you extract, as a plain key-value
object. Spiders yield them, and everything downstream (item pipelines, feed
exports) works with them regardless of which item type a project uses.

Settings
========

:ref:`Settings <topics-settings>` configure everything else on this page:
which middlewares and extensions are enabled and in what order, how item
pipelines behave, feed export destinations, and Scrapy's own defaults.
Settings are usually project-wide, but a spider can override them for itself
alone through :attr:`~scrapy.Spider.custom_settings`, which is often the
simplest way to turn something project-wide, such as a downloader middleware,
into behavior that only applies to the spiders that need it.

Downloader middleware
=====================

A :ref:`downloader middleware <topics-downloader-middleware>` sees every
request Scrapy sends and every response it receives, regardless of which
spider is running — though a spider can narrow that to itself alone through
:attr:`~scrapy.Spider.custom_settings`. Reach for one when the logic is about
the HTTP layer itself, such as adding proxies or authentication headers,
retrying or redirecting based on the response, or short-circuiting a request
without hitting the network.

Spider middleware
=================

A :ref:`spider middleware <topics-spider-middleware>` sits between the engine
and a spider's callbacks, processing the responses going in and the items and
requests coming out. Reach for one to post-process what a spider produces
(filtering items, adding requests, handling exceptions) without changing the
spider's own parsing code, especially when the same post-processing should
apply across several spiders.

Item pipelines
==============

An :ref:`item pipeline <topics-item-pipeline>` processes items after a spider
yields them: cleaning up fields, validating data, dropping duplicates, or
storing items in a database. This is the usual place for anything that acts on
a *scraped item* rather than on a request or response.

Feed exports
============

:ref:`Feed exports <topics-feed-exports>` write scraped items straight to a
file or storage (JSON, CSV, XML, and more) without any custom code. Reach for
them before writing an item pipeline if all you need is to dump the scraped
items somewhere.

Extensions
==========

An :ref:`extension <topics-extensions>` is the wildcard: use it for
functionality that does not fit any of the roles above, such as collecting
stats, enforcing a memory limit, or logging crawl progress. Extensions
typically hook into :ref:`signals <topics-signals>` rather than into the
request/response/item flow.

Signals
=======

:ref:`Signals <topics-signals>` notify your code when something happens during
a crawl, such as a spider opening or closing, or a response being downloaded.
Extensions are the usual place to connect to them, but any component can.

Other components
================

The pieces above are what most projects touch directly. Scrapy has more of
them under the hood, such as download handlers, the scheduler, and feed
storages, that most projects never need to customize; see
:ref:`topics-components` for the full list.
