.. _topics-scheduler:

=========
Scheduler
=========

.. module:: scrapy.core.scheduler

The scheduler component receives requests from the :ref:`engine <component-engine>`
and stores them into persistent and/or non-persistent data structures.
It also gets those requests and feeds them back to the engine when it
asks for a next request to be downloaded.


Overriding the default scheduler
================================

You can use your own custom scheduler class by supplying its full
Python path in the :setting:`SCHEDULER` setting.


Minimal scheduler interface
===========================

.. autoclass:: BaseScheduler

   .. automethod:: from_crawler

   .. automethod:: open

   .. automethod:: close

   .. automethod:: has_pending_requests

   .. automethod:: enqueue_request

   .. automethod:: next_request


Default Scrapy scheduler
========================

.. autoclass:: Scheduler

   .. automethod:: from_crawler

   .. automethod:: open

   .. automethod:: close

   .. automethod:: has_pending_requests

   .. automethod:: enqueue_request

   .. automethod:: next_request

   .. automethod:: __len__
